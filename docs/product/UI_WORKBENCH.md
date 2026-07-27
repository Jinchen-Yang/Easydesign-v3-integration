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

- 版本：`0.1.0.dev12`。
- `examples/apoe-ui-demo` 保存经用户授权的私有仓库只读证据包：307 个被逐一固定
  SHA-256 的文件、约 65 MiB，不包含约 970 MB 的 backend 中间目录。
- 共享包保留 Stage 01–05 manifest 闭包、21 个策略、840/100/12/10 各层结果、Stage 04
  双 GPU 历史和重点候选结构；Stage 06/07 继续显示“尚未开始”。
- `serve_ui_evidence_bundle.py` 在启动前验证 bundle 清单与 Run/Stage manifest 闭包，
  然后只把包内 `evidence-runs` 注册为工作台事实来源。
- 共享包只供协作审阅，不能恢复任务、重新计算或替代服务器完整 run；其中 APOE
  `stopped-no-scale-winner` 仍是可审计科学负结果。

## UI-008：远程执行与协作查看

- “新建设计 → 预算与资源”列出当前服务器和 runtime profile 显式声明的远端；选择不会
  写入科学 YAML。远端 preflight 先验证控制端配置和 SSH/version/GPU/disk 探针，提交
  冻结输入后再在远端执行配置校验与按需 doctor。
- “运行任务”列出控制端已知远程任务，可读取 worker 与结构化 progress、同步
  metadata 镜像，并在 worker 已停止时显式恢复。运行中的 worker 禁止重复 resume。
- metadata 镜像进入同一个本地 runs root 后，项目、运行和 Stage 页面复用现有
  manifest-only 投影；浏览器不直接访问 SSH、不接收私钥、IP 或远端绝对路径。
- Stage 04/06 的运行设备卡片显示最新 task heartbeat。旧版 worker 没有 heartbeat 时
  如实显示现有结构化进度，不扫描中间目录补猜。
- 远端选择、preflight 文案和启动解锁已在 Chromium 1440×900、1920×1080 验收；
  Python gateway 另有 profile-only executor 列表契约测试。

## UI-009：三种设计路线、项目整理与交互式选区

版本：`0.1.0.dev13`。

“新建设计”首先要求选择产品路线，而不是把所有用户塞进同一张七阶段表单：

1. 全流程设计：Stage 01–07 始终可以浏览和配置；输入不完整只阻止“检查并启动”，不
   阻止理解后续阶段。运行方式只有“连续运行”和“遇到科学选择暂停确认”，分别映射到
   `unattended` 与 `review-gated`。
2. 按步骤设计：第一次只填写 Stage 01；成功后直接进入目标结构结果页，再点击“配置
   下一步”。未改变已完成上游科学选择时，新 config revision 继续同一个 run；重新选区、
   更换 target 或改写已完成 Stage 参数时才创建带 lineage 的分支 run。两种方式都不覆盖
   历史 manifest/artifact。
3. 开发者自检：快速确定性工程自检与真实后端微型自检分开；自检运行不出现在“我的
   项目”，也不能作为科学输入。

项目页默认只显示 `project-run`。设置中的项目目录可以归档/恢复历史案例；归档后的
`archived-project-run` 与 `developer-smoke-run` 不污染科研项目和运行任务列表。

Stage 02 结果页提供“重新选择结合区域”：

- PSE 来源颜色、当前批准区域和本次编辑区域为三个独立图层。
- 可以隐藏来源颜色、清空编辑层、点击结构/序列、Shift 连选、粘贴编号和使用橡皮擦。
- A/B/C 分别为红/蓝/黄，一个残基只能属于一个编辑区域。
- 保存要求逐区理由、批准人和证据限制确认，并建立新的 Stage 02 分支。

Mol* 不再以 canvas DOM 存在或 hierarchy 中只有 model 作为成功。Viewer 单实例串行加载
结构状态，首次强制相机取景；结构和 representation 都建立后才显示“结构已就绪”。快速
切换阶段、候选和表示时，过期异步任务不能销毁或覆盖新实例。

当前验收边界必须如实区分：快速确定性七步自检已经实现；真实后端微型自检尚未完成固定
非 APOE coherent Stage 01–05 和 Stage 06/07 probe，因此产品按钮只生成
`not-started` 记录，不能显示为通过。

dev13 真实验收补充：

- 普通项目页严格只显示 `apoe-s02-006-pse` 与 `apoe-fasta`；归档和开发自检分别进入
  设置中的独立目录。
