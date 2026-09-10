# Stage 04 状态

稳定职责见 [`04-pilot-generation.md`](04-pilot-generation.md)。

| 总体状态 | 当前结论 | 更新时间 |
| --- | --- | --- |
| `smoke-validated` | 可恢复的本地 BoltzGen pilot、逐 variant 预算和不可变候选证据已实现并有真实 smoke；0.3 元数据链已完成代码与单元验证。 | 2026-08-12 |

## 当前能力

- 每个显式 StrategyBundle variant 独立规划候选预算，并在当前主机的本地 GPU worker 执行。
- StrategyBundle 0.3 的 experiment contract 进入 design matrix 和 Pilot review；首轮每个
  condition 的七 scaffold × 40 在进入 Stage 04 前由 research façade 验证，并在 immutable
  pilot plan 中显式记录 X、7、40、280 与总数。
- typed ActionIntent 只从 plan 渲染兼容命令；run 必须携带与 DecisionRecord 完全一致的
  current plan SHA，strategy、backend、mapping 或 plan 变化都会拒绝旧 approval。
- pilot review 只在 checksum 完整、scientifically complete 的报告上写 deterministic
  observation；partial/operational failure 不会变成 scientific negative。
- project-local typed `pilot interpret` 将 Agent inference 作为独立 InterpretationEvent 保存；
  reducer 派生 hypothesis 当前状态，follow-up Strategy 1.3 校验 H→O→I lineage。
- task、attempt、progress、backend output、candidate index 和 manifest 均保持可恢复、可审计。
- schema 0.1 仅为既有 StrategyBundle 的只读兼容；新运行使用当前语义 façade。
- GPU 不可用属于资源等待或 operational failure，不能解释成科学负结果。

## 仍有效的验证事实

- APOE 21×40 pilot 和独立小型 backend smoke 证明候选生成、收集与 manifest 链可运行；
  这些结果不代表候选达到科学门槛。

## 后续真实研究验证

- 用当前 Agent-native 命令完成新的真实 target Pilot，积累 prospective science evidence；这不再是
  v2.1 Agent/Harness 架构缺口。
