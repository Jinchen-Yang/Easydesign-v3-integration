import { expect, test, type Page } from '@playwright/test';
const demoOrigin = `http://127.0.0.1:${process.env.WORKBENCH_E2E_PORT || 13180}`;

async function finishPanel(page: Page) {
  await page.goto('/?mode=demo#workspace');
  await page.getByRole('button', { name: 'Start design', exact: true }).click();
  for (const label of [
    'Approve target',
    'Approve Site B',
    'Approve design',
    'Promote 6 candidates',
    'Review candidates',
  ]) {
    const skip = page.getByRole('button', { name: 'Skip animation', exact: true });
    if (await skip.isVisible()) await skip.click();
    await expect(page.getByTestId('phase-lab-order')).toBeDisabled();
    await page.getByRole('button', { name: label, exact: true }).click();
  }
  await expect(page.getByRole('button', { name: 'Finalize panel', exact: true })).toBeVisible();
}
const step = (page: Page, name: string) =>
  page
    .getByRole('navigation', { name: 'Request preparation', exact: true })
    .getByRole('button', { name, exact: true });
async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await page.locator('.lab-order').evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(
    true,
  );
}

test('lab order follows finalized candidates, persists a real draft and previews without sending', async ({
  page,
}, info) => {
  const errors: string[] = [];
  const external: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('request', (request) => {
    if (!request.url().startsWith(demoOrigin) && !request.url().startsWith('data:'))
      external.push(request.url());
  });
  await finishPanel(page);
  await page.getByRole('button', { name: 'Star ED-003', exact: true }).click();
  await page.getByRole('button', { name: 'Finalize panel', exact: true }).click();
  await page.getByRole('button', { name: 'Prepare Lab Order', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Choose samples to send' })).toBeVisible();
  await expect(page.getByTestId('lab-sample-count')).toHaveText('1 selected');
  await page.getByLabel('Send ED-003', { exact: true }).uncheck();
  await expect(
    page.getByRole('button', { name: 'Define requirements', exact: true }),
  ).toBeDisabled();
  await page.getByLabel('Send ED-001', { exact: true }).check();
  await page.getByLabel('Send ED-003', { exact: true }).check();
  await noOverflow(page);
  await page.screenshot({ path: `docs/screenshots/lab-samples-${info.project.name}.png` });
  await page.getByRole('button', { name: 'Define requirements', exact: true }).click();
  await expect(
    page
      .getByRole('navigation', { name: 'Lab order steps' })
      .getByRole('button', { name: /Specs/ }),
  ).toHaveAttribute('aria-current', 'step');
  await expect(page.getByRole('button', { name: 'Review request', exact: true })).toBeDisabled();
  await page.getByLabel('Construct format', { exact: true }).selectOption('VHH');
  await page.getByLabel('Amount per sample', { exact: true }).fill('2 mg');
  await page.getByLabel('Delivery & billing profile', { exact: true }).selectOption('demo-lab');
  await page.getByText('Quality & delivery details', { exact: true }).click();
  await page
    .getByLabel('Additional requirements', { exact: true })
    .fill('Three aliquots per sample.');
  await page.getByLabel('Endotoxin requirement', { exact: true }).fill('Please quote separately.');
  await page.getByRole('button', { name: 'Save Draft', exact: true }).click();
  await page.reload();
  await expect(page.getByLabel('Amount per sample', { exact: true })).toHaveValue('2 mg');
  await page.getByText('Quality & delivery details', { exact: true }).click();
  await expect(page.getByLabel('Additional requirements', { exact: true })).toHaveValue(
    'Three aliquots per sample.',
  );
  await page.screenshot({ path: `docs/screenshots/lab-requirements-${info.project.name}.png` });
  await page.getByRole('button', { name: 'Review request', exact: true }).click();
  await expect(page.getByText('Three aliquots per sample.', { exact: true })).toBeVisible();
  await page.getByLabel('I have reviewed the selected samples', { exact: false }).check();
  await page.screenshot({ path: `docs/screenshots/lab-review-${info.project.name}.png` });
  await page.getByRole('button', { name: 'Preview confirmation', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Send a quote request?' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Request Quote', exact: true })).toBeDisabled();
  await expect(page.getByRole('dialog')).toContainText('No order submitted');
  await page.keyboard.press('Escape');
  await expect(
    page.getByRole('button', { name: 'Preview confirmation', exact: true }),
  ).toBeFocused();
  await page.getByRole('button', { name: 'Edit requirements', exact: true }).click();
  await page.getByLabel('Buffer', { exact: true }).fill('PBS');
  await step(page, '3 Review').click();
  await expect(
    page.getByLabel('I have reviewed the selected samples', { exact: false }),
  ).not.toBeChecked();
  await expect(
    page.getByRole('button', { name: 'Preview confirmation', exact: true }),
  ).toBeDisabled();
  await page.getByTestId('phase-candidates').click();
  await expect(page.getByRole('region', { name: 'Demo completed', exact: true })).toBeVisible();
  await page
    .getByRole('navigation', { name: 'Main navigation' })
    .getByRole('button', { name: 'Projects', exact: true })
    .click();
  await page.getByRole('button', { name: 'New project', exact: true }).click();
  await page.getByLabel('Your research goal').fill('An independent lab project');
  await page.getByRole('button', { name: 'Start design', exact: true }).click();
  await expect(page.getByTestId('phase-lab-order')).toBeDisabled();
  await page.getByLabel('Current project').selectOption('demo-1');
  await expect(page.getByRole('heading', { name: 'Review your lab request' })).toBeVisible();
  await expect(page.getByTestId('lab-sample-count')).toHaveText('2 selected');
  await expect(page.getByText('PBS', { exact: true })).toBeVisible();
  await noOverflow(page);
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test('lab order works in a narrow workspace with a synchronized workflow drawer', async ({
  page,
}, info) => {
  await finishPanel(page);
  await page.getByRole('button', { name: 'Finalize panel', exact: true }).click();
  await page.getByRole('button', { name: 'Prepare Lab Order', exact: true }).click();
  await page.getByRole('button', { name: 'Collapse project sidebar', exact: true }).click();
  await page.setViewportSize({ width: 642, height: 948 });
  await noOverflow(page);
  await page.getByRole('button', { name: 'Toggle workflow', exact: true }).click();
  await page
    .getByRole('navigation', { name: 'Lab order steps' })
    .getByRole('button', { name: /Specs/ })
    .click();
  await expect(step(page, '2 Requirements')).toHaveAttribute('aria-current', 'step');
  await expect(page.getByRole('heading', { name: 'Expression requirements' })).toBeVisible();
  await noOverflow(page);
  await page.screenshot({ path: `docs/screenshots/lab-narrow-${info.project.name}.png` });
  await page.setViewportSize({ width: 480, height: 850 });
  await noOverflow(page);
  await step(page, '1 Samples').click();
  await expect(page.getByLabel('Send ED-001', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Define requirements', exact: true }).click();
  await expect(page.getByLabel('Construct format')).toBeVisible();
});
