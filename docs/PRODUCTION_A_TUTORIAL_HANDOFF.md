# A/B 新版部署、教程材料与科学执行器

核验日期：2026-09-29。A/B 当前应用源码均为
`2b7a3c2dfaa1647ae0030eb0ad67beb1fadbafe4`，取代此前的 `a33317b`。
数据量为发布/验收快照，运行中的站点会继续产生数据。

## 使用入口与教程

- A 主站：<https://easydesign.pro/app/>。
- B 测试站：<https://test.easydesign.pro/app/>。
- 主站账号：<https://easydesign.pro/app/#/account>，注册后即可登录。
- 固定演示：<https://easydesign.pro/app/#/demo>，不代表真实科研结果。
- 新版教程包：`runtime/releases/tutorial-materials-2b7a3c2.zip`，包含 A 的 11 张、
  B 的 7 张真实页面截图、操作说明和 SHA256 清单，没有凭证或数据库。

账号、登录、注册和团队页沿用现有 Pro 的浅色/紫色样式；交互参考 Kimi 的可折叠菜单、
头像菜单及覆盖式设置面板。打开设置时，项目和未提交输入保留在背景，关闭后回到原工作区。
手机使用紧凑侧栏，普通用户不显示后台管理入口。

## Kimi 工作与本次补齐

Kimi 已交付统一 SPA、访客演示、会话恢复、路由拆包、结构资源迁移、第三套 `/app/`
分发、`--app-web`、资源白名单与 HTML 404，以及其扫描范围内的中文抽取。
此前“共享数据、草稿、国际化尚未完成”的判断已过时：本次已经补齐并部署。

| 范围 | 当前结果 |
| --- | --- |
| 注册与登录 | 注册默认 active；登录成功后读 `/accounts/me` 获取完整 scopes；保留停用、拒绝和人工 pending 的限制。 |
| 共享数据 | `LiveProductStore` 统一契约、串行轮询、请求编号、恢复和订单命令；Easy/Pro adapter 保留输入编码与投影差异。 |
| 查看器 | 共用 `VerifiedStructureViewer`，保留 manifest URL、SHA256、大小校验、插入码和显式错误。 |
| 草稿 | 覆盖 Easy/Pro 创建、Gate 审核、重命名、对话、搜索、候选分页/选择、模拟订单；按用户、scope、项目、Gate card 隔离。 |
| 恢复 | 失败保留，成功才清除；晚到响应不清除新输入；文件需重选；恢复不自动审批。团队编辑冻结起始 revision，冲突由用户明确加载新版。 |
| 会话与权限 | 防止过期响应恢复旧登录或打断新登录；设置页 401 接入恢复；权限变更刷新权威 scopes，验证失去访问权后才切换工作区。 |
| 国际化 | Pro 导航、项目、计算、Gate、候选、订单、权限提示支持中英；修复旧插值，词典按路由加载，保留用户科学内容原文。 |
| 深链与 UI | Pro 使用 `#/projects/:id` 并保留 scope/view；账号与团队界面及设置唤起统一为上述 Pro 样式。 |

实现详见 [FRONTEND_REMAINING_WORK.md](FRONTEND_REMAINING_WORK.md)。

## 部署与数据保护

| 项目 | A 主站 | B 测试站 |
| --- | --- | --- |
| 独立目录 | `/data/Easydesign-v3-production` | `/data/Easydesign-v3-test` |
| systemd | `easydesign-production.service` | `easydesign-v3-test.service` |
| 当前静态目录 | `runtime/releases/account-refresh-2b7a3c2/app` | `runtime/releases/ui-2b7a3c2/{app,easy,workbench}` |
| 新 drop-in | `90-account-refresh-2b7a3c2.conf` | `70-account-refresh-2b7a3c2.conf` |
| 部署清单 | release 父目录 `DEPLOYED-SHA256.json`，116 文件 | release 根目录 `DEPLOYED-SHA256.json`，232 文件 |
| 本轮备份 | `runtime/backups/pre-account-refresh-2b7a3c2-compatible` | `runtime/backups/pre-account-refresh-2b7a3c2` |

