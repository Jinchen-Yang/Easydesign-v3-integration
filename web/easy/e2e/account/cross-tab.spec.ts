import {expect, test} from '@playwright/test';
import {installAccountRoutes} from './account-helpers';
import {
  emptyPage, injectAccountMode, jsonResponse, sessionFor, usage, workbenchSnapshot,
} from './fixtures';

/**
 * Cross-tab session isolation: another tab's logout must evict this tab to the
 * account page instead of letting a stale session keep acting. (In this dev
 * harness the eviction target shows Vite's 404 placeholder because the account
 * page is served under /easy/account/ in dev; production serves /account/.)
 */
function installWorkspaceRoutes(page: import('@playwright/test').Page) {
  // Match the document regardless of query string (?scope=...).
  void page.route(url => url.pathname === '/easy/', async route => injectAccountMode(route));
  void page.route('**/api/v1/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const reply = (body: unknown, status = 200) => jsonResponse(route, body, status);
    if (path === '/api/v1/accounts/config')
      return reply({mode: 'multi-user', registration: 'admin-review', setup_required: false, compute_available: true});
    if (path === '/api/v1/accounts/me') return reply(sessionFor('bob'));
    if (path === '/api/v1/scopes/team-1/usage') return reply(usage('team-1'));
    if (path.endsWith('/projects') && request.method() === 'GET')
      return reply({items: [workbenchSnapshot().project], total: 1, offset: 0, limit: 5});
    if (path.endsWith('/workbench') && request.method() === 'GET') return reply(workbenchSnapshot());
    if (path.endsWith('/candidates') && request.method() === 'GET') return reply(emptyPage);
    if (path === '/api/v1/scopes/team-1/rabbit/chat' && request.method() === 'GET')
      return reply({configured: false});
    return reply({error: {code: 'not_found', message: `fixture miss ${path}`}}, 404);
  });
}

test('logout in one tab evicts the other tab without self-redirect loops', async ({context}) => {
  const account = await context.newPage();
  installAccountRoutes(account);
  const workspace = await context.newPage();
  installWorkspaceRoutes(workspace);

  await account.goto('/easy/account/');
  await account.getByLabel('用户名').fill('bob');
  await account.getByLabel('密码', {exact: true}).fill('synthetic-password-12');
  await account.getByRole('button', {name: '登录', exact: true}).click();
  await expect(account.getByRole('heading', {name: 'Bob Member'})).toBeVisible();

  await workspace.goto('/easy/?scope=team-1');
  await expect(workspace.getByText('团队协作成员')).toBeVisible();
  expect(workspace.url()).toContain('/easy/');

  // Logging out must evict the workspace tab to the account entry...
  await account.getByRole('button', {name: '退出登录'}).click();
  await expect(account.getByRole('heading', {name: '登录 EasyDesign'})).toBeVisible();
  await expect
    .poll(() => workspace.url(), {timeout: 15000})
    .toContain('/account/');
  // ...and the account tab itself must not loop on its own broadcast.
  await expect(account.getByRole('heading', {name: '登录 EasyDesign'})).toBeVisible();
  expect(account.url()).toContain('/easy/account/');
});
