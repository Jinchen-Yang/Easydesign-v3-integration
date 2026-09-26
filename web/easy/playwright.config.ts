import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './e2e',
  timeout: 60000,
  expect: { timeout: 12000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: 'test-results/results.json' }]],
  use: {
    baseURL: 'http://127.0.0.1:13180',
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
  webServer: {
    command: 'pnpm dev',
    url: 'http://127.0.0.1:13180',
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
});
