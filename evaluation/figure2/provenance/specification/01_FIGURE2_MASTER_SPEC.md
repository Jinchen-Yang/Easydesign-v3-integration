# Figure 2 — Full Main-Figure Specification

Figure 2 不是只有四张图。推荐 a–h 八个 panel，但围绕四个问题组织。

## 2a — Workflow turnaround / time-to-valid-project
Primary：time_to_valid_project_min。
定义：任务输入开始，到产生首个 target/site/backend/artifact 全部有效且可 freeze 的 executable project。

展示：
- 左：按 target family 的 violin + box + raw run points，y 用 log scale
- 右：全体 target 合并的方法比较

Secondary：
active human time、time-to-first-valid-plan、retry time、failed-attempt time。

不要把必要 scientific approval 直接当坏的人工干预。

## 2b — Completion / first-pass validity / intervention burden
主文三个 aligned readouts：
1. task_completion_rate
2. first_pass_validity_rate
3. operational_intervention_count

可测：
invalid action/config、correction、schema/path repair、tool failure、abandoned run。
另报 scientific_approval_retention_rate，说明关键科研审批没有为了“自动化”被删除。

## 2c — GPCR challenge: computational HQ yield
主结果之一。

HQ_yield = candidates passing frozen independent profile / generated candidates

主图：
- per-target paired points：fixed pipeline / plain Codex / EasyDesign
- 右侧 forest plot：EasyDesign − Plain Codex 的 Δyield + 95% CI

Controlled benchmark 必须 same target/site/X/7×40×X/evaluator/seed policy。

## 2d — GPCR quality depth / diversity / biology
主文只选 3–4 个解释性指标：
- independent interface confidence
- interface PAE
- hotspot coverage/contact retention
- target local RMSD/deformation

VHH 可加：CDR3 engagement、developability。
任务适用时才加：TM6 state deviation、pocket engagement、counterstate/offtarget margin、forbidden-contact rate。

右侧可用 quality–diversity scatter/Pareto：
x = sequence diversity
y = independent interface quality
显示 run/candidate density 与 method frontier。

## 2e — Non-GPCR generalization heatmap
rows = targets
columns = methods
value = computational HQ yield
旁边 target-family annotation。

优先 BenchBB 7 targets：
PD-L1, EGFR, IL7Rα, BHRF1, SpCas9, BBF-14, MBP。
VHH 模态下只把它们当标准 target set，不直接对比历史 mini-protein wet-lab hit-rate。

## 2f — Generalization effect / robustness
Forest plot：
每个 target 的 EasyDesign − Plain Codex paired ΔHQ yield。
底部 pooled effect + 95% CI。

同时统计：
target win rate、median improvement、worst-target effect、inter-target variance、GPCR vs non-GPCR subgroup。

主文最好展示 target-level raw effect，不创造难解释的单一“通用分”。

## 2g — Scientific reliability stress test
故障至少包含：
checksum mismatch、stale plan、missing artifact、partial backend result、unsupported capability、invalid constraint、backend crash、zero accepted designs、conflicting evidence、attempted experimental claim、missing/wrong approval、wrong lineage、duplicate/stale result、counterstate constraint unavailable。

指标：
correct-stop rate
unsafe-continuation rate
recovery-success rate
false-completion rate
unsupported-claim rate
approval-compliance rate

主比较 Plain Codex vs EasyDesign。

## 2h — Evidence traceability & replay reproducibility
指标：
evidence-traceability
lineage completeness
replay success
plan-hash compliance
provenance completeness
interpretation grounding

建议 grouped bars + CI，并可配一个很小的 H→E→O→I provenance example。

## 主图优先级
最核心：2c、2g
其次：2e、2a
解释：2d、2f、2b、2h

资源利用/成本进入 Extended Data。
