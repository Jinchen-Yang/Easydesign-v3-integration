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
- 结构画布支持鼠标滚轮、触摸屏双指缩放、单指旋转和平移；画布内手势不触发页面缩放
  或滚动。
- 桌面优先，适配 1280–1920 像素；页面不访问 CDN、外部字体或远程分析服务。

## 页面

左侧主导航只保留：

1. 我的项目：target、最近结论、当前步骤、待确认和下一步建议。
2. 新建设计：六类目标输入、设计意图、第2步路线、预算和同步 YAML。
3. 运行任务：正在运行、等待确认、已完成、未达到继续条件和运行失败。

待确认以右上角动态通知进入对应任务；当前设备、公共算力和项目存档进入“设置”；配置、代码身份、运行记录、
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
- Stage 05：旧 v1.5 run 显示 840 pilot、唯一 Tier A、扩展至 100、12 local-gate
  pass、Top 10 Protenix 和 `stopped-no-scale-winner`；v1.6 continuation 另行显示
  “1 组晋级＋full-target pose warning”，不能覆盖旧结论。
- Stage 06：历史人工授权的单策略 50k 显示真实完成证据；原生 v1.6 页面同时支持一至
  三个晋级 YAML 的共享预算与逐策略进度。
- Stage 07：显示软件能力已实现；APOE 在采用历史 50k 并完成远端后端 probe 前仍为
  `not-reached`。
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
- 可以隐藏来源颜色、清空编辑层、点击结构/序列、Shift 连选和粘贴编号。
- 不提供独立橡皮擦；同一画笔再次点击已属于该区域的残基即取消选择，Mol* 与序列使用
  同一个交互规则。
- A/B/C 分别为红/蓝/黄，一个残基只能属于一个编辑区域。
- 保存要求批准人和证据限制确认；逐区保守说明由 Python 契约生成，并建立新的 Stage 02
  分支。

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

## UI-013 / REP-005：简化区域确认与触摸手势

版本：`0.1.0.dev17`。

- 区域 A/B/C 的成员已经在画笔区和序列中清楚呈现，确认区不再重复展示三套“设计目的、
  生物学理由、结构理由”表单。
- 设计目的沿用项目级 `design.intent`；EasyDesign 只生成关于用户选择、编号映射和坐标
  存在性的保守说明，不虚构生物学依据或自动结构优选。
- 用户仍需填写一次批准人，并确认人工区域不等于已经验证的真实结合位点。
- Workbench 第1/2/5/7步与便携 Stage 01 Viewer 均覆盖 Mol* 内联
  `touch-action: manipulation`，将双指缩放交还给 Mol*。
- 浏览器门禁同时检查 Workbench 宿主和真实便携 Viewer canvas 的计算样式为
  `touch-action: none`。

## UI-014 / ENG-020：Stage 02 continuation 与真实任务进度

版本：`0.1.0.dev19`。

- Stage 02 重新配置不是固定时长等待。automatic 和人工选区都从 checksum 正确的
  Stage 01 成功前缀建立新分支；来源 run 可处于等待确认或包含旧的后续阶段。
- 人工选区的批准人和两项 acknowledgement 就是本次人类批准。Stage 02 成功发布
  `hotspots.yaml` 后不再追加第二次相同审批。
- automatic `review-gated` 仍会在候选生成后等待用户选择；这是真实科学门，不与人工
  提交混为一谈。
- 页面只在后台 job 真实处于 `queued/running` 时显示进度条，并每秒读取 job record。
  终态后自动打开新 run；失败时显示结构化错误，不让用户反复点击创建重复分支。
- Mol* 与序列残基采用统一 toggle：当前画笔首次点击选中，再次点击取消；切换画笔后
  点击则把残基移动至新区。
- 人工提交区不再用一条远离问题字段的普通提示表达校验失败。按钮会直接说明尚缺批准人
  或证据限制确认；点击后问题字段变为红色、获得键盘焦点并通过 `role=alert` 告知辅助
  技术。确认完成后才恢复“保存并建立新的第2步分支”，随后展示真实任务进度。

