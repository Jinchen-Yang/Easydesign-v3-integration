# 2026-08 项目历史

本文件归档跨阶段工作；各 Stage 的详细证据仍以对应
`workflow/*/history/2026-08.md` 为准。

## 2026-08-01 — ENG-030 / ENG-031 / UX-008 / UI-022：双执行与 Suzhou2 统一队列

- 状态：`implemented`。
- 完成时间：2026-08-01T03:39:51+08:00
- 问题：Stage 04/06 既要在当前 GPU 机器自动分配，又要使已获授权的无本地算力用户通过 Suzhou2 运行；旧 SSH 路径缺少统一队列、一卡一租约和大数据原地交接。
- 方案：引入非科学 `ExecutionTarget`、本机 GPU 发现/租约、Suzhou2 `RemoteJobBundle`/Managed Worker、独立 SSH key 与 host fingerprint 配对、逻辑解绑、结构化观察及 metadata/review/complete 同步。
- 安全边界：新 worker 只能写 `/data/easydesign/managed-worker`；旧 `/data/easydesign`、APOE 50k、旧环境和 `/root/Easydesign/Easycontrol` 均保持原样。本任务没有执行删除、移动、覆盖、进程终止或系统代理修改。
- 验证：386 passed/8 skipped；Ruff 通过；149 个源文件 mypy 通过；Workbench 非视觉 60/60；Target Viewer 3 passed/2 skipped；dev32 wheel SHA-256 `50a9a1369ddce8106fbbec3cda7e51b4407493403b83e518a6d89f207480855b` 且资产/console script smoke 通过。
- 遗留边界：本轮达到工程 `implemented`，不伪装 Suzhou2 已部署。`VAL-008` 继续负责 systemd unit 人工审阅、专用 key 配对、本机极小 Stage 04、Suzhou2 极小 Stage 04、Stage 06 单 shard 和 Stage 07 adapter probe。
- 实现提交：`bede8e13f161987d5ce77658c73121ba0aeac5b5`。

## 2026-08-01 — UI-023：精简设置与自动就绪检查

- 状态：`smoke-validated`。
- 完成时间：2026-08-01T09:49:56+08:00
- 问题：旧设置页将环境、模型资产、安装任务、公共算力、项目 preflight、自检、存档和技术元数据堆在一个长页面，普通使用者难以快速判断“当前机器能否运行”、“如何连接 Suzhou2”和“如何找回存档”。
- 方案：将设置重构为“当前设备 / 公共算力 / 项目存档”三个可切换页面。当前设备自动投影工作区 setup plan 和注册表，区分基础环境与按需科学后端，仅对缺失组件提供安装操作；Suzhou2 配对和存档恢复各自进入独立上下文。
- 自动行为：进入页面、窗口重新获得焦点、页面恢复可见和安装任务运行期间都会自动更新状态；不再要求用户点击“刷新状态”。工作区绝对路径、environment/asset ID、安装任务、隔离区和结构助手状态统一收进默认折叠的“技术详情”。
- 验证：`make check` 通过，157 个 Python 源文件通过 mypy；386 passed / 8 skipped；Workbench 65 passed / 1 skipped，包含 1440×900、1920×1080 和 Firefox smoke；Target Viewer 3 passed / 2 skipped；dev33 wheel SHA-256 `76a9705d91a5bdddb93658652911d02a663ab76d6ba7ce83cad8567b63626711`，静态资产与 console script 验证通过。
- 安全边界：本任务没有执行删除、移动、清理、环境覆盖或系统配置修改；Stage 01/02 协作者历史和无关静态文件未纳入提交。
- 遗留边界：环境页只显示已有 setup plan 中的组件；真实 Suzhou2 配对和缺失科学后端安装继续由 `VAL-008` 与环境资产许可验收负责。
- 实现提交：`47cf194879264110d3ac353c7954221ccbe25b26`。

## 2026-08-01 — UX-008：Suzhou2 主机身份稳定配对

- 状态：`implemented`。
- 完成时间：2026-08-01T11:45:37+08:00
- 问题：同一台 Suzhou2 同时公布 Ed25519、ECDSA 和 RSA 主机密钥；旧逻辑只使用 `ssh-keyscan` 输出第一行，两次扫描顺序变化时会将同一服务器误报为 fingerprint 不一致。
- 方案：解析并去重全部主机密钥，以 Ed25519、ECDSA、RSA 稳定排序供界面展示，配对时在完整集合中查找用户已确认的 fingerprint；SSH 执行器增加 `IdentitiesOnly=yes`，只提交 EasyDesign 工作区专用密钥。
- 用户边界：配对页明确说明需通过 Suzhou2 控制台或管理员核对服务器身份；EasyDesign 不读取、替换或修改 `~/.ssh` 中的个人密钥。
- 验证：`make check` 通过；388 passed / 8 skipped；Workbench Chromium 非视觉流程 21/21 通过，含公共算力设置回归；真实 Suzhou2 扫描已确认三种主机密钥可同时观测。
- 安全边界：未修改个人 SSH、系统代理、shell 或 Git 全局配置；未删除、移动或覆盖环境、模型、run 或历史证据。
- 遗留边界：完成真实免密 worker 探针及极小 Stage 04/06 任务后，由 `VAL-008` 决定是否升级为 `smoke-validated`。
- 实现提交：`2bae835678a72a574d40377901966970744fcaef`。
