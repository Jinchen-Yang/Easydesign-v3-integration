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
| M9 Stage 04–07 通用后半流程 | `implemented` | 可恢复 BoltzGen generation、v1.5 历史筛选和 v1.6 多策略晋级、用户可调共享预算、Stage 07 全局竞争均已形成通用实现；APOE 的 v1.5 科学停止保持冻结，独立 50k 证据等待 v1.6 adoption 后进入 Stage 07。 |
| M10 产品级科研工作台 | `smoke-validated` | dev33 工作台已形成连续七阶段轨道、结构审查、真实运行投影和“当前设备 / 公共算力 / 项目存档”三页精简设置。 |
| M11 合作者共享证据 | `smoke-validated` | dev10 在 `main` 提供 65 MiB APOE 只读证据包、完整性校验与一条命令启动；21/840/100/12/10 结果及双 GPU 历史通过真实 API 复验。 |
| M12 跨服务器执行 | `smoke-validated` | dev11 已在 Suzhou2 真实提交 persistent run；8×A100 同时运行首批分片，远端独立 manifest/progress/resume 生效。 |
| M13 项目与设计路线整理 | `smoke-validated` | dev13 已建立可恢复项目归档、全流程/按步骤/开发者自检三条产品路线、通用 continuation、Mol* 生命周期修复和 Stage 02 交互式重选区；真实 APOE FASTA、PSE 新分支与浏览器验收均已完成。 |
| M14 仓库内自包含运行工作区 | `implemented` | ENG-023 已将启动器、profile、环境/资产 registry、cache、setup 状态和 UI job 收敛到仓库内；Proteindigger 完整环境、许可资产和真实后端逐步自检仍在验收。 |
| M15 单一 main 开发治理 | `implemented` | ENG-024 禁止开发分支和额外 Git worktree；已验证 ENG-023 提交链收敛到 `main`，历史 runtime 在无删除前提下保留。 |
| M16 双结构查看器与安全助手 | `implemented` | REP-009 已把新结构助手切换为 ChatPyMol 原生完整 PML/Skill/SceneVersion 主循环；Mol* 降为兼容投影，历史 typed 记录继续只读。真实 provider 连续对话与完整 APOE 浏览器矩阵待复验。 |
| M17 可靠草稿与递进冻结 | `smoke-validated` | UI-018/ENG-026/ENG-027/UI-019 已通过：主页草稿、事务式创建、持久上传回执和运行链递进冻结均有契约及真实 APOE 页面证据。 |
| M18 多策略规模筛选 | `implemented` | schema 0.8、Stage05Bundle/ScaleBundle 0.2、Tier A Top 3 晋级、诊断 warning、共享 50k 与 Stage 07 多来源 lineage 已实现；APOE 历史 50k 已通过独立采用记录引用，小预算 Stage 07 空结果 smoke 已完成。 |
| M19 受管算力执行 | `smoke-validated` | dev35 已在 Suzhou2 Manager 真实完成固定非 APOE 40 条 Stage 04→05 和 APOE 精确 8 条 Stage 06→07；中央队列、单卡租约、原地交接和 review-only 回传均有终态证据，未重跑历史 50k。 |
| EasyDesign 1.0 验收 | `planned` | VHH 七阶段、两条真实端到端基准和 Stage 01 六类入口测试通过。 |

## 长期工作板块索引

顶层每个板块只维护当前状态、一句话概述、当前宏观目标、下一里程碑和详细索引。Stage
内部细节仍以各 Stage STATUS 为准；非 Stage 工作默认归档到共享项目 history，避免提前
创建大量 Markdown。

