# Stage 05 状态

稳定职责见 [`05-pilot-filtering.md`](05-pilot-filtering.md)。

| 总体状态 | 当前结论 | 更新时间 |
| --- | --- | --- |
| `smoke-validated` | 硬门、Tier、扩展、full-target 验证、scientific stop 和最多三策略晋级已实现并有真实证据。 | 2026-08-10 |

## 当前能力

- 只从 Stage 04 manifest 读取候选并校验文件、数量和 checksum；后端或证据错误属于
  operational failure，不会被科学 warning 吞掉。
- 逐候选结构、界面、hotspot、clash、BSA、序列去重、`S_screen`、Tier 和 `F_YAML`
  均由冻结 profile 决定。
- Stage05Bundle 0.2 最多晋级三个 Tier A，不从 Tier B–D 补位；没有 Tier A 时发布
  `stopped-no-tier-a`。
- Tier A 扩展复用 Stage 04 的本地 BoltzGen executor；full-target Protenix 使用 target
  required MSA、binder query-only、无模板和固定 seed 101。
- 旧 Bundle 0.1 和 v1.5 scientific stop 只读保留；新 policy 不回写旧 manifest。

## 仍有效的验证事实

- APOE 真实 run 在 21 个策略中得到唯一 Tier A；扩展后 12/100 通过 local gate，Top 10
  的 full-target Protenix 均 operational success，但 binder pose RMSD 18.005–31.726 Å，
  因冻结的 3 Å 门槛合法发布 `stopped-no-scale-winner`。
- 独立 1UBQ 40-candidate smoke 在 0 operational failure 下全部未达到 Tier A，并如实
  发布 `stopped-no-tier-a`；该负结果不能用于证明 Stage 06/07 的非空路径。

## 待完成

- 在第二个真实 target 上验证 1–3 个 Tier A 和共享预算路径。
- 用相同候选、MSA 和 seeds 101/202/303 预注册比较 no-template、target-template 与
  hotspot constraint；不得为迎合既有案例放宽门槛。
- 在线公共 MSA 无 SLA；失败必须作为可恢复 operational failure，禁止 no-MSA fallback。