## UI-015 / ENG-021：连续七阶段工作区

版本：`0.1.0.dev20`。

按步骤设计不再把“已完成结果页”和“下一步配置弹窗”分成两套界面。项目运行页本身就是
七阶段连续工作区：

```text
第1步结果
→ 平滑切换到第2步内嵌配置
→ 第2步任务完成
→ 自动切换到第3步配置
→ 第3步任务完成
→ 自动切换到第4步
→ 依次推进到第7步
```

- 顶部七阶段轨道始终可点击。点击只改变当前查看内容，不会启动任务或修改科学结果；
  当前步骤自动滚入可视范围。
- Stage 02 区域编辑器直接嵌入运行页，不再以覆盖 Stage 01 的全屏弹窗出现。已完成
  Stage 02 的“重新选择区域”也复用同一工作区，但仍通过新分支保护历史结果。
- 尚未开始、且上游连续成功的 Stage 03–07 显示该步骤的真实配置摘要和启动动作，不再
  显示由破折号组成的空结果卡片。
- 表单标题、说明、按钮和默认值来自 Python `stage_form_definition()`；React 只展示
  投影，不另存一套科学默认参数。
- Stage 03 根据 Stage 02 正式结果展示真实的
  `区域数 × official-vhh7-v1 七个骨架 × 每方案候选预算`。点击只生成并验证 BoltzGen
  YAML，不会提前启动 Stage 04。
- Stage 04 和 Stage 06 在用户确认真实计算资源后才启动；其余步骤同样通过统一
  continuation job 创建、轮询和终态跳转。
- 后台任务处于 `queued/running` 时显示真实进度；`succeeded` 后打开下一步，
  `awaiting-human-approval` 时停留在当前步骤，失败则保留结构化错误。
- 页面切换使用 180 ms 的方向动画，并尊重系统 `prefers-reduced-motion` 设置。

当前产品边界：用户仍需逐步点击每一阶段的启动动作；这不是默认自动启动高成本 GPU
任务。连续无人值守模式继续由 canonical YAML 的 `workflow.execution_mode` 控制。

续跑状态必须按“成功 Stage 前缀”判断，而不是要求整个 Run 已经终态成功。按步骤设计在
等待用户配置下一步时，Run 保持 `running` 是正常状态；只要 Stage 01 至当前上游阶段
连续为 `succeeded`、StageManifest 与 ArtifactRef 完整性通过，就可以发布新的配置
revision 并执行下一阶段。`failed`、`cancelled`、前缀不连续或上游校验失败仍明确拒绝。

## UI-016 / VAL-006：仓库内安装中心与真实后端逐步自检

版本：`0.1.0.dev23`。

安装与环境页面直接读取仓库内 `runtime/` 的不可变环境/资产 revision，不读取
`/root/.config/easydesign`，也不扫描系统 Conda。七个环境和模型分别显示：

```text
未安装 / 安装中 / 待许可 / 可用 / 失败
```

- “安装计划”显示环境、资产、下载量、磁盘峰值、许可与目标相对路径。
- 环境状态会区分当前 lock 的 `available` 与旧 lock 的 `outdated`；旧目录继续保留。
- BoltzGen 只有五个 checkpoint、molecule dataset 和固定源码七项全部可用时才显示
  “可用”，不能因 Python package 已安装而提前解锁 Stage 04/06。
- “完整安装”调用与 `./easydesign setup` 相同的 Python API；UI 只轮询结构化 setup
  记录，不解析终端输出。
- 安装中心与 CLI 共用 `orchestration.setup_jobs`。安装 worker 脱离浏览器/SSH session
  运行，UI 重启后通过 request/process/result 恢复真实状态；不再出现
  `finished-before-ui-restart` 这种无法判断成功与否的模糊状态。
- 安装中心同时提供 PyMOL/PSE、Protenix-v2、ScanNet、BoltzGen 和 TNP 的独立安装
  动作。每张组件卡片展示本组件当前增量峰值和磁盘门；许可确认仍精确绑定资产，单组件
  按钮不得扩大为其他后端的安装授权。
