# Promotion、scale、selection 与实验验证边界

本章只在pilot已完成且数据可比较时加载。它防止“有一个高分candidate”被直接升级为production或最终实验选择。

## 目录

1. 输入与状态机
2. Promotion gate
3. Promotion receipt
4. Scale allocation
5. Production evidence
6. Selection framework
7. Developability 与 diversity
8. 实验验证计划
9. 负结果与停止
10. 输出模板

## 1. 输入与状态机

合法顺序：

`completed pilot → diagnosis → eligible strategy proposal → user promotion approval → immutable promotion receipt → scale proposal → user scale approval → completed scale → selection analysis → user selection approval`

任何一步都不能由后一步倒推。例如scale output存在不证明promotion receipt合法；用户批准pilot run不等于批准promotion或scale。

### 1.1 必需输入

- pilot run/manifest/strategy bundle/checksums；
- frozen filter profile与complete diagnosis；
- Tier/promotion records；
- representative structures、sequence/pose diversity；
- mechanism/assay与forbidden effects；
- current project phase/status；
- GPU/disk/runtime/budget预检；
- planned experimental validation。

## 2. Promotion gate

### 2.1 决策问题

哪个strategy有足够证据值得扩大sampling，而不是哪个candidate最高分？

### 2.2 必需证据

- 完整denominator与missingness；
- frozen hard-gate outcomes；
- target integrity、site/hotspot命中、interface plausibility；
- CDR/framework attribution；
- sequence/pose diversity；
- strategy-level distribution；
- experiment contract与comparator；
- crop/full-context、state与mechanism review；
- profile-defined eligible Tier。

### 2.3 当前产品边界

`knowledge_class: product_invariant + version_specific_tool_fact`：当前 repository 默认的`nanobody-filter-standard-v1.6`只允许Tier A strategy进入promotion，最多三个，按frozen `score_yaml` descending、`strategy_id` ascending；不得从较低Tier填充。条件性 v1.7 当前沿用这一promotion policy，但只有artifact显式绑定合法 v1.7/OpenFold3 identity时才能这样解释。最终始终以当前run的frozen profile与promotion semantics为准，不能从版本号猜规则。

### 2.4 条件分支

- 多个Tier A且机制/pose冗余：不必全promote，优先保留机制与几何多样性；一旦多个strategy进入同一promotion receipt，当前Stage 06必须按frozen equal policy分配，不能再主观降配；
- 仅一个Tier A但由top-1/duplicate支撑：先confirmatory，不自动scale；
- integrated alternative胜出：需要confirmatory matched evidence后再解释因素；
- full-target warning/zero pass：按frozen policy可能是warning而非operational stop，但科学上必须解释，不能隐去；
- 无Tier A：保留scientific stop，返回上游，不从Tier B/C填充。

### 2.5 正例

两个Tier A：A的分布稳健、pose多样且mechanism明确；B score略高但序列collapse且同一pose。可只推荐A进入本次promotion；若要有限复核B，应建立独立confirmatory strategy revision/pilot。不能把A、B同时写入同一promotion receipt后再对B做非等额“limited scale”。

### 2.6 反例/误判

- 一个高BSA candidate带动整组promotion；
- 用用户希望“继续”替代exact promotion approval；
- target drift/highscore候选进入scale；
- 无Tier A时手工挑“最接近阈值”的组。

### 2.7 反证或停止条件

- identity/denominator/missingness不完整；
- hard gate/profile drift；
- winner依赖crop edge/framework错向；
- mechanism与forbidden effect冲突；
- confirmatory结果不重现；
- promotion receipt无法绑定immutable inputs。

### 2.8 输出字段

`promotion_candidates`, `eligibility`, `distribution_evidence`, `diversity`, `mechanism_support`, `residual_risks`, `recommended_allocation`, `approval_status`。

## 3. Promotion receipt

receipt至少固定：

- `selection_id`
- `project_id`
- `pilot_run_id`
- `pilot_manifest_sha256`
- `strategy_ids`
- `approved_at`

receipt是scale输入身份，不是科学解释本身。若pilot manifest、strategy list或project identity改变，不能复用旧receipt。

### 3.1 审批前展示

- exact pilot run/manifest hash；
- proposed strategy IDs/ranks/Tiers；
-每组planned/generated/unique/pass denominator；
- hard-gate与full-target/representative review；
- alternatives rejected与residual uncertainty；
- exact promotion command/revision。

