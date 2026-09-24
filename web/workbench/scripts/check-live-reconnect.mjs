import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
const base = process.env.PRODUCT_URL || 'http://127.0.0.1:14380';
const project = process.env.PRODUCT_PROJECT_ID || 'phase34-nk2r-ranking-20260917-01';
const out = process.env.PRODUCT_RESULTS;
const token = (await fs.readFile(process.env.PRODUCT_TOKEN_FILE, 'utf8')).trim();
const browser = await chromium.launch({
  headless: true,
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
try {
  await page.request.post(base + '/api/v1/session', { data: { token } });
  await page.goto(base + '/?project=' + project);
  await expect(page.locator('.live-current h2')).toHaveText(/handoff complete/i, {
    timeout: 120000,
  });
  await expect(page.locator('.live-candidate-select')).toHaveCount(15, { timeout: 120000 });
  const before = await (
    await page.request.get(base + `/api/v1/projects/${project}/workbench`)
  ).json();
  console.log('READY_FOR_API_RESTART');
  await expect(page.getByRole('alert')).toContainText('Reconnecting', { timeout: 120000 });
  console.log('RECONNECTING_VISIBLE');
  await expect(page.getByRole('alert')).toHaveCount(0, { timeout: 120000 });
  await expect(page.locator('.live-current h2')).toHaveText(/handoff complete/i, {
    timeout: 120000,
  });
  const after = await (
    await page.request.get(base + `/api/v1/projects/${project}/workbench`)
  ).json();
  expect(after.revision).toBe(before.revision);
  expect(after.event_cursor).toBe(before.event_cursor);
  expect(after.candidates).toEqual(before.candidates);
  expect(errors).toEqual([]);
  await fs.mkdir(out, { recursive: true });
  const result = {
    project,
    apiRestart: true,
    reconnected: true,
    revisionUnchanged: true,
    eventCursorUnchanged: true,
    candidatesUnchanged: true,
    errors,
  };
  await fs.writeFile(path.join(out, 'live-restart-browser.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
} finally {
  await browser.close();
}
