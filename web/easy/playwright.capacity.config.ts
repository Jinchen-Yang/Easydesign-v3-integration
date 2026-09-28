import { defineConfig } from '@playwright/test';
import { randomUUID } from 'node:crypto';

const runId = (process.env.EASYDESIGN_CAPACITY_E2E_RUN_ID ||= randomUUID());
const evidenceRoot = `../../runtime/tmp/pw-capacity-${runId}`;
const executablePath = process.env.EASYDESIGN_PLAYWRIGHT_CHROMIUM;

export default defineConfig({
  timeout: 45000,
  expect: { timeout: 10000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: `${evidenceRoot}/results.json` }]],
  outputDir: `${evidenceRoot}/artifacts`,
  use: {
    channel: executablePath ? undefined : 'chrome',
    viewport: { width: 1440, height: 1000 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    launchOptions: {
      executablePath,
      args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
    },
  },
  projects: [
    {
      name: 'easy-capacity',
      testDir: './e2e/account',
      testMatch: 'capacity.spec.ts',
      use: { baseURL: 'http://127.0.0.1:13192' },
    },
    {
      name: 'chat-retry',
      testDir: './e2e/easy',
      testMatch: 'chat.spec.ts',
      grep: /failures never automatically retry/,
      use: { baseURL: 'http://127.0.0.1:13192' },
    },
  ],
  webServer: [
    {
      command: './node_modules/.bin/vite --host 127.0.0.1 --port 13192 --strictPort',
      url: 'http://127.0.0.1:13192/easy/',
      reuseExistingServer: false,
      timeout: 30000,
    },
  ],
});
