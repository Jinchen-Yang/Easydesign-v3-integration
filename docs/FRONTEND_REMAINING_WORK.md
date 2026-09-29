# EasyDesign 前端重构：剩余工作清单

面向执行方（Kimi）。截至提交 `5883bc2`，阶段 1–4 主体已完成并验收。
本文件列出全部剩余工作，按优先级排序，每项标注阻塞关系与验收标准。

事实核查日期：2026-09-29。所有代码位置与行数均为当日实测，动手前请复核。

---

## 当前状态基线

| 项目 | 数值 |
|---|---|
| 单元测试 | 71/71 |
| e2e | 4/4（需要 README 里的两个前提） |
| typecheck / build | 退出码 0 |
| 主包 gzip | 117 KB |
| 访客首屏 gzip | 约 159 KB（3Dmol 162 KB 已推迟） |

硬性约束仍然生效：不改 `web/easy/`、`web/workbench/`、`web/shared/`，
不删旧 dist，不静默迁移数据。唯一例外是下面 P0 的后端分支，已获授权。

---

## P0：发布路径（唯一阻塞项）

其余所有工作都可以并行，但阶段 5 的两周观察期从真实上线起算，
所以这一项决定整个项目何时收尾。

### P0-1 后端新增 `/app/` 静态分发分支

**为什么必须改后端。** `server.py` 的 `static()` 只有两个分支：
`/easy/` 走 `easy_web_root`，其余一律走 `web_root` 并用五项白名单
（`index.html`、`assets/`、`structures/`、`mascot/rabbit/`、`favicon.svg`）过滤。
`/app/` 会被当成 Pro 目录下的相对路径 `app/`，不在白名单内，必定 404。
反向代理能转发请求，但回源到这个后端仍然 404，所以"不碰 Python"不成立。

**改哪里。** `account_server.py` 的 `AccountHandler.static()`（约 670 行）已经
覆盖了父类实现来处理 `/account/`，那就是 `/app/` 分支的天然模板，形状照抄即可。

```python
def static(self, path: str) -> None:
    if path in {"/account", "/account/"}:
        ...  # 现有代码不动
    if path == "/app" or path.startswith("/app/"):
        root = self.server.app_web_root
        if root is None or self.command != "GET":
            raise ProductError("not_found", "统一应用尚未构建", 404)
        relative = path.removeprefix("/app").lstrip("/") or "index.html"
        if not (
            relative == "index.html"
            or relative.startswith(("assets/", "structures/", "mascot/rabbit/"))
            or relative in {"favicon.svg"}
        ):
            raise ProductError("not_found", "Unknown application resource", 404)
        self.send(
            200,
            self.server.app_assets.read(relative),
            mimetypes.guess_type(relative)[0] or "application/octet-stream",
            immutable=HASHED_BUILD_ASSET.fullmatch(relative) is not None,
        )
        return
    super().static(path)
```

配套：`MultiUserServer` 增加 `app_web_root` 参数与一个 `StaticAssets` 实例，
`accounts_cli` 增加 `--app-web` 参数。总量约 25–40 行，全部集中在静态分发。

**白名单必须包含 `mascot/rabbit/` 和 `structures/`。** 漏掉的话豆豆在生产环境
会退化成 emoji、演示结构会回落到 RCSB 远程下载。`publicAssets.test.ts` 只断言
源文件存在，拦不住服务端不分发，所以这一条只能靠 code review 保证。

**为什么选这个方案而不是让新应用顶替 Pro。** 三面并存才能灰度：`/`、`/easy/`、
`/app/` 同时活着，可以先让两三个人用新界面，出问题让他们换回旧地址，
不影响其他人。顶替方案是一刀切，回滚要重启服务且全员一起回滚。
另外顶替还要把 vite base 从 `/app/` 改回 `/`，牵动构建产物路径、e2e baseURL、
旧链接重定向判断，这些改动的风险比后端那 25 行更高。

**这段代码不碰鉴权、不碰科学数据、不碰队列、不碰会话**，是只读静态分发，
属于后端最无害的区域。

**验收标准**
- [ ] 新增后端单测：`/app/` 返回 index.html；`/app/assets/<hashed>.js` 带 immutable 缓存头；
      `/app/mascot/rabbit/rabbit-mascot.png` 与 `/app/structures/1MEL.pdb` 返回 200；
      `/app/../etc/passwd` 与白名单外路径返回 404；非 GET 返回 404
