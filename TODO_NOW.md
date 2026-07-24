# EasyDesign 当前工作

## 七阶段实时摘要

下表由各 Stage `STATUS.md` 的“顶层摘要”自动生成；详细证据和任务仍以对应 STATUS 为准。

<!-- BEGIN AUTO-GENERATED STAGE ROLLUP -->
| Stage | 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新 | 详情 |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 01 | `planned` | sequence/FASTA MSA、单 Target PSE 与便携 Mol* Viewer 已真实跑通，其余四类入口待实现。 | 排期本地 PDB/mmCIF 与标准 Target Bundle 输入；Viewer 后续 overlay 留给 Stage 02。 | 公共 ColabFold 无 SLA；离线 MSA cache、自建服务与其余输入 adapter 未完成。 | 2026-07-24 | [STATUS](workflow/01-target-preparation/STATUS.md) |
| Stage 02 | `planned` | SASA 与 ScanNet CPU 双方法已在 APOE 正式 run 发布 Top 3 和比较报告。 | 人工审阅两套区域并建立批准区域到 Stage 03 的交接。 | 人工批准契约尚未实现；GPU 在 RTX 4080 上不兼容旧运行栈。 | 2026-07-24 | [STATUS](workflow/02-hotspot-discovery/STATUS.md) |
| Stage 03 | `planned` | 尚未实现；1.0 将先生成并校验 VHH BoltzGen 配置。 | 等待 Stage 02 人工批准区域后定义 YAML 与策略 manifest。 | Stage 02 handoff 未建立，VHH scaffold 权利待审查。 | 2026-07-24 | [STATUS](workflow/03-boltzgen-configuration/STATUS.md) |
| Stage 04 | `planned` | 尚未实现；clean 仓还没有真实 BoltzGen pilot。 | Stage 03 稳定后定义 pilot request/result 与执行器边界。 | 依赖已校验的 Stage 03 策略 bundle。 | 2026-07-24 | [STATUS](workflow/04-pilot-generation/STATUS.md) |
| Stage 05 | `planned` | 尚未实现；filter profile、逐规则审计和 shortlist 均待开发。 | Stage 04 候选契约稳定后建立可版本化 filter engine。 | 依赖 Stage 04 规范候选与原始 artifact。 | 2026-07-24 | [STATUS](workflow/05-pilot-filtering/STATUS.md) |
| Stage 06 | `planned` | 通用预测接口已在 Stage 01 实现，放大生成和复合物 refold 尚未开始。 | 复用 Protenix-v2 adapter，等待 Stage 05 shortlist 后定义 scale 契约。 | 依赖 Stage 05 入选策略和复合物预测验证。 | 2026-07-24 | [STATUS](workflow/06-scale-generation-and-refolding/STATUS.md) |
| Stage 07 | `planned` | 尚未实现；最终规则、聚类、多样性和 Top N 审核包均待开发。 | Stage 06 输出稳定后定义 final decision 与人工批准包。 | 依赖 Stage 06 完整预测与覆盖报告。 | 2026-07-24 | [STATUS](workflow/07-final-filtering-and-selection/STATUS.md) |
<!-- END AUTO-GENERATED STAGE ROLLUP -->

## Now

- **当前跨阶段重心是人工审阅 Stage 02 两套 Top 3，并建立到 Stage 03 的批准交接。**
- ScanNet CPU 已通过官方 no-MSA、APOE 138-aa backend smoke 和正式双方法 run；
  GPU 不再阻塞当前主线。
- 详细设备决策、SASA/ScanNet 结果、未实现 annotation 和验证证据：
  [`workflow/02-hotspot-discovery/STATUS.md`](workflow/02-hotspot-discovery/STATUS.md)。
- Stage 01 的 APOE MSA-backed sequence 纵向切片已真实跑通：默认 ColabFold、有界不可变
  attempts、A3M 校验、模型默认参数预测、统一 mmCIF Target Bundle 和 Stage 02 读取均通过，
  证据见
  [`workflow/01-target-preparation/STATUS.md`](workflow/01-target-preparation/STATUS.md)。
- 顶层摘要同步机制已进入质量门：任何 Stage STATUS 变化都必须自动刷新本文件和
  `TODO.md`。

## Next

- REP-002/REP-003：在不改变 Stage 02 科学输出的前提下，为 SASA/ScanNet 独立区域增加
  Viewer overlay 与显式人工批准；不得把 PSE 颜色或两种方法自动融合成默认赢家。
- 人工检查 SASA Top 3、ScanNet CPU Top 3 及 PSE 原始颜色 annotation 的重合关系。
- 定义人工批准区域集及 Stage 03 handoff，禁止自动发布默认赢家。
- 建立 sequence-hash MSA cache；自建 ColabFold/MMseqs2 作为后续生产兜底，公共服务不得
  被假定具有 SLA。
- 后续按排期实现 Stage 01 本地 PDB/mmCIF、RCSB、UniProt 和标准 Target Bundle 输入；
  不因 sequence/PSE 两条纵向切片成功而提前完成整个阶段。
- 将 ScanNet GPU 兼容性和性能优化作为后续 benchmark，不改变当前 CPU 主线。

## Blocked

- Stage 01：默认 ColabFold endpoint 已成功验证，但公共服务没有 EasyDesign 可承诺的
  SLA；正式 executor、真实 APOE run 和 Stage 02 交接已完成，离线 cache/自建服务尚未
  完成。Protenix 官方 endpoint 持续 `PENDING`，不进入
  默认 fallback；公共 endpoint 只批准内部研究序列，商业/敏感序列等待隐私、服务条款和
  自建 provider 审查。旧 SMART cache 缺失只影响历史复现。
- Stage 02 CPU 主线当前没有 runtime 阻塞；人工批准区域集与 Stage 03 handoff 尚未实现。
- Stage 02 GPU 优化：TensorFlow 1.14 GPU probe 通过，但官方 1BRS 与 APOE 在 RTX 4080
  报 cuBLAS GEMM execution failure；这是后续性能待办，不阻塞 CPU 主线。
- 公开许可证和公开 release 等待 IP/release 决策。
- 第三方 VHH scaffold 迁移等待来源与权利审查。

## 历史索引

- [2026-07 项目历史](docs/history/2026-07/TODO_NOW.md)

阶段内部历史从对应 `workflow/<stage>/STATUS.md` 进入。历史不得改写；原记录有误时追加更正。