- 缺后端时新项目页面指向具体环境或资产，不再抛出 profile 文件不存在。
- `./easydesign ui` 自动使用当前工作区的 profile、projects 和 runs。

真实后端微型自检已从只登记记录升级为逐 Stage 执行器：

```text
固定 1UBQ mmCIF asset
→ PyMOL 生成 runtime-only 单 target PSE
→ Stage 01–05：1 个区域 × 1 个官方 scaffold × 极小候选预算
→ Stage 06/07：各执行一个真实 adapter probe
```

它与普通“按步骤设计”共用七阶段轨道、job、continuation、结构和指标页面。每一步都由
用户明确点击；环境/模型未就绪时记录 `blocked` 和具体缺项，不会创建假成功 run。
Stage 05 没有 Tier A 可以合法结束为科学停止；Stage 06/07 probe 只验证 adapter 健康，
不伪造主线的 scale winner 或最终候选。所有记录分类为 `developer-smoke-run`，禁止用于
科学结论或下单。

当前交付边界：执行器与产品投影已实现；只有 Proteindigger 上七个环境、所需资产许可、
checksum 和真实逐步运行全部完成后，`VAL-006` 才能从 `implemented` 升级为
`smoke-validated`。

安装中心与 doctor 必须区分三种事实：

1. profile 已声明某后端；
2. 当前 lock 的环境与全部必需资产是否可用；
3. 本次科学配置是否实际需要并已探测该后端。

普通 `doctor` 允许 core/UI 工作区在科学后端尚未安装时启动；`doctor --full` 则把每个
未达到第2项的科学后端记为失败并返回非零状态。界面不得把“已声明但未完整安装”翻译成
“profile 文件不存在”。

## REP-006 / UI-017：浏览器 PyMOL 与可收起结构助手

版本：`0.1.0.dev24`。

Stage 01/02 的统一结构工作区默认显示浏览器 PyMOL，Mol* 作为平级标签切换。两者读取
同一份经过 checksum 验证的 `target.cif`，共享当前残基、A/B/C 图层和 label/auth
编号；PSE 原始红/蓝/黄通过 `source-annotations.json` 重建，不把颜色写回 mmCIF。

浏览器 PyMOL 提供对象/链/序列、cartoon/surface/stick、颜色、标签、居中、视角、安全
PML 控制台与 PNG/PML/PSE 导出。鼠标旋转、触摸选择、双指缩放和平移均由画布接收；
加载进度、Pyodide/WebGL 错误和内存释放必须有可见终态。所有坐标修改、对象删除、任意
Python/PML 和对 Target Bundle 的覆盖都被拒绝。

右侧助手栏可收起。该段保留 REP-006 初始产品边界的历史背景；当前 provider 已由部署者
在仓库内统一配置，普通使用者不填写 API key。初始的多分支 proposal 协议也已由
REP-009 的完整 PML 四字段协议取代。

“寻找最佳区域”不得直接改变结构或选区。只有用户提交区域、通过 mapping/坐标/checksum
校验并完成证据限制确认后，系统才建立新的 Stage 02 branch。助手会话本身不是科学结果，
也不能作为下单依据。

## UI-018 / REP-007：可靠项目草稿、双查看器动作与递进冻结

版本：`0.1.0.dev28`。

“我的项目”同时投影正式运行和有效项目草稿。草稿必须已经原子发布
`project-metadata.json`、canonical 配置和输入；空 DesignSession、失败上传及 staging
不能形成项目卡片。同一项目存在正式运行时只显示正式项目卡，草稿可从“继续设计”恢复。

项目创建采用事务边界：

```text
项目名预检
→ 持久 UploadReceipt 0.2
→ 配置与环境预检
→ runtime/tmp 中的全新 staging
→ 原子发布 projects/<project_id>
→ 最后创建 DesignSession
```

