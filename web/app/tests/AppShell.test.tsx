import { act, cleanup, render, screen } from '@testing-library/react';
import { beforeEach, afterEach, describe, expect, it } from 'vitest';
import { AppShell } from '../src/shell/AppShell';
import { applyLegacyRedirect } from '../src/shell/legacyRedirect';
import { LANGUAGE_KEY } from '../src/shell/I18nProvider';

/**
 * Shell-level boot checks. Under jsdom the real session API is unreachable
 * (relative fetch fails), which drives the network-error branch exactly like
 * a dev server without a backend.
 */

afterEach(cleanup);

beforeEach(() => {
  localStorage.clear();
  window.history.pushState({}, '', '/');
});

describe('AppShell 统一壳（阶段 3）', () => {
  it('首次渲染即显示 App Shell Loading...（checking 状态）', () => {
    render(<AppShell />);
    expect(screen.getByText('App Shell Loading...')).toBeTruthy();
  });

  it('后端不可达时落入 network-error 面板并保留导航', async () => {
    render(<AppShell />);
    const retry = await screen.findByTestId('session-network-error');
    expect(retry.textContent).toContain('网络异常');
    expect(screen.getByText('重试')).toBeTruthy();
    expect(screen.getByRole('link', { name: '账号与团队' })).toBeTruthy();
  });

  it('network-error 面板可放弃并落到访客演示首页', async () => {
    render(<AppShell />);
    await screen.findByTestId('session-network-error');
    act(() => { screen.getByText('以访客继续').click(); });
    expect(await screen.findByText(/访客演示/)).toBeTruthy();
  });

  it('语言切换实时生效且持久化，不重新挂载应用', async () => {
    localStorage.setItem(LANGUAGE_KEY, 'zh');
    render(<AppShell />);
    await screen.findByTestId('session-network-error');
    expect(document.documentElement.lang).toBe('zh-CN');
    act(() => { screen.getByRole('button', { name: 'EN' }).click(); });
    expect((await screen.findByTestId('session-network-error')).textContent).toContain('Network problem');
    expect(document.documentElement.lang).toBe('en');
    expect(localStorage.getItem(LANGUAGE_KEY)).toBe('en');
  });

  it('#/account 渲染账号门户（登录表单可见）', async () => {
    const originalFetch = window.fetch;
    window.fetch = async () => Response.json({ error: { code: 'unauthorized' } }, { status: 401 });
    try {
      window.location.hash = '#/account';
      render(<AppShell />);
      expect(await screen.findByRole('heading', { name: '登录 EasyDesign' })).toBeTruthy();
    } finally { window.fetch = originalFetch; }
  });

  it('account network failure offers retry without assuming the visitor is signed out', async () => {
    window.location.hash = '#/account';
    render(<AppShell />);
    expect(await screen.findByRole('heading', { name: '暂时无法确认登录状态，请重试。' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '重试' })).toBeTruthy();
    expect(screen.queryByLabelText('密码')).toBeNull();
  });

  it('#/demo 渲染演示工作台，专业版链接指向应用内路由（死链已修）', async () => {
    window.location.hash = '#/demo';
    render(<AppShell />);
    const pro = await screen.findByRole('link', { name: '专业版' }, { timeout: 3000 });
    expect(pro.getAttribute('href')).toBe('#/projects');
  });

  it('#/projects（未登录）给出登录引导屏而不是弹跳', async () => {
    const originalFetch = window.fetch;
    window.fetch = (async () => new Response(JSON.stringify({ error: { code: 'unauthorized' } }), {
      status: 401, headers: { 'Content-Type': 'application/json' },
    })) as typeof fetch;
    try {
      window.location.hash = '#/projects?scope=s1&view=easy';
      render(<AppShell />);
      expect(await screen.findByText('登录后使用 Easy 工作区')).toBeTruthy();
      expect(screen.getByRole('link', { name: '登录 / 注册' })).toBeTruthy();
      expect(window.location.hash).toBe('#/projects?scope=s1&view=easy');
    } finally {
      window.fetch = originalFetch;
    }
  });
});

describe('legacyRedirect 旧链接规范化', () => {
  function arrive(path: string, search = ''): string[] {
    const calls: string[] = [];
    window.history.pushState({}, '', `${path}${search}`);
    applyLegacyRedirect((url) => { calls.push(url); });
    return calls;
  }

  it('/account/ → #/account', () => {
    expect(arrive('/account/', '')).toEqual(['#/account']);
  });

  it('/easy/?scope=u1&project=p1 → 项目路由（view=easy）', () => {
    expect(arrive('/easy/', '?scope=u1&project=p1')).toEqual(['#/projects/p1?scope=u1&view=easy']);
  });

  it('/?scope=u1&project=p1（旧 Pro 链接）→ view=pro', () => {
    expect(arrive('/', '?scope=u1&project=p1')).toEqual(['#/projects/p1?scope=u1&view=pro']);
  });

  it('仅有 scope 时保留为首页参数', () => {
    expect(arrive('/easy/', '?scope=u1')).toEqual(['#/?scope=u1']);
  });

  it('已在应用路由内或带 ?next= 时不动作', () => {
    const quiet: string[] = [];
    window.history.pushState({}, '', '/');
    window.location.hash = '#/projects/p9';
    applyLegacyRedirect((url) => { quiet.push(url); });
    window.history.pushState({}, '', '/?next=%23%2Faccount');
    applyLegacyRedirect((url) => { quiet.push(url); });
    expect(quiet).toEqual([]);
  });
});
