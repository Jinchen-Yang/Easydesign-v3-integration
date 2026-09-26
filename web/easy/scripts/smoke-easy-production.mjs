import { spawn } from 'node:child_process';
import { once } from 'node:events';
import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
const url = 'http://127.0.0.1:13191/';
const server = spawn(
  process.execPath,
  [
    'node_modules/vite/bin/vite.js',
    'preview',
    '--host',
    '127.0.0.1',
    '--port',
    '13191',
    '--strictPort',
  ],
  { stdio: 'pipe', env: { ...process.env, WORKBENCH_COMPUTE_SSH_HOST: '' } },
);
let log = '';
server.stdout.on('data', (value) => (log += value));
server.stderr.on('data', (value) => (log += value));
let browser;
try {
  for (let n = 0; n < 50; n++) {
    if (server.exitCode !== null) throw new Error(log);
    if (log.includes('Local:')) break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.ok(log.includes('Local:'), log);
  browser = await chromium.launch({
    args: [
      '--enable-webgl',
      '--use-gl=angle',
      '--use-angle=swiftshader',
      '--enable-unsafe-swiftshader',
    ],
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  const calls = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => {
    if (!request.url().startsWith(url) && !request.url().startsWith('data:'))
      calls.push(request.url());
  });
  await page.goto(url);
  await page.getByRole('button', { name: 'English', exact: true }).click();
  await page.getByRole('button', { name: 'Try lysozyme · VHH', exact: true }).click();
  await page.getByRole('button', { name: 'Start design', exact: true }).click();
  await page.locator('.molecule[data-status="ready"]').waitFor();
  await page.getByRole('heading', { name: '6 finalists' }).waitFor();
  assert.equal(
    await page.getByRole('group', { name: 'Example finalists' }).getByRole('button').count(),
    6,
  );
  await page.reload();
  await page.getByRole('button', { name: 'Download results' }).waitFor();
  assert.deepEqual(errors, []);
  assert.deepEqual(calls, []);
  console.log(
    'PASS: production Easy preview completes automatically, renders bundled reference, restores six finalists after reload; no external requests or page errors.',
  );
} finally {
  await browser?.close();
  if (server.exitCode === null) {
    server.kill('SIGTERM');
    await once(server, 'exit');
  }
}