## 4. Scale allocation

### 4.1 决策问题

在frozen production budget内，如何扩大有效搜索而不破坏pilot结论和可追踪性？

### 4.2 必需证据

- immutable promotion receipt；
- current scale policy/profile；
- promoted strategy identities；
- production candidate budget；
- historical uniqueness/pose diversity；
- GPU/disk/runtime与failure recovery；
- selection/experimental capacity。

### 4.3 当前默认

当前默认 v1.6 profile记录production总candidate budget为`50000`，allocation policy为`equal-across-promoted-v1`。这是version-specific product setting，不是科学最优分配定律；以实际scale config/artifact为准。若facade显式接受其他count，该run必须记录user-defined scale identity与单独审批，不能仍声称执行frozen standard 50,000。v1.7 artifact不得仅因数值相同就借用 v1.6 receipt或identity。

### 4.4 条件分支

- 一个promoted strategy：全部budget仍需检查diversity collapse风险；
- 多个promoted strategy：按current policy equal allocation，不凭Agent主观“更看好”改权重；
- 需要非等额scientific allocation：这是policy/config change，需明确新版本和用户审批；
- pilot uniqueness低：在scale前先考虑confirmatory/search-space adjustment，不能只加数量；
- native expert strategy：保留独立source/checksum/limitations。

### 4.5 正例

按receipt中的两个strategy和frozen equal policy形成allocation，展示每组数量、总量、预计资源和selection capacity，等待scale approval。

### 4.6 反例/误判

- 根据top candidate score私自90/10分配；
- 运行后删除失败任务并重命名同一scale run；
- 用更大数量掩盖site/representation问题；
- production启动后才检查disk。

### 4.7 停止条件

- receipt缺失/identity drift；
- budget与allocation不能整合且没有frozen rule；
- GPU/disk margin不足；
- pilot显示mode collapse而没有mitigation；
- selection/实验capacity无法承接输出；
- 用户未批准exact scale plan。

## 5. Production evidence

scale不是“更多pilot candidate”的简单同义词。分析必须保留：

- planned/complete/unique denominator；
- strategy/scaffold/site/CDR/context identity；
- profile、backend、model与definition；
- per-candidate hard gates与score components；
- sequence clusters与pose/interface clusters；
- target/site/mechanism representative review；
- failure/missingness；
- lineage从pilot strategy到scale candidate。

若scale阶段使用不同prediction/filter/selection规则，必须把它视为新证据层，不与pilot score直接合并。

当前Stage 07默认filter是`nanobody-final-v1.5`并使用Protenix。只有runtime、config、profile与artifact全部显式绑定OpenFold3 final合同，才可解释`nanobody-final-v1.6`；不得因文件存在或版本号更高而自动切换。

## 6. Selection framework

### 6.1 决策问题

应选择哪些候选进入实验，才能同时提高成功概率、覆盖机制/结构多样性并控制开发风险？

### 6.2 选择层次

1. identity与hard-gate合法；
2. target integrity与site/mechanism；
3. interface physical plausibility；
4. CDR/framework/crop/context审阅；
5. sequence/pose/epitope diversity；
6. developability proxies；
7. assay/format constraints；
8. 实验panel覆盖。

### 6.3 Pareto而非单分数

候选可在以下轴形成Pareto front：

- model confidence/geometry；
- mechanism footprint/approach；
- sequence与pose diversity；
- CDR vs framework attribution；
- target state robustness；
- developability risk；
- off-target/selectivity；
- assay/format适配。

单一aggregate score不能表达所有tradeoff。选择报告必须说明保留某个分数稍低候选是为了覆盖哪种独立假设。

### 6.4 Panel角色

- `primary_leads`：综合证据最强；
- `mechanism_diverse`：不同site/approach/steric path；
- `sequence_diverse`：减少同一sequence family集中；
- `risk_controls`：高分但某一明确风险，用于验证metric/机制；
- `negative_controls`：不命中机制或低confidence的可解释对照（必须安全且有价值）；
- `backup_formats`：对label/linker/valency或expression有替代。

### 6.5 正例

实验panel不只是top 20：保留若干不同pose/site/scaffold/sequence cluster，且每个候选都通过hard gates；加入一个target-site正确但CDR attribution边界的risk control验证framework假设。

