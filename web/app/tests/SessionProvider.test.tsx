import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, beforeEach, vi } from 'vitest';
import {
  reduceSession, SESSION_EXPIRED_EVENT, SessionProvider, useSession,
  type SessionApi, type SessionEvent, type SessionState,
} from '../src/shell/SessionProvider';
import {
  AccountApiError, type AccountScope, type AccountSession,
} from '../src/shared/account-client';
import { createDraftRecovery } from '../src/data/draftRecovery';

function memoryStorage(): Storage {
  const map = new Map<string, string>();
  return {
    get length() { return map.size; },
    clear: () => { map.clear(); },
    getItem: (key: string) => map.get(key) ?? null,
    key: (index: number) => [...map.keys()][index] ?? null,
    removeItem: (key: string) => { map.delete(key); },
    setItem: (key: string, value: string) => { map.set(key, value); },
  };
}

function scopeFixture(id: string): AccountScope {
  return { id, kind: 'personal', name: '个人工作区', role: 'owner', can_edit: true, can_execute: true };
}

function sessionFixture(userId = 'u1', username = 'test01'): AccountSession {
  return {
    user: {
      id: userId, username, display_name: username, role: 'user',
      status: 'active', must_change_password: false,
    },
    csrf_token: 'csrf-token',
    scopes: [scopeFixture(`scope-${userId}`)],
    invitations: [],
  };
}

interface FakeApiHandlers {
  probe?: () => Promise<AccountSession>;
  login?: (username: string, password: string) => Promise<AccountSession>;
}

function fakeSessionApi(handlers: FakeApiHandlers = {}) {
  const calls = { probe: 0, login: [] as Array<{ username: string; password: string }>, logout: 0 };
  const api: SessionApi = {
    probe: () => {
      calls.probe += 1;
      return handlers.probe ? handlers.probe() : Promise.resolve(sessionFixture());
    },
    login: (username, password) => {
      calls.login.push({ username, password });
      return handlers.login
        ? handlers.login(username, password)
        : Promise.resolve(sessionFixture(username === 'other' ? 'u2' : 'u1', username));
    },
    logout: () => {
      calls.logout += 1;
      return Promise.resolve();
    },
  };
  return { api, calls };
}

interface SetupOptions {
  handlers?: FakeApiHandlers;
}

function setup({ handlers = {} }: SetupOptions = {}) {
  const storage = memoryStorage();
  const drafts = createDraftRecovery({ storage });
  const { api, calls } = fakeSessionApi(handlers);
  const wrapper = ({ children }: { children?: ReactNode }) => (
    <SessionProvider api={api} drafts={drafts}>{children}</SessionProvider>
  );
  const view = renderHook(() => useSession(), { wrapper });
  return { ...view, api, calls, drafts, storage };
}

function fireSessionExpired(detail: Record<string, unknown> = {}): void {
  window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT, { detail }));
}

it('真实登录响应不含 scopes 时仍可登录并恢复过期会话', async () => {
  const session = sessionFixture();
  let signedIn = false;
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    if (input === '/api/v1/accounts/login') {
      signedIn = true;
      return Response.json({ user: session.user, csrf_token: session.csrf_token });
    }
    if (input === '/api/v1/accounts/me') {
      return signedIn
        ? Response.json(session)
        : Response.json({ error: { code: 'unauthorized' } }, { status: 401 });
    }
    throw new Error(`Unexpected request: ${String(input)}`);
  });
  const drafts = createDraftRecovery({ storage: memoryStorage() });
  const wrapper = ({ children }: { children?: ReactNode }) => (
    <SessionProvider drafts={drafts}>{children}</SessionProvider>
  );
  const view = renderHook(() => useSession(), { wrapper });
  try {
    await waitFor(() => expect(view.result.current.state.kind).toBe('guest'));
    await act(async () => { await view.result.current.login('test01', 'password'); });
    expect(view.result.current.state).toEqual({
      kind: 'authenticated', session, scope: session.scopes[0],
    });
    act(() => fireSessionExpired());
    expect(view.result.current.state.kind).toBe('expired');
    await act(async () => { await view.result.current.recoverSession('password'); });
    expect(view.result.current.state).toEqual({
      kind: 'authenticated', session, scope: session.scopes[0],
    });
  } finally {
    view.unmount();
    fetchMock.mockRestore();
  }
});

beforeEach(() => {
  localStorage.clear();
  window.history.pushState({}, '', '/');
});

