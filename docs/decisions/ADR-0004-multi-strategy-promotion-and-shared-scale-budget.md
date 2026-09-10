# ADR-0004：多策略晋级与共享规模预算

- 状态：accepted
- 日期：2026-07-31
- 关联任务：`S05-002`、`S06-004`、`S07-002`、`ENG-029`、`VAL-007`

> Architecture v2 amendment（2026-09-04）：本 ADR 的 50,000 allocation 是默认值示例与
> 历史 `production-50000` identity，不再是唯一合法总数。当前 façade 接受任意正整数；
> exact count 进入 plan/allocation/shard/resource/approval SHA，count 改变必须重新审批。

## 背景

Nanobody Filter Standard v1.5 在 Tier A pilot 后用 100 条扩增和 full-target Protenix
选择唯一策略。APOE 的冻结历史结果证明 pilot 中存在一个 Tier A，但 10 个 full-target
预测均没有保持原 binder pose，因此旧流程合法发布了
`stopped-no-scale-winner`。该结果不能被回写或重新命名。

产品下一版需要把 full-target 复核视为诊断证据，而不是撤销已经由 pilot Tier 和
`F_YAML` 形成的策略晋级。同时，规模预算必须是全体晋级策略共享的总数，避免把
“最多三组”误解为每组各生成 50,000。

## 决策

1. 新筛选 profile 固定为 `nanobody-filter-standard-v1.6`。
2. Stage 05 按 `F_YAML` 晋级最多三个 Tier A；不足三组时不从 Tier B–D 补位。
3. 每组扩增至 100 条并完成 local/full-target 诊断。科学负结果形成 warning，不撤销
   晋级；后端、数量、文件和 checksum 故障仍阻止发布。
4. v1.6 Stage05Bundle 0.2 不再发布唯一 `winner_strategy_id`，也不产生
   `stopped-no-scale-winner`；无 Tier A 仍以 `stopped-no-tier-a` 终止。
5. Stage 06 的默认 50,000 是全局预算示例。1/2/3 组分别分配
   `50000`、`25000/25000`、`16667/16667/16666`，余数按 promotion rank 分配。
6. 每个 strategy 使用独立 ordinal 空间和 shard，合并时同时验证每组与全局的数量、
   唯一性、连续性和 lineage。
7. Stage 07 在全局候选池中使用同一门槛和评分，不为不同 YAML 硬留候选名额；最终包
   必须保留每个候选的 strategy 来源和来源分布。
8. Stage05Bundle/ScaleBundle 0.1 保持可读。旧 APOE 结果通过新的
   `PolicyReevaluationRecord` 与 `ScaleEvidenceAdoptionRecord` 引用，不复制大型数据、
   不使用 symlink、不修改旧 manifest。

## 影响

- schema 0.8 对 v1.6 使用 `advisory_validation`，旧 schema 0.7 自动规范化并保留 v1.5
  字段语义。
- Stage 05 UI 默认只显示 Tier 数、晋级数和 warning；pilot 结构证据按需展开，100 条
  诊断默认折叠。
- Stage 06 UI 先显示全局进度，再按 strategy 展开预算、shard、重试和 ETA。
- Stage 07 UI 先显示全局漏斗与来源分布，再按层级或候选展开结构和指标。
- 旧 v1.5 scientific stop 与后续 policy continuation 必须并列呈现，不能用新政策覆盖
  历史结论。

## 未决事项

- APOE 历史 50k 的采用记录必须在完整 candidate identity/checksum 复核后发布。
- 当前 clone 所在主机需要先在本地 runtime 登记 Protenix、TNP 和模型资产，并等待 GPU
  自然释放；不得终止其他任务以抢占资源，也不得切换到另一执行主机。
- 第二条独立真实 target 需要验证 2–3 个晋级策略的真实共享预算执行。
