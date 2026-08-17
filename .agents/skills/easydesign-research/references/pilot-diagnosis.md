# Pilot diagnosis：从结果到可证伪的下一轮

本章是 `pilot` phase 核心。目标不是挑最高分，而是先确认数据可比较，再解释 target、binder、site、interface、CDR、scaffold 与实验因素，最后提出能区分竞争解释的下一轮。

## 目录

1. 输入、Dashboard 与完成标准
2. 数据可用性与 denominator
3. Group comparability
4. 诊断顺序
5. 分层诊断
6. 跨组因果推理
7. Candidate 结构审阅
8. 失败归因卡
9. 下一轮 experiment plan
10. Promotion/return-upstream
11. 输出模板

## 1. 输入与完成标准

### 1.1 必需输入

- pilot run/manifest/checksum；
- frozen strategy bundle与experiment metadata；
- planned/generated/parsed/evaluable/unique counts；
- filter profile/version/hash；
- per-candidate metrics、hard-gate decisions与missing reasons；
- representative structures与design mask；
- target/site/hotspot/scaffold/CDR/crop/context identity；
- operational warnings/errors。

### 1.2 完成标准

输出必须包含：

1. 数据是否足以科学比较；
2. 每组事实、相关性、假设和未知项；
3. dominant failure patterns与credible alternatives；
4. 为什么好、为什么坏的结构化解释；
5. promotion、停止、返回上游或下一轮的决策；
6. 下一轮每组的changed/held factors、prediction与falsifier；
7. 审批边界。

### 1.3 Stage 05 Review Dashboard 调用与解释合同

**决策问题**：如何用核心 Dashboard 高效检查完整 Pilot/Expansion 母集，同时不把页面交互或视觉印象升级为新的科学事实？

**必需证据**：先运行 `easydesign project status PROJECT --json`，绑定 current `project_id`、`run_id`、RunManifest、Stage 05 StageManifest、`stage05-bundle`、Dashboard report manifest/revision、report data SHA-256、filter profile、prediction backend/model/release 与所有 source artifact checksum。AFO 和 Protenix 在产品地位上等同；本次 Stage 05 使用哪一个，只能从 current config/artifact identity 读取，不能从项目历史或其他 stage 继承。

**调用分支**：

1. 状态为 `pilot-review-ready` 且 Dashboard revision 成功：用户明确要求打开/呈现时，执行状态给出的 `easydesign view PROJECT --run RUN --report stage05`；分析必须绑定该 revision 和 data hash。
2. 状态 warning 明确 Dashboard 缺失或 reporting failure：执行 `easydesign report build PROJECT --run RUN --report stage05`，确认新 revision 成功后再 view。重建只产生 reporting revision，不重跑 filter、不改变 Tier/promotion，也不修复 scientific artifact。
3. Stage 05 尚未完成、bundle/checksum 不合法或 report source identity 与 current run 不一致：停止 Dashboard 结论，回到数据恢复；不得扫描目录拼装页面，也不得调用旧 `easydesign-result-review` wrapper 或 `build_result_review.py`。

**解释合同**：

- `实验方案比较` 与 `全局候选审查`（Pilot/Expansion）用于遍历完整 denominator、missingness、hard/local gate、`score_screen`、`score_expand_structure` 和 target-conditioned evidence；页面不得缩成少数代表候选后替代分布分析。
- 搜索、排序、散点联动、置顶与收藏都是 `display-only`。收藏导出不是候选选择、promotion 或 approval receipt；页面显示顺序不是新的 rank。
- 页面中的结构来自 manifest 验证后的 artifact，并由本地 3Dmol.js 呈现。截图或人工观察必须记录 `report_revision`、`data_sha256`、`candidate_id`、structure artifact identity 和观察者结论；它属于 `fact`（页面显示内容）或 `inference`（人工解释），不能替代 hard gate。
- 比较组必须先满足本章第 3 节的 comparability。跨 backend/profile/model/release 的原始 score 不直接合并或解释为优劣；若阶段内确有不同身份，分层报告并说明不可比项。
- Dashboard reporting failure 不改变已完成 Stage 05 的科学状态；Stage 05 scientific stop、operational failure 与 reporting failure 必须分开。

