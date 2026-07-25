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
| EasyDesign 1.0 验收 | `planned` | VHH 七阶段、两条真实端到端基准和 Stage 01 六类入口测试通过。 |

## 长期工作板块索引

顶层每个板块只维护当前状态、一句话概述、当前宏观目标、下一里程碑和详细索引。Stage
内部细节仍以各 Stage STATUS 为准；非 Stage 工作默认归档到共享项目 history，避免提前
创建大量 Markdown。

| 前缀 | 板块 | 状态 | 一句话概述 | 当前宏观目标 | 下一里程碑或索引 |
| --- | --- | --- | --- | --- | --- |
| `S01–S07` | Scientific Pipeline | `planned` | 七阶段科学主线按独立契约推进。 | 先完成 VHH 1.0 真实端到端。 | 下方七阶段实时摘要。 |
| `ENG` | Core Engineering | `smoke-validated` | ENG-002/004/005/006/007 已建立代码身份、时间戳、ensemble、联网证据、Decision Gate 与六入口共享 dispatcher。 | 保持一个 API、不可变证据与跨平台 core。 | ENG-003：自建 MSA 服务和 CI 平台矩阵；[架构](docs/ARCHITECTURE.md)。 |
| `UX` | CLI & Developer Experience | `smoke-validated` | UX-001–004 已提供可安装 CLI、六入口 init、显式 MSA 策略、doctor、双模式运行、decision resume、runs 与 Viewer。 | 让真实能力通过一个稳定入口使用。 | 下一步随 Stage 03 增加配置生成与审批 UX；[README](README.md)。 |
| `REP` | Reporting & Visualization | `smoke-validated` | REP-001 自包含 Mol* Target Viewer 已通过真实 APOE smoke。 | 保持只读、便携、最小暴露的科学报告。 | REP-002：SASA/ScanNet overlay；可视化批准 UX 后续开发。 |
| `UI` | Product UI | `planned` | 尚未开发桌面或 Web 产品 UI。 | 未来只调用相同 Python API，不复制科学逻辑。 | UI-001：在 CLI/API 稳定后定义任务、审阅和恢复流程。 |
| `VAL` | Scientific Validation | `planned` | 当前只有工程 smoke，没有 binder 准确率结论。 | 建立预注册 benchmark、负结果和实验反馈链。 | VAL-001：VHH–抗原区域与端到端基准。 |
| `DATA` | Data & Assets | `planned` | 已有资产登记和 runtime-only 权重规则。 | 确保 scaffold、模型、fixture 的来源与权利可审计。 | DATA-001：VHH scaffold 授权和公开发布资产复审。 |
| `REL` | Release & Operations | `planned` | 当前只支持私有源码和本地 wheel。 | 建立 CI、版本兼容、安全和公开发布门槛。 | REL-001：等待 IP/LICENSE 决策后定义公开 release。 |
| `PAPER` | Publication | `planned` | 方法与证据持续积累，尚未冻结论文 claim。 | 形成可追溯方法、图表、benchmark 和补充材料。 | PAPER-001：Stage 01/02 方法和失败证据索引。 |
| `BIZ` | Product & Commercialization | `planned` | 商业路线存在，但未进入产品化承诺。 | 完成 IP、许可证、部署、支持和质量体系。 | BIZ-001：在科学/软件验证后建立产品需求与合规清单。 |

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
| Stage 01 | `smoke-validated` | schema 0.5 六类入口、三种 required-MSA 来源、Target Bundle 0.4、Viewer 与 Stage 02 交接均通过真实矩阵。 | 冻结 Stage 01 1.0 边界，把开发重心移交 Stage 02 审批与 Stage 03。 | 无 Stage 01 1.0 工程阻塞；商业敏感序列仍等待自建 MSA 与条款审查。 | 2026-07-25 | [STATUS](workflow/01-target-preparation/STATUS.md) |
| Stage 02 | `planned` | schema 0.4 已消费 Stage 01 冻结 UniProt 证据并支持 unattended 单方法交接；APOE 双方法仍等待人工批准。 | 用户从 SASA 或 ScanNet 中批准 2–3 个完整区域，再启动 Stage 03。 | 自动流程无 runtime 阻塞；Stage 03 等待真实人工区域批准，GPU 仅是后续优化。 | 2026-07-25 | [STATUS](workflow/02-hotspot-discovery/STATUS.md) |
| Stage 03 | `planned` | 尚未实现；1.0 将先生成并校验 VHH BoltzGen 配置。 | 等待 Stage 02 人工批准区域后定义 YAML 与策略 manifest。 | Stage 02 handoff 未建立，VHH scaffold 权利待审查。 | 2026-07-24 | [STATUS](workflow/03-boltzgen-configuration/STATUS.md) |
| Stage 04 | `planned` | 尚未实现；clean 仓还没有真实 BoltzGen pilot。 | Stage 03 稳定后定义 pilot request/result 与执行器边界。 | 依赖已校验的 Stage 03 策略 bundle。 | 2026-07-24 | [STATUS](workflow/04-pilot-generation/STATUS.md) |
| Stage 05 | `planned` | 尚未实现；filter profile、逐规则审计和 shortlist 均待开发。 | Stage 04 候选契约稳定后建立可版本化 filter engine。 | 依赖 Stage 04 规范候选与原始 artifact。 | 2026-07-24 | [STATUS](workflow/05-pilot-filtering/STATUS.md) |
| Stage 06 | `planned` | 通用预测接口已在 Stage 01 实现，放大生成和复合物 refold 尚未开始。 | 复用 Protenix-v2 adapter，等待 Stage 05 shortlist 后定义 scale 契约。 | 依赖 Stage 05 入选策略和复合物预测验证。 | 2026-07-24 | [STATUS](workflow/06-scale-generation-and-refolding/STATUS.md) |
| Stage 07 | `planned` | 尚未实现；最终规则、聚类、多样性和 Top N 审核包均待开发。 | Stage 06 输出稳定后定义 final decision 与人工批准包。 | 依赖 Stage 06 完整预测与覆盖报告。 | 2026-07-24 | [STATUS](workflow/07-final-filtering-and-selection/STATUS.md) |
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
| EasyDesign UI | `planned` | UI 调用同一 Python API，可创建、恢复、审阅和比较完整 run，不复制科学逻辑。 |
| 多 binder 设计平台 | `planned` | VHH、蛋白、肽及后续类型通过能力声明接入，用户用一次配置运行完整流程。 |
| 科研成果 | `planned` | 方法、benchmark、失败分析和真实实验结果形成可审计论文证据链。 |
| 商业产品 | `planned` | 完成 IP、许可证、安全、部署、支持、审计和质量体系，形成可持续产品。 |
| 数据与模型闭环 | `planned` | 经授权的实验反馈能够版本化回流，用于评估和改进而不污染历史证据。 |

长期目标不改变 1.0 的范围：当前首先把 VHH 主线真实跑通；蛋白和肽不会被包装成已经实现。
