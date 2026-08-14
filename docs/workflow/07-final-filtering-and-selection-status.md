# Stage 07 状态

稳定职责见 [`07-final-filtering-and-selection.md`](07-final-filtering-and-selection.md)。

| 总体状态 | 当前结论 | 更新时间 |
| --- | --- | --- |
| `smoke-validated` | 完整处置、multi-seed、TNP、全局多样性选择、空 review package 和科学停止语义已实现。 | 2026-08-10 |

## 当前能力

- 进入筛选前完整校验 ScaleBundle 的策略集合、allocation、ordinal 和 Stage 05 晋级
  identity；旧单策略 Bundle 只读兼容。
- 所有策略共享同一门槛、分数和 lazy-greedy pool；每个 primary/backup 保留 strategy
  lineage，不为任何策略硬留名额。
- 实现序列合法性、liability/Cys、BoltzGen prefilter、`S_refold`、Protenix
  seed 101/202/303、一致性门、TNP evidence 和 20+20 上限。
- AFO/Protenix complex prediction 使用统一逐链 feature 合同；binder MSA 可显式搜索或
  预计算，target/binder template 可独立提供且能够与 MSA 同时使用。历史默认仍为
  target required MSA、binder query-only、无模板。
- 候选包始终为 `awaiting-human-review/not-ordered`；实际下单不属于本阶段。
- 所有 backend、GPU job、artifact 和 review package 都在当前 clone 所在主机处理；没有
  跨主机提交或远程 review 同步入口。

## 仍有效的验证事实

- 非 APOE 1000-candidate 集成 fixture 产生过非空 review package，证明实现没有 APOE
  ID、固定残基或固定三分区依赖。
- 固定版本 TNP adapter 已对官方 7EOW VHH 完成真实 batch 和严格 parser smoke。
- APOE 的 8-candidate smoke 全部因官方 BoltzGen `pass_filters=false` 合法停在 prefilter，
  发布 `stopped-no-final-candidate`、空 review package 和 `not-ordered`；没有用失败候选
  凑数，也没有把未调用的 Protenix/TNP 报成成功。
- APOE 既有 scientific stop 与后来人工授权的大型 ScaleBundle 必须并列保留；当前代码
  不自动采用或改写它们。

## 待完成

- 在第二个真实 target 上验证能进入 Protenix multi-seed 和 TNP 的非空路径。
- 增加正式候选 review gate、独立正对照、湿实验反馈和阈值校准。
