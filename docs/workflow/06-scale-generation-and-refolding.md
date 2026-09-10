# 06 — Scale generation（内部实现）

公开产品阶段为 `scale`；数字 Stage 仅保留为科学 lineage identity。

## 职责

本阶段只消费研究者通过 `easydesign pilot promote ... --confirm` 发布的 selection receipt。
receipt 冻结 pilot RunManifest SHA-256、选择的一个或多个合法 Tier A strategy、顺序、审批
时间和自身 SHA-256。Stage 05 自动排序只定义可选集合，不能代替人工批准。

默认总预算为 50,000，但用户可选择任意合法正整数；50,000 是产品默认，不是科学规律。
总数在人工选择的策略之间等额分配，余数按 receipt 顺序分配；
它不是每个策略各 50,000。`scale plan` 只做资源说明，`scale run --confirm` 才创建新的
production run。

## Fail-closed 边界

- selection 必须属于当前项目，且 pilot manifest identity 未变化；
- strategy 必须是 Stage 05 合法 Tier A 的子集；
- Stage 05 无 Tier A 时禁止继续；
- Stage 06 frozen config 必须保存 selection IDs 和 receipt SHA-256；
- 计划、分片、候选索引和 coverage 必须消费同一人工子集；
- 启动前验证 GPU、backend、磁盘峰值和 25% 文件系统余量；
- 未确认时不得创建 run、job、attempt 或 shard。
- plan 必须冻结 total count、逐策略 allocation、shard/resource totals、backend/profile、
  source pilot manifest 与 mapping/foundation identity；任一字段改变都会产生新 plan SHA，
  旧 DecisionRecord 不得复用。

## 执行与输出

每个策略使用 strategy-local ordinal 和最多 2,500 条的稳定 shard。恢复只补缺口；合并时
同时验证每组与全局候选 identity 连续、唯一、checksum 正确，且 allocation/resource/shard
总和必须与用户选择的 exact count 完全一致。成功发布 `ScalePlanV0_2`、
candidate index、coverage、`ScaleBundleV0_2` 和 manifest。后续 `select` 在同一 production
lineage 中追加最终筛选，不补齐不存在的候选。

`smoke-1000` 与历史 `production-50000` artifact 保持读取兼容；新的公开 scale façade 使用
`user-defined-v1` exact count（包括用户接受默认 50,000 的情况），不会原地重写旧 artifact。
