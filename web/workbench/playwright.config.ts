import { defineConfig, devices } from "@playwright/test";

const chromiumLaunchOptions = process.env.EASYDESIGN_PLAYWRIGHT_CHROMIUM
  ? { executablePath: process.env.EASYDESIGN_PLAYWRIGHT_CHROMIUM }
  : undefined;
const includeFirefox = process.env.EASYDESIGN_SKIP_FIREFOX !== "1";
const skipVisualRegression = process.env.EASYDESIGN_SKIP_VISUAL_REGRESSION === "1";

export default defineConfig({
  testDir: "./tests",
  snapshotPathTemplate:
    "{testDir}/{testFilePath}-snapshots/{arg}-{projectName}{ext}",
  timeout: 30_000,
  expect: {
    timeout: 15_000,
  },
  fullyParallel: false,
  workers: 2,
  retries: 0,
  grepInvert: skipVisualRegression ? /approved visual hierarchy/ : undefined,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:4174",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium-1440",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
        launchOptions: chromiumLaunchOptions,
      },
    },
    {
      name: "chromium-1920",
      use: {
        ...devices["Desktop Chrome HiDPI"],
        viewport: { width: 1920, height: 1080 },
        launchOptions: chromiumLaunchOptions,
      },
    },
    ...(includeFirefox
      ? [
          {
            name: "firefox-smoke",
            use: {
              ...devices["Desktop Firefox"],
              viewport: { width: 1440, height: 900 },
            },
          },
        ]
      : []),
  ],
  webServer: {
    command: process.env.EASYDESIGN_WEB_DEV_COMMAND || "pnpm preview",
    url: "http://127.0.0.1:4174",
    reuseExistingServer: process.env.EASYDESIGN_REUSE_WEB_SERVER === "1",
    timeout: 30_000,
  },
});