describe('SessionProvider ?next= 回跳（痛点④⑥）', () => {
  it('访客打开深链后登录成功，回到原目标', async () => {
    window.location.hash = '#/projects/p1?scope=s1&view=easy';
    const view = setup({ handlers: { probe: () => Promise.reject(new AccountApiError('unauthorized', '请登录', 401)) } });
    await waitFor(() => expect(view.result.current.state.kind).toBe('guest'));
    expect(window.location.hash).toBe('#/projects/p1?scope=s1&view=easy');
    await act(async () => { await view.result.current.login('test01', 'password'); });
    expect(view.result.current.state.kind).toBe('authenticated');
    expect(window.location.hash).toBe('#/projects/p1?scope=s1&view=easy');
    expect(localStorage.getItem('easydesign-next-url')).toBeNull();
    view.unmount();
  });

  it('?next= 参数比当前 hash 优先', async () => {
    window.history.pushState({}, '', '/app?next=%23%2Faccount');
    const view = setup({ handlers: { probe: () => Promise.reject(new AccountApiError('unauthorized', '请登录', 401)) } });
    await waitFor(() => expect(view.result.current.state.kind).toBe('guest'));
    await act(async () => { await view.result.current.login('test01', 'password'); });
    expect(view.result.current.state.kind).toBe('authenticated');
    expect(window.location.hash).toBe('#/account');
    view.unmount();
  });

  it('根路由不算意图：无 next 时登录不改变路由', async () => {
    const view = setup({ handlers: { probe: () => Promise.reject(new AccountApiError('unauthorized', '请登录', 401)) } });
    await waitFor(() => expect(view.result.current.state.kind).toBe('guest'));
    await act(async () => { await view.result.current.login('test01', 'password'); });
    expect(view.result.current.state.kind).toBe('authenticated');
    expect(window.location.hash).toBe('');
    view.unmount();
  });

  it('已登录的探测会丢弃陈旧的 next 意图', async () => {
    localStorage.setItem('easydesign-next-url', '#/projects/stale');
    const view = setup();
    await waitFor(() => expect(view.result.current.state.kind).toBe('authenticated'));
    expect(localStorage.getItem('easydesign-next-url')).toBeNull();
    view.unmount();
  });

  it('访客意图与账号无关：任何登录成功都带回目标且只消费一次', async () => {
    localStorage.setItem('easydesign-next-url', '#/projects/other');
    const view = setup({
      handlers: {
        probe: () => Promise.reject(new AccountApiError('unauthorized', '请登录', 401)),
        login: () => Promise.resolve(sessionFixture('u2', 'other')),
      },
    });
    await waitFor(() => expect(view.result.current.state.kind).toBe('guest'));
    await act(async () => { await view.result.current.login('other', 'password'); });
    expect(view.result.current.state.kind).toBe('authenticated');
    // 深链属于这个浏览器标签页的访客意图，与登录了哪个账号无关（痛点⑥）。
    expect(window.location.hash).toBe('#/projects/other');
    expect(localStorage.getItem('easydesign-next-url')).toBeNull();
    view.unmount();
  });
});

describe('reduceSession 纯转移规则（非法转移一律保持原状态）', () => {
  const authenticated: SessionState = { kind: 'authenticated', session: sessionFixture(), scope: scopeFixture('s') };

  it('任意状态 probe-start 都进入 checking', () => {
    for (const state of [
      { kind: 'guest' } as SessionState,
      authenticated,
      { kind: 'expired', previousSession: sessionFixture(), recoverableData: {} } as SessionState,
    ]) {
      expect(reduceSession(state, { type: 'probe-start' })).toEqual({ kind: 'checking' });
    }
  });

  it('probe 结果只在 checking/network-error 状态生效', () => {
    expect(reduceSession({ kind: 'guest' }, { type: 'probe-authenticated', session: sessionFixture(), scope: scopeFixture('s') }))
      .toEqual({ kind: 'guest' });
    expect(reduceSession(authenticated, { type: 'probe-guest' })).toEqual(authenticated);
  });

  it('session-expired 只从 authenticated 进入 expired', () => {
    expect(reduceSession({ kind: 'guest' }, { type: 'session-expired', recoverableData: {} }))
      .toEqual({ kind: 'guest' });
    const expired = reduceSession(authenticated, { type: 'session-expired', recoverableData: { k: 1 } });
    expect(expired).toEqual({
      kind: 'expired',
      previousSession: (authenticated as { session: AccountSession }).session,
      recoverableData: { k: 1 },
    });
  });

  it('switch-account/recovery-dismissed 的合法来源', () => {
    const expired: SessionState = { kind: 'expired', previousSession: sessionFixture(), recoverableData: {} };
    expect(reduceSession(expired, { type: 'switch-account' })).toEqual({ kind: 'guest' });
    expect(reduceSession({ kind: 'guest' }, { type: 'switch-account' })).toEqual({ kind: 'guest' });
    expect(reduceSession(expired, { type: 'recovery-dismissed' })).toEqual({ kind: 'guest' });
    expect(
      reduceSession({ kind: 'network-error', retry: () => undefined }, { type: 'recovery-dismissed' }),
    ).toEqual({ kind: 'guest' });
  });

  it('signed-out 只从 authenticated/expired 进入 guest', () => {
    expect(reduceSession(authenticated, { type: 'signed-out' })).toEqual({ kind: 'guest' });
    expect(
      reduceSession({ kind: 'expired', previousSession: sessionFixture(), recoverableData: {} }, { type: 'signed-out' }),
    ).toEqual({ kind: 'guest' });
    expect(reduceSession({ kind: 'guest' }, { type: 'signed-out' })).toEqual({ kind: 'guest' });
  });

  it('login-authenticated 不覆盖已是 authenticated 的状态', () => {
    const event: SessionEvent = { type: 'login-authenticated', session: sessionFixture('u9'), scope: scopeFixture('s9') };
    expect(reduceSession(authenticated, event)).toBe(authenticated);
  });
});

