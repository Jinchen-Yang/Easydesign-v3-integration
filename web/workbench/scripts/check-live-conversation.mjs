import { chromium, expect as baseExpect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
const expect = baseExpect.configure({ timeout: 120000 });
const base = process.env.PRODUCT_URL || 'http://127.0.0.1:14382';
const out = process.env.PRODUCT_RESULTS;
const project = 'phase34-nk2r-ranking-20260917-01';
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
page.setDefaultTimeout(180000);
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
await fs.mkdir(out, { recursive: true });
const view = async () =>
  (
    await page.request.get(`${base}/api/v1/projects/${project}/workbench`, { timeout: 120000 })
  ).json();
try {
  await page.request.post(base + '/api/v1/session', { data: { token } });
  await page.goto(`${base}/?project=${project}#workspace`);
  const composer = page.getByLabel('Message Design Scientist', { exact: true });
  await expect(composer).toBeEnabled({ timeout: 120000 });
  await page.locator('.live-molecule[data-status="ready"]').waitFor();
  const before = await view();
  const question =
    '请基于这个 NK2R 项目已经保存的结果，简要解释目前候选的 PASS/FAIL 情况、最终 panel 和 validation-only 的含义。仅回答问题，不启动任务、不修改审批。';
  let requestId = process.env.PRODUCT_EXISTING_REQUEST;
  if (!process.env.PRODUCT_READ_ONLY) {
    const submission = page.waitForResponse(
      (r) => r.url().endsWith('/actions') && r.request().method() === 'POST',
    );
    await composer.fill(question);
    await composer.press('Enter');
    const reply = await submission;
    expect(reply.status()).toBe(202);
    requestId = (await reply.json()).id;
    await expect
      .poll(
        async () => {
          const r = (await page.request.get(base + '/api/v1/requests/' + requestId)).json();
          return (await r).state;
        },
        { timeout: 240000, intervals: [1500, 3000] },
      )
      .toBe('succeeded');
  }
  const after = await view();
  expect(after.revision).toBe(before.revision);
  expect(after.event_cursor).toBe(before.event_cursor);
  expect(after.candidates).toEqual(before.candidates);
  await page.reload();
  await expect(page.locator('.scientist-message').last()).toBeVisible();
  if (requestId) await expect(page.getByText(question, { exact: true })).toBeVisible();
  await page.locator('.live-molecule[data-status="ready"]').waitFor();
  await expect(page.locator('.candidate-metrics')).toContainText('RMSD');
  await expect(page.locator('.candidate-metrics')).not.toContainText('ala fraction');
  await expect(page.locator('.answer-text h3').first()).toBeVisible();
  await page
    .locator('.user-message')
    .last()
    .evaluate((e) => e.scrollIntoView({ block: 'start' }));
  await page.screenshot({ path: path.join(out, 'nk2r-conversation.png'), fullPage: true });
  await page.setViewportSize({ width: 642, height: 900 });
  if (await page.getByRole('button', { name: 'Close project sidebar', exact: true }).isVisible())
    await page.getByRole('button', { name: 'Close project sidebar', exact: true }).click();
  await expect(composer).toBeVisible();
  await page.getByRole('button', { name: 'Open scientific context', exact: true }).click();
  await expect(page.locator('#scientific-context')).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Close scientific context', exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: path.join(out, 'nk2r-context-narrow.png'), fullPage: true });
  await page.getByRole('button', { name: 'Close scientific context', exact: true }).click();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
  expect(overflow).toBe(false);
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.getByRole('button', { name: 'Compute & Queue', exact: true }).click();
  await page.getByRole('heading', { name: 'Compute & Queue', exact: true }).waitFor();
  await page.screenshot({ path: path.join(out, 'nk2r-compute.png'), fullPage: true });
  const receipt = requestId
    ? (await page.request.get(base + '/api/v1/requests/' + requestId)).json()
    : null;
  const result = {
    project,
    request: await receipt,
    revisionUnchanged: true,
    eventCursorUnchanged: true,
    candidatesUnchanged: true,
    reload: true,
    pageErrors: errors,
  };
  expect(errors).toEqual([]);
  await fs.writeFile(path.join(out, 'live-conversation.json'), JSON.stringify(result, null, 2));
  console.log(
    JSON.stringify({ project, requestId, realModelQuestion: !!requestId, unchanged: true, errors }),
  );
} catch (error) {
  await page.screenshot({ path: path.join(out, 'conversation-failure.png'), fullPage: true });
  console.error(String(error).replaceAll(token, '[redacted]'));
  process.exitCode = 1;
} finally {
  await browser.close();
}
