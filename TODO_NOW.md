# EasyDesign 当前工作

## 七阶段实时摘要

下表由各 Stage `STATUS.md` 的“顶层摘要”自动生成；详细证据和任务仍以对应 STATUS 为准。

<!-- BEGIN AUTO-GENERATED STAGE ROLLUP -->
| Stage | 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新 | 详情 |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 01 | `smoke-validated` | schema 0.6 六类入口、三种 required-MSA 来源、Target Bundle 0.4、Viewer 与 Stage 02 交接均通过真实矩阵。 | 冻结 Stage 01 1.0 边界，把开发重心移交 Stage 03。 | 无 Stage 01 1.0 工程阻塞；商业敏感序列仍等待自建 MSA 与条款审查。 | 2026-07-25 | [STATUS](workflow/01-target-preparation/STATUS.md) |
| Stage 02 | `planned` | schema 0.6 已打通 automatic、PSE 固定颜色和 YAML 四编号人工区域；APOE 用户区域已发布可供 Stage 03 消费的 hotspots.yaml 0.3。 | 冻结 Stage 02 工程交接，启动 Stage 03 BoltzGen YAML；科学 benchmark 继续独立推进。 | Stage 03 handoff 无工程阻塞；GPU、外部证据和 VHH–抗原科学验证仍是后续工作。 | 2026-07-25 | [STATUS](workflow/02-hotspot-discovery/STATUS.md) |
| Stage 03 | `smoke-validated` | S03-001 已完成通用基础编译器；APOE 3×7 共 21 个 YAML 全部通过固定 BoltzGen 0.3.2 官方校验。 | 冻结 1.0 基础模板，把开发重心移交 Stage 04 可恢复 pilot generation。 | 无 Stage 03 工程阻塞。 | 2026-07-26 | [STATUS](workflow/03-boltzgen-configuration/STATUS.md) |
| Stage 04 | `implemented` | S04-001/ENG-008 通用执行器、严格收集、进度、事件和恢复已实现并通过最小真实 BoltzGen smoke。 | 固定代码版本后启动 APOE 21×40，并以 840 个完整候选作为 smoke 门槛。 | 无代码前置阻塞；真实运行必须持续满足 GPU/磁盘门槛。 | 2026-07-26 | [STATUS](workflow/04-pilot-generation/STATUS.md) |
| Stage 05 | `planned` | 尚未实现；filter profile、逐规则审计和 shortlist 均待开发。 | Stage 04 候选契约稳定后建立可版本化 filter engine。 | 依赖 Stage 04 规范候选与原始 artifact。 | 2026-07-24 | [STATUS](workflow/05-pilot-filtering/STATUS.md) |
| Stage 06 | `planned` | 通用预测接口已在 Stage 01 实现，放大生成和复合物 refold 尚未开始。 | 复用 Protenix-v2 adapter，等待 Stage 05 shortlist 后定义 scale 契约。 | 依赖 Stage 05 入选策略和复合物预测验证。 | 2026-07-24 | [STATUS](workflow/06-scale-generation-and-refolding/STATUS.md) |
| Stage 07 | `planned` | 尚未实现；最终规则、聚类、多样性和 Top N 审核包均待开发。 | Stage 06 输出稳定后定义 final decision 与人工批准包。 | 依赖 Stage 06 完整预测与覆盖报告。 | 2026-07-24 | [STATUS](workflow/07-final-filtering-and-selection/STATUS.md) |
<!-- END AUTO-GENERATED STAGE ROLLUP -->

## Now

- `[S04-001]` `[ENG-008]` 从已验证 StrategyBundle 开始实现 TaskRecord、原子
  `progress.json`、append-only 事件、双 GPU 调度和精确 resume；先完成非 APOE fixture
  与最小 backend smoke，再启动 21×40。

## Next

- `[S05-001]` 按 Nanobody Filter Standard v1.5 完成逐规则 pilot 筛选、最多三组
  Tier A 扩展和唯一策略选择。
- `[S06-001]` `[S07-001]` 实现 1000 smoke / 50000 production plan、深度筛选、Protenix
  多 seed、TNP 和多样性候选包；本任务只授权真实执行 1000。
- `[S05/S06/S07]` 分别接入 pilot go/no-go、高成本预算和 Top N 候选包 gate；
  `required_reviews: [biosafety]` 不能被 unattended 绕过，真实下单始终是人工动作。
- `[REP-002]` 在不改变 Stage 02 科学输出的前提下增加 SASA/ScanNet 独立 overlay；
  可视化层不得融合 PSE、SASA 和 ScanNet。
- `[ENG-003]` 部署自建 ColabFold/MMseqs2，并建立 CI 平台矩阵；sequence-hash cache
  与 precomputed A3M 已由 S01-009 完成。
- `[S02]` 将 ScanNet GPU 兼容性和性能优化作为后续 benchmark，不改变 CPU 主线。

## Blocked

- `[S01]` 默认 ColabFold endpoint 已成功验证，但公共服务没有 EasyDesign 可承诺的
  SLA；remote、显式 offline cache、precomputed A3M、真实 APOE run 和 Stage 02
  交接均已完成。Protenix 官方 endpoint 持续 `PENDING`，不进入
  默认 fallback；公共 endpoint 只批准内部研究序列，商业/敏感序列等待隐私、服务条款和
  自建 provider 审查。旧 SMART cache 缺失只影响历史复现。
- `[S02]` GPU 优化：TensorFlow 1.14 GPU probe 通过，但官方 1BRS 与 APOE 在 RTX 4080
  报 cuBLAS GEMM execution failure；这是后续性能待办，不阻塞 CPU 主线。
- `[REL-001]` 公开许可证、PyPI 和正式 release 等待 IP/release 决策。
- `[DATA-001]` 第三方 VHH scaffold 迁移等待来源与权利审查。

## 历史索引

- [2026-07 项目历史](docs/history/2026-07/TODO_NOW.md)

阶段内部历史从对应 `workflow/<stage>/STATUS.md` 进入。历史不得改写；原记录有误时追加更正。
任何事项从 `Now` 移出前，必须在对应 history 写入带 UTC offset 的 RFC 3339 秒级
`完成时间`；该规则由 `make check` 自动校验。
