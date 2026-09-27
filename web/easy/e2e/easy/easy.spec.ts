import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    if (!localStorage.getItem('easydesign-easy-locale-v1'))
      localStorage.setItem('easydesign-easy-locale-v1', 'en');
  });
});

test('single-click journey, pause/reload, reference viewer, candidates, download and history', async ({
  page,
}, info) => {
  const errors: string[] = [];
  const requests: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => requests.push(request.url()));
  await page.goto('/easy/?mode=demo');
  await expect(page.getByRole('heading', { name: 'Start a design' })).toBeVisible();
  await page.screenshot({ path: `docs/easy/landing-${info.project.name}.png`, fullPage: true });
  await expect(page.getByRole('button', { name: 'Start design', exact: true })).toBeDisabled();
  await expect(page.getByLabel('Input type').locator('option')).toHaveCount(8);
  await page.getByRole('button', { name: 'Try lysozyme · VHH', exact: true }).click();
  await page.getByRole('button', { name: 'Start design', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Design progress' })).toBeVisible();
  await page.getByRole('button', { name: 'Pause preview' }).click();
  await expect(page.getByRole('heading', { name: 'Paused' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Candidates', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Target', exact: true })).toBeEnabled();
  await expect(page.locator('.molecule[data-status="ready"]')).toBeVisible();
  await page.screenshot({ path: `docs/easy/running-${info.project.name}.png`, fullPage: true });
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Paused' })).toBeVisible();
  await page.getByRole('button', { name: 'Resume', exact: true }).click();
  await expect(page.getByRole('heading', { name: '6 finalists' })).toBeVisible({
    timeout: 20000,
  });
  await expect(
    page.getByRole('group', { name: 'Example finalists' }).getByRole('button'),
  ).toHaveCount(6);
  await page.getByRole('button', { name: /2 ED-002/ }).click();
  await expect(page.locator('.molecule')).toHaveAttribute('data-selection', 'ED-002');
  await page.getByLabel('Structure chains').selectOption('binder');
  await expect(page.locator('.molecule')).toHaveAttribute('data-chain-mode', 'binder');
  await page.getByLabel('Structure chains').selectOption('complex');
  const downloading = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download results' }).click();
  const file = await downloading;
  const content = JSON.parse(await readFile((await file.path())!, 'utf8'));
  expect(content.mode).toBe('demo');
  expect(content.pilot).toBe(8);
  expect(content.scale).toBe(24);
  expect(content.finalists).toHaveLength(6);
  await page.screenshot({ path: `docs/easy/results-${info.project.name}.png`, fullPage: true });
  const savedRun = await page.evaluate(() => localStorage.getItem('easydesign-easy-preview-v1'));
  for (const [stage, heading] of [
    ['Target', 'Reference target'],
    ['Site', 'Site B'],
    ['Design', 'VHH'],
    ['Pilot', 'Pilot results'],
    ['Scale', 'Scale results'],
  ]) {
    const button = page.getByRole('button', { name: stage, exact: true });
    await button.click();
    await expect(button).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
    await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '6');
    await expect(page.locator('.easy-run-actions')).toContainText('Completed');
    if (stage === 'Target')
      await expect(page.locator('.molecule')).toHaveAttribute('data-chain-mode', 'target');
    if (stage === 'Site') {
      await expect(page.locator('.molecule')).toHaveAttribute('data-selection', 'Site B');
      await page.screenshot({
        path: `docs/easy/review-site-${info.project.name}.png`,
        fullPage: true,
      });
    }
    if (stage === 'Pilot') {
      await expect(
        page.getByRole('table', { name: 'Pilot candidates' }).locator('tbody tr'),
      ).toHaveCount(8);
      await expect(page.locator('.molecule')).toHaveAttribute('data-chain-mode', 'complex');
    }
  }
  await page.getByRole('button', { name: 'Candidates', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('group', { name: 'Example finalists' }).getByRole('button'),
  ).toHaveCount(6);
  expect(await page.evaluate(() => localStorage.getItem('easydesign-easy-preview-v1'))).toBe(
    savedRun,
  );

  await page.reload();
  await expect(
    page.getByRole('group', { name: 'Example finalists' }).getByRole('button'),
  ).toHaveCount(6);
  await page.getByRole('button', { name: 'New design', exact: true }).click();
  await page.getByLabel('Input type').selectOption('pdb-id');
  await page.getByLabel('PDB ID', { exact: true }).fill('1MEL');
  await page.getByRole('button', { name: 'Save draft' }).click();
  await expect(page.getByRole('status')).toContainText('Draft saved');
  await page.reload();
  await expect(page.getByLabel('PDB ID', { exact: true })).toHaveValue('1MEL');
  await page.getByLabel('Search designs').fill('1MEL');
  await expect(page.locator('.easy-history tbody tr')).toHaveCount(1);
  await page.getByLabel('Search designs').fill('');
  await expect(page.locator('.easy-history tbody tr')).toHaveCount(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(requests.filter((url) => url.includes('/api/'))).toEqual([]);
  expect(errors).toEqual([]);
});

test('all input controls, file checks and type-switch isolation', async ({ page }, info) => {
  await page.goto('/easy/?mode=demo');
  const type = page.getByLabel('Input type');
  const start = page.getByRole('button', { name: 'Start design', exact: true });
  await type.selectOption('protein-name');
  await page.getByLabel('Protein / Gene name', { exact: true }).fill('LYZ');
  await expect(start).toBeDisabled();
  await page.getByLabel('Organism', { exact: true }).fill('Gallus gallus');
  await expect(start).toBeEnabled();
  await type.selectOption('uniprot');
  await page.getByLabel('UniProt ID', { exact: true }).fill('bad');
  await expect(start).toBeDisabled();
  await page.getByLabel('UniProt ID', { exact: true }).fill('P00698');
  await expect(start).toBeEnabled();
  await type.selectOption('sequence');
  await page.getByLabel('Upload Sequence / FASTA').setInputFiles({
    name: 'test.fa',
    mimeType: 'text/plain',
    buffer: Buffer.from('>test\nACDEFGHIKLMNPQRSTVWY'),
  });
  await expect(page.getByLabel('Sequence / FASTA', { exact: true })).toHaveValue(
    'ACDEFGHIKLMNPQRSTVWY',
  );
  await expect(start).toBeEnabled();
  await page.getByLabel('Sequence / FASTA', { exact: true }).fill('>a\nACDE\n>b\nACDE');
  await expect(start).toBeDisabled();
  await type.selectOption('structure');
  await page
    .getByLabel('Upload Structure file')
    .setInputFiles({ name: 'bad.pdb', mimeType: 'text/plain', buffer: Buffer.from('bad') });
  await expect(page.getByRole('alert')).toContainText('coordinate');
  await expect(start).toBeDisabled();
  await page.getByLabel('Upload Structure file').setInputFiles('public/structures/1MEL.pdb');
  await expect(start).toBeEnabled();
  await page.screenshot({
    path: `docs/easy/structure-input-${info.project.name}.png`,
    fullPage: true,
  });
  await type.selectOption('pse');
  await expect(start).toBeDisabled();
  await page.getByLabel('Upload PyMOL session').setInputFiles({
    name: 'example.pse',
    mimeType: 'application/octet-stream',
    buffer: Buffer.from('opaque'),
  });
  await expect(start).toBeEnabled();
  await expect(page.getByText('File selection only', { exact: false })).toBeVisible();
  await type.selectOption('bundle');
  await page.getByLabel('Upload Existing target').setInputFiles({
    name: 'target.json',
    mimeType: 'application/json',
    buffer: Buffer.from('{"target_id":"demo"}'),
  });
  await expect(start).toBeEnabled();
  await type.selectOption('description');
  await expect(page.getByLabel('Description', { exact: true })).toHaveValue('');
  await expect(start).toBeDisabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('viewer failure does not block completion; guide has keyboard dismissal', async ({ page }) => {
  await page.route('**/structures/1MEL.pdb', (route) => route.abort());
  await page.route('**/files.rcsb.org/**', (route) => route.abort());
  await page.goto('/easy/?mode=demo');
  await page.getByRole('button', { name: 'Quick guide' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await page.getByRole('button', { name: 'Try lysozyme · VHH', exact: true }).click();
  await page.getByRole('button', { name: 'Start design', exact: true }).click();
  await expect(page.getByText('Structure preview unavailable')).toBeVisible();
  await expect(page.getByRole('heading', { name: '6 finalists' })).toBeVisible({
    timeout: 20000,
  });
  await expect(page.getByRole('button', { name: 'Download results' })).toBeEnabled();
});
