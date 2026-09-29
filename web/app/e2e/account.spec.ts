import { expect, test } from '@playwright/test';

const user = {id: 'ui-check', username: 'researcher', display_name: 'Researcher', role: 'user', status: 'active', must_change_password: false};
const personal = {id: 'personal-check', name: 'Personal workspace', kind: 'personal', role: 'owner', can_execute: true, can_edit: true};
const team = {id: 'team-check', name: 'Protein design lab', kind: 'team', role: 'owner', can_execute: true, can_edit: true};

test.beforeEach(async ({page}) => {
  await page.addInitScript(() => { if (!localStorage.getItem('easydesign-easy-locale-v1')) localStorage.setItem('easydesign-easy-locale-v1', 'en'); });
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown;
    if (path.endsWith('/accounts/me')) body = {user, csrf_token: 'test-csrf', scopes: [personal, team], invitations: []};
    else if (path.endsWith('/accounts/config')) body = {compute_available: true, setup_required: false, registration: 'open'};
    else if (path.endsWith('/projects')) body = {items: [], total: 0, offset: 0, limit: 20};
    else if (path.endsWith('/teams/team-check')) body = {team: {id: team.id, name: team.name, status: 'active', members: [{user_id: user.id, username: user.username, display_name: user.display_name, role: 'owner', status: 'active', account_status: 'active'}]}};
    else if (path.includes('/drafts')) body = {drafts: []};
    else return route.fulfill({status: 404, json: {error: {code: 'unmocked', message: path}}});
    await route.fulfill({json: body});
  });
});

test('account menu opens settings without replacing a project draft and Escape restores focus', async ({page}) => {
  await page.goto('/app/#/projects?scope=personal-check&view=pro&page=workspace');
  const input = page.locator('textarea').first();
  await input.fill('Investigate a new binding interface');
  const menu = page.getByRole('button', {name: 'Open account menu'});
  await menu.click();
  await page.getByRole('link', {name: 'Team collaboration', exact: true}).click();
  const dialog = page.getByRole('dialog', {name: 'Account and workspace settings'});
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('heading', {name: 'Protein design lab'})).toBeVisible();
  await expect(page).toHaveURL(/#\/projects\?scope=personal-check&view=pro&page=workspace$/);
  await page.screenshot({path: 'runtime/tmp/production-deploy/account-overlay-local.png'});
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(menu).toBeFocused();
  await expect(input).toHaveValue('Investigate a new binding interface');
});

test('settings collapse, translate and fit on a phone', async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto('/app/#/account?section=teams');
  await expect(page.getByRole('heading', {name: 'Team collaboration', exact: true}).first()).toBeVisible();
  await page.getByRole('button', {name: 'Collapse menu'}).click();
  await expect(page.getByRole('button', {name: 'Expand menu'})).toHaveAttribute('aria-expanded', 'false');
  await page.getByRole('button', {name: '中文', exact: true}).click();
  await expect(page.getByRole('heading', {name: '团队协作', exact: true}).first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: 'runtime/tmp/production-deploy/account-mobile-local.png'});
  await page.getByRole('button', {name: '账号安全', exact: true}).click();
  await expect(page.getByLabel('当前密码')).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', {name: '账号安全', exact: true}).first()).toBeVisible();
});
