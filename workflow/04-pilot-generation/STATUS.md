# Stage 04 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态状态和验证证据。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `smoke-validated` | APOE 21×40 共 840 个完整候选已由双 GPU 可恢复执行器收集，RunManifest 与全部交接产物完整性验证通过。 | 冻结 Stage 04 交接，把 840 个候选交给 Stage 05 v1.5 逐规则筛选。 | 无 Stage 04 工程阻塞；科学通过率由 Stage 05 判定。 | 2026-07-26 |

## 当前结论

- 阶段状态：`smoke-validated`；通用实现、最小 backend smoke 和 APOE 21×40
  真实矩阵均通过。
- 正式 run 为
  `runs/apoe-s02-006-pse/20260726-003-stage04-pilot`：21 个策略各 40 个完整候选，
  共 840 个，candidate ID 全部唯一，RunManifest revision 3 完整性验证通过。
- 完整候选固定为 metric row、原始 complex CIF 和 refold CIF 三者一致；BoltzGen
  `budget=30` 不是 Stage 04 候选预算。
- Stage 04 不按官方 `pass_filters` 选择策略；840 个候选中该字段为 true 的 28 个、
  false 的 812 个，全部如实交给 Stage 05。

## 功能矩阵

| 能力 | 状态 | 当前证据 |
| --- | --- | --- |
| BoltzGen backend | `smoke-validated` | 固定 0.3.2 完整 pipeline 完成 APOE 21×40；严格收集原始/refold CIF、官方 design mask 和指标 |
| local executor | `smoke-validated` | 双 GPU、每 GPU 一个串行 strategy；7xl0 首次 39/40 后只补跑缺失的 1 个，最终 840/840 |
| Slurm/SMART executor | `planned` | 无 |
| 任务终态和候选索引 | `smoke-validated` | 61 条 append-only 事件、840 个唯一 CandidateRecord、终态 ProgressSnapshot、PilotBundle 与 checksummed manifest-only handoff 均通过 |

## Now

- 无。S04-001/ENG-008 的 APOE 真实门已经完成并归档。

## Next

- Stage 05 只消费本次 succeeded StageManifest 声明的 PilotBundle 与 CandidateIndex，
  执行 v1.5 逐规则筛选、Tier 分层和科学停止判断。

## Blocked

- 无当前实现阻塞。
- 不终止服务器上的非 EasyDesign GPU 任务；资源繁忙时等待或明确失败。

## 验证证据

- Stage 03 正式输入：
  `/root/autodl-tmp/Protein_design/easydesign-clean/runs/apoe-s02-006-pse/`
  `20260726-002-stage03-basic-vhh`，StrategyBundle 21 个 strategy，SHA-256
  `a8451f5f7f7d09e69fbf7cf966c04b70aef01a3863132671b756aa4fe64b87`。
- 当前服务器审计：两张 RTX 4080 可见；实际启动前仍须重新检查占用。
- 自动检查：199 passed、8 skipped；Ruff、mypy、wheel build 和 wheel asset
  21/21 均通过。
- 最小真实 backend smoke：
  `/root/autodl-tmp/Protein_design/boltzgen_work/`
  `easydesign_stage04_backend_smoke_20260726_01/backend-output`。固定
  BoltzGen 0.3.2 在 GPU 0 完成 design → inverse folding → folding →
  analysis → filtering，严格收集 1/1 个候选；原始 CIF SHA-256
  `bfe9fdca4d8ba075de43b0b0dbed5352db9a3c9a66d7b29dc749d79c1454d274`，
  refold CIF SHA-256
  `a760f8e3b37935f7c0ae733842a898de0a711888213df34ad72b2b0a0ad12a27`。
  该单样本 `pass_filters=false` 是候选科学结果，不是后端失败。
- APOE 全矩阵真实 smoke：
  `/root/autodl-tmp/Protein_design/easydesign-clean/runs/apoe-s02-006-pse/`
  `20260726-003-stage04-pilot`。终态为 21/21 task、840/840 candidate、0 个终态失败，
  累计 20,914.80052 秒，吞吐率 144.5866 candidate/hour。`candidate-index.json`
  SHA-256 为
  `432ebb9638dbc50585ebd4d930bdc7e17f6a1b675320961dfadea4f3cfd299c5`，
  `stage-manifest.json` SHA-256 为
  `7fc7930a4b525f4b2e0d10aab0e06bb3f4e04463c9620e8e8d34c3d1eb240285`，
  RunManifest revision 3 SHA-256 为
  `fd93c28823b35f17a6f595ad2d1aa623f5b0a376ab2f1ad923f16f0933babe04`；
  `easydesign runs show 20260726-003-stage04-pilot --json` 返回
  `integrity_status=verified`。

## 工作日志

- 2026-07-26：启动 S04-001/ENG-008；审计 BoltzGen 0.3.2 CLI、官方输出和旧运行，
  区分 `num_designs`、`budget`、`pass_filters` 与 EasyDesign 完整候选。
- 2026-07-26：完成通用实现、故障注入、恢复测试和单候选真实 backend smoke；
  Stage 状态升级为 `implemented`，等待 21×40 APOE 真实门槛。
- 2026-07-26：真实候选审计发现 CSV 拼接序列在重复片段下不能唯一恢复 CDR；改为读取
  BoltzGen 官方 NPZ `design_mask`，同时校验 mask、完整 binder 序列、designed sequence、
  `num_design` 和结构 residue 数，并将 mask 文件纳入 ArtifactRef。APOE 7eow 40 个真实
  candidate 已通过新收集器验证。
- 2026-07-26：resume 增加旧 runtime state 的 design-mask 证据升级；仅重读每个
  TaskRecord 明确声明的 task-attempt output，candidate identity 或数量变化即失败，
  已完成候选不会重新生成。
- 2026-07-26：修正 resume 后吞吐率/ETA 将历史候选除以本次短时长的问题；进度快照现
  使用 attempt 创建时间起算的累计 wall-clock elapsed time。
- 2026-07-26：将单个 BoltzGen task 的 deficit、attempt、严格收集和错误状态抽成共享
  执行组件；Stage 04 回归和恢复测试通过，Stage 05 扩展将调用同一实现。
- 2026-07-26：APOE 21×40 正式完成；7xl0 首次只产生 39 个完整候选，resume 仅补齐
  1 个缺口。最终 21 个策略均为 40 个、840 个 candidate ID 唯一、0 个终态失败，
  状态提升为 `smoke-validated` 并移交 Stage 05。

## 历史索引

- [2026-07 工程实现与 APOE 真实验收归档](history/2026-07.md)。
