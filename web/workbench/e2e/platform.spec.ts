import { expect, test, type Page } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/api/compute/resources', (route) =>
    route.fulfill({
      json: {
        connection: 'not-configured',
        node: 'Compute node',
        sample: null,
      },
    }),
  );
});

async function nav(page: Page, name: 'Projects' | 'Agent Workspace' | 'Compute & Queue') {
  await page
    .getByRole('navigation', { name: 'Main navigation' })
    .getByRole('button', { name, exact: true })
    .click();
}
async function create(page: Page, goal: string) {
  await nav(page, 'Projects');
  await page.getByRole('button', { name: 'New project', exact: true }).click();
  await expect(page.getByLabel('Your research goal')).toHaveValue('');
  await expect(page.getByLabel('Your research goal')).toBeFocused();
  await page.getByLabel('Your research goal').fill(goal);
  await page.getByRole('button', { name: 'Start design', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Approve target', exact: true })).toBeVisible();
}
async function advance(page: Page, name: string, next: string) {
  await page.getByRole('button', { name, exact: true }).click();
  await expect(page.getByRole('button', { name: next, exact: true })).toBeVisible();
}
async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

test('three English destinations, empty states, browser history and narrow navigation', async ({
  page,
}, info) => {
  await page.goto('/?mode=demo');
  const navigation = page.getByRole('navigation', { name: 'Main navigation' });
  await expect(navigation.getByRole('button')).toHaveCount(3);
  await expect(page.getByRole('heading', { name: 'Projects', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Give your next idea a home.' })).toBeVisible();
  await noOverflow(page);
  await page.screenshot({ path: `docs/screenshots/projects-empty-${info.project.name}.png` });
  await nav(page, 'Compute & Queue');
  await expect(page.getByRole('heading', { name: 'No compute service connected' })).toBeVisible();
  await expect(page.getByTestId('demo-run')).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Compute & Queue', exact: true })).toBeVisible();
  await nav(page, 'Agent Workspace');
  await expect(page.getByRole('heading', { name: 'What would you like to design?' })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole('heading', { name: 'Compute & Queue', exact: true })).toBeVisible();
  await page.goForward();
  await expect(page.getByLabel('Your research goal')).toBeVisible();
  await page.getByRole('button', { name: 'Collapse project sidebar' }).click();
  await page.setViewportSize({ width: 642, height: 948 });
  await nav(page, 'Projects');
  await page.getByRole('button', { name: 'Expand project sidebar' }).click();
  await page.screenshot({ path: `docs/screenshots/navigation-narrow-${info.project.name}.png` });
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Expand project sidebar' })).toBeFocused();
  await page.keyboard.press('Enter');
  await nav(page, 'Compute & Queue');
  await expect(page.getByRole('button', { name: 'Expand project sidebar' })).toHaveAttribute(
    'aria-expanded',
    'false',
  );
  await noOverflow(page);
  await page.screenshot({ path: `docs/screenshots/compute-empty-narrow-${info.project.name}.png` });
});

test('project center creates, searches, renames and switches independent workspaces', async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  await page.goto('/?mode=demo');
  await create(page, 'Explore a compact lysozyme epitope.');
  await advance(page, 'Approve target', 'Approve Site B');
  await page
    .getByRole('group', { name: 'Candidate sites' })
    .getByRole('button', { name: 'Site C' })
    .click();
  await page.getByLabel('Message Design Scientist').fill('Keep Site C for this project only.');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await nav(page, 'Projects');
  await page.getByRole('button', { name: 'Rename project Lysozyme VHH', exact: true }).click();
  await page.getByLabel('Project name').fill('Compact epitope');
  await page.getByRole('button', { name: 'Save name' }).click();
  await create(page, 'A second independent lysozyme design.');
  await nav(page, 'Projects');
  await expect(page.getByTestId('design-project')).toHaveCount(2);
  await page.getByLabel('Search projects').fill('Compact');
  await expect(page.getByTestId('design-project')).toHaveCount(1);
  await page.getByLabel('Search projects').fill('missing-project');
  await expect(page.getByRole('heading', { name: 'No matching projects' })).toBeVisible();
  await page.getByRole('button', { name: 'Clear search' }).click();
  await expect(page.getByTestId('design-project')).toHaveCount(2);
  await page.screenshot({ path: `docs/screenshots/project-center-${info.project.name}.png` });
  await page.getByRole('button', { name: 'Open project Compact epitope', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Approve Site C' })).toBeVisible();
  await expect(page.getByText('Keep Site C for this project only.', { exact: true })).toBeVisible();
  await page.getByLabel('Message Design Scientist').fill('Unsent first-project note');
  await page.getByLabel('Current project').selectOption({ label: 'Lysozyme VHH 2' });
  await expect(page.getByRole('button', { name: 'Approve target', exact: true })).toBeVisible();
  await expect(page.getByLabel('Message Design Scientist')).toHaveValue('');
  await page.getByLabel('Current project').selectOption({ label: 'Compact epitope' });
  await page.reload();
  await expect(page.getByRole('button', { name: 'Approve Site C' })).toBeVisible();
  await expect(page.locator('.conversation')).toHaveCount(1);
  await expect(page.locator('.scientific-context')).toHaveCount(1);
  await noOverflow(page);
  await page.screenshot({ path: `docs/screenshots/agent-workspace-${info.project.name}.png` });
  const saved = await page.evaluate(() => localStorage.getItem('easydesign-workbench-projects-v1'));
  await nav(page, 'Projects');
  await page.getByRole('button', { name: 'New project', exact: true }).click();
  await page.getByLabel('Your research goal').fill('An abandoned new draft');
  await nav(page, 'Projects');
  await nav(page, 'Agent Workspace');
  await expect(page.getByRole('button', { name: 'Approve Site C' })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('easydesign-workbench-projects-v1'))).toBe(
    saved,
  );
  await nav(page, 'Projects');
  await page.getByRole('button', { name: 'Collapse project sidebar' }).click();
  await page.setViewportSize({ width: 642, height: 948 });
  await noOverflow(page);
  await page.screenshot({
    path: `docs/screenshots/project-center-narrow-${info.project.name}.png`,
  });
  await page.getByRole('button', { name: 'Open project Compact epitope', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Approve Site C' })).toBeVisible();
  await noOverflow(page);
  expect(errors).toEqual([]);
});

test('compute page reflects approved demo runs, filters and returns to the correct project', async ({
  page,
}, info) => {
  await page.goto('/?mode=demo');
  await create(page, 'Review a small lysozyme pilot and scale.');
  await advance(page, 'Approve target', 'Approve Site B');
  await advance(page, 'Approve Site B', 'Approve design');
  await nav(page, 'Compute & Queue');
  await expect(page.getByTestId('demo-run')).toHaveCount(0);
  await nav(page, 'Agent Workspace');
  await advance(page, 'Approve design', 'Promote 6 candidates');
  await advance(page, 'Promote 6 candidates', 'Review candidates');
  await create(page, 'Another independent demo project.');
  await nav(page, 'Compute & Queue');
  await expect(page.getByTestId('demo-run')).toHaveCount(2);
  await expect(page.getByTestId('demo-run').first()).toContainText('8 / 8');
  await expect(page.getByTestId('demo-run').last()).toContainText('24 / 24');
  await expect(page.getByText('No GPU jobs are submitted.', { exact: false })).toBeVisible();
  await page.getByLabel('Filter runs by project').selectOption({ label: 'Lysozyme VHH 2' });
  await expect(page.getByTestId('demo-run')).toHaveCount(0);
  await page.getByRole('button', { name: 'Clear filters' }).click();
  await page.getByLabel('Filter runs by status').selectOption('running');
  await expect(page.getByRole('heading', { name: 'No runs match these filters' })).toBeVisible();
  await page.getByRole('button', { name: 'Clear filters' }).click();
  await noOverflow(page);
  await page.screenshot({ path: `docs/screenshots/compute-queue-${info.project.name}.png` });
  await page.reload();
  await expect(page.getByTestId('demo-run')).toHaveCount(2);
  await page.getByRole('button', { name: 'Open scale project Lysozyme VHH', exact: true }).click();
  await expect(page.getByLabel('Current project')).toHaveValue('demo-1');
  await expect(page.getByRole('button', { name: 'Review candidates' })).toBeVisible();
  await page.getByRole('button', { name: 'Collapse project sidebar' }).click();
  await page.setViewportSize({ width: 642, height: 948 });
  await nav(page, 'Compute & Queue');
  await noOverflow(page);
  await page.screenshot({ path: `docs/screenshots/compute-queue-narrow-${info.project.name}.png` });
  await page.getByRole('button', { name: 'Open pilot project Lysozyme VHH', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Review candidates' })).toBeVisible();
});
