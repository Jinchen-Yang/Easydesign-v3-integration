import { act, cleanup, render, screen } from '@testing-library/react';
import { beforeEach, afterEach, describe, expect, it } from 'vitest';
import { AppShell } from '../src/shell/AppShell';
import { LANGUAGE_KEY } from '../src/shell/I18nProvider';

/**
 * Boot-level checks for the phase-1 shell: the loading text, the fallback when
 * no backend answers, hash routing and the language toggle. The real session
 * API is unreachable under jsdom (relative fetch fails), which exercises the
 * network-error branch exactly like a dev server without a backend.
 */

afterEach(cleanup);

beforeEach(() => {
  localStorage.clear();
  window.location.hash = '';
});

describe('AppShell 空壳', () => {
  it('首次渲染即显示 App Shell Loading...（checking 状态）', () => {
    render(<AppShell />);
    expect(screen.getByText('App Shell Loading...')).toBeTruthy();
  });

  it('后端不可达时落入 network-error 面板并保留路由与导航', async () => {
    render(<AppShell />);
    const retry = await screen.findByTestId('session-network-error');
    expect(retry.textContent).toContain('网络异常');
    expect(screen.getByText('重试')).toBeTruthy();
    expect(screen.getByText('以访客继续')).toBeTruthy();
    expect(screen.getByText('账号与团队')).toBeTruthy();
  });

  it('network-error 面板可放弃并以访客继续', async () => {
    render(<AppShell />);
    await screen.findByTestId('session-network-error');
    act(() => { screen.getByText('以访客继续').click(); });
    expect((await screen.findByTestId('session-guest')).textContent).toContain('访客模式');
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

  it('hash 路由表：#/account 渲染账号占位', async () => {
    window.location.hash = '#/account';
    render(<AppShell />);
    expect(await screen.findByText(/账号与团队（阶段 3 迁入）/)).toBeTruthy();
  });
});
