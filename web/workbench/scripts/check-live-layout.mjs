import { chromium, expect as baseExpect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
const expect = baseExpect.configure({ timeout: 60000 });
const base = process.env.PRODUCT_URL || 'http://127.0.0.1:14381';
const project = process.env.PRODUCT_PROJECT_ID;
const out = process.env.PRODUCT_RESULTS;
const token = (await fs.readFile(process.env.PRODUCT_TOKEN_FILE, 'utf8')).trim();
const browser = await chromium.launch({
  headless: true,
  args: [
    '--enable-webgl',
    '--use-gl=angle',
    '--use-angle=swiftshader',
    '--enable-unsafe-swiftshader',
  ],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.setDefaultTimeout(60000);
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
const view = async () =>
  (
    await page.request.get(`${base}/api/v1/projects/${project}/workbench`, { timeout: 120000 })
  ).json();
await fs.mkdir(out, { recursive: true });
let originalTitle;
try {
  await page.request.post(base + '/api/v1/session', { data: { token } });
  const before = await view();
  originalTitle = before.project.title;
  expect(before.project.validation_only).toBe(true);
  const rename = await page.request.post(`${base}/api/v1/projects/${project}/title`, {
    headers: { Origin: base },
    data: { title: 'SYNTHETIC UI review' },
  });
  expect(rename.status()).toBe(200);
  await page.goto(base + '/#projects');
  await page.getByLabel('Search projects', { exact: true }).fill('SYNTHETIC UI review');
  await page
    .getByRole('button', { name: 'Rename project SYNTHETIC UI review', exact: true })
    .click();
  await page.getByLabel('Project name', { exact: true }).fill('SYNTHETIC UI review — Site B');
  await page.getByRole('button', { name: 'Save name', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'SYNTHETIC UI review — Site B', exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByLabel('Search projects', { exact: true }).fill('SYNTHETIC UI review — Site B');
  await expect(
    page.getByRole('heading', { name: 'SYNTHETIC UI review — Site B', exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: path.join(out, 'projects.png'), fullPage: true });
  await page.getByRole('button', { name: 'New project', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Start a new design', exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel('Your research goal', { exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(out, 'new-project.png'), fullPage: true });
  await page.goto(`${base}/?project=${project}#workspace`);
  await expect(page.getByRole('heading', { name: 'Design Scientist', exact: true })).toBeVisible();
  await expect(page.getByLabel('Current project', { exact: true })).toHaveValue(project);
  await expect(
    page.getByLabel('Current project', { exact: true }).locator('option:checked'),
  ).toHaveText('SYNTHETIC UI review — Site B');
  for (const phase of ['target', 'site', 'design', 'pilot', 'scale', 'candidates']) {
    await page.getByTestId('phase-' + phase).click();
    await expect(page.locator('#scientific-context')).toHaveClass(new RegExp('phase-' + phase));
    if (['target', 'site', 'pilot', 'candidates'].includes(phase))
      await page.locator('.live-molecule[data-status="ready"]').waitFor();
    await page.screenshot({ path: path.join(out, 'phase-' + phase + '.png'), fullPage: true });
  }
  const after = await view();
  expect(after.revision).toBe(before.revision);
  expect(after.event_cursor).toBe(before.event_cursor);
  expect(after.candidates).toEqual(before.candidates);
  expect(errors).toEqual([]);
  const result = {
    project,
    renamePersisted: true,
    originalLayoutPages: [
      'projects',
      'new-project',
      'target',
      'site',
      'design',
      'pilot',
      'scale',
      'candidates',
    ],
    scientificStateUnchanged: true,
    pageErrors: errors,
  };
  await fs.writeFile(path.join(out, 'layout-browser.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
} catch (error) {
  await page.screenshot({ path: path.join(out, 'failure.png'), fullPage: true });
  console.error(String(error).replaceAll(token, '[redacted]'));
  process.exitCode = 1;
} finally {
  if (originalTitle)
    await page.request.post(`${base}/api/v1/projects/${project}/title`, {
      headers: { Origin: base },
      data: { title: originalTitle.slice(0, 80) },
    });
  await browser.close();
}
