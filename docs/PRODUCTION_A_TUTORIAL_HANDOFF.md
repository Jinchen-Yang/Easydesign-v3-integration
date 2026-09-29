# A 机教程预览部署与重构余项

核验日期：2026-09-29。应用源码固定为 `a33317b4089df81d0394020c393c4407d8be7c69`。

## 使用入口与验收边界

- 主站：<https://easydesign.pro/>，自动进入 `/app/`。
- 账号：<https://easydesign.pro/app/#/account>，新用户注册后即可登录。
- 演示：<https://easydesign.pro/app/#/demo>，试用溶菌酶后可逐阶段截图。
- 教程材料：`runtime/releases/tutorial-materials-a33317b.zip`，含 8 张 PNG 和说明。
- 此部署是教程预览：显式 `--accounts-only`，`compute_available=false`。
  新目录的 5 个科学环境及 14 项模型/资产仍未安装；真实计算与真实 AI 对话未启用。
  没有创建科学任务，不能据此宣称真实设计流程或双机算力池已验收。
- 新库保留在 A；B 的账号、项目与研究记录未迁移，使用者可在主站自行注册。

## Kimi 已交付的范围

`1d813b2` 已实现第三套 `/app/` 静态分发、`--app-web`、资源白名单与 HTML 404。
`8204882` 已抽取其扫描范围内的硬编码中文。此前统一 SPA、访客演示、会话恢复、
路由拆包、豆豆图片和结构资源迁移也已进入当前版本。
这些提交不是“重构全部完成”的证明，剩余项以本次代码与浏览器核验为准。

## 本次补齐

- `8f340c0`：注册默认 active，更新注册文案，保留停用/拒绝/人工 pending 门禁。
- `2a91fb4`：HTTP 注册即用回归。
- `6ab6460`：真实 `/login` 只返回 user/CSRF；前端随后读取 `/accounts/me` 得到 scopes。
  修复此前真实登录及会话恢复读取缺失 scopes 的崩溃；注册响应状态同步为 registered。
- `a33317b`：Easy 页内导航滚动不再覆盖 Hash Router；输入类型接入现有词典。

## 尚未完成的重构

| 事项 | 当前证据与下一步 |
| --- | --- |
| Easy/Pro 共享数据层 | 两个 adapter 仍分别存在（539 与 430 行），契约、轮询与请求状态未统一。保留同一 request_id 和恢复时的实例语义。 |
| 草稿覆盖 | `draftRecovery` 的实际业务写入仍集中在 Easy 设计输入，Pro/Gate 备注等需要补齐并做过期恢复测试。 |
| 完整国际化 | 公网中文模式下 Pro 仍显示 Projects、Agent Workspace 等英文；演示存在 `{stage}`、`{name}` 未插值文本。中文扫描归零不等于全部界面已翻译。 |
| 真实科学纵向验收 | 安装当前 A clone 的科学环境和资产后，再验收输入、Gate、计算、恢复、结果。当前截图和模拟演示不能替代。 |
| 旧面退役 | 旧 Easy/Workbench 源码和 release 保留；稳定观察后再按兼容链接与回退要求清理。 |
| A/B 统一算力 | 未实现，当前 A/B 之间只有保留测试站的入口转发，不能当成双机调度。 |

注册审核通知已不再是本次注册流程的必需项；HTML 404 已完成，不再照抄旧清单为待办。

## 部署实况与回退

A 的独立目录为 `/data/Easydesign-v3-production`；科学模型、旧环境和其他服务均未覆盖。
主站：Cloudflare → A cloudflared → A loopback 8096 网关 → A loopback 18771 应用。

实际隧道还承载 test 域名，不能当作主站专用隧道处理。
测试站保持：Cloudflare → A 的 8097 SSH 转发 → B 的 127.0.0.1:18771。
3080 原隧道容器已停止并设 restart=no，原静态网站容器、文件、token 均保留。
没有修改 Cloudflare DNS/ingress，也没有把 3080 留在服务请求链路中。

A 的四个自启动服务：`easydesign-production`、`easydesign-gateway`、
`easydesign-tunnel`、`easydesign-test-forward`。
最终静态目录：`runtime/releases/production-tutorial-final/app`。
之前两次新构建与原 hashed assets 均保留；新版本资产目录包含旧 hashed 文件，防止旧标签页失效。

数据库使用 SQLite backup API 备份；服务/config/source 备份位于
`runtime/backups/pre-login-fix` 与 `runtime/backups/pre-tutorial-final`。
禁止用旧备份覆盖上线后产生的新账号或数据。

如需回退网络入口：先在 3080 恢复原 `easydesign-tunnel` 的 unless-stopped 策略并启动，
确认连接后停 A 隧道；这会把主站恢复为旧静态图谱站，不是回滚成当前应用。
应用/UI 回退应保留新数据库，只切换已保留且兼容的代码与静态目录，切换前重新核对活动任务。

## 验证证据

证据目录：`runtime/tmp/production-deploy/`。

- 产品后端：`product-final.log`，387 passed。
- 注册与静态分发专项：`final-account-tests.log`，47 passed。
- 前端：`app-tests-final.log`，72 passed；`app-e2e-final.log`，5 passed；类型检查与构建通过。
- `final-check.log`：结构、Ruff、mypy 通过。
- `target-viewer-tests.log`：5 passed、2 skipped；`wheel-check.log`：wheel 资源与入口校验通过。
- 公网真实浏览器：注册、登录、退出后重登、个人工作区、Easy/Pro 切换、页内导航与演示结构。
- 主域名 GET /app/ 为 200，根路径跳转正确；原测试站 GET /account/ 为 200。
- A 数据库 quick_check=ok，科学 admissions=0；四个服务 active，隧道 4 条连接。
- 完整仓库回归 `final-release-verify.log` 仍在执行；尚未宣称全量 release 验证通过。
- Cloudflare 注入的统计 beacon 被现有 CSP 阻止，产品页面仍正常；未为了统计脚本放宽 CSP。
