import { expect, test, type Page, type TestInfo } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
const shots = 'docs/screenshots';
async function shot(page: Page, info: TestInfo, name: string) {
  await mkdir(shots, { recursive: true });
  await page.screenshot({ path: `${shots}/${name}-${info.project.name}.png` });
}
async function skip(page: Page) {
  // Animation may finish naturally before a browser action reaches the button.
  // Either path must reach an actual approval gate, not merely hide the button.
  await expect(async () => {
    const button = page.getByRole('button', { name: 'Skip animation', exact: true });
    if (await button.isVisible()) await button.click({ timeout: 1000 });
    await expect(page.getByRole('region', { name: 'Decision', exact: true })).toBeVisible({
      timeout: 1000,
    });
  }).toPass({ intervals: [100, 250, 500], timeout: 12000 });
}
async function approve(page: Page, name: string) {
  await page.getByRole('button', { name, exact: true }).click();
  await skip(page);
}
async function start(page: Page) {
  await page.goto('/#workspace');
  await page.getByRole('button', { name: 'Start design', exact: true }).click();
  await skip(page);
  await expect(page.getByRole('button', { name: 'Approve target', exact: true })).toBeVisible();
}
async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
}

test('entire product journey, structure interactions, explicit approvals, completion and replay', async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  const outbound: string[] = [];
  page.on('request', (r) => {
    if (!r.url().startsWith('http://127.0.0.1:13180') && !r.url().startsWith('data:'))
      outbound.push(r.url());
  });
  await page.goto('/#workspace');
  await expect(page.getByRole('heading', { name: 'What would you like to design?' })).toBeVisible();
  await noOverflow(page);
  await shot(page, info, 'landing');
  // The transition is client-side: this marker survives throughout the same document.
  await page.evaluate(() => document.body.setAttribute('data-no-reload', 'yes'));
  await page.getByRole('button', { name: 'Start design', exact: true }).click();
  await skip(page);
  await expect(page.getByRole('button', { name: 'Approve target', exact: true })).toBeVisible();
  await expect(page.locator('body')).toHaveAttribute('data-no-reload', 'yes');
  for (const phase of ['goal', 'target', 'site', 'design', 'pilot', 'scale', 'candidates'])
    await expect(page.getByTestId(`phase-${phase}`)).toBeVisible();
  await expect(page.getByRole('region', { name: 'Molecular structure' })).toHaveAttribute(
    'data-status',
    'ready',
  );
  await page.getByLabel('Structure chains').selectOption('binder');
  await expect(page.getByRole('region', { name: 'Molecular structure' })).toHaveAttribute(
    'data-chain-mode',
    'binder',
  );
  await page.getByLabel('Structure chains').selectOption('target');
  await approve(page, 'Approve target');
  const sites = page.getByRole('group', { name: 'Candidate sites' });
  for (const id of ['A', 'C', 'B']) {
    await sites.getByRole('button', { name: `Site ${id}` }).click();
    await expect(page.getByRole('region', { name: 'Molecular structure' })).toHaveAttribute(
      'data-selection',
      `Site ${id}`,
    );
  }
  await page.getByRole('button', { name: 'Compare', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Compare all three sites' })).toBeVisible();
  await page.getByRole('button', { name: 'Compare', exact: true }).click();
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Save changes' }).click();
  await page.locator('.tool-toggle').first().click();
  await expect(page.locator('.tool-detail').first()).toBeVisible();
  await page.locator('.tool-toggle').first().click();
  await noOverflow(page);
  await shot(page, info, 'site');
  await approve(page, 'Approve Site B');
  await expect(page.getByText('4 + 4', { exact: false })).toBeVisible();
  await approve(page, 'Approve design');
  await expect(page.getByTestId('pilot-candidate')).toHaveCount(8);
  await page.getByTestId('pilot-candidate').nth(2).click();
  await expect(page.getByRole('region', { name: 'Molecular structure' })).toHaveAttribute(
    'data-selection',
    'P-03',
  );
  await expect(page.getByRole('region', { name: 'Molecular structure' })).toHaveAttribute(
    'data-status',
    'ready',
  );
  await noOverflow(page);
  await shot(page, info, 'pilot');
  await approve(page, 'Promote 6 candidates');
  await expect(page.getByRole('progressbar', { name: 'Scale progress' })).toHaveAttribute(
    'aria-valuenow',
    '24',
  );
  await expect(page.locator('.scale-dots>span')).toHaveCount(24);
  await approve(page, 'Review candidates');
  await expect(page.getByTestId('finalist-card')).toHaveCount(6);
  await page.getByRole('button', { name: 'Select ED-003', exact: true }).click();
  await page.getByRole('button', { name: 'Star ED-003', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Star ED-003', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.getByRole('region', { name: 'Molecular structure' })).toHaveAttribute(
    'data-selection',
    'ED-003',
  );
  await page.getByRole('button', { name: 'Next candidate' }).click();
  await expect(page.getByRole('region', { name: 'Molecular structure' })).toHaveAttribute(
    'data-selection',
    'ED-004',
  );
  await expect(page.getByRole('region', { name: 'Molecular structure' })).toHaveAttribute(
    'data-status',
    'ready',
  );
  await page.getByRole('button', { name: 'Finalize panel', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Demo completed' })).toBeVisible();
  await noOverflow(page);
  await shot(page, info, 'candidates');
  await page.reload();
  await expect(page.getByRole('region', { name: 'Demo completed' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Star ED-003', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await page.getByTestId('phase-site').click();
  await expect(sites).toBeVisible();
  await page.getByTestId('phase-candidates').click();
  await page.getByRole('button', { name: 'Replay demo', exact: true }).first().click();
  await skip(page);
  await expect(page.getByRole('button', { name: 'Approve target', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'What would you like to design?' })).toBeVisible();
  expect(errors).toEqual([]);
  expect(outbound).toEqual([]);
});

test('refresh mid-animation, follow-up goal preservation and corrupted storage recovery', async ({
  page,
}) => {
  await page.goto('/#workspace');
  await page.getByLabel('Your research goal').fill('My immutable lysozyme VHH research goal');
  await page.getByRole('button', { name: 'Start design', exact: true }).click();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Approve target', exact: true })).toBeVisible();
  await page
    .getByLabel('Message Design Scientist')
    .fill('Please compare cautiously and keep the original goal.');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  const saved = await page.evaluate(() => {
    const w = JSON.parse(localStorage.getItem('easydesign-workbench-projects-v1')!);
    return w.projects.find((p: { id: string }) => p.id === w.activeProjectId).state;
  });
  expect(saved.goal).toBe('My immutable lysozyme VHH research goal');
  expect(saved.phase).toBe('target');
  await page.evaluate(() => localStorage.setItem('easydesign-workbench-projects-v1', 'corrupt'));
  await page.reload();
  await expect(page.getByRole('heading', { name: 'What would you like to design?' })).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('fresh workspace');
});

test('viewer failure cannot block completion', async ({ page }) => {
  await page.route('**/structures/1MEL.pdb', (r) => r.abort());
  await page.route('https://files.rcsb.org/**', (r) => r.abort());
  await start(page);
  await expect(page.getByText('Structure preview unavailable')).toBeVisible();
  for (const label of [
    'Approve target',
    'Approve Site B',
    'Approve design',
    'Promote 6 candidates',
    'Review candidates',
  ])
    await approve(page, label);
  await expect(page.getByTestId('finalist-card')).toHaveCount(6);
  await page.getByRole('button', { name: 'Finalize panel', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Demo completed' })).toBeVisible();
});

test('keyboard dialog focus, linked context and reversible design revision', async ({ page }) => {
  await page.goto('/#workspace');
  const help = page.getByRole('button', { name: 'About this demo', exact: true });
  await help.focus();
  await page.keyboard.press('Enter');
  const close = page.getByRole('button', { name: 'Close dialog', exact: true });
  await expect(close).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(
    page.getByRole('button', { name: 'Explore the workbench', exact: true }),
  ).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(close).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(help).toBeFocused();
  expect(await help.evaluate((el) => getComputedStyle(el).outlineStyle)).toBe('solid');
  await page.getByRole('button', { name: 'Start design', exact: true }).click();
  await skip(page);
  await approve(page, 'Approve target');
  await page.getByRole('button', { name: 'Explore site context', exact: true }).click();
  await expect(page.getByRole('group', { name: 'Candidate sites' })).toBeVisible();
  await approve(page, 'Approve Site B');
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByLabel('Scaffold label').fill('Reviewer VHH scaffold');
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(page.getByText('Reviewer VHH scaffold', { exact: true })).toBeVisible();
  await approve(page, 'Approve design');
  await page.getByRole('button', { name: 'Revise', exact: true }).click();
  await skip(page);
  await expect(page.getByRole('button', { name: 'Approve design', exact: true })).toBeVisible();
  await expect(page.getByText('Reviewer VHH scaffold', { exact: true })).toBeVisible();
  await approve(page, 'Approve design');
  await expect(page.getByTestId('pilot-candidate')).toHaveCount(8);
});
