# EasyDesign 宏观路线图

状态定义见 `PROJECT_CHARTER.md`。本文件按产品时间尺度维护宏观方向；它不保存正在编码的
细节，也不承诺日期。七个科学 Stage 与工程、CLI、报告、UI、验证、数据、发布、论文和
商业板块并列管理；阶段内部任务、验证和历史进入各自 `STATUS.md`，当前跨板块重点见
`TODO_NOW.md`。

## 短期目标：EasyDesign 1.0

目标是以 VHH 为首个参考 binder，把七阶段真实跑通并形成稳定 Python API。功能完整优先于
设计准确率，任何模型失败和科学负结果必须如实报告。

| 里程碑 | 状态 | 完成门槛或阶段索引 |
| --- | --- | --- |
| M0 仓库基础 | `implemented` | 私有 Git 仓库、中文治理、七阶段契约、包骨架和基础检查完成。 |
| M1 统一运行契约 | `implemented` | 类型化 manifest、不可变 attempt、规范 JSON、SHA-256 和契约测试完成。 |
| M2 交互式科学报告基础 | `smoke-validated` | Stage 01 sequence/PSE 均生成自包含 Mol* 5.11.0 报告；checksum、localhost 服务、Chromium 和真实 APOE smoke 通过。 |
| M3 Developer Preview 可用性 | `smoke-validated` | 本地源码/wheel 可安装；`easydesign` 支持 init、profile、validate、doctor、Stage 01/02 run、runs 和 viewer；真实 PSE→Stage 02 CPU 与 required-MSA sequence Stage 01 CLI smoke 通过。 |
| M4 可审计开发历史 | `implemented` | ENG-004 统一 Stage 与顶层完成记录的 RFC 3339 时间戳，并由 `make check` 阻止缺失、重复或无时区记录。 |
| M5 canonical 配置与科学审批边界 | `smoke-validated` | schema 0.3 展示七阶段；Target Bundle 0.3 支持 ensemble；Stage 02 自动结果停在显式人工批准并只通过 `hotspots.yaml` 交接。 |
| M6 Stage 01 六入口与双运行模式 | `smoke-validated` | schema 0.5、六 source handler、Decision resume、remote/cache/precomputed MSA 与十条 live fixture 均通过；Stage 01 1.0 工程边界已冻结。 |
| M7 Stage 02 用户区域交接 | `smoke-validated` | schema 0.6 将 PSE 固定红/蓝/黄和 YAML 四编号统一为 UserProvidedRegionSet；APOE 两条来源得到相同 9/14/14 成员并发布带不同 provenance 的 hotspots.yaml 0.3。 |
| M8 Stage 03 基础策略编译 | `smoke-validated` | schema 0.7、通用 region×official VHH7 策略、固定 scaffold 资产和 BoltzGen 0.3.2 官方校验已完成；APOE 21/21 通过。 |
| M9 Stage 04–07 通用后半流程 | `implemented` | 可恢复 BoltzGen generation、v1.5 pilot/final filter、scale profiles、Protenix 三 seed、TNP 和主备候选包均已形成通用实现；APOE 已在 Stage 05 合法科学停止。 |
| M10 产品级科研工作台 | `smoke-validated` | dev9 工作台已完成统一浅色结构工作区、执行/筛选证据和可自由浏览的新建设计向导；文件接收、草稿、检查与启动状态边界通过双尺寸 Chromium 和 Python API 验收。 |
| EasyDesign 1.0 验收 | `planned` | VHH 七阶段、两条真实端到端基准和 Stage 01 六类入口测试通过。 |

## 长期工作板块索引

顶层每个板块只维护当前状态、一句话概述、当前宏观目标、下一里程碑和详细索引。Stage
内部细节仍以各 Stage STATUS 为准；非 Stage 工作默认归档到共享项目 history，避免提前
创建大量 Markdown。