**正例**：先核对 report manifest 指向 current Stage 05 bundle，再用完整 strategy 分布定位七 scaffold 共同 low hotspot coverage，并从候选结构抽查 approach/crop-edge；结论仍引用原始 metric/hard-gate artifact，Dashboard 只提供可追踪的审阅视图。

**反例/误判**：按页面默认排序截取 top 10，把收藏列表称为 promoted panel；或把 AFO 组与 Protenix 组的 raw confidence 直接平均。

**反证或停止条件**：report manifest/data hash 不可验证、页面与 current run 不一致、关键候选结构缺失、backend/profile identity 未绑定、页面展示与 source artifact 冲突。此时只报告 reporting/provenance gap，不作候选优劣结论。

**输出字段**：`dashboard_review.report_kind`, `report_revision`, `report_manifest_sha256`, `data_sha256`, `source_stage_bundle_sha256`, `backend_identity`, `display_only_actions_excluded`, `structured_observations`, `reporting_status`。

## 2. 数据可用性与 denominator

### 2.1 决策问题

结果缺失是科学失败、operational failure、解析缺失，还是候选被合法hard gate过滤？

### 2.2 必需证据

对每个strategy记录：

- `planned_candidate_count`
- `generated_candidate_count`
- `parsed_candidate_count`
- `metric_complete_count`
- `hard_gate_evaluable_count`
- `hard_gate_pass_count`
- `unique_sequence_count`
- `duplicate_count`
- `missing_by_metric`
- `operational_failure_count`

pass rate 的分母必须明确。缺失不是0，也不是自动pass/fail，除非frozen profile明确定义。

### 2.3 条件分支

- planned未生成：优先operational/sampling诊断；
- structure/metric缺失集中某组：可能是group-specific pipeline bias，不可直接与完整组排名；
- generated完整但hard gates零pass：科学或representation信号，可进入分层诊断；
- duplicate多：保留planned denominator，同时单列unique denominator与collapse；
- manifest/artifact不完整：停止scientific comparison。

### 2.4 正例

报告“planned N, generated N, metric-complete M, unique U, hard-pass P”，并将`N-M`个metric missing先解释为数据质量；pass rate必须写明使用`P/N`还是`P/M`及其理由。

### 2.5 反例/误判

只比较每组最高分；或删除failed/duplicate后重新定义本轮总数，使低多样性看起来优秀。

### 2.6 停止条件

- run/strategy identity不一致；
- denominator无法重建；
- metric/profile checksum漂移；
- candidate与strategy映射不唯一。

### 2.7 输出字段

`data_readiness`, `denominators`, `missingness`, `operational_failures`, `comparability_warning`。

## 3. Group comparability

### 3.1 对照矩阵

从frozen experiment metadata重建：

| group | comparator | changed_factors | held_constant | planned_n | identity/profile | comparable? |
|---|---|---|---|---:|---|---|

不要根据variant名字猜比较意图。

### 3.2 可比较条件

- target/site/hotspot/context身份明确；
- backend/profile/filter一致，或差异被明确建模；
- candidates per expanded strategy一致；
- operational completion与missingness相近；
- changed factor与held factors真实符合artifact；
- 组间没有隐含scaffold/asset/CDR/crop差异；
- sample selection未使用outcome-dependent规则。

### 3.3 因果边界

- 单因素matched diagnostic：可形成“该改变与结果差异一致”的有限因果推断；
- 多因素integrated alternative：只能评价方案整体，不得归因某一个因素；
- observational scaffold差异：先视为interaction hypothesis，需要重测；
- 少量top candidates：不能代表完整分布；
- shared pipeline：全组共同趋势并非独立重复。

### 3.4 正例

CDR3 diagnostic与baseline只差override，其他identity、scaffolds、counts一致；可检验reach hypothesis，但仍要检查override是否在每个asset产生等价科学改变。

### 3.5 反例/误判

crop+长CDR3+backup site组胜出后，结论写“长CDR3更好”。正确结论只能是integrated方案更有支持，单因素未解析。

## 4. 诊断顺序

严格按顺序，上一层失败会降低后层解释权重：

1. identity与artifact完整性；
2. operational completion与missingness；
3. target integrity/state/context；
4. binder integrity与sequence diversity；
5. site/hotspot命中；
6. interface物理质量；
7. CDR/framework attribution；
8. scaffold与实验因素interaction；
9. mechanism plausibility与assay prediction；
10. promotion或下一轮。