- `apoe-fasta/20260727-002-stage01-protenix` 真实消费 143 aa FASTA 与 609-depth A3M，
  Mol* 在 `#EEF1F6` 画布上建立真实 representation；非背景像素占整页约 5.2%。
- APOE PSE Stage 02 编辑器真实显示结构、来源红蓝黄和编辑层，并建立
  `20260727-003-stage02-reselection-lineage`。产品会话记录 revision、run key 和
  `awaiting-human-approval`，旧科学 run 不变。
- continuation 不复用旧项目的悬空相对路径：Stage 01 冻结输入与预计算 MSA 按
  SHA-256 原子复制到新项目，并使用可移动的相对引用。

## UI-010：项目主展示运行

“我的项目”中的一张卡片代表项目，不等于项目中最新创建的分支。项目可以在运行索引中
显式指定一条“主展示运行”：

- 首页使用指定运行呈现阶段进度、最近结论和“查看项目”入口。
- 同项目中更晚创建的科学分支、等待确认分支或远程探索运行仍保留在运行任务和历史
  运行中，不会覆盖项目卡片。
- 未指定主展示运行的项目继续采用最近更新的可验证运行，保持旧索引兼容。
- 选择动作只更新可再生导航索引；科学 manifest、artifact 和 checksum 保持不变。

当前服务器明确指定：

- `apoe-s02-006-pse` → `20260726-004-stage05-pilot-filter`，首页展示 Stage 01–05
  真实结果与 Stage 05 科学停止。
- `apoe-fasta` 未被本次操作修改，继续展示原有 Stage 01 Protenix 结果。

维护入口：

```bash
easydesign projects select-primary PROJECT_ID \
  --run-id RUN_ID \
  --runs-root RUNS_ROOT
```

## UI-011 / ENG-019：按步骤 Stage 01 单页运行

版本：`0.1.0.dev16`。

按步骤设计的第一次运行不再复用全流程向导的“第5项·启动前检查”：

```text
选择 PSE
→ 本地服务流式接收
→ 在当前页面校验配置和 PyMOL 环境
→ 启动 Stage 01
→ 轮询结构化任务状态
→ 直接打开第1步结构审查
```

- PSE 原始字节直接传给 localhost gateway，不再先由浏览器 `FileReader` 生成完整 Base64
  副本。64 MiB 上限同时由浏览器和服务器执行；浏览器请求有 120 秒有界超时。
- 上传只能进入“文件已接收”或“文件接收失败”终态；失败时在同一页面显示原因并允许
  重选，不能无限停在“正在接收文件”。
- PSE receipt 成功即代表用户授权执行本次低成本 Stage 01 导入。草稿创建、配置校验、
  doctor 和任务启动仍真实执行，只是不再暴露为三张工程按钮。
- 第1步运行中在原页面显示“建立配置 / 检查环境 / 准备目标结构”；失败可在原页面重试。
  成功后通过 job 的 `run_key` 打开正式 RunManifest 投影，而不是扫描输出目录猜结果。
- FASTA/序列等可能触发预测的入口仍在同一页面显示“开始准备结构”操作，保留高成本动作
  的明确授权，但不会跳转到通用第5项页面。
- 全流程设计继续保留独立的草稿、preflight 和真实启动步骤；本次收敛只影响按步骤路线。
- localhost job 必须写入 UI 配置的 `runs_root`，并把 session ID、Stage 编号和最终
  run key 写回 DesignSession lineage。

## UI-012：Stage 02 可编辑区域状态

版本：`0.1.0.dev16`。

区域编辑器不再让只读颜色和可保存成员呈现相互矛盾的状态：

- 有当前批准区域时，打开编辑器即复制到本次可编辑层。
- 尚无 Stage 02、但 PSE 存在标准红/蓝/黄时，复制 PSE 来源区域。
- 两类上游区域都不存在时才显示 A/B/C 为 0。
- “从空白开始”会清空本次编辑层并隐藏 PSE/当前批准参考层；上游 artifact 不受影响。
- “恢复上游区域”重新复制优先级最高的上游区域。
- 选择 A/B/C 只表示切换画笔；点击结构、点击序列或粘贴规范编号后才改变成员。
- 每次增删显示实际 `label_seq_id`，三维画布使用十字光标，避免用户误以为只点击画笔
  就完成了残基选择。

APOE PSE 的初始可编辑计数必须为 A/B/C `9/14/14`。从空白开始后为 `0/0/0`，此时
参考颜色同时隐藏；恢复后回到 `9/14/14`。
