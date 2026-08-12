# 04 — Pilot generation（内部实现）

公开产品阶段为 `pilot`；数字 Stage 仅用于 manifest、artifact 和历史 run identity。

## 职责

本阶段消费冻结的 `StrategyBundle`，为每个显式 variant 调用本地 BoltzGen 0.3.2，保存
任务、attempt、日志、原始结构、refold 结构、官方 design mask 和 checksum。它只判断
候选是否完整，不做科学筛选或策略晋级。

每个 variant 的候选预算来自该 variant 的 `candidates`。新项目首轮在进入本阶段前已由
research façade 强制七个 scaffold 各 40 个候选；已有 Pilot 后的诊断或确认轮可让 20/40/55
等不同预算在同一 Pilot 中共存。旧 `required_complete_candidates_per_strategy` 仅用于
schema 0.1 兼容；`CandidateIndex`/`PilotBundle` schema 0.2 同时记录逐策略预算和总数。

StrategyBundle 0.3 还把 hypothesis、role、evidence、changed/held-constant factors、预期与
失败解释原样传入 Pilot 证据，供后续诊断使用；Stage 04 不根据这些文字自动晋级策略。

## 执行与恢复

- 每个 strategy 一个稳定 task；每张 GPU 同时最多一个重型 task。
- 启动前检查 GPU 占用和本地租约；不终止其他进程。
- 重试只补 deficit，不覆盖旧 attempt，不重跑 checksum 正确的候选。
- `Ctrl-C` 只脱离观察；`job drain` 只在安全检查点停止新调度。
- 进度由原子快照和 append-only event 提供，CLI 不解析日志猜状态。

## 完整候选

完整候选必须同时具有唯一 metrics 行、原始 complex mmCIF、refold mmCIF、官方 NPZ
design mask、可验证的 binder residue 映射和全部 SHA-256。BoltzGen 的 `pass_filters`
原样保存，但不参与本阶段成功判定。

## 输出

- `PilotPlan`
- `TaskTable`
- `CandidateIndex` 0.1/0.2
- `PilotBundle` 0.1/0.2
- progress、events、backend identity 和 StageManifest

公开 `easydesign pilot review` 随后读取 Stage 05 的结构化诊断；本阶段不会自动替代研究者
选择策略。
