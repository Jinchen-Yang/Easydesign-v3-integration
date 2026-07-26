# EasyDesign 产品级科研工作台

## 产品定位

EasyDesign UI 是运行在 `127.0.0.1` 的单用户科研工作台。它通过同一套 Python
application/orchestration API 创建、验证、执行、恢复和审阅 run，不在浏览器中复制
科学逻辑，也不建立第二套科学事实数据库。

产品面向计算人员和湿实验人员组成的混合团队。默认界面先解释“当前结果、为什么、下一步
做什么”，专家信息再进入运行内的“技术记录”。信息结构固定为：

```text
我的项目
└── 某次运行
    ├── 第1步至第7步
    └── 技术记录
```

软件能力状态和单次 run 状态必须分别展示。例如 Stage 06/07 的通用能力可以是
`implemented`，但在 APOE Stage 05 发布 `stopped-no-scale-winner` 后，该次 run 的
Stage 06/07 只能是 `not-reached`。

## 视觉与交互

- 视觉继承 Stage 01 Viewer：浅灰背景、白色工作区、蓝色主操作和清晰边框；第1/2/5/7步
  的 Mol* 画布统一使用浅灰白 `#EEF1F6`，加载层、工具栏和结构控制均采用浅色体系。
- 正文 16px，表格与按钮 14px，次要说明 13px，技术元数据不低于 12px；禁止 7–10px
  产品正文。
- 蓝色表示运行或选中，琥珀色表示等待确认，紫色表示未达到科学继续条件，红色只表示
  真正的运行错误。
- 状态必须同时使用中文、形状和颜色；默认页面除 EasyDesign、BoltzGen、Protenix、
  Mol*、RMSD、iPTM、PAE 等品牌或科学缩写外使用中文。
- 第1/2/5/7步共用“左侧信息和控制＋右侧大 Mol* 画布”的结构工作区。
- 桌面优先，适配 1280–1920 像素；页面不访问 CDN、外部字体或远程分析服务。

## 页面

左侧主导航只保留：

1. 我的项目：target、最近结论、当前步骤、待确认和下一步建议。
2. 新建设计：六类目标输入、设计意图、第2步路线、预算和同步 YAML。
3. 运行任务：正在运行、等待确认、已完成、未达到继续条件和运行失败。

待确认以右上角动态通知进入对应任务；运行环境进入“设置”；配置、代码身份、运行记录、
文件完整性和原始输出进入单次运行的“技术记录”，不占据用户首屏。

七阶段显示名固定为“准备目标结构、选择结合区域、生成设计方案、小规模生成、筛选与
验证、规模化生成、最终候选”。第3步使用真实区域 × scaffold 矩阵；第4/6步共用任务、
GPU、吞吐和 ETA 组件；第5步默认先显示筛选证据，再提供“策略比较 / 候选筛选 /
指标说明 / 结论与原因”专家入口。科学停止只能作为证据链末端结论，不能隐藏已形成的
策略、候选、指标或结构。

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

默认界面将 `scientific-stop` 译为“未达到继续条件”，并固定解释“程序已正常完成，但
当前结果没有达到进入下一步的科学门槛”；它不是运行失败。
`simulated-preview` 必须始终带演示标识，不能修改 run manifest 或占用 GPU。

## 数据与安全边界

- 只读取 RunManifest 当前声明的 StageManifest 和其 ArtifactRef。
- 每次展示或下载 artifact 前验证大小和 SHA-256。
- 浏览器只接收由 manifest 派生的短期 artifact token，不接收服务器绝对路径。
- 服务固定绑定 `127.0.0.1`；禁止任意 CORS、路径穿越和 symlink 逃逸。
- 长任务实时状态只从原子 `progress.json` 和 append-only `task-events.jsonl` 读取；
  已完成运行从 StageManifest 声明的 task table、终态 progress 和 events 恢复设备历史。
- UI 的“停止”首版只表示完成当前任务后停止调度，不强杀当前 backend。
- 实际向供应商下单永远不是自动动作；UI 最多生成 `draft-order-package` 并请求人工审批。

## APOE 验收边界

- Stage 01–04：显示真实完成产物。
- Stage 05：显示 840 pilot、唯一 Tier A、扩展至 100、12 local-gate pass、Top 10
  Protenix 和 `stopped-no-scale-winner`。
- Stage 06/07：显示软件能力已实现、当前 APOE run 未到达。
- “回放已验证案例”只重放已审计状态；“按相同配置重新运行”创建新 run，并在资源预检和
  用户确认后启动真实 backend。
- APOE 完整 runtime、模型和后端中间目录不得提交 Git；自动测试使用小型通用 fixture。
  经 DATA-004 明确授权的精简只读 evidence bundle 可以提交私有 `main`，但必须保留
  manifest 闭包、逐文件 SHA-256、科学停止语义，并明确不能恢复任务或替代完整 run。

## 完成门槛

- React/TypeScript 工作台从 Python wheel 提供，Node.js 只用于构建和测试。
- `easydesign ui serve` 能启动 localhost 服务并打印 SSH 端口转发提示。
- 新建设计、配置校验、doctor、执行、审批、进度、停止调度和恢复调用统一 Python API。
- 七阶段视图从 manifest/artifact 投影，不硬编码 APOE ID、残基或候选数量。
- Playwright 覆盖主要状态、Mol*、artifact 下载、回放隔离和 draft-order gate。
- Proteindigger1 真实 APOE run 的 UI 投影与 CLI/API 证据一致。

## Stage 05 产品投影