高interface score不能越过target drift、错误site、clash、missingness或错误state。

## 5. 分层诊断

### 5.1 Layer 0：Identity / provenance

**决策问题**：分析的candidate是否真的来自声称的target/site/strategy/profile？

**证据**：manifest hashes、project/run/strategy/candidate IDs、target/scaffold asset hashes、filter profile。

**分支**：任何identity drift→停止scientific conclusion；只读恢复/重建provenance。

**正例**：每个代表结构能追到candidate record、strategy、scaffold、design YAML和target bundle。

**反例**：从文件夹名识别scaffold，忽略manifest。

**停止**：checksum不匹配或candidate重复ID。

**输出**：`identity_status`, `provenance_gaps`。

### 5.2 Layer 1：Operational completeness

**问题**：失败发生在生成、解析、结构metric还是filter？

**证据**：任务状态、stderr/stdout hashes、missing reasons、counts。

**分支**：operational failure不升级为scientific negative；metric缺失按 [metric-guide.md](metric-guide.md) 处理。

**反例**：某scaffold任务全crash，于是结论“该scaffold不适合target”。

**停止**：组间completion差异足以颠覆排名。

### 5.3 Layer 2：Target integrity / state / context

**问题**：candidate中的target是否保持设计所需的结构与state？

**证据**：`target-ca-rmsd`、chain/length、state markers、ligand/partner/context、full-vs-crop对齐、局部结构。

**分支**：

- target drift高：interface score降级；
- 全组drift：shared representation/backend/config；
- 某scaffold特异drift：scaffold×target interaction或sampling；
- crop合格、full验证失败：crop artifact；
-全局RMSD合格但mechanism loop漂移：局部state仍可能错误。

**正例**：高iPTM候选target drift超过frozen gate，明确判“不支持晋级”，再检查是否因crop/context。

**反例**：高BSA补偿target变形。

**反证**：full-context复算保持state且interface仍合格，才削弱representation artifact解释。

**输出**：`target_integrity`, `state_consistency`, `context_failure_hypotheses`。

### 5.4 Layer 3：Binder integrity / diversity

**问题**：binder是否保持合理fold，结果是否只是少数重复序列/pose？

**证据**：`binder-ptm`, filter/refold RMSD, pass-filters, sequence uniqueness, pose clusters, design mask。

**分支**：

- fold confidence差：先诊断CDR search/scaffold，不解释interface；
- unique低：diversity collapse；
- sequence多样但pose单一：可能强geometry funnel或model bias；
- sequence重复跨ordinal：按artifact dedup规则保留representative，报告collapse。

**反例**：40个candidate中35个同序列，仍按40个独立支持计算。

**反证**：新sampling/independent run恢复多样性且同一pose/metric模式重现。

**输出**：`binder_integrity`, `sequence_diversity`, `pose_diversity`, `collapse_risk`。

### 5.5 Layer 4：Site / hotspot / off-site

**问题**：binder是否命中approved mechanism site，并以预期方向接触？

**证据**：`hotspot-coverage`, contacted hotspot count/total, off-site contacts, 3D pose, crop-edge contacts。

**分支**：

- coverage低、total contact高：错误表面吸附；
- coverage高但只触达一个cluster：可能hotspot set过宽；
- coverage高且mechanism footprint合理：支持site命中，不证明功能；
-全scaffold coverage低：shared hotspot/approach/context；
-backup site优于primary：比较mechanism而非仅分数。

**正例**：报告4个hotspot中接触2个，覆盖0.5，并指出这2个是否为mechanism anchors。

**反例**：只写coverage达标，不检查接触的是哪几个residue与approach。

**反证**：改变hotspot topology后off-site下降且mechanism contacts上升。

**输出**：`site_hit`, `hotspot_contacts`, `off_site_pattern`, `crop_edge_binding`。

### 5.6 Layer 5：Interface physical plausibility

**问题**：界面是否在当前模型内物理一致，而不是大但冲突？

**证据**：hard gates、BSA及source、residue/atom contacts、clash、polar/H-bond/salt-bridge proxies、confidence/PAE。

**分支**：

- BSA高+clash：不允许大界面补偿冲突；
- confidence高+BSA低：可能小anchor或metric/fallback问题，保留替代解释；
- H-bond多：几何proxy，不证明能量/质子化；
- BSA missing：查看fallback与missing reason；
- high iPTM/low PAE：只支持model confidence，非affinity。

