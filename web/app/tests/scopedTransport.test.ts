import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { scopedTransport, type AccountScope, type AccountSession } from '../src/shared/account-client';
import { SESSION_EXPIRED_EVENT, type SessionExpiredDetail } from '../src/shared/sessionEvents';

const session: AccountSession = {
  user: {
    id: 'u1', username: 'test01', display_name: 'test01', role: 'user',
    status: 'active', must_change_password: false,
  },
  csrf_token: 'csrf-token',
  scopes: [],
  invitations: [],
};

const scope: AccountScope = {
  id: 's1', kind: 'personal', name: '个人', role: 'owner', can_edit: true, can_execute: true,
};

function jsonResponse(status: number, body: unknown = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

let originalFetch: typeof fetch;

beforeEach(() => {
  originalFetch = window.fetch;
  window.location.hash = '';
});

afterEach(() => {
  window.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe('scopedTransport 的 401 行为（痛点⑤）', () => {
  it('401 时派发 session-expired 事件、携带会话与 scope，且不跳转页面', async () => {
    window.fetch = vi.fn().mockResolvedValue(jsonResponse(401, { error: { code: 'unauthorized' } }));
    const details: SessionExpiredDetail[] = [];
    const listener = (event: Event) => {
      details.push((event as CustomEvent<SessionExpiredDetail>).detail);
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, listener);
    try {
      const transport = scopedTransport(session, scope);
      const response = await transport('/api/v1/projects', {});
      expect(response.status).toBe(401);
      expect(details).toEqual([{ session, scope }]);
      // 关键断言：不再 location.replace 到 /account/，地址保持原样。
      expect(window.location.pathname).toBe('/');
      expect(window.location.href).not.toContain('/account');
    } finally {
      window.removeEventListener(SESSION_EXPIRED_EVENT, listener);
    }
  });

  it('成功响应照常透传且不发事件', async () => {
    window.fetch = vi.fn().mockResolvedValue(jsonResponse(200, { projects: [] }));
    const dispatch = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, dispatch);
    try {
      const transport = scopedTransport(session, scope);
      const response = await transport('/api/v1/projects', {});
      expect(response.status).toBe(200);
      expect(dispatch).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener(SESSION_EXPIRED_EVENT, dispatch);
    }
  });

  it('非 401 错误（403/500）不触发过期事件', async () => {
    for (const status of [403, 500]) {
      window.fetch = vi.fn().mockResolvedValue(jsonResponse(status, { error: { code: 'x' } }));
      const dispatch = vi.fn();
      window.addEventListener(SESSION_EXPIRED_EVENT, dispatch);
      try {
        const transport = scopedTransport(session, scope);
        expect((await transport('/api/v1/projects', {})).status).toBe(status);
        expect(dispatch).not.toHaveBeenCalled();
      } finally {
        window.removeEventListener(SESSION_EXPIRED_EVENT, dispatch);
      }
    }
  });

  it('请求带上 CSRF 头并落入 scope 作用域路径', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
    window.fetch = fetchMock as unknown as typeof fetch;
    const transport = scopedTransport(session, scope);
    await transport('/api/v1/projects', {});
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/v1/scopes/s1/projects');
    expect(new Headers(init.headers).get('X-CSRF-Token')).toBe('csrf-token');
  });
});
