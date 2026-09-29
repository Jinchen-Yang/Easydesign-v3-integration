import { expect, test } from '@playwright/test';

// Read-only product-contract fixtures: a language change must never submit science.
test('Pro switches navigation, permissions and compute controls without changing scope data', async ({
  page,
}) => {
  const mutations: string[] = [];
  const scope = {
    id: 'team-language',
    kind: 'team',
    name: 'Research Ω',
    role: 'member',
    can_edit: true,
    can_execute: false,
  };
  await page.route('**/api/v1/accounts/**', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(
        route.request().url().endsWith('/config')
          ? {
              mode: 'accounts',
              registration: 'open',
              setup_required: false,
              compute_available: true,
            }
          : {
              user: {
                id: 'language-reader',
                username: 'reader',
                display_name: 'Reader',
                role: 'user',
                status: 'active',
                must_change_password: false,
              },
              csrf_token: 'fixture',
              scopes: [scope],
              invitations: [],
            },
      ),
    }),
  );
  await page.route('**/api/v1/scopes/team-language/**', (route) => {
    if (route.request().method() !== 'GET') mutations.push(route.request().method());
    return route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ items: [], total: 0, offset: 0, limit: 50 }),
    });
  });
  await page.route('**/api/compute/resources', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        connection: 'not-configured',
        node: 'fixture-node',
        sample: null,
      }),
    }),
  );
  await page.goto('/app/#/projects?scope=team-language&view=pro');
  await expect(page.getByRole('heading', { name: '项目', exact: true })).toBeVisible();
  await expect(page.getByRole('note')).toHaveText(
    '团队成员不能启动计算；请协作编辑团队草稿，由团队管理员创建项目。',
  );
  await page.getByRole('button', { name: '打开账号菜单', exact: true }).click();
  await page.getByRole('button', { name: 'EN', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Projects', exact: true })).toBeVisible();
  await expect(page.getByRole('note')).toHaveText(
    'Team members cannot start compute; collaborate on team drafts and let a team admin create the project.',
  );
  await page.getByRole('button', { name: 'Compute & Queue', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Compute & Queue', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'No compute service connected' })).toBeVisible();
  await page.getByRole('button', { name: 'Open account menu', exact: true }).click();
  await page.getByRole('button', { name: '中文', exact: true }).click();
  await expect(page.getByRole('heading', { name: '算力与队列', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '尚未连接计算服务' })).toBeVisible();
  await expect(page.getByRole('option', { name: 'Research Ω', exact: true })).toHaveCount(1);
  expect(mutations).toEqual([]);
});