| 前缀 | 板块 | 状态 | 一句话概述 | 当前宏观目标 | 下一里程碑或索引 |
| --- | --- | --- | --- | --- | --- |
| `S01–S07` | Scientific Pipeline | `planned` | 七阶段科学主线按独立契约推进。 | 先完成 VHH 1.0 真实端到端。 | 下方七阶段实时摘要。 |
| `ENG` | Core Engineering | `smoke-validated` | manifest、Decision Gate、跨主机执行与统一 run layout 已形成可审计工程底座；ENG-023 的自包含工作区正在真实重建验收。 | 保持一个 API、不可变证据、仓库内写边界与跨平台 core。 | 完成 Proteindigger 全后端 setup、资产许可和移动工作区验收；[运行目录规则](docs/architecture/RUN_LAYOUT.md)。 |
| `UX` | CLI & Developer Experience | `smoke-validated` | UX-001–005 已提供可安装 CLI；UX-006 增加从 clone 到 setup/doctor/ui 的单一启动器。 | 让真实能力和可审计结果通过稳定、自包含入口使用。 | 验收 Linux 完整安装、minimal 安装和 macOS/Windows core/UI；[README](README.md)。 |
| `REP` | Reporting & Visualization | `implemented` | 自包含 Viewer 和双查看器底座已 smoke；REP-009 已实现完整 PML 单一场景、动态 Skills、不可变版本及 Mol* 兼容投影，真实 provider 浏览器复验待完成。 | 保持只读、便携、最小暴露，并扩展跨平台结构交互矩阵。 | REP-009 真实 APOE/平台 provider smoke；[产品规范](docs/product/UI_WORKBENCH.md)。 |
| `UI` | Product UI | `smoke-validated` | 连续七阶段工作区、可靠结构审查、递进只读冻结和三页精简设置已形成统一产品入口。 | 继续在第二真实案例和长任务中验证产品流程。 | UI-002 长任务；[产品规范](docs/product/UI_WORKBENCH.md)。 |
| `VAL` | Scientific Validation | `planned` | 当前只有工程 smoke，没有 binder 准确率结论；APOE Stage 05 负结果等待受控解释。 | 建立预注册 benchmark、负结果和实验反馈链。 | VAL-003：Protenix target-template / hotspot-constraint 受控对照。 |
| `DATA` | Data & Assets | `smoke-validated` | DATA-002/003 固定 VHH7 和 TNP；DATA-005 增加环境内容身份、安装后 inventory、模型 registry 与许可门。 | 确保 scaffold、模型、环境、fixture 和共享结果的来源、授权与边界可审计。 | 生成并验证 Linux 环境锁，完成逐资产许可与 checksum 验收。 |
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
| `S05-002` | Scientific Pipeline | `smoke-validated` | v1.6 只按 `F_YAML` 晋级最多三个 Tier A；APOE 冻结 pilot 已独立重评为 1 组晋级、1 条诊断 warning，旧 v1.5 停止结论未改写。 |
| `S06-001` | Scientific Pipeline | `implemented` | smoke-1000 与 production-50000 分片计划、25% 资源门、共享恢复和精确 merge 已通过通用测试；APOE 因 Stage 05 科学停止而未运行。 |
| `S06-004` | Scientific Pipeline | `smoke-validated` | ScaleBundle 0.2 将 50,000 作为共享总预算；APOE 单策略采用记录已验证 Suzhou2 20/20 分片、50,000/50,000、连续候选及 8 GPU 历史，多策略真实规模待第二案例。 |
| `S06-005` | Scientific Pipeline | `smoke-validated` | Stage 06 新任务使用用户可调 `total_candidate_count`，默认推荐 50,000；dev35 已在 Suzhou2 按用户最终输入精确生成 APOE 8/8 条、单 shard、无缺口且 ID 唯一。 |
| `S07-001` | Scientific Pipeline | `smoke-validated` | 深度筛选、多 seed Protenix、TNP 与多样性候选包实现完成；APOE 8 条受管 smoke 已发布合法空结果，但因 8/8 在 BoltzGen 预筛停止，本作业未调用 Protenix/TNP。 |
| `S07-002` | Scientific Pipeline | `smoke-validated` | Stage 07 兼容 ScaleBundle 0.1/0.2 和多策略 lineage；真实 APOE 8 条原地交接、全局处置、空 review package 与 review-only 回传已通过。 |
| `ENG-008` | Core Engineering | `smoke-validated` | 通用任务、原子进度、append-only 事件、多 GPU 调度和精确 deficit resume 已由 APOE 840-candidate 长任务验证。 |
| `REP-002` | Reporting & Visualization | `planned` | SASA/ScanNet 独立 overlay 不改变科学输出。 |
| `DATA-001` | Data & Assets | `planned` | 面向公开 release 的第三方 VHH 资产复审完成。 |
| `DATA-002` | Data & Assets | `smoke-validated` | 七个官方 VHH scaffold 的来源、MIT 许可证、逐文件 checksum 和 wheel 分发完成。 |
| `DATA-003` | Data & Assets | `smoke-validated` | TNP fixed commit、Python 3.10 独立环境、完整显式依赖、许可证、严格 adapter 与官方 VHH 单候选真实 batch 已验证；模型仍保持 runtime-only。 |
| `VAL-001` | Scientific Validation | `planned` | 选择第二条独立真实 target，复用冻结的 1.0 主线进行端到端工程与科学验收。 |
| `VAL-002` | Scientific Validation | `smoke-validated` | APOE PSE 真实验收完成到 Stage 05：840 pilot、60 扩展和 10 full-target prediction 后如实记录 `stopped-no-scale-winner`；Stage 06/07 未伪运行。 |
| `VAL-007` | Scientific Validation | `implemented` | APOE policy reevaluation 与 Suzhou2 50k ScaleEvidence adoption 已发布；旧 v1.5 结论保持冻结。远端 Protenix/TNP probe 和 Stage 07 真实运行尚未完成。 |
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
| `DATA-004` | Data & Assets | `smoke-validated` | APOE Stage 05 已形成 65 MiB、307 文件的 manifest 完整 UI evidence bundle；约 970 MB backend 中间目录未提交。 |
| `UX-005` | CLI & Developer Experience | `smoke-validated` | 合作者 clone `main` 后可用一条命令完成 SHA-256/manifest 校验并启动相同 APOE 工作台。 |
| `ENG-013` | Core Engineering | `smoke-validated` | whole-run SSH executor、严格主机/版本探针、rsync staging、systemd worker、远端独立 manifest/progress/resume 和 CLI 已由 Suzhou2 8×A100 真实提交验证。 |
| `S06-002` | Scientific Pipeline | `implemented` | 以源 Stage05Bundle SHA-256 和双重 acknowledgement 人工授权的探索性单策略 50k 已在 Suzhou2 完成 20×2500、50,000 候选；APOE Stage 05 v1.5 科学停止保持不变。 |
| `ENG-014` | Core Engineering | `smoke-validated` | SSH watch/resume、manifest 驱动 metadata/complete 同步和 BoltzGen task heartbeat 已通过真实 Suzhou2 运行只读验收。 |
| `S06-003` | Scientific Pipeline | `implemented` | Stage 06 远程协作闭环完成；旧 worker 保持兼容，新 dev12 任务记录逐 shard heartbeat。 |
| `UI-008` | Product UI | `smoke-validated` | 新建设计可显式选择本机或 profile 远端；运行任务页可刷新、同步和恢复远端任务，双尺寸 Chromium 验收通过。 |
| `ENG-015` | Core Engineering | `smoke-validated` | 项目目录只从 run-index 读取；17 个非主项目已可恢复归档并通过字节/manifest 完整性复验，普通项目页只保留两个 APOE 主项目。 |
| `VAL-004` | Scientific Validation | `smoke-validated` | `runs/apoe-fasta/20260727-002-stage01-protenix` 真实消费 143 aa FASTA 与 SHA-256 为 `12d913…f72716` 的 609-depth A3M，发布 Protenix-v2 Target Bundle 0.4 和 Viewer。 |
| `UI-009` | Product UI | `smoke-validated` | 全流程七阶段可自由浏览；按步骤路线已从真实 APOE Stage 01 建立独立 Stage 02 continuation；开发者自检与科研项目保持隔离。 |
| `UI-010` | Product UI | `smoke-validated` | 项目可在运行索引中显式指定一条主展示运行；新分支继续保留在历史中，但不会擅自覆盖首页选定结果。 |
| `UI-011` | Product UI | `smoke-validated` | 按步骤设计已收敛为单页 Stage 01：PSE 接收后自动校验、运行并进入结构审查，真实 APOE 与双尺寸浏览器验收通过。 |
| `UI-012` | Product UI | `smoke-validated` | Stage 02 手工编辑默认复制当前批准区域或 PSE 来源颜色；APOE 初始 9/14/14、从空白 0/0/0、恢复与结构/序列点击反馈均已验证。 |
| `ENG-016` | Core Engineering | `smoke-validated` | DesignSession 0.1 的不可变 config revision、run lineage、冻结输入重定位和等待审批状态已由真实 APOE continuation 验证。 |
| `ENG-017` | Core Engineering | `smoke-validated` | Project/Run/Stage/Attempt/branch 语义、同 run 阶段延续、惰性 Stage 目录、项目导航和归档空壳清理均通过真实目录验收。 |
| `ENG-018` | Core Engineering | `planned` | 为 dev14 前的 Stage checkpoint runs 生成依赖报告，并对无引用终态 run 提供逐 run 可恢复归档；不合并或重写科学文件。 |
| `ENG-019` | Core Engineering | `smoke-validated` | 有界原始字节流已替代浏览器 Base64 预处理；上传终态、job 查询、配置 runs root 和 DesignSession lineage 均通过真实 PSE 验收。 |
| `REP-003` | Reporting & Visualization | `implemented` | Stage 02 产品层保留批准人与证据限制确认；逐区 design goal 继承项目配置，保守说明由 orchestration 生成，科学授权仍使用现有 Stage 02/Decision 契约。 |
| `REP-004` | Reporting & Visualization | `smoke-validated` | Mol* 单实例、过期加载防护、表示/相机就绪门已通过真实 143 aa APOE FASTA 与 PSE 红蓝黄页面的可见结构和非背景像素验收。 |
| `REP-005` | Reporting & Visualization | `smoke-validated` | Workbench 与便携 Stage 01 Viewer 的 Mol* 宿主、canvas 和运行时画布层均固定 `touch-action: none`，双指手势由 Mol* 接收。 |
| `S02-009` | Scientific Pipeline | `smoke-validated` | APOE PSE 三层编辑器已将 A/B/C 9/14/14 保存为新的 `manual-residue-list` Stage 02 分支，并停在人工确认门；旧运行保持不变。 |
| `UI-013` | Product UI | `smoke-validated` | Stage 02 不再重复询问 A/B/C 的设计目的和两类理由；设计意图继承 canonical 配置，保守说明由 orchestration 生成，批准人与证据限制确认保留。 |
| `UI-014` | Product UI | `smoke-validated` | Stage 02 显示真实 job 进度并在终态打开新分支；dev19 补充提交前逐项校验、问题字段聚焦和明确按钮状态。 |
| `ENG-020` | Core Engineering | `smoke-validated` | Stage 02 continuation 只复制并验证成功的 Stage 01 前缀；显式人工区域提交一次完成 human approval，不要求来源整条 run 终态。 |
| `UI-015` | Product UI | `smoke-validated` | 七阶段轨道支持点击和完成后平滑前进；Stage 02 已内嵌，Stage 03 从真实 `3×7` 配置启动并在成功后定位 Stage 04。 |
| `ENG-021` | Core Engineering | `smoke-validated` | Python 为 Stage 01–07 提供产品表单投影；按步骤 continuation 依据连续成功 Stage 前缀推进，开放中的 running Run 不再被旧终态规则误拒绝。 |
| `ENG-022` | Core Engineering | `implemented` | 根级 `DATA_SAFETY.md` 已把默认禁止删除、逐次审批、非覆盖归档和非破坏性跨主机恢复定义为最高优先级制度；新 ProteinDigger 已通过独立 deploy key 克隆到数据盘新目录。 |
| `VAL-005` | Scientific Validation | `implemented` | 快速确定性自检真实创建 Stage 01–07 manifest/attempt/artifact 链并隔离为 developer-smoke-run；真实后端微型自检当前只提供诚实的待运行记录，完整非 APOE Stage 01–05 与 Stage 06/07 probe 仍是下一验收。 |
| `ENG-023` | Core Engineering | `implemented` | `WorkspaceContext`、仓库根标记、相对 profile、不可变 registry、安全写入边界和旧部署显式导入已实现；完整服务器验收进行中。 |
| `ENG-024` | Core Engineering | `implemented` | Git 开发拓扑收敛为唯一 `main`；禁止创建开发分支和 worktree，旧 worktree 数据在提交收敛后继续原样保留。 |
| `REP-006` | Reporting & Visualization | `smoke-validated` | Pyodide/PyMOL WASM 与 Mol* 平级读取同一 verified CIF；APOE 138-aa 结构与 9/14/14 来源区域已通过真实浏览器首帧复验。 |
| `ENG-025` | Core Engineering | `smoke-validated` | StructureInteractionSession 0.1、revision-only PML、DeepSeek/GLM provider、最小请求和安全编译边界通过。 |
| `S02-010` | Scientific Pipeline | `smoke-validated` | 明确残基可进入用户编辑草稿；模糊 hotspot 请求只能生成待确认 SASA/ScanNet 计划，不直接发布区域。 |
| `DATA-006` | Data & Assets | `smoke-validated` | ChatPyMol 固定 commit、Pyodide 0.22.1、NumPy 1.23.5、PyMOL WASM 2.6.0a0 的来源、SHA-256、许可证和 wheel 离线分发通过。 |
| `UI-017` | Product UI | `smoke-validated` | Stage 01/02 默认浏览器 PyMOL、平级 Mol*、共享区域/编号及可收起助手已经通过真实 APOE 浏览器复验。 |
| `UI-018` | Product UI | `smoke-validated` | 主页同时投影正式 run 与有效项目草稿；失败创建、空会话和暂存记录不会形成项目卡片。 |
| `ENG-026` | Core Engineering | `smoke-validated` | 上传回执 0.2、容量门和事务式项目发布形成可恢复且无自动删除的闭环；精确物理清理仍需用户逐次批准。 |
| `REP-007` | Reporting & Visualization | `smoke-validated` | PyMOL 状态机、canvas/viewport、相机和非背景首帧已由真实 APOE 验收；助手显示动作经中立 ViewState 同步 PyMOL/Mol*。 |
| `ENG-027` | Core Engineering | `smoke-validated` | 持久 Stage attempt 受理后由服务端推导递进冻结；冻结修改 API 统一返回结构化 `409 stage_locked`。 |
| `UI-019` | Product UI | `smoke-validated` | 冻结阶段显示只读摘要和锁定原因，移除上传、重选、重批和重生成入口，同时保留查看、下载和纯显示操作。 |
| `REP-008` | Reporting & Visualization | `smoke-validated` | PyMOL 与 Mol* 首次加载后保持挂载；真实 APOE Stage 02 已通过 `PyMOL → Mol* → PyMOL` 回归，返回 PyMOL 后 reshape、viewport、redraw 和结构首帧均恢复。 |
| `REP-009` | Reporting & Visualization | `smoke-validated` | 新助手统一发送当前完整 PML、结构/场景 metadata、最近十轮对话和动态 Skills，并接收四字段完整 PML；dev31 已通过真实 APOE 的 label-first 区域编辑、9/14/14 配色、空闲稳定性及 PyMOL/Mol* 往返验收。 |
| `ENG-028` | Core Engineering | `smoke-validated` | 结构助手改为部署者拥有的单一平台配置；请求端不再提交 provider 或用户密钥，公开状态接口不泄露 provider、模型、endpoint 或 API key。 |
| `UI-020` | Product UI | `smoke-validated` | 普通设置页和 Stage 01/02 助手栏不再提供模型、endpoint 或 API key 表单，只显示“EasyDesign 结构助手”的平台可用状态。 |
| `ENG-029` | Core Engineering | `smoke-validated` | Stage05Bundle/ScaleBundle 0.2、跨 run 不可变证据链接和旧 0.1 兼容已由 APOE policy/50k adoption 验证；没有复制 39 GB 或修改历史 manifest。 |
| `UI-021` | Product UI | `smoke-validated` | 真实 APOE 页面已显示 Tier A/B/C/D=1/1/5/14、1 组晋级、1 条诊断 warning，以及 Stage 06 50,000/50,000 与 8 GPU 历史。 |
| `ENG-030` | Core Engineering | `implemented` | Stage 04/06 执行位置已从科学 YAML 分离；本机支持 GPU 自动发现、资源门、最大卡数、append-only 租约、heartbeat 和恢复。 |
| `ENG-031` | Core Engineering | `implemented` | `/data/easydesign/managed-worker` 布局、RemoteJobBundle、`flock` 中央队列、8 GPU 租约、重启对账与 4→5/6→7 就地执行已实现；安装 systemd 仍由运维审核。 |
| `ENG-032` | Core Engineering | `smoke-validated` | Suzhou2 Manager dev1 revision 8 已用精确 dev35 wheel 激活，三后端/8 GPU probe 和真实 4→5、6→7 小链通过；私有远端推送权限仍是独立运维事项。 |
| `UX-008` | CLI & Developer Experience | `implemented` | 已实现稳定 host fingerprint 确认、工作区 key pair 检测/复用、一次性密码公钥安装、免密 worker 探针和可恢复逻辑解绑；不读取或修改个人 `~/.ssh`。 |
| `UI-022` | Product UI | `implemented` | Stage 04/06 已提供“当前机器 / Suzhou2”执行卡片；配对向导可复用已有密钥并用一次性密码完成公钥安装，随后展示队列/GPU/ETA 与同步状态。 |
| `UI-023` | Product UI | `smoke-validated` | 设置已收敛为“当前设备 / 公共算力 / 项目存档”三页；环境自动检查、缺失组件按需安装和折叠技术详情已通过双尺寸 Chromium 视觉验收。 |
| `UI-024` | Product UI | `smoke-validated` | Stage 04/06 与设置页统一使用真实 `pairing_state`，已配对 Suzhou2 可立即选择；设置支持安全逻辑解绑后重新配置，并可一键返回进入设置前的项目或页面。 |
| `UI-025` | Product UI | `smoke-validated` | dev36 在选择 GPU 数量前显示目标机空闲/总卡数，并用按需弹窗展示逐卡快照；受管 4→5/6→7 运行视图使用结构化阶段轨道和真实任务进度，真实 Suzhou2 probe 与三浏览器矩阵已通过。 |
| `VAL-008` | Scientific Validation | `smoke-validated` | dev35 已完成 Suzhou2 固定非 APOE 40 条 Stage 04→05 与 APOE 精确 8 条、1 GPU、单 shard Stage 06→07；两次均保持科学停止与历史 50k 不变。 |
| `UX-006` | CLI & Developer Experience | `implemented` | 根 `./easydesign` 提供 setup/doctor/ui/env/assets/workspace 命令；dev23 增加独立组件安装、显式可信 HTTPS pip 源与 SSH 断开后仍可恢复状态的 `setup --detach/--status`。完整后端矩阵仍待许可资产验收。 |
| `DATA-005` | Data & Assets | `implemented` | 七个环境已提交解析后的 linux-64 Conda/pip package set、安装后 inventory 与十五项资产 catalog；BoltzGen 五个 checkpoint 已独立登记并强制离线显式注入。全部许可资产下载验收仍待用户逐项确认。 |
| `UI-016` | Product UI | `implemented` | 安装中心展示环境/资产状态、完整及逐后端安装计划；与 CLI 共用持久 setup job，UI 重启后仍能恢复结构化终态。 |
| `VAL-006` | Scientific Validation | `implemented` | 固定 1UBQ fixture 的真实 Stage 01–05 逐步执行器与 Stage 06/07 adapter probe 已实现；只有实际全后端运行完成后才升级 smoke。 |
| `REL-001` | Release & Operations | `planned` | IP/LICENSE 决策后冻结公开 release 门槛。 |

