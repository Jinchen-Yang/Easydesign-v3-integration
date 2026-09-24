import { defineConfig } from '@playwright/test';
const liveURL = process.env.EASYDESIGN_LIVE_URL;
const demoPort = Number(process.env.WORKBENCH_E2E_PORT || 13180);
if (!Number.isInteger(demoPort) || demoPort < 1024 || demoPort > 65535)
  throw new Error('WORKBENCH_E2E_PORT must be a non-privileged TCP port');
const demoURL = `http://127.0.0.1:${demoPort}`;
export default defineConfig({
  testDir: './e2e',
  timeout: 60000,
  expect: { timeout: 12000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: 'test-results/results.json' }]],
  use: {
    baseURL: liveURL || demoURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: {
      args: [
        '--enable-webgl',
        '--use-gl=angle',
        '--use-angle=swiftshader',
        '--enable-unsafe-swiftshader',
      ],
    },
  },
  projects: [
    { name: 'desktop-1440', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'desktop-1366', use: { viewport: { width: 1366, height: 768 } } },
    { name: 'desktop-1728', use: { viewport: { width: 1728, height: 1117 } } },
  ],
  webServer: liveURL
    ? undefined
    : {
        command: `pnpm exec vite --host 127.0.0.1 --port ${demoPort} --strictPort`,
        url: demoURL,
        reuseExistingServer: !process.env.CI,
        timeout: 30000,
      },
});
