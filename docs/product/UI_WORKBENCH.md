# EasyDesign 产品级科研工作台

## 产品定位

EasyDesign UI 是运行在 `127.0.0.1` 的单用户科研工作台。它通过同一套 Python
application/orchestration API 创建、验证、执行、恢复和审阅 run，不在浏览器中复制
科学逻辑，也不建立第二套科学事实数据库。

信息结构固定为：

```text
Project
└── Run
    └── Stage 01–07
```

软件能力状态和单次 run 状态必须分别展示。例如 Stage 06/07 的通用能力可以是
`implemented`，但在 APOE Stage 05 发布 `stopped-no-scale-winner` 后，该次 run 的
Stage 06/07 只能是 `not-reached`。

## 视觉与交互

- 暖灰白工作区、深墨色文本、青绿色主操作色和深色 Mol* 画布。
- 蓝色表示运行中，琥珀色表示待审批，紫色表示科学停止，红色只表示运行故障。
- 默认层显示结论、风险、关键数字和下一动作；专家抽屉显示 manifest、参数、日志、
  checksum 与原始 artifact。
- 桌面优先，适配 1280–1920 像素；状态必须同时使用文字、形状和颜色。
- 页面不访问 CDN、外部字体或远程分析服务。

## 页面

1. 首页：项目、最近运行、待审批、环境和科学停止。
2. 新建设计：六类 Stage 01 输入、design intent、Stage 02 路线、预算和 YAML。
3. Run 工作台：七阶段轨道、阶段证据和审计抽屉。
4. Decisions：身份、结构、hotspot、放大预算和候选包审批。
5. Environment：core、Protenix、BoltzGen、PyMOL、ScanNet、TNP、GPU 和磁盘。
6. Audit：配置、代码身份、profile、manifest revision、checksum 和事件。

## 状态语义

```text
draft
validating
ready
queued
running
awaiting-human-approval
succeeded
scientific-stop
operational-failed
not-reached
simulated-preview
```

`scientific-stop` 表示软件正常完成、科学门槛未通过；它不是 operational failure。
`simulated-preview` 必须始终带演示标识，不能修改 run manifest 或占用 GPU。

## 数据与安全边界

- 只读取 RunManifest 当前声明的 StageManifest 和其 ArtifactRef。
- 每次展示或下载 artifact 前验证大小和 SHA-256。
- 浏览器只接收由 manifest 派生的短期 artifact token，不接收服务器绝对路径。
- 服务固定绑定 `127.0.0.1`；禁止任意 CORS、路径穿越和 symlink 逃逸。
- 长任务只从原子 `progress.json` 和 append-only `task-events.jsonl` 读取状态。
- UI 的“停止”首版只表示完成当前任务后停止调度，不强杀当前 backend。
- 实际向供应商下单永远不是自动动作；UI 最多生成 `draft-order-package` 并请求人工审批。

## APOE 验收边界

- Stage 01–04：显示真实完成产物。
- Stage 05：显示 840 pilot、唯一 Tier A、扩展至 100、12 local-gate pass、Top 10
  Protenix 和 `stopped-no-scale-winner`。
- Stage 06/07：显示软件能力已实现、当前 APOE run 未到达。
- “回放已验证案例”只重放已审计状态；“按相同配置重新运行”创建新 run，并在资源预检和
  用户确认后启动真实 backend。
- APOE runtime、PSE、大型候选和模型不得提交 Git；自动测试使用小型通用 fixture。

## 完成门槛

- React/TypeScript 工作台从 Python wheel 提供，Node.js 只用于构建和测试。
- `easydesign ui serve` 能启动 localhost 服务并打印 SSH 端口转发提示。
- 新建设计、配置校验、doctor、执行、审批、进度、停止调度和恢复调用统一 Python API。
- 七阶段视图从 manifest/artifact 投影，不硬编码 APOE ID、残基或候选数量。
- Playwright 覆盖主要状态、Mol*、artifact 下载、回放隔离和 draft-order gate。
- Proteindigger1 真实 APOE run 的 UI 投影与 CLI/API 证据一致。

## UI-001 验收结果

- 完成时间：2026-07-26T13:19:19+08:00
- 版本：`0.1.0.dev6`。
- 启动入口：`easydesign ui serve --runs-root RUNS_ROOT --port 8765`；固定监听
  `127.0.0.1`，远程机器通过 SSH 端口转发访问。
- Python 3.11：`make check` 通过，235 passed、8 个需要显式 PyMOL 环境的集成测试
  按预期 skipped；wheel 同时包含 Workbench、Mol* Target Viewer 和 VHH7 资产。
- 浏览器：本机 Chromium 1440/1920 与 Firefox 共 9/9 通过；Proteindigger1
  Chromium 1440/1920 共 6/6 通过。
- 真实证据：
  `/root/autodl-tmp/Protein_design/easydesign-clean/runs/apoe-s02-006-pse/`
  `20260726-004-stage05-pilot-filter` 投影为 Stage 01–04 `succeeded`、Stage 05
  `scientific-stop`、Stage 06/07 `not-reached`；完整性为 `verified`。
- Stage 05 页面来自 manifest 的事实为 840 pilot、1 个 Tier A、100 expansion、
  12 local pass、10 Protenix prediction、0 full-target gate pass。UI 只登记
  `VAL-003 planned`，不把当前现象宣称为 Protenix bug。
- 完成范围：UI-001、ENG-009 与 UI-003 达到 `smoke-validated`；UI-002 的接口和界面
  达到 `implemented`，下一条可继续的真实 run 仍需做长任务启动、drain、审批和恢复
  浏览器 smoke。