| 前缀 | 板块 | 状态 | 一句话概述 | 当前宏观目标 | 下一里程碑或索引 |
| --- | --- | --- | --- | --- | --- |
| `S01–S07` | Scientific Pipeline | `planned` | 七阶段科学主线按独立契约推进。 | 先完成 VHH 1.0 真实端到端。 | 下方七阶段实时摘要。 |
| `ENG` | Core Engineering | `smoke-validated` | ENG-002/004/005/006/007 已建立代码身份、时间戳、ensemble、联网证据、Decision Gate 与六入口共享 dispatcher。 | 保持一个 API、不可变证据与跨平台 core。 | ENG-008：Stage 04–06 通用任务、进度、事件与恢复执行器；[架构](docs/ARCHITECTURE.md)。 |
| `UX` | CLI & Developer Experience | `smoke-validated` | UX-001–004 已提供可安装 CLI、六入口 init、显式 MSA 策略、doctor、双模式运行、decision resume、runs 与 Viewer。 | 让真实能力通过一个稳定入口使用。 | 下一步随 Stage 03 增加配置生成与审批 UX；[README](README.md)。 |
| `REP` | Reporting & Visualization | `smoke-validated` | REP-001 自包含 Mol* Target Viewer 已通过真实 APOE smoke。 | 保持只读、便携、最小暴露的科学报告。 | REP-002：SASA/ScanNet overlay；可视化批准 UX 后续开发。 |
| `UI` | Product UI | `smoke-validated` | dev9 本地科研工作台已统一结构/筛选证据，并以非线性五步向导连接输入、配置、检查和真实启动。 | 在第二真实案例和可继续长任务上验证完整交互。 | UI-002 长任务 UX、第二案例和跨平台验收；[产品规范](docs/product/UI_WORKBENCH.md)。 |
| `VAL` | Scientific Validation | `planned` | 当前只有工程 smoke，没有 binder 准确率结论；APOE Stage 05 负结果等待受控解释。 | 建立预注册 benchmark、负结果和实验反馈链。 | VAL-003：Protenix target-template / hotspot-constraint 受控对照。 |
| `DATA` | Data & Assets | `smoke-validated` | DATA-002 已固定 VHH7；DATA-003 的 TNP fixed-source/isolated-runtime 与真实 batch smoke 已通过，模型和重型依赖继续 runtime-only。 | 确保 scaffold、模型、fixture 的来源与权利可审计。 | 在公开发布前复审 TNP 完整依赖、NanoBodyBuilder2 模型下载来源和再分发边界。 |
| `REL` | Release & Operations | `planned` | 当前只支持私有源码和本地 wheel。 | 建立 CI、版本兼容、安全和公开发布门槛。 | REL-001：等待 IP/LICENSE 决策后定义公开 release。 |
| `PAPER` | Publication | `planned` | 方法与证据持续积累，尚未冻结论文 claim。 | 形成可追溯方法、图表、benchmark 和补充材料。 | PAPER-001：Stage 01/02 方法和失败证据索引。 |
| `BIZ` | Product & Commercialization | `planned` | 商业路线存在，但未进入产品化承诺。 | 完成 IP、许可证、部署、支持和质量体系。 | BIZ-001：在科学/软件验证后建立产品需求与合规清单。 |

### 当前跨板块任务登记