describe('SessionProvider 探测与登录', () => {
  it('初始为 checking；探测 401 后进入 guest', async () => {
    let rejectProbe: ((error: unknown) => void) | undefined;
    const view = setup({ handlers: { probe: () => new Promise<AccountSession>((_resolve, reject) => { rejectProbe = reject; }) } });
    expect(view.result.current.state.kind).toBe('checking');
    await act(async () => { rejectProbe?.(new AccountApiError('unauthorized', '请登录', 401)); });
    await waitFor(() => expect(view.result.current.state.kind).toBe('guest'));
    view.unmount();
  });

  it('探测成功进入 authenticated，scope 取第一个已知工作区', async () => {
    const view = setup();
    await waitFor(() => expect(view.result.current.state.kind).toBe('authenticated'));
    if (view.result.current.state.kind !== 'authenticated') throw new Error('unreachable');
    expect(view.result.current.state.session.user.id).toBe('u1');
    expect(view.result.current.state.scope.id).toBe('scope-u1');
    expect(view.drafts.identity).toBe('u1');
    view.unmount();
  });

  it('网络异常进入 network-error，重试成功后进入 authenticated', async () => {
    let fail = true;
    const view = setup({
      handlers: {
        probe: () => (fail
          ? Promise.reject(new AccountApiError('network_error', '网络异常', 0))
          : Promise.resolve(sessionFixture())),
      },
    });
    await waitFor(() => expect(view.result.current.state.kind).toBe('network-error'));
    const networkState = view.result.current.state;
    if (networkState.kind !== 'network-error') throw new Error('unreachable');
    expect(typeof networkState.retry).toBe('function');
    fail = false;
    await act(async () => { networkState.retry(); });
    await waitFor(() => expect(view.result.current.state.kind).toBe('authenticated'));
    expect(view.calls.probe).toBe(2);
    view.unmount();
  });

  it('network-error 放弃后进入 guest', async () => {
    const view = setup({
      handlers: { probe: () => Promise.reject(new AccountApiError('network_error', '网络异常', 0)) },
    });
    await waitFor(() => expect(view.result.current.state.kind).toBe('network-error'));
    act(() => { view.result.current.dismissRecovery(); });
    expect(view.result.current.state.kind).toBe('guest');
    view.unmount();
  });

  it('guest 登录成功进入 authenticated，草稿命名空间切到该账号', async () => {
    const view = setup({ handlers: { probe: () => Promise.reject(new AccountApiError('unauthorized', '请登录', 401)) } });
    await waitFor(() => expect(view.result.current.state.kind).toBe('guest'));
    await act(async () => { await view.result.current.login('test01', 'password'); });
    expect(view.result.current.state.kind).toBe('authenticated');
    expect(view.drafts.identity).toBe('u1');
    expect(view.calls.login).toEqual([{ username: 'test01', password: 'password' }]);
    view.unmount();
  });
});