**正例**：一个候选满足target/site gates但有moderate clashes；根据frozen decision判fail，不用综合分覆盖。

**反例**：将所有metric标准化后相加，允许任何hard gate被另一项抵消。

**反证**：独立full-target/refold或实验binding复核。

**输出**：`hard_gate_status`, `interface_metrics`, `physical_risks`, `metric_limits`。

### 5.7 Layer 6：CDR / framework attribution

**问题**：设计区域是否承担预期paratope，还是framework/crop edge主导？

**证据**：official design mask、`cdr-dominance`, `cdr-utilization`, per-CDR contacts、framework contacts、representative pose。

**分支**：

- dominance高/utilization适中：CDR主导；
- dominance低/total contact高：framework-driven或mixed paratope；
- dominance高/utilization低：少数anchor或未充分利用设计空间；
- framework contact集中某scaffold：scaffold×approach；
-全scaffold framework-driven：site/context/hotspot或attribution shared问题。

**正例**：不把low dominance自动判坏；检查framework contact是否合理、是否碰crop edge、是否偏离site。

**反例**：用通用IMGT range猜designed residues，忽略实际design mask。

**反证**：重设approach/hotspot后framework contact下降且site/CDR contacts保留。

**输出**：`paratope_attribution`, `per_cdr_role`, `framework_contact_class`, `design_mask_source`。

### 5.8 Layer 7：Scaffold / factor interaction

**问题**：模式来自scaffold、site、CDR、crop、context还是共同pipeline？

**证据**：matched matrix、per-group distributions、failure-rule frequencies、pose families、missingness。

**分支**：

- 单scaffold好：需confirmatory matched rerun；
- 单scaffold坏：检查asset/override/operational；
-七scaffold共同坏：优先shared factor；
-同scaffold跨site好：可能scaffold robustness；
-site effect只在某scaffold出现：interaction，不能宣布全局site优劣。

**正例**：用factor table列出所有组合，指出哪些contrast存在、哪些不存在。

**反例**：将每个candidate当独立样本，忽略candidate嵌套在strategy/scaffold。

**反证**：新的balanced matched experiment重现interaction。

**输出**：`factor_contrasts`, `interaction_hypotheses`, `unsupported_attributions`。

### 5.9 Layer 8：Mechanism / assay prediction

**问题**：结构上合格的binder是否真的支持desired biological effect？

**证据**：site与partner/ligand/state footprint、full-body steric model、assay contract、forbidden effect。

**分支**：

- blocking：检查direct overlap/steric path；
- imaging：检查功能面距离与扰动风险；
- state selection：检查counter-state可达性；
- enzyme：检查entry/rim/catalytic path；
- chaperone：检查state/assembly stabilization逻辑。

**反例**：interface metric优秀就声称功能抑制。

**反证**：competition/activity/state-selectivity/low-perturbation实验。

**输出**：`mechanism_support`, `functional_prediction`, `forbidden_effect_risk`, `required_experiment`。

## 6. 跨组因果推理

### 6.1 最小证据规则

任何“为什么好/坏”至少引用：

- 一条identity/completeness证据；
- 一条target/binder integrity证据；
- 一条site/interface证据；
- experiment comparator；
- 至少一个替代解释。

### 6.2 推理强度

- `observed`：明确数值/结构；
- `associated`：组间差异与changed factor一致；
- `supports`：matched design、multiple metrics/structures与prediction一致；
- `causes`：通常需实验或严格干预证据，pilot计算结果不轻易使用。

### 6.3 多重比较与小样本

不要因许多metric中某一个偶然差异挑故事。优先预先声明的primary metrics与failure rules；分布、denominator和effect direction优于单个极值。

## 7. Candidate 结构审阅

对每个晋级候选至少看：

- full target、binder、site与hotspots同屏；
- membrane/glycan/partner/assembly context；
- target drift局部位置；
- CDR1/2/3与framework contacts；
- clashes、buried unsatisfied polar/明显疏水暴露（若artifact支持）；
- crop edge/artificial surface；
- 与同组其他pose的diversity；
- counter-state/off-target结构的可达性。

结构截图/人工观察是evidence item，必须记录viewer/source/candidate ID；不能替代metric artifact。

## 8. 失败归因卡

每个dominant failure使用：

