import { expect, test } from '@playwright/test';

/**
 * 阶段 4 验收（无需后端）：
 *  - 访客首页立即可见演示工作台与登录 CTA（痛点①）
 *  - 动作边界：访客自有输入提交转登录引导；固定演示可走通
 *  - 旧链接归一（阶段 3 兼容）
 *  - 语言唯一权威：演示页控件与壳层共享同一偏好
 *  - 访客首屏不触碰任何作用域数据接口（不越权）
 */

test.beforeEach(async ({ page }) => {
  // dev 服务器没有后端：vite 会把 /api/** 兜底成 index.html(200)，应用会
  // 正确地判为 network-error。这里按真实部署的匿名响应（401 JSON）委托，
  // 让 e2e 验证的是产品行为而不是 dev 服务器的兜底差异。
  await page.route('**/api/v1/accounts/**', (route) =>
    route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ error: { code: 'unauthorized', message: '请登录' } }),
    }),
  );
});

test('visitor lands on a visible demo workbench with a sign-in CTA', async ({ page }) => {
  const scopedCalls: string[] = [];
  page.on('request', (request) => {
    const url = request.url();
    if (url.includes('/api/v1/scopes/')) scopedCalls.push(url);
  });

  await page.goto('/app/');
  await expect(page.getByRole('heading', { name: /开始设计|Start (a )?design/ })).toBeVisible();
  await expect(page.getByText(/当前为访客演示/)).toBeVisible();
  await expect(page.getByRole('link', { name: '登录 / 注册' })).toBeVisible();
  // 访客不得触发任何作用域数据请求。
  expect(scopedCalls).toEqual([]);
});

test('guest submitting a custom design gets a sign-in prompt; fixed demo stays runnable', async ({ page }) => {
  await page.goto('/app/');
  await page.getByPlaceholder(/设计一个针对|UniProt|PDB|VHH|溶菌酶/).fill('为 EGFR 设计一个 VHH');
  await page.getByRole('button', { name: /开始设计/ }).click();
  const dialog = page.getByRole('dialog', { name: '登录后可提交真实设计任务' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('link', { name: '登录 / 注册' })).toBeVisible();
  await dialog.getByRole('button', { name: '先看固定演示' }).click();
  await expect(dialog).toBeHidden();
  // 固定演示保持可走通：试用填充后提交，运行卡出现在「我的设计」中
  await page.getByRole('button', { name: /试用溶菌酶/ }).click();
  await page.getByRole('button', { name: /^\s*开始设计\s*$/ }).click();
  await expect(page.getByText('溶菌酶 · VHH').first()).toBeVisible();
});

test('legacy deep links normalize onto hash routes', async ({ page }) => {
  await page.goto('/app/?scope=s9&project=p7');
  await expect.poll(() => page.evaluate(() => location.hash)).toBe('#/projects/p7?scope=s9&view=easy');
});

test('the language control drives the whole shell through one authority', async ({ page }) => {
  await page.goto('/app/');
  await page.getByRole('button', { name: 'English' }).click();
  await expect(page.getByRole('heading', { name: /^Start (a )?design$/ })).toBeVisible();
  // 偏好写入与壳层共享的存储键
  expect(await page.evaluate(() => localStorage.getItem('easydesign-easy-locale-v1'))).toBe('en');
  await page.reload();
  await expect(page.getByRole('heading', { name: /^Start (a )?design$/ })).toBeVisible();
});

test('the guest Pro screen follows the same language authority', async ({ page }) => {
  await page.goto('/app/#/projects?view=pro');
  await expect(page.getByRole('heading', { name: '登录后使用专业版工作台' })).toBeVisible();
  // 语言控件在演示视图里（工作区路由为全幅页面）：切 EN 后同一权威驱动 Pro 引导屏
  await page.goto('/app/');
  await page.getByRole('button', { name: 'English' }).click();
  await page.goto('/app/#/projects?view=pro');
  await expect(page.getByRole('heading', { name: 'Sign in to use the Pro workbench' })).toBeVisible();
});