原始构建含 81 个文件，两站均补留 35 个旧 hashed 文件，避免旧标签页加载失败。
同名 hashed 资源内容一致。发布包为本地
`runtime/releases/account-refresh-2b7a3c2/app.tar.gz`，SHA256：
`0fde19545f8cbcee940f624d5af6221c070e66e4408ac0d557e42c40ca4181ba`。
主入口 `index-xtQQH8Fm.js` 的 SHA256：
`63ad407f1bb22df88bb164e5d0b881f872b1dbaa25cdda43d88f1c037634f98e`。

本轮静态发布没有改变 Python/科学源码和依赖。A 最初发现 queued admission 后，
空闲发布脚本主动停止在服务切换之前；核对兼容性与独立 worker 保留机制后，
使用只停止 Web 主进程的方式更新。没有取消、重放或改写科学任务。

- A 切换前后保留 8 用户、2 团队、2 成员关系、19 admissions，用户完整行 hash 一致；
  原 queued 请求在切换前后标识/状态不变。之后它由系统自然进入 running，再进入 released；
  released 只表示释放资源，不能据此宣称科学结果成功。
- B 切换前后保留 18 用户、2 团队、3 成员关系、46 admissions，active=0；
  原 17 用户完整行 hash 一致，5111 个受保护文件 SHA256 全部一致。
- 两站专用 QA 仅临时启用用于登录和截图，结束后恢复 suspended 并撤销会话。
  QA 未创建科学项目、团队或审批 Gate，也没有改变真实用户权限。
- 数据库使用 SQLite backup API 备份并检查 quick_check。未覆盖研究数据或科学环境，
  未迁移两站账号。历史 release、配置、代码和备份均保留。

主站链路：Cloudflare → A cloudflared → A loopback 8096 网关 → A loopback 18771 应用。
测试站链路：Cloudflare → A loopback 8097 SSH 转发 → B loopback 18771 应用。
没有改动 DNS/ingress。A 的 `easydesign-production`、`easydesign-gateway`、
`easydesign-tunnel`、`easydesign-test-forward` 四个服务均已启用并运行。

3080 原隧道容器停止且 restart=no，文件和容器保留。恢复该入口会回到旧静态图谱站，
不是当前应用回退。应用回退先检查当时活动任务，再切换保留的兼容源码和静态目录、
恢复旧 drop-in；保留当前数据库，禁止用历史备份覆盖新账号或研究数据。
B 具体回退步骤见 `runtime/tmp/production-deploy/b-account-refresh/README.md`。

## 验证结果

本地证据根目录：`runtime/tmp/production-deploy/`。

- `refactor-final-unit.log`：17 文件、136 项前端测试通过。
- `refactor-final-e2e.log`：8 项构建预览浏览器用例通过，包含覆盖层保留输入、Escape 恢复焦点、
  菜单收起、手机布局、中英切换、访客及 Pro 权限流程。
- TypeScript 检查通过；`refactor-final-build.log` 构建通过，主入口 gzip 约 105 KB。
- `refactor-dev-local.log`：局部验证通过；`refactor-make-check.log`：结构、Ruff、mypy 通过。
- `refactor-viewer-tests.log`：5 passed、2 skipped；`refactor-wheel-build.log`：wheel 资源与入口校验通过。
- 此前 `product-final.log` 后端 387 passed，`final-account-tests.log` 注册/静态专项 47 passed。
- 全量 `final-release-verify.log` 已结束：1953 passed、21 failed、11 skipped。
  21 个失败涉及本机代理环境下 SDK 初始化；清除测试进程代理变量后，相关完整测试文件分别
  24、6、47 项通过，见 `evidence-research-clean-env.log`、`prerequisite-recovery-clean-env.log`、
  `remaining-clean-env-regression.log`。这是失败后的独立复跑，不是原 release 验证器一次全通过。
- A/B 公网真实浏览器验证了普通账号登录、账号/团队页、覆盖层、输入保留、语言与 Easy/Pro 切换，
  accounts/config/projects/usage/compute API 均可调用；没有产品 JavaScript 异常。
- A `a-account-public-assets.json`：115 个非 HTML 文件逐字节 SHA256 一致；HTML 去除身份标记、
  Cloudflare beacon 并规范化标签间空白后与构建入口一致。原严格 HTML 比较失败记录仍保留。