| ID | 板块 | 状态 | 完成门槛 |
| --- | --- | --- | --- |
| `ENG-003` | Core Engineering | `planned` | 自建 MSA 服务与 CI 平台矩阵完成。 |
| `S03-001` | Scientific Pipeline | `smoke-validated` | 基础 BoltzGen VHH strategy compiler 与 APOE 21/21 YAML 验收完成。 |
| `S04-001` | Scientific Pipeline | `smoke-validated` | 双 GPU 可恢复 pilot generation 完成 APOE 21×40；840 个完整候选与 RunManifest 完整性验证通过。 |
| `S05-001` | Scientific Pipeline | `smoke-validated` | APOE 840 个 pilot 完成 v1.5 审计；唯一 Tier A 扩展到 100 后，10/10 full-target prediction 未保持 binder pose，合法停止。 |
| `S06-001` | Scientific Pipeline | `implemented` | smoke-1000 与 production-50000 分片计划、25% 资源门、共享恢复和精确 merge 已通过通用测试；APOE 因 Stage 05 科学停止而未运行。 |
| `S07-001` | Scientific Pipeline | `implemented` | 深度筛选、多 seed Protenix、TNP 与多样性候选包完成；APOE 没有合法 ScaleBundle，未运行本阶段。 |
| `ENG-008` | Core Engineering | `smoke-validated` | 通用任务、原子进度、append-only 事件、多 GPU 调度和精确 deficit resume 已由 APOE 840-candidate 长任务验证。 |
| `REP-002` | Reporting & Visualization | `planned` | SASA/ScanNet 独立 overlay 不改变科学输出。 |
| `DATA-001` | Data & Assets | `planned` | 面向公开 release 的第三方 VHH 资产复审完成。 |
| `DATA-002` | Data & Assets | `smoke-validated` | 七个官方 VHH scaffold 的来源、MIT 许可证、逐文件 checksum 和 wheel 分发完成。 |
| `DATA-003` | Data & Assets | `smoke-validated` | TNP fixed commit、Python 3.10 独立环境、完整显式依赖、许可证、严格 adapter 与官方 VHH 单候选真实 batch 已验证；模型仍保持 runtime-only。 |
| `VAL-001` | Scientific Validation | `planned` | 选择第二条独立真实 target，复用冻结的 1.0 主线进行端到端工程与科学验收。 |
| `VAL-002` | Scientific Validation | `smoke-validated` | APOE PSE 真实验收完成到 Stage 05：840 pilot、60 扩展和 10 full-target prediction 后如实记录 `stopped-no-scale-winner`；Stage 06/07 未伪运行。 |
| `VAL-003` | Scientific Validation | `planned` | 冻结 APOE 现有负结果，对相同候选和 MSA 比较 no-template、target-template、target-template+hotspot constraint 及已知 VHH–抗原正对照；任何默认策略变化必须形成新 profile/ADR。 |
| `UI-001` | Product UI | `smoke-validated` | React/TypeScript 本地科研工作台、设计 token 与 project/run/stage 导航已通过真实 APOE 展示和 1440/1920 浏览器验收。 |
| `ENG-009` | Core Engineering | `smoke-validated` | localhost gateway、manifest 投影、安全 artifact token、SSE、drain/resume job controller 已通过 Python 3.11 和真实服务器服务 smoke。 |
| `UI-002` | Product UI | `implemented` | 六入口向导、表单/YAML 同步、doctor、真实启动、通用/Hotspot 审批、停止调度和恢复均调用统一 Python API；真实长任务交互仍需下一条可继续 run 验收。 |
| `UI-003` | Product UI | `smoke-validated` | 七阶段证据视图、APOE 审计回放、Stage 06/07 capability/run 状态分离与 draft-order gate 已通过真实 APOE 投影验收。 |
| `UI-004` | Product UI | `smoke-validated` | 主导航、中文术语、字号和 Stage 01/02/05/07 的 `#EEF1F6` Mol* 工作区已通过真实页面与视觉回归。 |
| `ENG-010` | Core Engineering | `smoke-validated` | Stage 05 分页、安全结构 token、Stage 03 策略身份联接和缺失值安全聚合已通过真实 APOE 复验。 |
| `UI-005` | Product UI | `smoke-validated` | Stage 05 已默认展示 21 个策略、Tier、12 个初筛候选、10 个 Protenix 结果，再说明科学停止。 |
| `UI-006` | Product UI | `smoke-validated` | 统一浅色 Mol* 工作区与证据优先 Stage 05 已通过 1440/1920 视觉回归及真实 APOE 浏览器验收。 |
| `ENG-011` | Core Engineering | `smoke-validated` | Stage 04/06 统一 execution API 已覆盖实时 SSE 和历史重建；APOE 840 候选双 GPU 记录恢复准确。 |
| `UI-007` | Product UI | `smoke-validated` | 五步向导可自由浏览并显示逐步 readiness；草稿、环境检查和真实启动只在各自边界按顺序解锁。 |
| `ENG-012` | Core Engineering | `smoke-validated` | 本地文件立即原子接收并返回 filename/size/SHA-256 receipt；token 单次消费、空文件/超限/失败/重选均有明确处置。 |
| `REL-001` | Release & Operations | `planned` | IP/LICENSE 决策后冻结公开 release 门槛。 |

