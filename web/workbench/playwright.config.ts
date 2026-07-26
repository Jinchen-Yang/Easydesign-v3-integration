import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:4174",
    trace: "retain-on-failure",
    launchOptions: process.env.EASYDESIGN_PLAYWRIGHT_CHROMIUM
      ? { executablePath: process.env.EASYDESIGN_PLAYWRIGHT_CHROMIUM }
      : undefined,
  },
  projects: [
    {
      name: "chromium-1440",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "chromium-1920",
      use: { ...devices["Desktop Chrome HiDPI"], viewport: { width: 1920, height: 1080 } },
    },
    {
      name: "firefox-smoke",
      use: { ...devices["Desktop Firefox"], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: {
    command: process.env.EASYDESIGN_WEB_DEV_COMMAND || "pnpm dev",
    url: "http://127.0.0.1:4174",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