- B 浏览器、发布身份和文件保护证据见 `b-account-refresh/README.md`。
- Cloudflare 统计 beacon 被既有 CSP 阻止；没有为统计脚本放宽 CSP。

旧主工作树按 `TEST_DEPLOYMENT_BASELINE.md` 中已有授权例外保留，未锁定、改名或删除；
`dev.py context` 仍报告该已知拓扑 blocker。未修改检查器或绕过新的发布限制。

## 科学执行器：已连接，但 A 单卡异常待维护

A 已退出 accounts-only，公网 `compute_available=true`。科学资产使用 A 当前 clone 自己的
runtime，环境由锁定包重建，模型/源码经 SHA256/revision 校验。预测后端为 Protenix-v2。
以下为本次会话早先完成的探针证据，不代表后续硬件状态始终健康：

- `a-runtime-status-enabled.json`：PyMOL、BoltzGen、Protenix-v2、ScanNet、TNP 共 5 个环境、14 项资产 available。
- `a-backend-gpu-probes.jsonl`：6 个必需 backend 探针 passed，Landlock ABI 1 通过；ScanNet CPU 运算通过。
  当时编号为 4 的 GPU 上，PyTorch 2.7.1/CUDA 12.6、PyTorch 2.13.0/CUDA 13.0 矩阵运算及 Protenix FusedLayerNorm 通过。
- `a-provider-probe.json`：7 个科学角色客户端配置成功，coordinator 和 target 调用取得真实响应。
- `a-public-science-check.log`：启用时公网资源接口 connected，检测到 A 的 8 张卡。
- 必需 19 个安装项完成后，可选 AFO 下载网络不可达，原安装任务因此记录 failed；
  未隐藏或启用 AFO。当前配置路径为 Protenix-v2。

**最后一次在线复测发现主机故障，不能再宣称 A 八卡完全健康：**

- PCI `0000:b1:00.0` 持续报 `RmInitAdapter failed (0x62:0x40:2674)`，
  只读检查窗口首次记录早于本轮 UI 切换。对应 Device Minor 4，
  UUID `GPU-cfa596d9-8ac4-f571-52a4-d55b24635b52`。
- `/proc` 仍有 8 张卡，nvidia-smi 只返回 7 张；全局进程查询间歇超时，
  公网监控在 connected/stale 之间变化。stale 保留上一份有效采样，不代表最新状态。
  进程查询失败单独只会使进程数未知；当前证据没有确定每次 stale 的具体采样异常类型。
- 服务仍为 `--gpu-devices 4,5,6,7`。掉卡后当前 nvidia-smi index 4/5/6 对应原 minor 5/6/7，
  index 7 消失；数字索引不能当成固定物理卡身份，不能简单改为 5–7。
- probe 目前先全卡查询再过滤 allowed_devices。健康 PCI 选择查询有成功样本，
  但单健康卡也出现超时，尚不能证明选择器完全消除驱动卡顿。
- 既有请求自然调度并释放资源，整个执行器没有停止；未以此推断科学结果。
  没有重启主机、reset GPU、卸载驱动、杀科学进程或重分配任务。
- B 此轮资源接口 connected，返回其 8 张 A100。

证据见 `a-telemetry-check/`。需要维护窗口处理故障卡及驱动，再复核全部 GPU 的
UUID/PCI/数字索引和真实分配。若先做软件隔离，应使资源探针与遥测均使用稳定身份，
不能静默丢卡或将探测失败解释为“空闲”。维护前不承诺 A 的完整四卡容量或监控稳定性。

## 保留事项

- A 上述单卡/驱动异常尚未修复，页面和账号服务可以用于教程截图。
- 真实研究全流程仍需明确目标、输入与研究者 Gate 确认；未用工程 QA 擅自启动科研验收。
- A/B 统一算力池未实现；入口 SSH 转发不是跨机调度。
- 旧 Easy/Workbench 源码与历史 release 保留，稳定观察两周后再决定退役。
- B 从访客进入 Pro 后 tab 标题可能保留 Easy 标题；正文和功能正常，记录为低优先级余项。