```yaml
failure_card:
  failure_id: fail-001
  scope: strategy|scaffold|candidate|all-groups
  observations: []
  dominant_rules: []
  identity_and_denominator: ""
  primary_hypothesis:
    statement: ""
    evidence_for: []
    evidence_against: []
    prediction: ""
    falsifier: ""
  alternatives:
    - statement: ""
      evidence_for: []
      discriminating_test: ""
  confidence: low|medium|high
  conclusion_not_supported: []
  safe_action: ""
```

不要把多个层次合成“模型不好”。例如：target drift、low hotspot coverage、framework contact和duplicate collapse应分别保留，再判断共同原因。

## 9. 下一轮 experiment plan

### 9.1 选择原则

下一轮优先区分当前最高价值、最可行动的不确定性；不是把所有参数都调到本轮winner附近。

### 9.2 每组必填

- `hypothesis_id`；
- comparator；
- `changed_factors`（最好一个主要因素）；
- `held_constant`；
- evidence refs；
- expected metric/structural/functional result；
- failure interpretation；
- candidate denominator；
- stop/promotion criterion。

### 9.3 常见下一轮

- target representation test；
- primary vs backup site matched test；
- hotspot topology test；
- CDR3 reach test；
- full vs crop test；
- scaffold confirmation；
- diversity/sampling test；
- missingness/metric pipeline audit；
- mechanism assay验证。

### 9.4 正例

七scaffold共同low coverage且target integrity合格：下一轮先比较primary hotspot topology与backup site，保持scaffold/CDR/full context不变；不先微调score weights。

### 9.5 反例

本轮只有integrated winner，下一轮直接scale；缺少confirmatory组，无法知道成功是否可重现。

## 10. Promotion/return-upstream

### 10.1 可考虑promotion

- data/identity完整；
- frozen hard gates通过；
- target integrity与site/mechanism plausibility成立；
- sequence/pose具有可接受diversity；
- result不依赖未解释missing/fallback/crop edge；
- strategy为当前profile允许的Tier；
- promotion receipt可绑定immutable inputs；
- residual uncertainty与实验验证计划明确。

### 10.2 返回上游

- identity/mapping问题→prepare/evidence；
- site/hotspot共同失败→prepare/strategize；
- context/crop/state错误→prepare/strategize；
- CDR/scaffold search问题→strategize；
- metric/parser/adapter能力问题→停止research mutation，形成code gap；
- operational failure→恢复/重跑同一immutable plan，不伪装新科学组。

### 10.3 不允许promotion

- 仅凭aggregate score；
- target drift或hard gate失败；
- denominator/missingness不清；
- framework/crop-edge主导且未解释；
- 因用户说“继续”就推断promotion approval。

## 11. 输出模板

```yaml
pilot_diagnosis:
  run_identity:
    project_id: ""
    run_id: ""
    manifest_sha256: ""
    strategy_bundle_sha256: ""
    filter_profile: ""
    filter_profile_sha256: ""
  dashboard_review:
    report_kind: stage05
    report_revision: ""
    report_manifest_sha256: ""
    data_sha256: ""
    source_stage_bundle_sha256: ""
    backend_identity: ""
    display_only_actions_excluded: []
    structured_observations: []
    reporting_status: available|rebuilt|failed|not_applicable
  data_readiness:
    status: comparable|partially-comparable|not-comparable
    denominators_by_strategy: []
    missingness_by_metric: []
    operational_failures: []
  group_comparisons:
    - contrast_id: ""
      groups: []
      changed_factors: []
      held_constant: []
      comparability: ""
      observations: []
      inference_limit: ""
  layered_findings:
    identity: []
    target: []
    binder: []
    site: []
    interface: []
    cdr_framework: []
    scaffold_factors: []
    mechanism: []
  failure_cards: []
  representative_candidates:
    - candidate_id: ""
      strategy_id: ""
      hard_gate_status: ""
      target_site_interface_summary: ""
      structural_review: ""
      interpretation_limit: ""
  decision:
    action: promote|iterate|return-prepare|return-strategize|stop-operational
    rationale: ""
    alternatives_rejected: []
    residual_uncertainty: []
  next_experiment_plan:
    groups: []
    success_stop_criteria: []
  approvals:
    promotion: awaiting_user_approval|not-eligible|not-requested
    next_run: not_requested
```
