// Opt-in integration check: fixed read-only GPU telemetry, no scientific jobs.
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdir } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';

const base = 'http://127.0.0.1:13182/';
const server = spawn(
  process.execPath,
  [
    'node_modules/vite/bin/vite.js',
    'preview',
    '--host',
    '127.0.0.1',
    '--port',
    '13182',
    '--strictPort',
  ],
  { stdio: 'pipe' },
);
let log = '';
server.stdout.on('data', (chunk) => {
  log += chunk;
});
server.stderr.on('data', (chunk) => {
  log += chunk;
});
let browser;
try {
  for (let tries = 0; tries < 50; tries++) {
    if (server.exitCode !== null) throw new Error(log);
    if (log.includes('Local:')) break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.ok(log.includes('Local:'), log || 'Preview did not start');
  const response = await fetch(`${base}api/compute/resources`);
  assert.equal(response.status, 200);
  const resources = await response.json();
  assert.equal(
    resources.connection,
    'connected',
    'Configure WORKBENCH_COMPUTE_SSH_HOST and working SSH first',
  );
  assert.ok(resources.sample.gpus.length > 0);
  assert.ok(Date.now() - Date.parse(resources.sample.sampledAt) < 25_000);
  const rejected = await fetch(`${base}api/compute/resources?host=other`);
  assert.equal(rejected.status, 400);
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1728, height: 1117 } });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(`${base}#compute`);
  await page.locator('.resource-status.live').waitFor();
  assert.equal(await page.locator('.gpu-card').count(), resources.sample.gpus.length);
  assert.equal(await page.getByTestId('demo-run').count(), 0);
  await mkdir('test-results', { recursive: true });
  await page.screenshot({ path: 'test-results/resources-live-preview-1728.png' });
  assert.deepEqual(errors, []);
  console.log(
    `PASS: production preview reads ${resources.sample.gpus.length} real GPUs from ${resources.node}, displays live cards, rejects browser host overrides; zero scientific jobs submitted.`,
  );
} finally {
  await browser?.close();
  if (server.exitCode === null) {
    server.kill('SIGTERM');
    await once(server, 'exit');
  }
}
