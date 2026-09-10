# Stage 06 状态

稳定职责见 [`06-scale-generation-and-refolding.md`](06-scale-generation-and-refolding.md)。

| 总体状态 | 当前结论 | 更新时间 |
| --- | --- | --- |
| `implemented` | 本地多策略人工选择、任意正整数 exact budget、plan-bound approval、可恢复 scale/refold 和不可变 selection receipt 已实现。 | 2026-09-04 |

## 当前能力

- 研究者明确选择 1–3 个 Stage 05 晋级策略；选择 receipt SHA-256、策略子集和总预算冻结到
  Stage 06 config，不默认消费全部自动排序结果。
- allocation、尾分片、candidate ordinal、重复和缺口校验有确定性回归。
- 公开 façade 默认建议 50,000，但接受任意正整数；exact count 同时进入 immutable plan、
  allocation、resource/shard identity 与 approval。count 改变必然生成新 plan SHA 并要求重新批准。
- `smoke-1000`、历史 `production-50000` 与 `user-defined-v1` reader 兼容保留；新 artifact 不会
  反向覆盖历史 run。
- 生成、refold、progress、resume 和 ScaleBundle 全部在当前 clone 所在主机执行并保留
  manifest lineage。
- 既有单策略 ScaleBundle 和大型 run 只读保留，不因当前政策重写或自动续跑。

## 仍有效的验证事实

- 旧单策略真实运行证明 50,000 候选生成和 refold 管线可完成；它不等于当前多策略路径
  已完成同规模验证。

## 待完成

- 从当前 Pilot promotion receipt 完成一个小预算多策略 production smoke。
- 正式 50,000 运行属于高成本操作，必须在 plan 审阅后由研究者再次明确确认。