- [ ] `/easy/`、`/`、`/account/` 行为逐字节不变（回归断言）
- [ ] 按仓库策略走 `dev.py verify --mode integration`
- [ ] `make check`（ruff + mypy）通过

注意：全量套件里有 24 个既有失败，全部在 `tests/unit/agent/` 与 GPCR 目录，
根因是本机 `ALL_PROXY=socks://127.0.0.1:7890` 且 venv 缺 `socksio`。
清掉代理变量后这批 152 个测试全过。与本项目改动无关，不要试图"修"它们。

### P0-2 发布与域名切换

- [ ] 新应用 dist 作为第三个 release 目录发布，不覆盖现有 `ui-*` 目录
- [ ] 启动参数增加 `--app-web` 指向它
- [ ] 切一级域名 `easydesign.pro` 时，`--public-origin` 必须同步改成
      `https://easydesign.pro`。它决定 cookie 的 Secure 标志
      （`account_server.py:187`，仅当值以 `https:` 开头才加）和可信来源校验
- [ ] 会话 cookie 是 `HttpOnly; SameSite=Strict; Path=/` 且不带 Domain，
      所以两个域名的登录态天然隔离，用户在新域名要重新登录一次。
      这是正确行为，不要为此加 Domain 属性，但要提前告知用户
- [ ] 回滚预案：去掉 `--app-web` 重启即可，`/app/` 变 404，旧两面不受影响

**发布本身走受控 release 流程，不要直接动线上。**

---

## P1：语言权威收尾

根因 D 的架构部分已经除掉（单一 i18next 实例，演示词典已迁入）。
剩下的是纯机械搬迁，但范围比之前报告的更大。

### P1-1 抽取剩余硬编码中文

上一轮报告说"残留中文扫描 0"，实测不成立。全量扫描（排除注释与 locales）：

| 文件 | 行数 |
|---|---|
| `src/views/easy/live-presentation.ts` | 26 |
| `src/views/easy/RabbitChat.tsx` | 21 |
| `src/views/pro/LiveWorkbench.tsx` | 10 |
| `src/views/pro/ProWorkspace.tsx` | 8 |
| `src/views/easy/EasyWorkspace.tsx` | 8 |
| `src/views/easy/live-input.ts` | 4 |
| `src/views/easy/queue-presentation.ts` | 3 |
| `src/views/easy/EasyApp.tsx` | 3 |
| `src/shared/account-client.ts` | 3 |
| 另有 5 个文件各 1 行 | 5 |

合计约 91 行。`pro.json` 目前是空的，Pro 那 18 行应该进去。

`LiveWorkbench.tsx` 的 10 行都是权限错误提示与过期屏文案，例如
`'当前身份不能启动计算，请由项目所有者或团队管理员执行。'`（288 行）。
上一轮判断"Pro 没有待抽取的中文"不准确。

**注意 `.ts` 文件（非组件）不能用 `useTranslation`**，要用
`appI18n.getFixedT`，README 的国际化约定里已经写明这个模式。

**验收标准**
- [ ] 全量 CJK 扫描（排除注释、locales、科学数据）归零
- [ ] `pro.json` 不再为空
- [ ] 键即英文源文，`en/*.json` 保持稀疏
- [ ] 词典键与代码引用双向校验零缺失
- [ ] 切 EN 后这些文案确实变英文（补 e2e 断言，至少覆盖 Pro 的权限提示）

### P1-2 词典懒加载（可选）

主包从 106 涨到 117 KB，因为四个命名空间的词典都在 `I18nProvider` 静态引入
（`src/shell/I18nProvider.tsx:4-11`）。P1-1 做完会再涨。

方向：`common` 随首屏，`easy`/`pro`/`account` 跟随各自的路由块按需加载。
i18next 支持运行时 `addResourceBundle`。

**只在 P1-1 完成后评估。** 如果那时主包超过 130 KB 就做，否则不值得动。

---

## P2：数据层合并

阶段 3 只合并了展示层，数据层仍是两份。这是 Codex 方案里"Easy 与 Pro 共享
项目数据"尚未实现的部分。

| 重复项 | 规模 |
|---|---|
| `EasyProductAdapter.ts` | 536 行 |
| `LiveWorkbenchAdapter.ts` | 427 行 |
| `product-contracts.ts` vs `contracts.ts` | 293 + 315 行，128 行差异 |
| `ApiError` 类 | 两个独立定义 |
| 3Dmol 包装组件 | 三个（`MolecularViewer`、`StructureViewer`、`EasyStructureViewer`） |