- `overview` 回答本次结论、真实数量、转化链、失败规则和下一步建议。
- `strategies` 提供全部策略的区域、scaffold、候选数、去重数、hard/final gate、Tier、
  `S_screen`、前四分位均值、`F_YAML`、是否扩展、原始 YAML 安全下载和规范指标聚合。
- 策略身份只能从 Stage 03 `strategy-bundle` / `design-matrix` 与 Stage 05 report 的
  ArtifactRef 联接，禁止拆 strategy ID 字符串猜 region 或 scaffold。
- 指标聚合保存有效样本数、缺失数、均值、中位数、最小值和最大值；缺失值不得按零填充。
- `candidates` 后端分页访问 pilot、expansion 和 full-target 三个 phase，page size
  最大 100，排序字段采用白名单。
- `candidate detail` 展示序列、全部规范指标、原始 BoltzGen 指标、逐规则实测值/操作符/
  阈值/结论、淘汰原因和 original/refold/Protenix 结构切换。
- `metrics` 统一解释中文名称、科学缩写、定义、单位、来源、方向、用途、当前阈值和
  缺失值处理。
- JSON 报告按 artifact SHA-256 建立进程内只读缓存；不增加数据库。

## Stage 04/06 执行投影

统一接口：

```text
GET /api/v1/runs/{run}/stages/4/execution
GET /api/v1/runs/{run}/stages/6/execution
```

返回计划/成功/失败/待重试任务、候选数、耗时、吞吐率、ETA，以及每张 GPU 的当前任务、
历史策略或 shard、attempt、失败重试、候选数和累计运行时间。正在运行时由 SSE 发送同一
`ExecutionProgressProjection`，前端直接应用结构化 payload；终态页面从 manifest
声明的 task table/progress/events 重建历史，不以“当前 GPU 已空闲”为由丢失执行证据。
老运行确实没有设备记录时明确显示“此运行未记录历史设备分配”。

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

## UI-004 / ENG-010 / UI-005 / UI-006 / ENG-011 重构结果

- 版本：`0.1.0.dev8`。
- 主导航收敛为“我的项目 / 新建设计 / 运行任务”；“运行任务”没有选中运行时展示任务
  列表，不再落入技术审计。
- 产品术语、字号和颜色形成统一 token；内部工程词从默认页面移至技术记录。
- 第1/2步采用 Stage 01 Viewer 的左栏＋大 Mol* 结构工作区；第3步采用真实设计矩阵；
  第4/6步共用进度视觉；第6/7步继续区分软件能力与 APOE 本次未到达状态。
- 第5步的 840/100/10 候选和 21 个策略通过分页产品投影访问，全部规范指标、原始
  BoltzGen 指标、规则门槛、失败原因与候选结构均可进入详情。
- 第5步默认按“21 个策略与 Tier → 扩展策略 → 12 个初筛候选 → 10 个 Protenix 结果
  → 第6步条件判断”展示；APOE 的 `1/1/5/14` Tier 分布和最低约 `18.00 Å` 的观测
  binder pose RMSD 均保留，但不会被误称为通过者。
- 第4步现有 APOE 运行无需重跑，即可从结构化任务记录恢复 GPU 0 的 11 个策略/
  440 个候选/14 attempts 与 GPU 1 的 10 个策略/400 个候选/14 attempts。
- 未改变 Stage 05 门槛、APOE `stopped-no-scale-winner` 结论或任何历史运行记录。

## UI-007 / ENG-012 新建设计向导

- 版本：`0.1.0.dev9`。
- 顶部“目标输入 / 设计意图 / 区域策略 / 预算与资源 / 检查并启动”都是可点击的真实
  页面，不以第一项完成度阻止浏览；每项同时显示待填写、正在接收、已设置或检查通过。
- 第2项明确展示当前 1.0 的 VHH profile、blocking/nonblocking/detection/imaging/
  exploratory 意图和 review-gated/unattended 运行方式；第3项解释 PSE 染色检测与
  SASA/ScanNet 的独立关系；第4项解释 Stage 03/04/06 的默认预算和到达条件。
- 本地文件选择会立即传给 localhost gateway。界面只有在后端返回文件名、大小和
  SHA-256 receipt 后才显示“文件已接收”；失败、超限、空文件和重选都有独立状态。
- 第5项集中显示输入、意图、区域和范围 readiness；“生成项目草稿 → 检查配置与环境 →
  确认并真实启动”按顺序解锁，并在按钮下直接说明当前未开放的原因。
- 草稿创建后目标输入冻结，避免浏览器选择与已复制到项目中的事实来源发生漂移；专家
  修改 canonical YAML 后必须重新执行 preflight。

## DATA-004 / UX-005 共享案例

- 版本：`0.1.0.dev10`。
- `examples/apoe-ui-demo` 保存经用户授权的私有仓库只读证据包：307 个被逐一固定
  SHA-256 的文件、约 65 MiB，不包含约 970 MB 的 backend 中间目录。
- 共享包保留 Stage 01–05 manifest 闭包、21 个策略、840/100/12/10 各层结果、Stage 04
  双 GPU 历史和重点候选结构；Stage 06/07 继续显示“尚未开始”。
- `serve_ui_evidence_bundle.py` 在启动前验证 bundle 清单与 Run/Stage manifest 闭包，
  然后只把包内 `evidence-runs` 注册为工作台事实来源。
- 共享包只供协作审阅，不能恢复任务、重新计算或替代服务器完整 run；其中 APOE
  `stopped-no-scale-winner` 仍是可审计科学负结果。
