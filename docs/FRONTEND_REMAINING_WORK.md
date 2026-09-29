# EasyDesign 统一前端：收尾状态

核验日期：2026-09-29。本页取代基于 `5883bc2` 的旧待办；部署实况与科学执行器边界见
[PRODUCTION_A_TUTORIAL_HANDOFF.md](PRODUCTION_A_TUTORIAL_HANDOFF.md)。

## 已补齐的实现

| 原任务 | 当前实现与验证重点 |
| --- | --- |
| P0 `/app/` 分发与发布 | 后端第三套静态入口、路径白名单、HTML 404 已实现；注册默认 active，真实登录后通过 `/accounts/me` 获取完整 scopes。A/B 均使用统一应用。 |
| P1 国际化 | Pro 导航、项目、计算、Gate、候选、实验订单、权限提示统一接入 i18next；中英切换保留用户和科学内容原文。旧 `{stage}` / `{name}` 与新插值语法兼容。 |
| P1 按路由加载词典 | common 随主壳，easy/pro/account 按需加载；每个 namespace 一次装入中英资源，兼容非 React 同步翻译入口。 |
| P2 数据层 | `LiveProductStore` 共用请求编号、串行轮询、暂停恢复与订单命令；两个 adapter 只保留输入编码和投影差异。科学契约在 `data/product-contracts.ts` 单一维护。 |
| P2 查看器 | Easy/Pro 使用 `VerifiedStructureViewer`，保留 manifest URL、SHA256、大小校验、插入码映射与显式失败；切高亮不重复解析结构。演示查看器仍用于固定演示。 |
| P3 草稿 | 覆盖 Easy/Pro 创建、Gate 审核、重命名、对话、项目搜索、候选分页与选中、模拟实验订单；按用户/scope/项目/不可变 Gate card 隔离。失败保留，成功才清，晚到响应不能清新输入。 |
| P3 恢复边界 | 文件只存元数据，必须重新选择；区分本地暂存、服务器保存、请求已提交。恢复不自动重新审批或执行。团队草稿冻结编辑起始 revision，冲突保留输入并由用户主动加载新版。 |
| 账号与团队 UI | 使用现有 Pro 紫色与浅色样式；可折叠侧栏、头像菜单、覆盖式设置面板。打开设置不替换当前工作区，关闭恢复焦点；手机布局支持表格横向滚动。 |
| 会话与权限 | 权限刷新更新同一 SessionProvider；统一操作代次防止取消恢复后被迟到响应重新登录。账号设置 401 加入恢复流程，旧 CSRF 的迟到 401 不打断新登录。 |
| Pro 深链 | 读取 `#/projects/:id`；打开项目保留 scope/view，避免旧 `#workspace` 使 Hash Router 进入 404。 |

注册审核通知不再是注册即用流程的阻塞项。未知页面的 HTML 404 已完成，不再列为待办。

## 保留的边界

- **旧版退役**：继续保留 `web/easy/`、`web/workbench/`、`web/shared/` 与历史 release。
  真实上线稳定运行两周后，再按兼容链接和回退要求决定清理；当前不删除。
- **真实科学纵向验收**：A 已验证模型接口、环境、模型资产和 GPU 算子；完整研究需要
  明确研究目标、真实输入与研究者 Gate 确认。固定演示、接口测试和截图不能替代这一验收。
- **A/B 统一算力池**：仍未实现。本次连接的是各站真实后端；保留 test 入口的 SSH 转发不等于双机调度。

## 验证与复现

前端回归覆盖接口幂等、过期恢复、跨账号竞态、权限变化、结构完整性、草稿冲突、
中英界面、Pro 深链及设置面板的焦点和输入保留。证据保存在
`runtime/tmp/production-deploy/`，最终数量与部署版本见交接文档。

使用现有依赖运行 `web/app/node_modules/.bin/tsc -b web/app` 与
`web/app/node_modules/.bin/vitest run --root web/app`。
浏览器使用 `PLAYWRIGHT_BROWSERS_PATH=$PWD/runtime/cache/playwright`；
`EASYDESIGN_E2E_BASE_URL` 可指向已启动的构建预览服务，避免开发服务器编辑过程中的 HMR 状态干扰。

仓库后端全量测试中，本机代理环境（包括 NO_PROXY）可导致 SDK 初始化失败；
记录原失败并在清除代理变量后重跑对应完整测试文件，不把环境失败归因为产品缺陷，
也不把重跑结果描述为原验证器一次通过。