两个适配器的轮询调度、请求编号表、错误映射、暂停恢复逻辑几乎一致，
差异主要在快照投影的字段。

**建议做法**：先合并契约类型（取并集，差异字段设为可选），再抽出共享的
轮询与幂等基类，最后各自只保留投影逻辑。**不要一次性重写**，每合并一块
就跑一次 `expiryRecovery.test.tsx`，那条测试断言了适配器实例存活与
请求编号表不丢，是这次重构的安全网。

**验收标准**
- [ ] 适配器总行数显著下降，两份契约合并为一份
- [ ] 只剩一个 `ApiError`
- [ ] 3Dmol 包装收敛（至少 Pro 与 Easy 的两个查看器合并）
- [ ] `expiryRecovery.test.tsx` 与全部既有测试保持绿
- [ ] 防重复提交语义不变：同一操作重试复用同一 request_id

---

## P3：草稿覆盖面补齐

`draftRecovery` 目前只有一个写入方：`EasyLiveApp` 的设计输入
（`DRAFT_KEYS.projectCreate`）。恢复遮罩宣称"暂存内容已保留"，
但以下字段仍会在会话过期后丢失：

- [ ] Gate 审核备注（Pro 的 `GateReview`，执行指南 §2.2 存储策略表里列了此项）
- [ ] 项目重命名、候选筛选等表单中间态
- [ ] Pro 侧完全没有草稿接线（`src/views/pro` 与 `src/features` 零引用）

执行指南的存储策略表要求区分三态：输入还在、已保存到服务器、已提交执行。
目前只做到第一态。

**边界**：文件选择只存元数据（名称与大小），刷新后提示重新选择，
不要承诺跨设备恢复。访客草稿必须留在独立命名空间，
不能在登录后静默变成真实项目输入。

---

## P4：产品缺口（需要后端能力，本轮范围外）

这两项是原始痛点里未解决的，都不能靠前端补齐，**不要自行实现**。

### 痛点③ 注册审核通知
后端 `accounts.py` 没有任何通知能力（无邮件、无站内信）。
前端最多能在访客态显示"审核中"状态。真正的通知需要独立立项。

### 痛点⑨ 裸 JSON 404
应用内未知路由已有友好页面（`AppShell` 的 `NotFoundPage`）。
但服务端任意路径的 404 仍返回 JSON（`server.py:640`），
应用根本没加载时前端无法接管。需要服务端在
`Accept: text/html` 时返回 HTML 错误页，约半小时的小改动，
建议与 P0-1 同一笔提交做掉。

---

## P5：阶段 5 清理（观察期后）

**前置条件：新应用真实上线并稳定运行两周。**

- [ ] 删除 `web/easy/`、`web/workbench/`
- [ ] 后端移除 `/easy/` 分支与 `easy_web_root`
- [ ] 旧 release 目录保留一个版本用于紧急回滚
- [ ] 考虑把新应用从 `/app/` 挪到 `/`（此时无并存压力，是纯收尾）

在此之前**一律不要删除旧代码或旧 dist**。

---

## 交接注意事项

**e2e 有两个前提**，README 已写明，不满足会 4/4 全挂而且报错指向浏览器缺失：
从 `web/app/` 执行 `PLAYWRIGHT_BROWSERS_PATH=../../runtime/cache/playwright pnpm test:e2e`，
并且要先另开 shell 跑 `pnpm dev`（`reuseExistingServer` 在本环境不自动拉起）。

**降级路径会掩盖资源缺失。** 豆豆的 `RabbitArt` 有三级降级
（WebGL 纹理 → `<img>` → emoji 🐰），所以静态资源丢失时测试、构建、e2e
全都能绿，界面上只是悄悄退化。`tests/publicAssets.test.ts` 已经把
"资源必须存在"固化成断言，不要删或跳过它。同类陷阱还有
`MolecularViewer` 的本地结构回落远程，失败时只是变慢不报错。

**真实浏览器验证不可省。** 本轮三次关键判断都是靠浏览器实测纠正的：
jsdom 里 `location.hash` 赋值不触发 popstate 而 Chrome 会触发；
豆豆"看起来在渲染"实际是 emoji 兜底；结构文件在 `/app/` 下静默 404。
单测环境与真实浏览器的差异会藏住这类问题。
