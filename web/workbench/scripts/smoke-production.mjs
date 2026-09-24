import { spawn } from 'node:child_process';
import { once } from 'node:events';
import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';

const port = Number(process.env.WORKBENCH_PREVIEW_PORT || 13181);
if (!Number.isInteger(port) || port < 1024 || port > 65535)
  throw new Error('WORKBENCH_PREVIEW_PORT must be a non-privileged TCP port');
const url = `http://127.0.0.1:${port}/`;
// Use the installed Vite executable directly so the exact child can be cleaned up.
const server = spawn(
  process.execPath,
  [
    'node_modules/vite/bin/vite.js',
    'preview',
    '--host',
    '127.0.0.1',
    '--port',
    String(port),
    '--strictPort',
  ],
  { stdio: 'pipe', env: { ...process.env, WORKBENCH_COMPUTE_SSH_HOST: '' } },
);
let serverLog = '';
server.stdout.on('data', (chunk) => {
  serverLog += chunk;
});
server.stderr.on('data', (chunk) => {
  serverLog += chunk;
});
let browser;
try {
  for (let tries = 0; tries < 50; tries++) {
    if (server.exitCode !== null) throw new Error(serverLog);
    // Wait until this child owns the preview URL, not another existing process.
    if (serverLog.includes('Local:')) break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.ok(serverLog.includes('Local:'), serverLog || 'Preview server did not become ready');
  const resources = await fetch(`${url}api/compute/resources`).then((r) => r.json());
  assert.equal(resources.connection, 'not-configured');
  assert.equal(resources.sample, null);
  browser = await chromium.launch({
    args: [
      '--enable-webgl',
      '--use-gl=angle',
      '--use-angle=swiftshader',
      '--enable-unsafe-swiftshader',
    ],
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  const external = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('request', (request) => {
    if (!request.url().startsWith(url) && !request.url().startsWith('data:'))
      external.push(request.url());
  });
  await page.goto(`${url}?mode=demo#workspace`);
  await page.getByRole('button', { name: 'Start design', exact: true }).click();
  await page.getByRole('button', { name: 'Skip animation', exact: true }).click();
  await page.locator('[aria-label="Molecular structure"][data-status="ready"]').waitFor();
  for (const label of [
    'Approve target',
    'Approve Site B',
    'Approve design',
    'Promote 6 candidates',
    'Review candidates',
  ]) {
    await page.getByRole('button', { name: label, exact: true }).click();
    await page.getByRole('button', { name: 'Skip animation', exact: true }).click();
    if (label === 'Approve design')
      assert.equal(await page.getByTestId('pilot-candidate').count(), 8);
    if (label === 'Promote 6 candidates')
      assert.equal(await page.locator('.scale-dots>span').count(), 24);
  }
  assert.equal(await page.getByTestId('finalist-card').count(), 6);
  await page.getByRole('button', { name: 'Finalize panel', exact: true }).click();
  await page.getByRole('region', { name: 'Demo completed', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Projects', exact: true }).click();
  await page.getByRole('button', { name: 'New project', exact: true }).click();
  await page.getByLabel('Your research goal').fill('A second independent lysozyme design');
  await page.getByRole('button', { name: 'Start design', exact: true }).click();
  await page.getByRole('button', { name: 'Skip animation', exact: true }).click();
  await page.getByRole('button', { name: 'Projects', exact: true }).click();
  assert.equal(await page.getByTestId('design-project').count(), 2);
  await page.getByRole('button', { name: 'Open project Lysozyme VHH', exact: true }).click();
  await page.getByRole('region', { name: 'Demo completed', exact: true }).waitFor();
  assert.equal(await page.getByTestId('finalist-card').count(), 6);
  assert.equal(await page.locator('.conversation').count(), 1);
  assert.equal(await page.locator('.scientific-context').count(), 1);
  await page.getByRole('button', { name: 'Compute & Queue', exact: true }).click();
  await page.getByRole('heading', { name: 'No compute service connected' }).waitFor();
  assert.equal(await page.getByTestId('demo-run').count(), 2);
  await page.getByRole('button', { name: 'Open scale project Lysozyme VHH', exact: true }).click();
  await page.getByRole('region', { name: 'Demo completed', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Prepare Lab Order', exact: true }).click();
  assert.equal(await page.locator('.lab-sample').count(), 6);
  await page.getByRole('button', { name: 'Define requirements', exact: true }).click();
  await page.getByLabel('Construct format', { exact: true }).selectOption('VHH');
  await page.getByLabel('Amount per sample', { exact: true }).fill('2 mg');
  await page.getByLabel('Delivery & billing profile', { exact: true }).selectOption('demo-lab');
  await page.getByRole('button', { name: 'Review request', exact: true }).click();
  await page.getByLabel('I have reviewed the selected samples', { exact: false }).check();
  await page.getByRole('button', { name: 'Preview confirmation', exact: true }).click();
  assert.ok(await page.getByRole('button', { name: 'Request Quote', exact: true }).isDisabled());
  await page.keyboard.press('Escape');
  await page.reload();
  await page.getByRole('heading', { name: 'Review your lab request' }).waitFor();
  assert.equal(await page.getByTestId('lab-sample-count').textContent(), '6 selected');
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  console.log(
    'PASS: production bundle full 8 → 24 → 6 journey, three destinations, independent second project, restored final panel, demo compute rows and project links, real reference viewer, Lab Order draft/confirmation/reload, no render errors, no external requests.',
  );
} finally {
  await browser?.close();
  if (server.exitCode === null) {
    server.kill('SIGTERM');
    await once(server, 'exit');
  }
}