项目名冲突在上传前返回建议名称。上传内容、回执及 SHA-256 在服务重启后仍可重试；
相同待处理文件复用一份 receipt。成功发布时输入移动到项目目录，不保留第二份暂存副本。
项目 ID 在上传前同时校验规范格式：只允许小写字母、数字、点、下划线和连字符；例如
`Test` 会在接收文件前提示使用 `test`，不会等到 YAML 发布时暴露底层校验错误。
7 天以上只给出清理建议；1 GiB 提醒、5 GiB 阻止新上传。两个阈值由仓库根
`easydesign-workspace.yaml` 的
`upload_warning_bytes/upload_blocking_bytes` 声明。EasyDesign 不运行定时删除，
也不把项目、运行、环境、模型或普通 quarantine 纳入上传清理范围。任何物理删除仍必须
由使用者针对清单中的精确路径另行批准并留审计记录。

## REP-008 / ENG-028 / UI-020：隔离式 PyMOL 生命周期与平台结构助手

同一结构工作区内的 PyMOL 与 Mol* pane 持续挂载，切换查看器只调整显隐和交互焦点。
浏览器可以复用已经下载的 Pyodide/PyMOL 静态资产，但不能跨
`NativePyMOLViewer` 挂载复用 Pyodide/PyMOL 运行时：Emscripten 的 WebGL context 与
首次创建它的 canvas 绑定，尝试把全局运行时改绑到新 canvas 会出现对象已经读取但画布
空白、切回失败或绘制到已脱离 DOM 的旧 canvas。每个真实挂载因此创建独立运行时；
返回同一已挂载 pane 时，在布局稳定后的两个浏览器帧执行 canvas backing size、PyMOL
reshape、OpenGL viewport 和 redraw。Stage 01/02 必须覆盖
`PyMOL → Mol* → PyMOL` 以及跨 Stage 往返的真实结构回归。

dev28 的回归修复进一步固定：

- 两个 viewer pane 始终挂载；非活动 pane 只使用 `opacity` 和 `pointer-events`，
  禁止 `visibility:hidden` 触发 WASM/WebGL 画布失效。
- 只缓存 `pyodide.js` 与 WASM/包资产；每个新 PyMOL canvas 创建独立运行时，禁止
  全局 `pyodidePromise` 跨组件复用。
- 结构 identity 与显示 revision 分开。切换 tab 或恢复显示版本不得删除对象、重复下载
  `target.cif` 或重建 PyMOL runtime。
- 场景只由基础显示、最新 ViewState 和最新专家 PML 组成，禁止把全部历史 revision
  重新拼接执行。
- PyMOL ready 必须有对象、原子和可见表示；无 `preserveDrawingBuffer` 时
  `readPixels` 可能读到空帧，因此它只用于诊断和浏览器视觉测试，不作为唯一运行门。
- Stage 01 不载入 Stage 02 辅助参考结构；Stage 02 的可选参考结构失败只形成 warning，
  不能遮蔽已经成功载入的 target。

结构助手是 EasyDesign 平台能力，不是用户自带密钥功能：

- 普通界面只显示“EasyDesign 结构助手”和可用状态；
- 不显示 provider、模型、endpoint、key 掩码或配置表单；
- 部署者只在
  `runtime/secrets/structure-assistant/platform-provider.yaml` 配置一个服务；
- 服务端不在 DeepSeek 与智谱 GLM 之间静默 fallback；
- 前端状态接口不得泄露 provider、模型、endpoint 或密钥；
- 没有平台助手时，PyMOL、Mol*、手工选区、SASA 和 ScanNet 保持可用。

浏览器 PyMOL 的 ready 状态必须依次通过静态资源、Pyodide、NumPy/PyMOL、WebGL、
`target.cif`、对象/原子、表示、相机和非背景首帧检查。`ResizeObserver` 同步 CSS 尺寸、
canvas backing size、PyMOL reshape 和 OpenGL viewport；generation token 与
AbortController 阻止旧异步加载覆盖新实例。失败时显示具体环节并允许切到 Mol*，不能
以“脚本已载入”伪装成结构可见。

dev28 的 `StructureInteractionSession 0.2` 曾将普通助手动作保存为查看器中立
ViewState；该混合协议只保留旧记录读取能力，新会话由 REP-009 的完整 PML 场景契约
取代。

