import { expect, test } from '@playwright/test';

test('live metrics, refresh failure, stale data and recovery remain separate from demo runs', async ({
  page,
}, info) => {
  let fail = false;
  await page.route('**/api/compute/resources', (route) =>
    fail
      ? route.abort()
      : route.fulfill({
          json: {
            connection: 'connected',
            node: 'Suzhou2',
            sample: {
              sampledAt: new Date().toISOString(),
              gpus: Array.from({ length: 8 }, (_, index) => ({
                index,
                name: 'NVIDIA A100-PCIE-40GB',
                utilization: 97,
                memoryTotalMiB: 40960,
                memoryUsedMiB: 11264,
                temperatureC: 60,
                powerW: 230.5,
                powerLimitW: 250,
                processCount: 1,
                driverVersion: '580.173.02',
              })),
            },
          },
        }),
  );
  await page.goto('/#compute');
  await expect(page.getByRole('heading', { name: 'Suzhou2 compute node' })).toBeVisible();
  await expect(page.locator('.resource-status')).toHaveText('Live');
  await expect(page.locator('.gpu-card')).toHaveCount(8);
  await expect(page.locator('.resource-summary')).toContainText('320.0');
  await expect(page.getByText('Job queue not connected.', { exact: false })).toBeVisible();
  await expect(page.getByTestId('demo-run')).toHaveCount(0);
  await page.screenshot({
    path: `test-results/resources-${info.project.name}.png`,
    fullPage: true,
  });
  fail = true;
  await page.getByRole('button', { name: 'Refresh resources' }).click();
  await expect(page.locator('.resource-status')).toHaveText('Stale data');
  await expect(page.locator('.gpu-card')).toHaveCount(8);
  await expect(page.getByText('Connection delayed.', { exact: false })).toBeVisible();
  fail = false;
  await page.getByRole('button', { name: 'Refresh resources' }).click();
  await expect(page.locator('.resource-status')).toHaveText('Live');
  await page.setViewportSize({ width: 642, height: 948 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({
    path: `test-results/resources-narrow-${info.project.name}.png`,
    fullPage: true,
  });
});

test('unavailable monitoring never fabricates an idle GPU', async ({ page }) => {
  await page.route('**/api/compute/resources', (route) =>
    route.fulfill({
      json: {
        connection: 'unavailable',
        node: 'Suzhou2',
        sample: null,
      },
    }),
  );
  await page.goto('/#compute');
  await expect(page.getByRole('heading', { name: 'Suzhou2 is unavailable' })).toBeVisible();
  await expect(page.locator('.gpu-card')).toHaveCount(0);
  await expect(page.locator('.resource-status')).toHaveText('Not connected');
});

test('missing metrics stay unavailable instead of becoming zero', async ({ page }) => {
  await page.route('**/api/compute/resources', (route) =>
    route.fulfill({
      json: {
        connection: 'connected',
        node: 'Suzhou2',
        sample: {
          sampledAt: new Date().toISOString(),
          gpus: [
            {
              index: 0,
              name: 'NVIDIA A100-PCIE-40GB',
              driverVersion: '',
              utilization: null,
              memoryTotalMiB: 40960,
              memoryUsedMiB: null,
              temperatureC: null,
              powerW: null,
              powerLimitW: null,
              processCount: null,
            },
          ],
        },
      },
    }),
  );
  await page.goto('/#compute');
  await expect(page.locator('.gpu-card')).toHaveCount(1);
  await expect(page.locator('.gpu-load-label')).toHaveText('Unknown');
  await expect(page.locator('.gpu-card progress')).toHaveCount(0);
  await expect(page.locator('.gpu-utilization strong')).toHaveText('—');
  await expect(page.getByText('Compute processes').locator('..').locator('dd')).toHaveText('—');
});

test('project deletion requires confirmation and preserves other projects across refresh', async ({
  page,
}, info) => {
  await page.goto('/');
  for (const goal of ['Keep this project', 'Delete this test project']) {
    await page.getByRole('button', { name: 'New project', exact: true }).click();
    await page.getByLabel('Your research goal').fill(goal);
    await page.getByRole('button', { name: 'Start design', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Approve target', exact: true })).toBeVisible();
    await page
      .getByRole('navigation')
      .getByRole('button', { name: 'Projects', exact: true })
      .click();
  }
  const trash = page.getByRole('button', { name: 'Delete project Lysozyme VHH 2', exact: true });
  await trash.click();
  await expect(page.getByRole('dialog', { name: 'Delete project?' })).toContainText(
    'Lysozyme VHH 2',
  );
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.getByTestId('design-project')).toHaveCount(2);
  await expect(trash).toBeFocused();
  await trash.click();
  await page.screenshot({ path: `test-results/project-delete-${info.project.name}.png` });
  await page.getByRole('button', { name: 'Delete project', exact: true }).click();
  await expect(page.getByTestId('design-project')).toHaveCount(1);
  await page.reload();
  await expect(page.getByTestId('design-project')).toHaveCount(1);
  await expect(page.getByTestId('design-project')).toContainText('Keep this project');
  await page.getByRole('button', { name: 'Delete project Lysozyme VHH', exact: true }).click();
  await page.getByRole('button', { name: 'Delete project', exact: true }).click();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Give your next idea a home.' })).toBeVisible();
});
