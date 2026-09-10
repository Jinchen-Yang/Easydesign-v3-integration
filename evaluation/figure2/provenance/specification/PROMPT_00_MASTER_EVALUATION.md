# MASTER PROMPT — EasyDesign Figure 2 Full Evaluation

你现在负责在当前 EasyDesign v2.1 repository 上启动一次论文级、可复现、可审计的 Figure 2 benchmark。

这不是架构重构任务。不要为了 benchmark 赢而修改 EasyDesign 核心科学架构。

## 要回答的四个问题
1. EasyDesign 是否比 plain Codex / fixed pipeline 更容易正确完成蛋白设计工作流？
2. 在相同 backend、相同计算预算下，EasyDesign 是否提高困难 GPCR 任务的最终计算设计质量？
3. 这种增益是否泛化到非 GPCR target？
4. evidence / approval / research graph / capability / immutable artifact 是否真的提高科研可靠性与可复现性？

## 禁止
- 修改 7×40×X invariant；
- 看见结果后改 evaluator threshold；
- Plain Codex 和 EasyDesign 用不同模型/effort；
- 主比较使用不同生成后端或候选预算；
- 把计算指标称为实验 affinity / hit rate；
- 把数万 candidate 当数万独立统计样本；
- 伪造 manual-expert 或 wet-lab 数据；
- 未做 preflight 就启动 50k 或大规模 GPU；
- 引入大型新 workflow/agent framework。

## 建立 workspace
优先创建：
evaluation/figure2/
  configs/
  manifests/
  runners/
  metrics/
  fixtures/
  results/raw/
  results/derived/
  reports/
  plots/
  provenance/

## 主方法
1. easydesign_full：冻结 v2.1
2. plain_codex_same_model：同模型、同 effort、同底层工具，但不加载 EasyDesign Skill/Harness/ResearchGraph/claim/approval/capability
3. fixed_pipeline：同 backend/evaluator 的 deterministic protocol
4. manual_expert_reference：只有真实专家数据存在时使用，可只做代表性子集，严禁 LLM 模拟专家

Supplementary ablation 可选：
- EasyDesign no-interpretation-loop
- EasyDesign no-evidence-gate
- EasyDesign single-pass/no-redesign
不要做十几个无解释 ablation。

## 两种 benchmark 模式
### Controlled
所有方法共享 target structure、site/hotspot、X conditions、backend、budget、seed policy、evaluator。
用于 Figure 2C–F 的主要因果比较。

### End-to-End
只给 target identity + design goal + constraints。
允许 target→structure→site→strategy→pilot→interpretation→next strategy。
用于 2A/B、代表性 case 和 Extended Data。
不要把两种 effect 混成一个。

## 分层执行
### Tier 0：无 GPU/极低成本，立即执行
至少覆盖：
checksum mismatch、stale plan、missing artifact、unsupported capability、partial result、claim-evidence violation、approval mutation、wrong lineage、zero accepted designs、backend failure。
输出 2G/H 与一部分 2A/B。

### Tier 1：真实 target setup，低成本
对真实 GPCR/非GPCR做到 executable plan / validated strategy。
测 time-to-valid-project、completion、first-pass-validity、corrections、operational interventions。

### Tier 2：GPCR real computational benchmark
preflight 后执行。
First Pilot 严格 7×40×X。
Controlled 主比较必须 same X / same total candidate budget。
优先 4–8 个异质 GPCR target。

### Tier 3：Non-GPCR generalization
优先 BenchBB 7 targets：PD-L1, EGFR, IL7Rα, BHRF1, SpCas9, BBF-14, MBP。
若 EasyDesign 只设计 VHH，则仅把它们当 standardized target set，不能把历史 mini-protein wet-lab hit rate 当 apples-to-apples baseline。
可补 ion channel / soluble / lipid-associated 等 target family。

### Tier 4：Wet-lab
只有真实实验存在时使用；否则标 NOT AVAILABLE。

## Figure 2 主图
按 `01_FIGURE2_MASTER_SPEC.md` 实现 a–h：
2a time-to-valid-project
2b completion / first-pass validity / operational intervention
2c GPCR computational HQ yield
2d GPCR quality-depth / diversity / task-specific biology
2e non-GPCR generalization heatmap
2f per-target paired generalization effect
2g reliability stress test
2h evidence traceability / replay reproducibility

CPU/GPU utilization、成本、完整指标、ablation 放 Extended Data。

## Computational HQ yield
主终点：
accepted designs / all generated designs

成功判据必须是预先冻结、对所有方法相同的 independent evaluator profile，不得只用 EasyDesign 内部 ranking score。
至少覆盖：
- independent interface confidence
- interface PAE
- hotspot/contact engagement
- no severe clash
- target deformation
- multi-seed consistency
可增强：
- ipSAE
- BSA/ΔSASA
- Rosetta interface ΔG
- ΔG/ΔSASA
- shape complementarity
- VHH/TNP developability

如果生成/内部筛选用 AFO，不得只再用同一 AFO 单分数证明 EasyDesign 成功。

## Statistics
主单位 = target × independent campaign/run。
candidate 只用于计算 campaign yield。
至少报告：
- target-level paired effect
- 95% CI
- paired bootstrap
- effect size
- N targets / N runs / raw candidate count
如用 p-value，明确假设并做 FDR。
禁止候选级 pseudo-replication。

## Provenance
每个 run 至少保存：
repository commit/dirty status、method、model/effort、prompt hash、backend/evaluator versions、hardware、GPU、seeds、target hash、site/condition manifest hash、candidate budget、start/end time、plan SHA、output manifest SHA、failure/retry history。
没有 provenance 的数据不得进入主图。

## Expensive-run gate
Tier 0/1 直接做。
Tier 2/3 启动前生成：
evaluation/figure2/reports/EVAL_PREFLIGHT.md
必须列 target、methods、X、总 candidate、GPU-hours、storage、backends、evaluator cost、commands、hardware capacity。
若环境没有明确允许大 GPU benchmark，不得偷偷运行；把 commands 与任务队列准备好即可。

## 必须输出
EVAL_PREFLIGHT.md
EVAL_MANIFEST.json
TARGET_MANIFEST.csv
RUN_MANIFEST.csv
METRIC_DICTIONARY.csv
FIGURE2_DATA_LONG.csv
FIGURE2_SUMMARY.csv
FAILURE_EVENTS.csv
PROVENANCE_MANIFEST.csv
FIGURE2_RESULTS_REPORT.md
FIGURE2_STATISTICAL_REPORT.md
FIGURE2_MISSING_DATA.md
plots/figure2_a ... figure2_h

缺真实数据时允许 plotting-ready empty schema，禁止用 mock 数值冒充结果。

## 最终审计
生成 FIGURE2_FINAL_AUDIT.md，明确：
- 哪些是真实数据
- 哪些只完成 infrastructure
- 哪些 GPU 未运行
- 哪些可进主文/只能 Supplement
- fairness/leakage/threshold tuning/provenance 问题
- 下一批最值得运行的任务

除真正外部阻塞外，不要逐 Phase 问我。先完成 Tier 0 / Tier 1 / preflight。
