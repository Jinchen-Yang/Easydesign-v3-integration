import { defineConfig } from '@playwright/test';
import { randomUUID } from 'node:crypto';

const runId = (process.env.EASYDESIGN_CAPACITY_E2E_RUN_ID ||= randomUUID());
const evidenceRoot = `../../runtime/tmp/pw-professional-capacity-${runId}`;
const executablePath = process.env.EASYDESIGN_PLAYWRIGHT_CHROMIUM;

export default defineConfig({
  testDir: './e2e/account',
  testMatch: 'workbench.spec.ts',
  grep: /capacity:/,
  timeout: 45000,
  expect: { timeout: 10000 },
  workers: 1,
  reporter: [['list'], ['json', { outputFile: `${evidenceRoot}/results.json` }]],
  outputDir: `${evidenceRoot}/artifacts`,
  use: {
    baseURL: 'http://127.0.0.1:13182',
    channel: executablePath ? undefined : 'chrome',
    viewport: { width: 1440, height: 1000 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    launchOptions: {
      executablePath,
      args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
    },
  },
  webServer: {
    command: './node_modules/.bin/vite --host 127.0.0.1 --port 13182 --strictPort',
    url: 'http://127.0.0.1:13182/',
    reuseExistingServer: false,
    timeout: 30000,
  },
});
