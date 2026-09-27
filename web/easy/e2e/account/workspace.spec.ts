import {expect, test, type Page} from '@playwright/test';
import {
  emptyPage, injectAccountMode, jsonResponse, observerScope, sessionFor, usage, users,
  workbenchSnapshot,
} from './fixtures';

/**
 * Account-mode Easy workspace gating with synthetic fixtures: members discuss and
 * co-edit but cannot start or approve; admin observation is read-only and audited;
 * Gate review links stay inside the scope.
 */
function installWorkspaceRoutes(page: Page, username: string, scopeId: string, compute = true) {
  // Match the document regardless of query string (?scope=...).
  void page.route(url => url.pathname === '/easy/', async route => injectAccountMode(route));
  void page.route('**/api/v1/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const reply = (body: unknown, status = 200) => jsonResponse(route, body, status);
    if (path === '/api/v1/accounts/config')
      return reply({mode: 'multi-user', registration: 'admin-review', setup_required: false, compute_available: compute});
    if (path === '/api/v1/accounts/me')
      return reply(username ? sessionFor(username) : {error: {code: 'session_required', message: '请先登录'}}, username ? 200 : 401);
    if (path === '/api/v1/scopes/team-1/usage' || path === `/api/v1/scopes/${users.bob.id}/usage`)
      return reply({...usage(scopeId), scope: scopeId === 'team-1' ? sessionFor('bob').scopes[1] : observerScope(users.bob.id, 'Bob Member 的个人工作区')});
    if (path.endsWith('/projects') && request.method() === 'GET')
      return reply({items: [workbenchSnapshot().project], total: 1, offset: 0, limit: 5});
    if (path.endsWith('/workbench') && request.method() === 'GET')
      return reply(workbenchSnapshot());
    if (path.endsWith('/candidates') && request.method() === 'GET')
      return reply(emptyPage);
    if (path === '/api/v1/scopes/team-1/rabbit/chat' && request.method() === 'GET')
      return reply({configured: false});
    return reply({error: {code: 'not_found', message: `fixture miss ${path}`}}, 404);
  });
}

test.describe('account-mode Easy workspace', () => {
  test('team member cannot start or approve but keeps read and co-edit surfaces', async ({page}) => {
    installWorkspaceRoutes(page, 'bob', 'team-1');
    // A stale single-user workspace token is dropped silently, never authenticated.
    await page.goto('/easy/?scope=team-1&token=stale-legacy-token-fixture');
    await expect(page).toHaveURL(/scope=team-1$/);
    await expect(page.getByText('Bob Member', {exact: true})).toBeVisible();
    await expect(page.locator('.account-workspace-bar > span', {hasText: 'Antibody Crew'})).toBeVisible();
    await expect(page.locator('.account-workspace-bar > span', {hasText: '团队协作成员'})).toBeVisible();
    await expect(page.getByText('团队协作成员：可以查看和讨论，科学审批及计算启动由团队管理员负责。')).toBeVisible();
    await expect(page.getByRole('button', {name: /开始设计/})).toBeDisabled();
    await expect(page.getByRole('region', {name: 'Gate 2'})).toBeVisible();
    await expect(page.getByRole('button', {name: /批准并继续/})).toBeDisabled();
    await expect(page.getByRole('button', {name: '修改', exact: true})).toBeDisabled();
    // The Gate provenance link is scope-projected, never the unscoped API.
    await page.getByText('查看技术详情').click();
    await expect(page.getByRole('link', {name: '查看当前 Gate 的审查与 provenance'}))
      .toHaveAttribute('href', '/api/v1/scopes/team-1/projects/proj-1/review');
    // The dropped legacy token never surfaces anywhere in the document.
    expect(await page.locator('body').innerText()).not.toContain('stale-legacy-token-fixture');
  });

  test('system admin observation is explicitly read-only', async ({page}) => {
    installWorkspaceRoutes(page, 'root', users.bob.id);
    await page.goto(`/easy/?scope=${users.bob.id}`);
    await expect(page.getByText('管理员只读访问 · 已审计')).toBeVisible();
    await expect(page.getByText('管理员只读查看：不能修改他人项目、批准 Gate 或启动计算。')).toBeVisible();
    await expect(page.getByRole('button', {name: /开始设计/})).toBeDisabled();
    await expect(page.getByRole('button', {name: /批准并继续/})).toBeDisabled();
  });

  test('accounts-only service keeps browsing and co-editing but removes execution', async ({page}) => {
    installWorkspaceRoutes(page, 'alice', 'team-1', false);
    await page.goto('/easy/?scope=team-1');
    await expect(page.getByText('未连接科学执行器')).toBeVisible();
    await expect(page.getByText(/当前服务未连接科学执行器（账号管理模式）/)).toBeVisible();
    // Even the team admin loses launch/approval affordances without a launcher.
    await expect(page.getByRole('button', {name: /开始设计/})).toBeDisabled();
    await expect(page.getByRole('button', {name: /批准并继续/})).toBeDisabled();
    await expect(page.getByRole('region', {name: 'Gate 2'})).toBeVisible();
  });
});
