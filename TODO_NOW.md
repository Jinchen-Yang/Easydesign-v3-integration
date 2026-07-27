# EasyDesign 当前工作

## 七阶段实时摘要

下表由各 Stage `STATUS.md` 的“顶层摘要”自动生成；详细证据和任务仍以对应 STATUS 为准。

<!-- BEGIN AUTO-GENERATED STAGE ROLLUP -->
| Stage | 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新 | 详情 |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 01 | `smoke-validated` | schema 0.6 六类入口、三种 required-MSA 来源、Target Bundle 0.4、Viewer 与 Stage 02 交接均通过真实矩阵。 | 冻结 Stage 01 1.0 边界，把开发重心移交 Stage 03。 | 无 Stage 01 1.0 工程阻塞；商业敏感序列仍等待自建 MSA 与条款审查。 | 2026-07-25 | [STATUS](workflow/01-target-preparation/STATUS.md) |
| Stage 02 | `planned` | schema 0.6 已打通 automatic、PSE 固定颜色和 YAML 四编号人工区域；APOE 用户区域已发布可供 Stage 03 消费的 hotspots.yaml 0.3。 | 冻结 Stage 02 工程交接，启动 Stage 03 BoltzGen YAML；科学 benchmark 继续独立推进。 | Stage 03 handoff 无工程阻塞；GPU、外部证据和 VHH–抗原科学验证仍是后续工作。 | 2026-07-25 | [STATUS](workflow/02-hotspot-discovery/STATUS.md) |
| Stage 03 | `smoke-validated` | S03-001 已完成通用基础编译器；APOE 3×7 共 21 个 YAML 全部通过固定 BoltzGen 0.3.2 官方校验。 | 冻结 1.0 基础模板，把开发重心移交 Stage 04 可恢复 pilot generation。 | 无 Stage 03 工程阻塞。 | 2026-07-26 | [STATUS](workflow/03-boltzgen-configuration/STATUS.md) |
| Stage 04 | `smoke-validated` | APOE 21×40 共 840 个完整候选已由双 GPU 可恢复执行器收集，RunManifest 与全部交接产物完整性验证通过。 | 冻结 Stage 04 交接，把 840 个候选交给 Stage 05 v1.5 逐规则筛选。 | 无 Stage 04 工程阻塞；科学通过率由 Stage 05 判定。 | 2026-07-26 | [STATUS](workflow/04-pilot-generation/STATUS.md) |
| Stage 05 | `smoke-validated` | APOE 840 个 pilot 已完成 v1.5 审计；唯一 Tier A 扩展到 100 后，10/10 full-target Protenix 因 binder pose 不稳定而合法停止。 | 冻结 `stopped-no-scale-winner` 负结果，不启动本轮 APOE Stage 06/07。 | 无 operational failure；APOE 本轮没有通过科学规模化门。 | 2026-07-26 | [STATUS](workflow/05-pilot-filtering/STATUS.md) |
| Stage 06 | `implemented` | S06-003 已补齐远程 watch、心跳、恢复、manifest 同步和 UI 服务器选择；APOE 50k 继续运行。 | 跟踪 Suzhou2 20×2500，并用控制端只读镜像让合作者查看相同运行记录。 | 无代码阻塞；当前 dev11 worker 没有心跳字段，新提交/恢复的 dev12 任务才产生心跳。 | 2026-07-27 | [STATUS](workflow/06-scale-generation-and-refolding/STATUS.md) |
| Stage 07 | `implemented` | S07-001 已实现 v1.5 预筛、Protenix 三 seed、一致性、TNP 证据和确定性主备候选包，固定 TNP batch smoke 已通过。 | 保持通用能力冻结；APOE 在 Stage 05 科学停止，本轮不生成 Stage 07 候选包。 | 无代码阻塞；APOE 没有合法 Stage 06 ScaleBundle，50k 未授权。 | 2026-07-26 | [STATUS](workflow/07-final-filtering-and-selection/STATUS.md) |
<!-- END AUTO-GENERATED STAGE ROLLUP -->

## Now

- `[S06-002]` APOE 唯一已扩展 Tier A 已获探索性 `production-50000` 人工授权；保持
  Stage 05 `stopped-no-scale-winner` 不变；Suzhou2 首批 8 个 2500-candidate shard
  已在 8×A100 运行。`ENG-014/S06-003/UI-008` 已提供远程 watch、校验镜像、恢复与
  UI 服务器选择；继续跟踪 20 个分片直到完成或形成可恢复的 operational failure 证据。

## Next

- `[VAL-003]` 冻结当前 APOE 负结果，对相同候选、相同 MSA 和 seeds 101/202/303
  比较 no-template、target-template、target-template+hotspot constraint，并加入已知
  VHH–抗原正对照；未形成新 profile/ADR 前不得改变 Stage 05 默认 gate。
- `[UI-002]` 在下一条可继续的真实 run 上验收浏览器中的 doctor、启动、hotspot
  审批、drain 和 resume；当前 API/界面已实现，但不以只读 APOE scientific-stop
  冒充长任务交互 smoke。
- `[VAL-001]` 选择第二条独立真实 target，复用 frozen 1.0 主线；APOE 的
  binder-pose gate 只能通过预注册 benchmark 和新版本 profile 研究，不能事后调参。
- `[S06-001]` 通用 1000 smoke / 50000 production plan、25% 磁盘门、共享恢复和精确
  merge 已实现；正常主线仍要求 Stage 05 winner，人工 override 只用于明确记录的探索性
  运行。
- `[S07-001]` 通用深度筛选、Protenix 三 seed、TNP 和多样性候选包已实现，固定 TNP
  backend 单候选真实 smoke 已通过；APOE 因 Stage 05 科学停止而不会进入本轮 Stage 07。
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