### 通用决策门路线

`ENG-006` 已在 Stage 01/02 建立可恢复、可审计的通用 Decision Gate；后续阶段复用同一
`DecisionRequest` / `DecisionRecord`，不各自发明审批协议：

| Stage | 未来 gate | 状态 | 完成门槛 |
| --- | --- | --- | --- |
| Stage 03 | BoltzGen YAML 与设计矩阵确认 | `planned` | review-gated 由人确认；unattended 只允许版本化确定性 policy。 |
| Stage 05 | pilot filter 后 go/no-go | `planned` | 保存逐规则证据、预算和批准 authority。 |
| Stage 06 | 高成本规模预算授权 | `planned` | 启动大规模生成前显式批准预算与 backend profile。 |
| Stage 07 | Top N 候选包批准 | `planned` | 只生成候选下单包；供应商下单永远由人工执行。 |
| 跨阶段 | biosafety 等 required review | `planned` | 未完成时最多生成 `draft-order-package`，不因 unattended 绕过。 |

### 七阶段实时摘要

下表由各 Stage `STATUS.md` 的“顶层摘要”自动生成；不得手工维护。

<!-- BEGIN AUTO-GENERATED STAGE ROLLUP -->
| Stage | 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新 | 详情 |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 01 | `smoke-validated` | schema 0.6 六类入口、三种 required-MSA 来源、Target Bundle 0.4、Viewer 与 Stage 02 交接均通过真实矩阵。 | 冻结 Stage 01 1.0 边界，把开发重心移交 Stage 03。 | 无 Stage 01 1.0 工程阻塞；商业敏感序列仍等待自建 MSA 与条款审查。 | 2026-07-25 | [STATUS](workflow/01-target-preparation/STATUS.md) |
| Stage 02 | `planned` | schema 0.6 已打通 automatic、PSE 固定颜色和 YAML 四编号人工区域；APOE 用户区域已发布可供 Stage 03 消费的 hotspots.yaml 0.3。 | 冻结 Stage 02 工程交接，启动 Stage 03 BoltzGen YAML；科学 benchmark 继续独立推进。 | Stage 03 handoff 无工程阻塞；GPU、外部证据和 VHH–抗原科学验证仍是后续工作。 | 2026-07-25 | [STATUS](workflow/02-hotspot-discovery/STATUS.md) |
| Stage 03 | `smoke-validated` | S03-001 已完成通用基础编译器；APOE 3×7 共 21 个 YAML 全部通过固定 BoltzGen 0.3.2 官方校验。 | 冻结 1.0 基础模板，把开发重心移交 Stage 04 可恢复 pilot generation。 | 无 Stage 03 工程阻塞。 | 2026-07-26 | [STATUS](workflow/03-boltzgen-configuration/STATUS.md) |
| Stage 04 | `smoke-validated` | APOE 21×40 共 840 个完整候选已由双 GPU 可恢复执行器收集，RunManifest 与全部交接产物完整性验证通过。 | 冻结 Stage 04 交接，把 840 个候选交给 Stage 05 v1.5 逐规则筛选。 | 无 Stage 04 工程阻塞；科学通过率由 Stage 05 判定。 | 2026-07-26 | [STATUS](workflow/04-pilot-generation/STATUS.md) |
| Stage 05 | `smoke-validated` | APOE 840 个 pilot 已完成 v1.5 审计；唯一 Tier A 扩展到 100 后，10/10 full-target Protenix 因 binder pose 不稳定而合法停止。 | 冻结 `stopped-no-scale-winner` 负结果，不启动本轮 APOE Stage 06/07。 | 无 operational failure；APOE 本轮没有通过科学规模化门。 | 2026-07-26 | [STATUS](workflow/05-pilot-filtering/STATUS.md) |
| Stage 06 | `implemented` | S06-001 已实现 2×500/20×2500 分片计划、25% 磁盘门、精确 merge 和共享恢复执行器。 | 保持通用能力冻结；APOE 因 Stage 05 无 scale winner，本轮不创建 1000 任务。 | 无代码阻塞；APOE 已科学停止，50k 也没有本轮执行授权。 | 2026-07-26 | [STATUS](workflow/06-scale-generation-and-refolding/STATUS.md) |
| Stage 07 | `implemented` | S07-001 已实现 v1.5 预筛、Protenix 三 seed、一致性、TNP 证据和确定性主备候选包，固定 TNP batch smoke 已通过。 | 保持通用能力冻结；APOE 在 Stage 05 科学停止，本轮不生成 Stage 07 候选包。 | 无代码阻塞；APOE 没有合法 Stage 06 ScaleBundle，50k 未授权。 | 2026-07-26 | [STATUS](workflow/07-final-filtering-and-selection/STATUS.md) |
<!-- END AUTO-GENERATED STAGE ROLLUP -->

