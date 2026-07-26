const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  expect: {
    timeout: 15_000,
  },
  fullyParallel: false,
  workers: 1,
  reporter: [["line"]],
  use: {
    browserName: "chromium",
    headless: true,
    viewport: { width: 1440, height: 960 },
    launchOptions: {
      executablePath: process.env.EASYDESIGN_PLAYWRIGHT_CHROMIUM || undefined,
      args: [
        "--enable-webgl",
        "--ignore-gpu-blocklist",
        "--use-gl=swiftshader",
        "--enable-unsafe-swiftshader",
      ],
    },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