### 通用决策门路线

`ENG-006` 已在 Stage 01/02 建立可恢复、可审计的通用 Decision Gate；后续阶段复用同一
`DecisionRequest` / `DecisionRecord`，不各自发明审批协议：

| Stage | 未来 gate | 状态 | 完成门槛 |
| --- | --- | --- | --- |
| Stage 03 | BoltzGen YAML 与设计矩阵确认 | `planned` | review-gated 由人确认；unattended 只允许版本化确定性 policy。 |
| Stage 05 | pilot filter 后 go/no-go | `planned` | 保存逐规则证据、预算和批准 authority。 |
| Stage 06 | 高成本规模预算授权 | `implemented` | 预算、源 Stage05Bundle、授权人、理由和科学限制确认进入不可变 ScalePlan；通用 Decision UI 后续补齐。 |
| Stage 07 | Top N 候选包批准 | `planned` | 只生成候选下单包；供应商下单永远由人工执行。 |
| 跨阶段 | biosafety 等 required review | `planned` | 未完成时最多生成 `draft-order-package`，不因 unattended 绕过。 |

### 七阶段实时摘要

下表由各 Stage `STATUS.md` 的“顶层摘要”自动生成；不得手工维护。

<!-- BEGIN AUTO-GENERATED STAGE ROLLUP -->
| Stage | 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新 | 详情 |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 01 | `smoke-validated` | 六类入口与 Target Bundle 0.4 已通过真实 APOE；REP-009 已把结构助手重构为完整 PML/Skill/SceneVersion 主循环，历史 typed 记录只读兼容。 | 冻结 Stage 01 科学边界；复验真实 provider 连续对话和双查看器投影。 | 无 Stage 01 1.0 工程阻塞；REP-009 的 live provider 浏览器矩阵待完成。 | 2026-07-31 | [STATUS](workflow/01-target-preparation/STATUS.md) |
| Stage 02 | `planned` | automatic、PSE/YAML、交互选区共享人工批准交接；REP-009 已用完整 PML `ed_region_A/B/C` 桥接替代模型 typed 区域协议。 | 复验完整 PML 区域往返，同时推进科学 benchmark 和 REP-002 独立 overlay。 | Stage 03 handoff 无工程阻塞；GPU、外部证据和 VHH–抗原科学验证仍是后续工作。 | 2026-07-31 | [STATUS](workflow/02-hotspot-discovery/STATUS.md) |
| Stage 03 | `smoke-validated` | S03-001 已完成通用基础编译器；APOE 3×7 共 21 个 YAML 全部通过固定 BoltzGen 0.3.2 官方校验。 | 冻结 1.0 基础模板，把开发重心移交 Stage 04 可恢复 pilot generation。 | 无 Stage 03 工程阻塞。 | 2026-07-26 | [STATUS](workflow/03-boltzgen-configuration/STATUS.md) |
| Stage 04 | `smoke-validated` | dev35 Manager 已在 Suzhou2 真实完成固定非 APOE 40-candidate Stage 04→05，队列、GPU 租约与落盘无 operational failure。 | 复用同一受管路径寻找能合法产生 Tier A 的第二真实 fixture。 | 当前 1UBQ 40/40 未通过 Stage 05 iPTM 门，不能进入 Stage 06；旧 APOE 证据不受影响。 | 2026-08-02 | [STATUS](workflow/04-pilot-generation/STATUS.md) |
| Stage 05 | `smoke-validated` | Suzhou2 已真实完成 dev35 原地 Stage 04→05 连续链；40 条 1UBQ 候选均被科学门正常处置。 | 在第二真实案例验证合法 Tier A 和 2–3 组晋级，同时保持正式门槛冻结。 | 1UBQ 40/40 均未达到 iPTM 0.5，合法发布 `stopped-no-tier-a`，不能用于 06→07 连通。 | 2026-08-02 | [STATUS](workflow/05-pilot-filtering/STATUS.md) |
| Stage 06 | `smoke-validated` | dev35 已在 Suzhou2 Manager 真实完成 APOE 8-candidate Stage 06→07；计划、分片、coverage 与终态均精确为 8。 | 在第二真实 target 验证 2–3 组 Tier A 的共享预算和深筛非空路径。 | Manager 私有 remote 仍缺推送权限；本次 8/8 均未通过 BoltzGen `pass_filters`，未进入 Protenix/TNP。 | 2026-08-02 | [STATUS](workflow/06-scale-generation-and-refolding/STATUS.md) |
| Stage 07 | `smoke-validated` | dev35 已在 Suzhou2 Manager 原地消费 APOE 8/8 ScaleBundle，并发布可审计空 review package。 | 在第二真实 target 验证进入 Protenix 多 seed 与 TNP 的非空深筛路径。 | 本次 8/8 均未通过 BoltzGen `pass_filters`，因此没有调用 Protenix/TNP；Manager 私有 remote 另缺推送权限。 | 2026-08-02 | [STATUS](workflow/07-final-filtering-and-selection/STATUS.md) |
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
