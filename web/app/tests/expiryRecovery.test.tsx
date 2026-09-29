import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { HashRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { I18nProvider } from '../src/shell/I18nProvider';
import { SessionProvider, SESSION_EXPIRED_EVENT, useSession, type SessionContextValue } from '../src/shell/SessionProvider';
import { EasyWorkspace } from '../src/views/easy/EasyWorkspace';
import type { EasyProductPort } from '../src/views/easy/EasyProductAdapter';
import { createDraftRecovery, draftRecovery, DRAFT_KEYS, type DraftRecoveryModule } from '../src/data/draftRecovery';
import type { AccountSession } from '../src/shared/account-client';

/**
 * 验收点（节点 3 阻塞项 1）：会话过期不卸载工作区。
 * 断言：输入内容保留、适配器实例不变（防重复提交的请求编号表存活）、
 * 过期暂停轮询 / 恢复后继续，并且设计输入已进入草稿模块。
 */

const session: AccountSession = {
  user: {
    id: 'u1', username: 'test01', display_name: '测试用户', role: 'user',
    status: 'active', must_change_password: false,
  },
  csrf_token: 'csrf-token',
  scopes: [{
    id: 's1', kind: 'personal', name: '个人工作区',
    role: 'owner', can_edit: true, can_execute: true,
  }],
  invitations: [],
};

class FakeAdapter {
  static instances = 0;
  readonly instanceId = ++FakeAdapter.instances;
  pauseCount = 0;
  resumeCount = 0;
  disposeCount = 0;
  private listeners = new Set<(event: unknown) => void>();
  private state = {
    connection: 'connected',
    projects: { items: [], total: 0, offset: 0 },
    snapshot: null,
    candidates: { items: [], total: 0, offset: 0 },
    selectedCandidate: null,
    selectedProject: null,
    pending: false,
    error: null,
    pendingRequest: null,
  };
  async load() { return this.state; }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  subscribe(cb: (event: any) => void) { this.listeners.add(cb); return () => { this.listeners.delete(cb); }; }
  dispose() { this.disposeCount += 1; }
  pausePolling() { this.pauseCount += 1; }
  resumePolling() { this.resumeCount += 1; }
}

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

afterEach(cleanup);

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  draftRecovery.setIdentity(null);
  FakeAdapter.instances = 0;
  window.history.pushState({}, '', '/');
  window.fetch = (async () => new Response(JSON.stringify({
    mode: 'multi-user', registration: 'admin-review', setup_required: false, compute_available: true,
  }), { status: 200, headers: { 'Content-Type': 'application/json' } })) as typeof fetch;
});

describe('会话过期：工作区保活与适配器稳定', () => {
  it('过期 → 恢复全程：输入保留、适配器实例不变、轮询暂停/恢复、草稿已暂存', async () => {
    const fake = new FakeAdapter();
    const drafts: DraftRecoveryModule = createDraftRecovery({ storage: memoryStorage() });
    const machine: { current: SessionContextValue | null } = { current: null };
    function SessionProbe() { machine.current = useSession(); return null; }
    const api = {
      probe: () => Promise.resolve(session),
      login: () => Promise.resolve(session),
      logout: () => Promise.resolve(),
    };

    window.location.hash = '#/projects?scope=s1&view=easy';
    render(
      <I18nProvider>
        <SessionProvider api={api} drafts={drafts}>
          <HashRouter>
            <SessionProbe />
            <EasyWorkspace adapterFactory={() => fake as unknown as EasyProductPort} />
          </HashRouter>
        </SessionProvider>
      </I18nProvider>,
    );

    await waitFor(() => expect(machine.current?.state.kind).toBe('authenticated'));
    const input = await screen.findByPlaceholderText(/NK2R/);
    fireEvent.change(input, { target: { value: '设计针对鸡卵清溶菌酶的 VHH 结合分子' } });

    // 设计输入进入草稿模块（阻塞项 1 的最后半条：有人写入了）。
    await waitFor(() => expect(draftRecovery.recover(DRAFT_KEYS.projectCreate).hasLocal).toBe(true));

    // 会话过期：只切状态，不卸载工作区。
    await act(async () => {
      window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT, { detail: { session } }));
    });
    await waitFor(() => expect(machine.current?.state.kind).toBe('expired'));
    expect((screen.getByPlaceholderText(/NK2R/) as HTMLTextAreaElement).value)
      .toBe('设计针对鸡卵清溶菌酶的 VHH 结合分子');
    // 适配器没有被重建（请求编号表存活），并且轮询已暂停。
    expect(FakeAdapter.instances).toBe(1);
    expect(fake.pauseCount).toBeGreaterThanOrEqual(1);
    expect(fake.disposeCount).toBe(0);

    // 同账号恢复登录：不换 key、不重建适配器，输入原样保留。
    await act(async () => { await machine.current!.recoverSession('password'); });
    expect(machine.current?.state.kind).toBe('authenticated');
    expect((screen.getByPlaceholderText(/NK2R/) as HTMLTextAreaElement).value)
      .toBe('设计针对鸡卵清溶菌酶的 VHH 结合分子');
    expect(FakeAdapter.instances).toBe(1);
    expect(fake.resumeCount).toBeGreaterThanOrEqual(1);

    // 恢复路径被正确消费（阶段 2 语义未被本轮改动破坏）。
    expect(localStorage.getItem('easydesign-recovery-path')).toBeNull();
  });

  it('主动登出才释放适配器并回到登录引导', async () => {
    const fake = new FakeAdapter();
    const drafts: DraftRecoveryModule = createDraftRecovery({ storage: memoryStorage() });
    const machine: { current: SessionContextValue | null } = { current: null };
    function SessionProbe() { machine.current = useSession(); return null; }
    window.location.hash = '#/projects?scope=s1&view=easy';
    render(
      <I18nProvider>
        <SessionProvider
          api={{ probe: () => Promise.resolve(session), login: () => Promise.resolve(session), logout: () => Promise.resolve() }}
          drafts={drafts}
        >
          <HashRouter>
            <SessionProbe />
            <EasyWorkspace adapterFactory={() => fake as unknown as EasyProductPort} />
          </HashRouter>
        </SessionProvider>
      </I18nProvider>,
    );
    await waitFor(() => expect(machine.current?.state.kind).toBe('authenticated'));
    await screen.findByPlaceholderText(/NK2R/);
    await act(async () => { await machine.current!.logout(); });
    expect(machine.current?.state.kind).toBe('guest');
    expect(await screen.findByText('请先登录')).toBeTruthy();
    expect(fake.disposeCount).toBeGreaterThanOrEqual(1);
  });
});

// 给 SessionProbe 一个引用，避免 TS 判定未使用。
void (null as unknown as ReactNode);