阶段访问权由持久 attempt、DesignSession lineage 和不可变 manifest 推导。Stage N
真正进入 queued/running 后，当前运行链的 Stage 01–N 全部只读；失败和科学停止也不
解锁。服务端所有修改 API 复用同一检查并返回 `409 stage_locked`。界面移除重新上传、
重新选区、重新批准、重新生成和同项目快捷重跑，只保留查看、下载、纯显示操作及不改变
配置的 resume。上游满足交接时，仅唯一下一阶段显示“配置下一步”。

## REP-009：ChatPyMol 原生完整 PML 场景

版本：`0.1.0.dev31`。

结构助手不再返回 `viewer-actions/view-control/region-edit` 多分支 proposal。每次请求
统一包含：

- 固定系统规则；
- 始终存在的 `safe-pml` 和最多两个按关键词匹配的 PML Skill；
- 当前完整 PML；
- 场景摘要及对象、链、格式、SHA-256 metadata；
- A/B/C 当前区域摘要；
- 最近十轮对话；
- 用户请求。

模型只能返回恰好四个字段：

```json
{
  "assistantMessage": "用户可读说明",
  "summary": "版本摘要",
  "conversationTitle": "对话标题",
  "pml": "完整新 PML"
}
```

完整 PML 是唯一可视化事实。每个 SceneVersion 保存完整文档、parent/base version、
SHA-256、actor、provider/model、实际 Skill ID 和时间，并用 `baseVersionId` 做乐观并发
检查。安全的末尾追加只在当前 PyMOL 场景执行增量；修改旧内容、恢复历史、增量失败或
状态不确定时，从已校验结构重新构建并完整重放。禁止把整份 PML 重复执行在未知旧状态上
冒充恢复。

Mol* 是同一 active SceneVersion 的兼容投影：representation、颜色、选择、聚焦和背景等
受支持命令会同步；不支持的 PyMOL 原生命令只显示兼容提示，不阻止保存，也不产生第二套
Mol* 场景事实。切换查看器始终读取同一 active PML。

Stage 02 保留 `ed_region_A/B/C` 三个受管理 selection。用户明确要求的残基编辑由完整
PML 表达，服务端确定性映射到 `label_seq_id` 草稿；再次选择可取消，换区会移动。PML
修改不会改写历史 Stage 02，只有人工确认和证据限制确认完成后才发布
`UserProvidedRegionSet` 与新 `hotspots.yaml`。科学问题仍只能形成待确认的
SASA/ScanNet 计划。

dev31 固定了编号交互和场景同步规则：助手中未限定的数字一律按序列格显示的
规范 `label_seq_id` 解释，只有用户明确说原始/auth/author/PDB 编号时才切换到
author 体系。序列格同时显示“规范”和“原始”编号。服务端先确定性生成期望
A/B/C，再验证模型的完整 PML 映射结果必须一致；对话文字不再能与左栏、序列区或
PyMOL 场景分离。区域 overlay 始终位于全局配色命令之后，保证 A/B/C 的红蓝黄不被
`color gray70, target` 覆盖。重放期间不打开原生操作日志，不持久化瞬时 `deselect`
或已存在的命令尾部，避免 SceneVersion 自增长和 PyMOL 闪烁。

参考依据：

- ChatPyMol commit：`43517d2dc0795357f35f93a2bde8cfc442f568c5`；
- 《ChatPyMOL 网页端架构与 PML Skill 机制完整记录》SHA-256：
  `22567ed89e0aef96cdab56b114ee98ade20540bcf42876e97738712429b0fa8f`。

### 验收结论

- Proteindigger 的系统 Chrome 已完成 Workbench 功能矩阵；真实 APOE 页面显示
  138-aa 结构、9/14/14 红蓝黄来源区域、有效未运行草稿和 Stage 01–05 递进只读状态。
- Chromium 1440×900 与 1920×1080 的完整功能矩阵为 40/40 通过；按步骤任务完成后
  必须按 job 返回的精确 `run_key` 打开新运行，即使项目索引尚未刷新，也不得退回同项目
  的旧运行。
