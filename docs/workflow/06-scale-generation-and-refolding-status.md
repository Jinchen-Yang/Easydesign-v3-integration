# Stage 06 状态

- 状态：`smoke-validated`（旧单策略真实证据）/ `implemented`（Local 人工多策略选择）。
- 既有 50,000 候选与验证 runs 保持不可变；本次没有重跑或删除。
- 新 Local 路径会把人工 selection receipt SHA-256 与策略子集冻结到 Stage 06 config，
  不再默认消费 Stage 05 自动排序的全部策略。
- 1/2/3 策略预算、尾分片、重复/缺口拒绝和人工子集授权均有回归测试。
- 当前待验收：从 Agent-native Pilot 的真实 promotion receipt 完成小预算 production smoke；
  正式 50,000 仍需研究者明确确认。

历史远程工程记录保存在 `06-scale-generation-and-refolding-2026-07.md` 与
`06-scale-generation-and-refolding-2026-08.md`，不属于 Local 产品操作面。
