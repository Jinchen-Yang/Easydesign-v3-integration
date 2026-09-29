import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { AppShell } from '../src/shell/AppShell';
import { appI18n } from '../src/shell/I18nProvider';

/**
 * 阶段 4：先看到、用时登录。访客首页直接渲染演示工作台；动作边界
 * （自有输入提交 / 真实工作区）转为登录引导；语言只有一个权威。
 */

function stubUnauthorized(): typeof fetch {
  return (async () => new Response(JSON.stringify({ error: { code: 'unauthorized' } }), {
    status: 401, headers: { 'Content-Type': 'application/json' },
  })) as typeof fetch;
}

let originalFetch: typeof fetch;

afterEach(cleanup);

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  window.history.pushState({}, '', '/');
  originalFetch = window.fetch;
});

describe('访客首页（阶段 4）', () => {
  it('未登录访问 / 立即看到演示工作台与登录 CTA，无需任何跳转', async () => {
    window.fetch = stubUnauthorized();
    try {
      render(<AppShell />);
      // 演示工作台的核心输入卡在访客首页可见
      expect(await screen.findByText('开始设计', {}, { timeout: 3000 })).toBeTruthy();
      // 登录 CTA 常驻
      expect(screen.getByText(/当前为访客演示/)).toBeTruthy();
      expect(screen.getByRole('link', { name: '登录 / 注册' })).toBeTruthy();
      // 页面地址不变（不发生整页跳转）
      expect(window.location.pathname).toBe('/');
    } finally {
      window.fetch = originalFetch;
    }
  });

  it('访客用自有输入点开始设计：拦截并弹出登录引导；固定演示不受影响', async () => {
    window.fetch = stubUnauthorized();
    try {
      render(<AppShell />);
      const textarea = await screen.findByPlaceholderText(/VHH|UniProt|PDB|溶菌酶/, {}, { timeout: 3000 });
      fireEvent.change(textarea, { target: { value: '为 EGFR 设计一个 VHH' } });
      const submit = screen.getByRole('button', { name: /开始设计/ });
      await act(async () => { submit.click(); });
      const dialog = await screen.findByRole('dialog');
      expect(within(dialog).getByText('登录后可提交真实设计任务')).toBeTruthy();
      // 引导层提供登录入口与「先看固定演示」两个出口
      expect(within(dialog).getByRole('link', { name: '登录 / 注册' })).toBeTruthy();
      expect(within(dialog).getByRole('button', { name: '先看固定演示' })).toBeTruthy();
    } finally {
      window.fetch = originalFetch;
    }
  });
});

describe('语言唯一权威（根因 D）', () => {
  it('演示页语言控件经统一 i18n：切英文后文案变为英文源文', async () => {
    window.fetch = stubUnauthorized();
    try {
      render(<AppShell />);
      await screen.findByText('开始设计', {}, { timeout: 3000 });
      const en = screen.getByRole('button', { name: 'English' });
      await act(async () => { en.click(); });
      // h1 走 easy 命名空间；切英文后演示文案变为英文源文（zh 时为「开始设计」）
      await waitFor(() => expect(screen.getByRole('heading', { name: /^Start (a )?design$/ })).toBeTruthy());
      expect(document.title).toContain('Start');
      expect(localStorage.getItem('easydesign-easy-locale-v1')).toBe('en');
    } finally {
      window.fetch = originalFetch;
    }
  });

  it('英文缺译回落为键本身（英文即源文），绝不回落中文', () => {
    const en = appI18n.getFixedT('en', 'easy');
    // 字典里有英文覆盖的键走覆盖值
    expect(en('Lysozyme')).toBe('Lysozyme');
    // 无英文覆盖的键返回键本身（英文源文），而不是中文翻译
    expect(en('My designs')).toBe('My designs');
    const zh = appI18n.getFixedT('zh', 'easy');
    expect(zh('My designs')).toBe('我的设计');
  });

  it('缺省插值保留花括号字面量（MolecularViewer 依赖手动 replace）', () => {
    const zh = appI18n.getFixedT('zh', 'easy');
    expect(zh('Site {site} highlighted')).toContain('{site}');
  });
});