- PyMOL 首帧检查在对象、原子与可见表示确认后立即主动绘制并读取 framebuffer，避免
  `preserveDrawingBuffer=false` 时浏览器在下一帧前清空像素造成假失败。
- 服务器 Chrome 与本地视觉基线存在约 1% 的字体/栅格像素差异；交互、布局和科学数据
  投影均通过，后续将为平台分别维护视觉基线。

## UI-021：Stage 05–07 精简科研证据界面

版本：`0.1.0.dev27`。

Stage 05 的默认页面遵循“先结论、再展开证据”：

```text
设计方案总数
Tier A/B/C/D 数量
晋级 YAML 数量
诊断 warning 数量
```

Tier 金字塔可点击。只有进入某个 Tier 后才列出 Region、scaffold、pilot 通过数、
`F_YAML`、晋级状态和 warning；只有进入 Tier A 策略后才加载原始 40 条 pilot 中通过
final gate 的候选结构。100 条诊断扩增默认折叠，只显示“扩增数 → local gate →
full-target → 结构通过 → warning”，不会在首页加载大型扩增报告或默认渲染诊断结构。

Stage 06 与 Stage 04 共用进度组件，但 v0.2 增加全局预算及逐 YAML 分配。页面先显示
50k 总进度，再按需展开每个策略的预算、完成数、GPU、shard、重试、吞吐率和 ETA。
一、二、三个晋级策略分别显示 `50000`、`25000/25000` 和
`16667/16667/16666`，不得把每组误解为各自 50k。

Stage 07 默认显示全局漏斗、主备数量、结论和 YAML 来源分布。所有策略使用同一筛选门
和全局候选池，不按 YAML 预留名额；进入层级或候选详情后才加载完整指标、序列与结构。
旧 ScaleBundle 0.1 的单策略历史继续显示其人工授权来源，新 ScaleBundle 0.2 则显示
全部 promotion rank 和分配，二者不会被合并成一条伪造历史。

## UI-022：Stage 04/06 执行位置

版本：`0.1.0.dev32`。

Stage 04 和 Stage 06 的未开始配置页在科学参数之外显示两张运行位置卡：

- “当前机器”展示检测到的 GPU、可用数、显存和环境状态；默认使用全部符合
  门槛的卡，专家选项可限制最大 GPU 数。
- “Suzhou2 公共算力”展示配对状态、worker 版本、GPU 数、队列长度、数据盘和
  资产就绪状态。未配对时链接到“设置 → 公共算力”的 Suzhou2 配对向导。

配对向导依次完成 host/port/user 输入、主机指纹确认、当前工作区专用密钥检测或
生成、一次性密码公钥安装与 worker 探测。完整 key pair 会直接复用，不重复生成；
密码只发往 localhost EasyDesign 服务并写入单次 OpenSSH PTY，不保存到浏览器、
配置、日志、参数、环境或磁盘。用户仍可手动复制公钥后直接验证。“取消连接配对”
是可恢复逻辑解绑，不撤销远端公钥、不删除本地私钥和历史。

受管任务卡每 15 秒读取一次队列和结构化进度，展示队列位置、分配 GPU、
完成量、吞吐率、ETA、最近事件和同步状态。连接中断时明确写“远程连接暂时
中断”，不将远端 job 标红为失败。Stage 04 远程任务固定运行 `4→5`，Stage 06
固定运行 `6→7`；大型候选保留在 Suzhou2，默认只同步 review 证据。

## UI-023：精简设置与自动就绪检查

版本：`0.1.0.dev35`。

设置不再将安装、项目 preflight、公共算力、开发者自检、存档和软件元数据堆在
一个长页面中。顶层只保留三个可切换页面：

1. “当前设备”自动检查基础环境和按需科学后端，仅对缺失组件显示安装操作。
2. “公共算力”只承载 Suzhou2 的状态、host fingerprint、专用密钥和可恢复解绑。
3. “项目存档”只列出可恢复的存档项目，不混入活跃项目或开发者自检。