### 6.6 反例/误判

- 取score top-N，实际18个是同一sequence/pose；
- 为多样性纳入hard-gate失败候选而不标control；
- 将computational rank当实验affinity排序；
- 没有针对desired/forbidden effect的assay。

## 7. Developability 与 diversity

### 7.1 可检查维度

只有artifact/tool真实提供时才报告数值；否则标planned analysis：

- sequence identity/cluster；
- CDR length/composition与extreme motifs；
- hydrophobic/charged patches；
- unpaired cysteine、glycosylation/deamidation/isomerization等sequence liabilities；
- predicted aggregation/solubility/stability；
- expression/fold proxy；
- pose/interface cluster；
- off-target/homolog conservation；
- linker/label/valency compatibility。

这些多为proxy。任何单一developability predictor不能替代表达、SEC、thermal、mass或functional experiments。

### 7.2 Diversity规则

- 先按exact sequence去重；
- 再按CDR/whole-binder sequence cluster；
- 再按pose/interface fingerprint cluster；
- 在cluster内按hard gates、mechanism与risk排序；
- panel同时控制cluster breadth与每cluster代表数；
- 保留scaffold/strategy lineage，避免把多样性仅理解为序列差异。

### 7.3 反证

如果不同sequence cluster收敛到相同wrong pose，这不是机制多样性；如果同sequence在不同structure state给不同pose，需要独立确认而不能按两个lead计数。

## 8. 实验验证计划

### 8.1 最低层次

1. expression/purity/monodispersity；
2. target binding与negative target/control；
3. affinity/kinetics（若目标需要）；
4. competition/functional/state-selectivity assay；
5. forbidden-effect/low-perturbation control；
6. target state/context：full-length、cell surface、ligand/partner/assembly；
7. developability/format；
8. structure/epitope验证（按项目价值）。

### 8.2 Mechanism-specific

- PPI blocking：binding + partner competition + target integrity；
- enzyme：binding + kinetic mode + fold/activity control；
- GPCR state：active/inactive binding + signaling/effector + ligand context；
- imaging：specific signal + localization + dose-dependent perturbation；
- chaperone：binding + state marker + particle/crystal quality +功能边界；
- membrane/glycan：cell-surface/full-context + glycoform/side controls；
- multimer：stoichiometry/assembly + monomer/alternative assembly control。

### 8.3 计算到实验的边界

不得把iPTM/PAE/BSA/H-bond/score改名为predicted affinity或functional potency。若用户需要实验排序，明确当前selection是“实验panel优先级”，不是结论。

## 9. 负结果与停止

### 9.1 Scale负结果

- production无合格candidate：保留完整run，返回pilot/site/context，不修改denominator；
- highscore不复现实验binding：更新project evidence，检查model calibration/mechanism，不删除candidate；
- binding有、function无：site/mechanism假设失败或format/context问题；
- function有、low-perturbation失败：对imaging等目标属于明确no-go；
- developability失败：可在保留mechanism证据下进入独立优化，不自动否定site。

### 9.2 停止条件

- 无合法promotion receipt；
- identity/profile/manifest drift；
- scientific diagnosis未完成；
- 选择依赖missing或unexplained fallback；
- panel完全缺少diversity或controls；
- 没有能验证desired和forbidden effect的assay；
- 用户未批准exact promotion/scale/select revision。

## 10. 输出模板

```yaml
scale_selection_plan:
  project_id: ""
  pilot_identity:
    run_id: ""
    manifest_sha256: ""
    filter_profile: ""
  promotion:
    proposed_strategy_ids: []
    eligibility_evidence: []
    rejected_alternatives: []
    receipt: null
    approval: awaiting_user_approval
  scale:
    policy: ""
    total_budget: null
    allocation: []
    gpu_preflight: ""
    disk_margin: ""
    estimated_runtime: ""
    approval: not_requested
  selection:
    hard_gate_pool: null
    unique_sequence_pool: null
    sequence_clusters: null
    pose_clusters: null
    panel:
      primary_leads: []
      mechanism_diverse: []
      sequence_diverse: []
      risk_controls: []
      negative_controls: []
    candidate_rationales: []
    approval: not_requested
  experimental_validation:
    expression_quality: []
    binding: []
    mechanism: []
    forbidden_effect: []
    context: []
    developability: []
  residual_uncertainty: []
  stop_conditions: []
```
