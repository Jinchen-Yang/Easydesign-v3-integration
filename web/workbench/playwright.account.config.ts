import { defineConfig } from '@playwright/test';
import { randomUUID } from 'node:crypto';

const runId = (process.env.EASYDESIGN_ACCOUNT_E2E_RUN_ID ||= randomUUID());
const evidenceRoot = `../../runtime/tmp/pw-workbench-account-${runId}`;
const executablePath = process.env.EASYDESIGN_PLAYWRIGHT_CHROMIUM;

export default defineConfig({
  testDir: './e2e/account',
  timeout: 60000,
  expect: { timeout: 15000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: `${evidenceRoot}/results.json` }]],
  outputDir: `${evidenceRoot}/artifacts`,
  use: {
    baseURL: 'http://127.0.0.1:13191',
    // Allow the same explicit browser selection as the repository verifier.
    channel: executablePath ? undefined : 'chrome',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    launchOptions: {
      executablePath,
      args: [
        '--enable-webgl',
        '--use-gl=angle',
        '--use-angle=swiftshader',
        '--enable-unsafe-swiftshader',
      ],
    },
  },
  projects: [{ name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } }],
  webServer: {
    command: 'corepack pnpm exec vite --host 127.0.0.1 --port 13191 --strictPort',
    url: 'http://127.0.0.1:13191/',
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
});
