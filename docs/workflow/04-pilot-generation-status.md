# Stage 04 状态

稳定职责见 [`04-pilot-generation.md`](04-pilot-generation.md)。

| 总体状态 | 当前结论 | 更新时间 |
| --- | --- | --- |
| `smoke-validated` | 可恢复的本地 BoltzGen pilot、逐 variant 预算和不可变候选证据已实现并有真实 smoke。 | 2026-08-10 |

## 当前能力

- 每个显式 StrategyBundle variant 独立规划候选预算，并在当前主机的本地 GPU worker 执行。
- task、attempt、progress、backend output、candidate index 和 manifest 均保持可恢复、可审计。
- schema 0.1 仅为既有 StrategyBundle 的只读兼容；新运行使用当前语义 façade。
- GPU 不可用属于资源等待或 operational failure，不能解释成科学负结果。

## 仍有效的验证事实

- APOE 21×40 pilot 和独立小型 backend smoke 证明候选生成、收集与 manifest 链可运行；
  这些结果不代表候选达到科学门槛。

## 待完成

- 用当前 Agent-native 命令完成一个新的最小真实 Pilot，并从负结果形成下一版 strategy，
  不覆盖既有 run。
