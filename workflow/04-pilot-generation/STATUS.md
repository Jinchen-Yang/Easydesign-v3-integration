# Stage 04 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态状态和验证证据。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `implemented` | S04-001/ENG-008 通用执行器、严格收集、进度、事件和恢复已实现并通过最小真实 BoltzGen smoke。 | 固定代码版本后启动 APOE 21×40，并以 840 个完整候选作为 smoke 门槛。 | 无代码前置阻塞；真实运行必须持续满足 GPU/磁盘门槛。 | 2026-07-26 |

## 当前结论

- 阶段状态：`implemented`；通用代码和最小真实 backend smoke 已通过，但未满足
  APOE 840-candidate 门槛，因此不能标记 `smoke-validated`。
- Stage 03 APOE 21/21 StrategyBundle 已通过，可作为正式输入。
- 完整候选固定为 metric row、原始 complex CIF 和 refold CIF 三者一致；BoltzGen
  `budget=30` 不是 Stage 04 候选预算。

## 功能矩阵

| 能力 | 状态 | 当前证据 |
| --- | --- | --- |
| BoltzGen backend | `implemented` | 固定 0.3.2 完整 pipeline 的单候选真实 smoke 成功；严格收集原始/refold CIF、官方 design mask 和指标 |
| local executor | `implemented` | 双 GPU、每 GPU 一个串行 strategy；资源门槛、结构化失败和精确 deficit resume 已测试 |
| Slurm/SMART executor | `planned` | 无 |
| 任务终态和候选索引 | `implemented` | TaskRecord、ProgressSnapshot、CandidateRecord、PilotBundle 与 manifest-only handoff 已测试 |

## Now

- `[S04-001]` 在固定实现提交上执行 APOE 21 个 strategy，每组收集 40 个完整候选。
- `[ENG-008]` 在长任务中验证 `runs watch`、中断恢复和 GPU 归属证据。

## Next

- 840/840 完成后审计每组计数、checksum、事件序列和 Run/Stage manifest。
- 通过 Stage 04 完成门后，将唯一事实来源交给 Stage 05 filter engine。

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

## 历史索引

已结束日志按月移动到 `history/YYYY-MM.md`；当前尚无归档。
