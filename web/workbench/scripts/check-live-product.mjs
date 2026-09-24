import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
const base = process.env.PRODUCT_URL || 'http://127.0.0.1:14380';
const out = process.env.PRODUCT_RESULTS;
const access = (await fs.readFile(process.env.PRODUCT_TOKEN_FILE, 'utf8')).trim();
const browser = await chromium.launch({
  headless: true,
  args: [
    '--enable-webgl',
    '--use-gl=angle',
    '--use-angle=swiftshader',
    '--enable-unsafe-swiftshader',
  ],
});
const page = await browser.newPage({ viewport: { width: 1728, height: 1117 } });
page.on('response', (r) => {
  if (r.status() >= 400) console.log('HTTP', r.status(), new URL(r.url()).pathname);
});
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
await page.goto(base + '/#access=' + access);
await page.getByRole('heading', { name: 'Projects', exact: true }).waitFor({ timeout: 120000 });
await page
  .getByRole('button', { name: /phase34-nk2r-ranking-20260917-01/ })
  .first()
  .click({ timeout: 120000 });
await page
  .getByText('Validation only · not authorized for experiment', { exact: true })
  .waitFor({ timeout: 120000 });
await page.locator('.live-candidate-select').first().waitFor({ timeout: 120000 });
await page.locator('.live-molecule[data-status="ready"]').waitFor({ timeout: 120000 });
const first = await page.locator('.live-molecule').getAttribute('data-artifact');
const firstCandidate = await page.locator('.live-molecule').getAttribute('data-candidate');
await fs.mkdir(out, { recursive: true });
await page.screenshot({ path: path.join(out, 'live-nk2r-final-panel.png'), fullPage: true });
await page.locator('.live-candidate-select').nth(1).click();
await page.waitForFunction(
  (old) => document.querySelector('.live-molecule')?.getAttribute('data-artifact') !== old,
  first,
);
await page.locator('.live-molecule[data-status="ready"]').waitFor({ timeout: 120000 });
const second = await page.locator('.live-molecule').getAttribute('data-artifact');
const secondCandidate = await page.locator('.live-molecule').getAttribute('data-candidate');
await page.reload();
await page
  .getByText('Validation only · not authorized for experiment', { exact: true })
  .waitFor({ timeout: 120000 });
await page.getByRole('button', { name: 'Compute & queue', exact: true }).click();
await page.getByRole('heading', { name: 'Compute & queue', exact: true }).waitFor();
await page.screenshot({ path: path.join(out, 'live-nk2r-compute.png'), fullPage: true });
const result = {
  project: 'phase34-nk2r-ranking-20260917-01',
  validationLabel: true,
  first,
  second,
  firstCandidate,
  secondCandidate,
  realStructureChanges: first !== second && firstCandidate !== secondCandidate,
  reload: true,
  pageErrors: errors,
};
await fs.writeFile(path.join(out, 'live-readonly-browser.json'), JSON.stringify(result, null, 2));
console.log(JSON.stringify(result));
await browser.close();
if (errors.length || !result.realStructureChanges) process.exitCode = 1;
