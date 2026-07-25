# Stage 06 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态状态和验证证据。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `implemented` | S06-001 已实现 2×500/20×2500 分片计划、25% 磁盘门、精确 merge 和共享恢复执行器。 | 完成自动测试与最小 backend smoke；APOE 仅在 Stage 05 选出唯一策略后运行真实 1000。 | APOE 真实验收依赖 Stage 04/05 上游门；50k 没有本轮执行授权。 | 2026-07-26 |

## 当前结论

- 阶段状态：`implemented`，不是 `smoke-validated`。
- `smoke-1000` 表示全新 1000 个候选，固定为两个 500-candidate shard。
- `production-50000` 的二十个 2500-candidate shard 计划契约已实现，但不真实启动。
- Stage 06 复用 Stage 04 的 BoltzGen adapter、collector、TaskRecord、事件与恢复执行器。
- Stage 04/05 候选不计入 scale 数量；Stage 07 才执行 Protenix 深度筛选和 TNP。
- 软件能力与 APOE 科学结果分别报告；Stage 05 科学停止不会被改阈值绕过。

## 功能矩阵

| 能力 | 状态 | 当前证据 |
| --- | --- | --- |
| `smoke-1000` 2×500 计划 | `implemented` | `ScaleProfile`/`ScalePlan` 类型与单元测试 |
| `production-50000` 20×2500 计划 | `implemented` | 只验证计划和授权边界，不执行真实 50k |
| 25% 磁盘余量门 | `implemented` | Stage 04 声明 artifact 基线、20×保守倍率、任务前二次检查 |
| 多 GPU shard 调度 | `implemented` | 复用 ENG-008，一张 GPU 同时一个 shard |
| 中断恢复与增量收集 | `implemented` | 稳定 task/shard/ordinal、共享恢复状态机 |
| 精确 merge 与覆盖报告 | `implemented` | 1000 fixture 校验 identity 唯一和 ordinal `1..1000` |
| 发布中断恢复 | `implemented` | 终态 artifact identity/bytes 校验后复用，不覆盖 |
| APOE 新 1000 候选 | `planned` | 等待 Stage 04/05 真实门 |
| 真实 50,000 | `planned` | 本轮未授权 |

## Now

- Stage 06 不占用顶层 `Now`；当前顶层仍只跟踪正在运行的 S04-001。
- 完成全套自动测试与最小真实 BoltzGen backend smoke，冻结 `implemented` 证据。

## Next

- Stage 04 840 个候选发布后真实运行 Stage 05。
- 只有 Stage 05 唯一 winner 存在时，执行 APOE `smoke-1000`。
- 用真实运行重新测量每 candidate 磁盘峰值，并评估当前 20×安全倍率。
- 在另行授权前只验证 `production-50000` plan/resume，不创建真实 50k 任务。

## Blocked

- APOE 真实 Stage 06 依赖 Stage 05 唯一 scale winner。
- production 50k 依赖显式预算、容量和运行授权；当前不构成代码阻塞。

## 验证证据

- 模型与计划测试：1000/50000 profile、连续 shard、预授权拒绝、coverage 失败。
- 集成 fixture：非 APOE target 精确生成 1000 个新候选；发布恢复复用同一 bundle
  SHA-256；磁盘门失败时没有创建 task。
- 全仓：`make check`、`218 passed, 8 skipped`、`make build` 通过；wheel 的
  `21/21` 个资产和 console script 校验通过。
- 最小真实 backend smoke：待完成。
- APOE 真实 run：待 Stage 05 gate。

## 工作日志

### 2026-07-26

- 建立 `ScaleProfile`、`ScalePlan`、`ScaleShard`、`ScaleResourceReport`、
  `ScaleCoverageReport` 与 `ScaleBundle`。
- 资源门测试首次在临时文件系统触发拒绝，确认执行器在任务创建前停止；测试改为显式模拟
  足量磁盘，没有削弱 25% 产品规则。
- 将 Stage 04 candidate index 正式加入 Stage 06 input artifact，避免容量测量成为未声明
  的隐式读取。
- 增加终态发布恢复：崩溃遗留 artifact 只能在模型 identity 或原始 bytes 一致时复用。

## 历史索引

完成工程 smoke 后追加
[`history/2026-07.md`](history/2026-07.md)，记录秒级时间、验证、问题、解决方法、遗留
范围和完整 commit SHA。
