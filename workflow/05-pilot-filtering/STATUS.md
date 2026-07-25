# Stage 05 状态

稳定职责和算法见 [`README.md`](README.md)。本文件只记录动态状态、当前工作和证据。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `implemented` | Nanobody Filter Standard v1.5 的 pilot 审计、Tier、100-candidate 扩展、Protenix full-target 与唯一策略选择已形成统一可恢复实现。 | 等待 Stage 04 APOE 840-candidate 正式输入后运行真实 Stage 05。 | 真实 APOE 验收依赖 Stage 04 完成；代码实现无前置阻塞。 | 2026-07-26 |

## 当前结论

- 阶段状态：`implemented`，尚未达到 `smoke-validated`。
- 必需 pilot 硬门、逐候选证据、序列去重、strategy Tier、`S_screen` 和
  `F_YAML` 已实现。
- Tier A 扩展复用 Stage 04 的 BoltzGen task/executor/collector，不存在第二套生成逻辑。
- full-target Protenix 使用 target required MSA、binder query-only、无模板、seed 101。
- 没有 Tier A 或没有 scale winner 会发布 succeeded StageManifest 与明确
  `ScientificStop`，不会修改阈值迎合案例。
- 正式 APOE 结论尚不存在；历史结果不能代替当前 v1.5 真实运行。

## 功能矩阵

| 能力 | 状态 | 当前证据 |
| --- | --- | --- |
| FilterMetric / FilterDecision / Stage05Bundle 契约 | `implemented` | Pydantic 严格 schema、mypy strict |
| manifest-only 上游读取与 SHA-256 | `implemented` | Stage05 orchestration 与 scientific-stop 集成测试 |
| 结构、界面、hotspot、clash、BSA | `implemented` | `interface-geometry-v1` 单元测试；40-candidate 运行时性能审计 |
| 官方 design mask → CDR identity | `implemented` | 缺失 mask 明确失败；Stage 04 回归 |
| pilot 硬门与逐规则处置 | `implemented` | Tier A/B/C/D、去重和负结果测试 |
| `S_screen`、Tier 与 `F_YAML` | `implemented` | 冻结 profile 与确定性排序测试 |
| Tier A 扩展到配置总量 | `implemented` | 共用可恢复 BoltzGen executor；通用 fixture |
| full-target Protenix seed 101 | `implemented` | complex input、full confidence 和真实 cross-chain PAE parser 测试 |
| 唯一 scale winner / scientific stop | `implemented` | winner 与 no-tier 集成路径 |
| 原子 progress、append-only event、resume | `implemented` | 结构指标 cache、expansion/full-target TaskRecord、通用 watch |
| APOE 真实 Stage 05 | `planned` | 等待当前 Stage 04 21×40 完成 |

## Now

- 等待 `S04-001` 的 APOE `840/840` 完成并冻结 CandidateIndex。
- 上游完成后先核对每个候选的 structure、metrics、NPZ design mask 和 checksum，再运行
  `S05-001` APOE 正式 smoke。

## Next

- 对 APOE 840 个候选生成逐规则 pilot 报告。
- 若存在 Tier A，最多扩展三组到各 100 并执行 Protenix full-target top 10。
- 发布唯一 winner 或如实发布 `stopped-no-tier-a` /
  `stopped-no-scale-winner`。
- 完成真实 evidence、history、完整测试和 wheel smoke 后再提升为
  `smoke-validated`。

## Blocked

- 仅真实 APOE 验收等待 Stage 04；本阶段实现和 fixture 测试未被阻塞。
- 公共 ColabFold MSA 无 SLA；网络失败属于 operational failure，可恢复但不能无 MSA
  fallback。

## 验证证据

- 2026-07-26：`ruff check src tests` 通过。
- 2026-07-26：`mypy --strict src` 通过，92 个源文件无问题。
- 2026-07-26：Stage 04/05、filter、Protenix adapter 和 core task 定向测试
  `25 passed`。
- 通用 fixture 验证 scientific stop 会发布完整 Bundle、终态 progress 和 event artifact，
  且不启动 BoltzGen expansion 或 Protenix。
- 真实 Stage 04 strategy 的 40 个候选结构指标审计约 37 秒完成；这只是容量证据，不是
  APOE Stage 05 科学结论。

## 工作日志

- `2026-07-26T04:33:17+08:00`：完成 S05-001 的类型、指标、筛选、恢复和文档初版；
  状态保持 `implemented`，等待正式 APOE 输入。

## 历史索引

完成验收后追加 [`history/2026-07.md`](history/2026-07.md)，记录真实 run、科学结论、
问题、修复、完整 commit SHA 与远端核验。
