import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { I18nProvider } from '../src/shell/I18nProvider';
import { SessionProvider, SESSION_EXPIRED_EVENT } from '../src/shell/SessionProvider';
import { SessionRecoveryModal } from '../src/shell/SessionRecoveryModal';
import { AccountApiError, type AccountSession } from '../src/shared/account-client';
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

function sessionFixture(): AccountSession {
  return {
    user: {
      id: 'u1', username: 'test01', display_name: '测试用户', role: 'user',
      status: 'active', must_change_password: false,
    },
    csrf_token: 'csrf-token',
    scopes: [{
      id: 'scope-u1', kind: 'personal', name: '个人工作区',
      role: 'owner', can_edit: true, can_execute: true,
    }],
    invitations: [],
  };
}

function setup(handlers: { login?: (username: string, password: string) => Promise<AccountSession> } = {}) {
  const session = sessionFixture();
  const loginImpl = handlers.login ?? (() => Promise.resolve(sessionFixture()));
  const api = {
    probe: () => Promise.resolve(session),
    login: (username: string, password: string) => loginImpl(username, password),
    logout: () => Promise.resolve(),
  };
  const drafts = createDraftRecovery({ storage: memoryStorage() });
  const wrapper = ({ children }: { children?: ReactNode }) => (
    <I18nProvider>
      <SessionProvider api={api} drafts={drafts}>{children}</SessionProvider>
    </I18nProvider>
  );
  const view = render(<SessionRecoveryModal />, { wrapper });
  return { ...view, api, drafts };
}

function expireSession(): void {
  window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT, { detail: { session: sessionFixture() } }));
}

afterEach(cleanup);

beforeEach(() => {
  localStorage.clear();
  window.history.pushState({}, '', '/');
});

describe('SessionRecoveryModal（恢复遮罩）', () => {
  it('仅在 expired 状态出现；过期前不渲染任何内容', async () => {
    const view = setup();
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expireSession();
    expect(await screen.findByRole('dialog')).toBeTruthy();
    view.unmount();
  });

  it('展示过期账号、密码输入与暂存提示', async () => {
    const view = setup();
    await act(async () => {}); // 让会话探测先完成（checking → authenticated）
    await act(async () => { expireSession(); });
    expect(screen.getByText('会话已过期')).toBeTruthy();
    expect(screen.getByText('账号：测试用户')).toBeTruthy();
    expect(screen.getByLabelText('密码')).toBeTruthy();
    expect(screen.getByText('未保存的输入已暂存，登录后将自动恢复')).toBeTruthy();
    expect(screen.getByRole('button', { name: '重新登录' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '取消' })).toBeTruthy();
    view.unmount();
  });

  it('密码错误：显示后端错误信息并保持遮罩', async () => {
    const view = setup({
      login: () => Promise.reject(new AccountApiError('invalid_credentials', '用户名或密码错误', 401)),
    });
    await act(async () => {}); // 让会话探测先完成（checking → authenticated）
    await act(async () => { expireSession(); });
    await act(async () => {
      fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'wrong-password' } });
      fireEvent.click(screen.getByRole('button', { name: '重新登录' }));
    });
    expect((await screen.findByRole('alert')).textContent).toContain('用户名或密码错误');
    expect(screen.getByRole('dialog')).toBeTruthy();
    view.unmount();
  });

  it('重新登录成功：遮罩消失并回到过期前的路由', async () => {
    const view = setup();
    await act(async () => {}); // 让会话探测先完成（checking → authenticated）
    window.location.hash = '#/projects/p1?scope=s1&view=easy';
    await act(async () => { expireSession(); });
    expect(screen.getByRole('dialog')).toBeTruthy();
    await act(async () => {
      fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'correct-password' } });
      fireEvent.click(screen.getByRole('button', { name: '重新登录' }));
    });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(window.location.hash).toBe('#/projects/p1?scope=s1&view=easy');
    view.unmount();
  });

  it('取消恢复：遮罩消失（进入访客态）', async () => {
    const view = setup();
    await act(async () => {}); // 让会话探测先完成（checking → authenticated）
    await act(async () => { expireSession(); });
    await act(async () => { screen.getByRole('button', { name: '取消' }).click(); });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    view.unmount();
  });
});
