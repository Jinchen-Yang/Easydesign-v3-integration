# EasyDesign 当前工作

## 七阶段实时摘要

下表由各 Stage `STATUS.md` 的“顶层摘要”自动生成；详细证据和任务仍以对应 STATUS 为准。

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

## Now

- `[S02-005]` canonical schema 0.4 兼容的 APOE PSE→Stage 02 双方法真实回归已完成；当前只
  等用户从 SASA 或 ScanNet 中选择并批准 2–3 个完整区域。
- `[S02]` 多模型 SASA、显式 UniProt annotation policy 和审批契约已完成；详细方法、
  真实结果与仍未实现的证据源见
  [`workflow/02-hotspot-discovery/STATUS.md`](workflow/02-hotspot-discovery/STATUS.md)。

## Next

- `[S03]` 用户批准真实 APOE 区域并发布 `hotspots.yaml` 后，启动 BoltzGen YAML；
  Stage 03 不读取未批准的 automatic Top 3，并复用通用 YAML/design-matrix gate。
- `[S05/S06/S07]` 后续分别接入 pilot go/no-go、高成本预算和 Top N 候选包 gate；
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
- `[S03]` 工程契约无 runtime 阻塞，但 APOE Stage 03 handoff 等待用户完成真实区域批准；
  系统不会替用户编造 biological/structural rationale。
- `[S02]` GPU 优化：TensorFlow 1.14 GPU probe 通过，但官方 1BRS 与 APOE 在 RTX 4080
  报 cuBLAS GEMM execution failure；这是后续性能待办，不阻塞 CPU 主线。
- `[REL-001]` 公开许可证、PyPI 和正式 release 等待 IP/release 决策。
- `[DATA-001]` 第三方 VHH scaffold 迁移等待来源与权利审查。

## 历史索引

- [2026-07 项目历史](docs/history/2026-07/TODO_NOW.md)

阶段内部历史从对应 `workflow/<stage>/STATUS.md` 进入。历史不得改写；原记录有误时追加更正。
任何事项从 `Now` 移出前，必须在对应 history 写入带 UTC offset 的 RFC 3339 秒级
`完成时间`；该规则由 `make check` 自动校验。