设备状态在打开设置、窗口重新获得焦点、页面恢复可见和安装任务运行时自动刷新，
产品页面不再提供“刷新状态”按钮。用户默认只看到“可用 / 未安装 / 等待许可确认 /
需要处理”等产品语义。工作区绝对路径、environment/asset ID、安装任务、隔离区和结构助手
状态收进默认折叠的“技术详情”。

## UI-025：GPU 资源弹窗与连续阶段进度

版本：`0.1.0.dev36`。

Stage 04/06 在“最多使用 GPU 数量”之前先显示所选目标的“当前空闲 / 总卡数”。
用户点击“查看 GPU 状态”后才打开逐卡弹窗；每张卡显示设备号、型号、显存、利用率、
是否符合 admission 门槛及占用原因。当前机器读取本机 inventory，Suzhou2 读取固定
`managed-worker probe` 的 schema 0.3；远端只公开 compute process 数量，不公开 PID，
也不允许页面传入 shell。这个数字是只读瞬时快照，真正启动时仍由同一租约门再次仲裁。

运行后不再只显示一根无语义动画。Suzhou2 的 Stage 04 和 Stage 06 分别展示固定的
`4→5`、`6→7` 两段轨道；`ProgressSnapshot.stage_id` 进入下一阶段时，前一段转为完成，
后一段成为当前阶段。阶段内进度只使用结构化 `completed_tasks / total_tasks`、候选完成量、
队列状态与 ETA；尚无可计算分母时明确显示等待/不定进度，不按经过时间伪造百分比。
本机直跑当前仍是单阶段执行契约，因此只显示当前阶段，不假装已经自动串联下一阶段。

## UI-026：先选执行位置，再启动

版本：`0.1.0.dev36`。

Stage 04/06 未开始页不再用“生成后端 / 目标候选数 / 默认设备数”三张事实卡重复系统
配置。科学默认值仍来自 Python 契约，需要审计时进入配置和任务记录查看。

“当前机器”和“Suzhou2 公共算力”两张位置卡在资源请求发出后立即可见，且初始均未
选中。用户必须主动选择一个目标后，页面才显示该目标的空闲/总卡数、最多使用卡数、
逐卡弹窗和真实计算确认；启动按钮在目标未选、未确认或 Suzhou2 未配对时保持禁用。

远端资源探针有 60 秒响应上界；它会同时验证固定科学后端，Suzhou2 满载时真实观测约需
36 秒。加载中必须显示“正在读取逐卡状态”，不得提前显示“探针不可用”；结果返回后卡片
和已打开弹窗原地更新。加载中或探针失败都不隐藏选择器、不自动选择当前机器，也不修改
科学参数；失败文案不得展示 SSH 命令、密钥位置或工作区绝对路径。本机可在资源摘要
暂不可用时先被选择，启动
preflight 仍会重新检查 GPU、磁盘和环境；Suzhou2 只有确认配对后才可提交。可用的
Suzhou2 schema 0.3 探针必须让弹窗显示全部 8 张 GPU 的设备号、型号、显存、利用率、
占用和 admission 原因。

## UI-027：模型直接生成完整 PML

版本：`0.1.0.dev37`。

Stage 01/02 结构助手不再在请求模型前用正则把用户文字压缩成单个 A/B/C 操作。
当前完整 PML、结构 metadata、编号表和当前区域直接交给平台模型；模型可在同一次请求中
加入、移除、替换或清空多个区域，并返回表示最终状态的完整 PML。Stage 02 左栏、序列和
PyMOL/Mol* 投影都从该 PML 的 `ed_region_A/B/C` 反向映射，避免助手说明与草稿分离。

危险命令、文件/系统/网络访问、未知对象或链、不可映射残基、区域重叠和损坏的管理行仍
明确拒绝；第一次校验失败允许模型修复一次。要求“最佳区域”、hotspot、SASA 或 ScanNet
时仍只形成待确认分析计划，不能直接改写 A/B/C。请求失败时对话气泡显示服务端实际原因，
不再只显示统一占位错误。