describe('SessionProvider 过期与恢复（痛点⑤）', () => {
  async function setupAuthenticated() {
    const view = setup();
    await waitFor(() => expect(view.result.current.state.kind).toBe('authenticated'));
    return view;
  }

  it('401 事件只切换到 expired 状态，页面不跳转，并收集本地草稿', async () => {
    const view = await setupAuthenticated();
    view.drafts.saveLocal('draft:project:create', { goal: '正在编辑的目标' });
    window.location.hash = '#/projects/p1?scope=s1&view=easy';
    await act(async () => { fireSessionExpired({ session: sessionFixture() }); });
    const state = view.result.current.state;
    expect(state.kind).toBe('expired');
    if (state.kind !== 'expired') throw new Error('unreachable');
    expect(state.previousSession.user.id).toBe('u1');
    expect(state.recoverableData['draft:project:create']).toEqual({ goal: '正在编辑的目标' });
    // 不跳转：地址与路由保持原样。
    expect(window.location.hash).toBe('#/projects/p1?scope=s1&view=easy');
    expect(window.location.pathname).toBe('/');
    view.unmount();
  });

  it('expired 后用原账号重新登录：恢复 authenticated 并回到原路由', async () => {
    const view = await setupAuthenticated();
    window.location.hash = '#/projects/p1?scope=s1&view=easy';
    await act(async () => { fireSessionExpired({ session: sessionFixture() }); });
    expect(view.result.current.state.kind).toBe('expired');
    await act(async () => { await view.result.current.recoverSession('password'); });
    expect(view.result.current.state.kind).toBe('authenticated');
    expect(window.location.hash).toBe('#/projects/p1?scope=s1&view=easy');
    expect(localStorage.getItem('easydesign-recovery-path')).toBeNull();
    view.unmount();
  });

  it('expired 后密码错误：保持 expired 并把错误抛给调用方', async () => {
    const view = await setupAuthenticated();
    await act(async () => { fireSessionExpired({ session: sessionFixture() }); });
    expect(view.result.current.state.kind).toBe('expired');
    view.api.login = () =>
      Promise.reject(new AccountApiError('invalid_credentials', '用户名或密码错误', 401));
    await expect(view.result.current.recoverSession('wrong')).rejects.toThrow('用户名或密码错误');
    expect(view.result.current.state.kind).toBe('expired');
    view.unmount();
  });

  it('expired 后换账号登录：旧账号草稿被清除、回跳路径作废', async () => {
    const view = await setupAuthenticated();
    view.drafts.saveLocal('draft:project:create', { goal: '用户一的输入' });
    window.location.hash = '#/projects/p1';
    await act(async () => { fireSessionExpired({ session: sessionFixture() }); });
    await act(async () => { await view.result.current.login('other', 'password'); });
    expect(view.result.current.state.kind).toBe('authenticated');
    if (view.result.current.state.kind !== 'authenticated') throw new Error('unreachable');
    expect(view.result.current.state.session.user.id).toBe('u2');
    expect(view.drafts.identity).toBe('u2');
    // 旧命名空间已被物理清除。
    const staleKeys = [...Array(view.storage.length).keys()]
      .map((index) => view.storage.key(index) ?? '')
      .filter((key) => key.includes('easydesign:draft:u1:'));
    expect(staleKeys).toEqual([]);
    // 新账号不承接上一位用户的路由。
    expect(window.location.hash).toBe('#/projects/p1');
    expect(localStorage.getItem('easydesign-recovery-path')).toBeNull();
    view.unmount();
  });

  it('expired 取消恢复后进入 guest，草稿保留但回跳路径作废', async () => {
    const view = await setupAuthenticated();
    view.drafts.saveLocal('draft:project:create', { goal: '输入' });
    window.location.hash = '#/projects/p2';
    await act(async () => { fireSessionExpired({ session: sessionFixture() }); });
    act(() => { view.result.current.dismissRecovery(); });
    expect(view.result.current.state.kind).toBe('guest');
    expect(view.drafts.recover('draft:project:create').hasLocal).toBe(true);
    expect(localStorage.getItem('easydesign-recovery-path')).toBeNull();
    view.unmount();
  });

  it('不属于当前账号的 401 事件被忽略', async () => {
    const view = await setupAuthenticated();
    await act(async () => { fireSessionExpired({ session: sessionFixture('u9', 'stranger') }); });
    expect(view.result.current.state.kind).toBe('authenticated');
    view.unmount();
  });

  it('非 expired 状态调用 recoverSession 明确报错', async () => {
    const view = setup({ handlers: { probe: () => Promise.reject(new AccountApiError('unauthorized', '请登录', 401)) } });
    await waitFor(() => expect(view.result.current.state.kind).toBe('guest'));
    await expect(view.result.current.recoverSession('password')).rejects.toThrow('当前没有待恢复的会话');
    view.unmount();
  });

  it('主动登出：进入 guest、草稿清空、调用登出接口', async () => {
    const view = await setupAuthenticated();
    view.drafts.saveLocal('draft:project:create', { goal: 'x' });
    await act(async () => { await view.result.current.logout(); });
    expect(view.result.current.state.kind).toBe('guest');
    expect(view.calls.logout).toBe(1);
    expect(view.drafts.recover('draft:project:create').hasLocal).toBe(false);
    expect(view.drafts.identity).toBe('guest');
    view.unmount();
  });
});
