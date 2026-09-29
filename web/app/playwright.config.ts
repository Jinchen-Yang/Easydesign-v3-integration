import { defineConfig } from '@playwright/test';

const baseURL = process.env.EASYDESIGN_E2E_BASE_URL ?? 'http://127.0.0.1:13200';

/**
 * e2e 面向统一应用（/app/）。dev 环境没有后端：这里只覆盖无需后端即可
 * 验证的产品行为（访客首页、动作边界、旧链接归一、语言权威、无越权请求），
 * 需要真实账号的流程由阶段 4 的联调清单在带后端的环境执行。
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'pnpm dev',
    url: `${baseURL}/app/`,
    reuseExistingServer: true,
    timeout: 60_000,
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
});