## 中期目标：多 binder 与正式开发者产品

| 里程碑 | 状态 | 完成门槛 |
| --- | --- | --- |
| 通用 binder profile | `planned` | 分子表示、约束、生成后端、filter 和输出包均有稳定 adapter 契约，不复制 pipeline。 |
| 蛋白 binder 主线 | `planned` | 至少一条真实小规模端到端基准通过，并与 VHH 共用运行契约。 |
| 肽 binder 主线 | `planned` | 至少一条真实小规模端到端基准通过，明确线性/环肽表示与筛选边界。 |
| 方法 benchmark | `planned` | 按 binder 类型建立预注册数据集、基线、负结果和科学验证报告。 |
| CLI 与公开 release | `planned` | Developer Preview CLI 已完成；正式发布仍需稳定 API、英文文档、授权、安全、引用和第三方资产审查。 |
| 多执行环境 | `planned` | local、Slurm/SMART 和可移植容器使用相同请求/结果契约。 |
| 可选 Agent 建议层 | `planned` | 只在确定性 1.0 主线完整后加入；建议必须转成类型化配置、通过规则校验并接受人工批准，没有 Agent 时七阶段仍完整运行。 |

## 长期目标：一键式平台、科研与商业产品

| 里程碑 | 状态 | 完成门槛 |
| --- | --- | --- |
| EasyDesign UI | `smoke-validated` | dev8 UI 已调用同一 Python API 创建、恢复、审阅和比较运行，并形成混合科研团队可读、证据优先的中文产品层；production-ready 仍需真实长任务交互、第二案例和跨平台验收。 |
| 多 binder 设计平台 | `planned` | VHH、蛋白、肽及后续类型通过能力声明接入，用户用一次配置运行完整流程。 |
| 科研成果 | `planned` | 方法、benchmark、失败分析和真实实验结果形成可审计论文证据链。 |
| 商业产品 | `planned` | 完成 IP、许可证、安全、部署、支持、审计和质量体系，形成可持续产品。 |
| 数据与模型闭环 | `planned` | 经授权的实验反馈能够版本化回流，用于评估和改进而不污染历史证据。 |

长期目标不改变 1.0 的范围：当前首先把 VHH 主线真实跑通；蛋白和肽不会被包装成已经实现。
