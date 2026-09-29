# EasyDesign 统一应用（web/app）

Easy / Pro / 账号门户合并后的单一 SPA。Hash Router，访客态/登录态同源。
规范见 `docs/FRONTEND_REFACTOR_PROPOSAL.md` 与 `docs/FRONTEND_REFACTOR_EXECUTION_GUIDE.md`。

## 常用命令

```bash
pnpm install
pnpm dev          # 开发服务器 http://127.0.0.1:13200/app/（base 固定为 /app/）
pnpm test         # vitest 单元测试
pnpm typecheck    # tsc -b
pnpm build        # tsc -b && vite build → dist/
pnpm test:e2e     # Playwright e2e（前提见下）
```

## e2e 前提条件（两个都必须满足，否则 4/4 全挂）

1. **浏览器二进制在本仓库 runtime 里，不在默认路径。** 本机没有把浏览器装到
   `~/.cache/ms-playwright`，而是装在仓库的 `runtime/cache/playwright`。直接跑会报
   `chromium_headless_shell-1161` 缺失。从 `web/app/` 执行：

   ```bash
   PLAYWRIGHT_BROWSERS_PATH=../../runtime/cache/playwright pnpm test:e2e
   ```

2. **dev 服务器要先手动起来。** `playwright.config.ts` 的 `webServer.reuseExistingServer`
   在本环境不会自动拉起 `pnpm dev`，必须先另开一个 shell 跑 `pnpm dev`，再跑 e2e。

当前 e2e 只覆盖无后端可验证的行为（访客首页、动作边界、旧链接归一、语言权威、
访客零 scoped-API 请求）；需要真实账号的流程走部署环境联调。

## 国际化约定

- 单一 i18next 实例（`src/shell/I18nProvider.tsx` 的 `appI18n`），命名空间
  `common` / `easy` / `pro` / `account`，词典在 `src/locales/{zh,en}/`。
- `keySeparator: false` + `fallbackLng: false`：**键即英文源文**，英文缺译时显示键本身，
  绝不回落中文；`en/*.json` 只收与键不同的英文显示（如品牌名）。
- 组件内用 `useTranslation('<ns>')` 的 `t()`（语言切换不卸载组件）；React 之外
  （事件回调、校验函数）用 `appI18n.getFixedT`。
- 服务器返回的内容（项目名、目标、科学文本）不翻译。
