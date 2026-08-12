# Artifact metric、hard gate 与 missingness 指南

本章只解释当前 artifact 实际字段。所有metric都是模型或几何proxy，不是实验affinity、specificity、function或developability证明。最终以run中frozen `FilterDecision`、profile identity和source为准。

## 目录

1. 固定 profile identity
2. Identity 与 completeness
3. BoltzGen/refold metrics
4. EasyDesign structure metrics
5. Pilot hard gates
6. Score 与排名
7. Missingness 与 fallback
8. 组合解释
9. 误判与停止条件
10. Metric report 模板

## 1. 先恢复 profile identity

`knowledge_class: version_specific_tool_fact`

不要从本章、聊天或最新版本号猜当前 run。先读取 frozen config、filter profile、
prediction receipt、metric definition 与 source hash，再选择解释合同。

当前 repository 默认路径是：

- Stage 05 filter：`nanobody-filter-standard-v1.6`；
- full-target prediction backend：`protenix-v2`；
- metric definition：`interface-geometry-v1`；
- source document：`NANOBODY_FILTER_STANDARD_V1.6.md`；
- source SHA-256：`7fd2d11eba6fe634095bb8cb1e902f39ca59d837cd601c393e978424a4848cfb`。

`nanobody-filter-standard-v1.7`是显式 OpenFold3 路径，不是默认升级或 fallback。只有同时满足以下条件才按 v1.7 解释：

- frozen config 明确选择`filter_profile=nanobody-filter-standard-v1.7`；
- full-target backend 明确为`openfold3-af3-jax`；
- runtime component、model、runner、profile hash与artifact receipt均可验证；
- metric definition为`openfold3-p2-af3-jax-complex-confidence-v1`。

任一条件不满足都停止 v1.7 解释，不能借用 v1.7 字段或阈值补全 v1.6/未知 artifact。历史 v1.5、当前 v1.6、条件性 v1.7 的同名 metric 也必须保留各自 source/version。

## 2. Identity 与 completeness

这些不是“性能分数”，却是所有解释的前提：

- `candidate_id`, `strategy_id`, `ordinal_within_strategy`：候选追踪；
- target/scaffold/strategy/profile/checksum：输入与规则身份；
- `design_mask_source`, `designed_binder_residue_ids`：CDR/design attribution来源；
- planned/generated/parsed/metric-complete/evaluable counts：denominator；
- `duplicate_of_candidate_id`, unique sequence count：去重与collapse；
- source、unit、definition version、missing reason、fallback flag：metric语义。

没有identity/completeness就不应比较score。

## 3. BoltzGen/refold metrics

| metric | source/unit | 可支持 | 不支持 |
|---|---|---|---|
| `pass-filters` | `boltzgen`/bool | backend自身filter汇总 | 实验binding或无偏质量 |
| `design-to-target-iptm` | `boltzgen` | model内设计链-target界面置信proxy | affinity、specificity、mechanism |
| `min-design-to-target-pae` | `boltzgen`/Å | 最小界面PAE proxy | 全界面均可靠 |
| `filter-rmsd` | `boltzgen`/Å | filter/refold整体几何一致性 | target state正确 |
| `filter-rmsd-design` | `boltzgen`/Å | 设计区域几何一致性 | sequence可表达/可开发 |
| `binder-ptm` | `boltzgen`或profile定义 | binder fold confidence proxy | 溶解性、热稳定或产量 |
| `delta_sasa_refolded` | `boltzgen`/Å² | structure BSA缺失时的候选fallback来源 | 与EasyDesign BSA无条件等价 |

这些字段不能跨backend/model/profile/version无条件比较。

## 4. EasyDesign structure metrics

### 4.1 Target/binder integrity

- `target-ca-rmsd` / `target_ca_rmsd_angstrom`：candidate target相对reference的Cα drift。全局值合格不保证局部state loop正确；高值会降级后续interface解释。
- `binder-pose-rmsd`：full-target/最终验证时binder pose偏移；只在相同定义与reference下解释。
- `binder-ptm`：见上；source可能随artifact阶段不同，必须读source。

### 4.2 Site/interface coverage

- `hotspot-coverage`：approved hotspot被接触比例；必须同时看`contacted_hotspot_count`与`hotspot_count`，并检查具体residue。
- `binder-contact-coverage`：binder residues中参与接触的比例。
- `residue-pair-contact-count`：接触residue pair数量。
- `atom-contact-count`：接触atom pair数量。

接触多不等于机制正确；off-site、crop-edge或framework-driven接触可能同样增加数值。

### 4.3 Paratope attribution

- `cdr-dominance`：接触binder residues中由official designed/CDR residues贡献的比例；
- `cdr-utilization`：designed/CDR residues中参与接触的比例；
- `design_mask_source`：必须来自BoltzGen official design mask，不靠通用序列范围猜测。

低dominance需结构复核，不自动等于失败；高dominance也不证明affinity。

### 4.4 Physical geometry

- `severe-clash-count`：低于profile severe threshold的atom-pair冲突数；
- `moderate-clash-count`：profile moderate范围的atom-pair冲突数；
- `hydrogen-bond-count`：当前实现统计跨链N/O/S heavy-atom在3.5 Å内的几何proxy；不判断氢、donor/acceptor角色或角度，因此不能称为严格氢键；
- `salt-bridge-count`：带电原子/残基的几何proxy；
- `polar-contact-fraction`：接触中极性atom-pair比例；
- `interface-bsa` / `interface_bsa_angstrom2`：buried surface area；可missing。

当前默认 v1.6 profile 的几何定义包括：heavy-atom contact 5.0 Å、severe clash <1.5 Å、moderate clash 1.5–<1.8 Å、H-bond heavy-atom 3.5 Å、salt bridge 4.0 Å、SASA probe 1.4 Å；这些是版本化计算定义，不是普适物理定律。其他 profile 即使数值恰好相同，也必须引用其自身 identity。

### 4.5 BSA provenance

- `interface-bsa-fallback-used`：是否使用fallback；
- `interface_bsa_missing_reason`：若当前manifest-verified artifact真实暴露，则保留EasyDesign BSA缺失原因；
- source=`easydesign-structure`或`boltzgen`必须保留。

fallback值不能在不声明source的情况下与primary BSA混排。当前`pilot-filter-report`可暴露fallback value、source与`interface-bsa-fallback-used`，但不保证暴露runtime structure-metrics cache中的原始missing reason。正式artifact未提供时写`not-exposed-in-pilot-filter-report`与`capability_gap`；不得扫描cache猜reason或编造一个。

## 5. Pilot hard gates

当前默认 v1.6 pilot core hard gates如下。解释时仍以candidate artifact的`FilterDecision`为准，报告`rule_id`, `metric_id`, `operator`, `threshold`, `observed`, `passed`；不要凭记忆重算，也不要仅因 v1.7 当前沿用相同数值就混用 profile identity。

| rule_id | metric | operator/threshold |
|---|---|---|
| `require-boltzgen-pass` | `pass-filters` | `eq true` |
| `require-hotspot-coverage` | `hotspot-coverage` | `ge 0.40` |
| `require-iptm` | `design-to-target-iptm` | `ge 0.50` |
| `require-interface-pae` | `min-design-to-target-pae` | `le 10.0 Å` |
| `require-target-rmsd` | `target-ca-rmsd` | `le 3.0 Å` |
| `forbid-severe-clash` | `severe-clash-count` | `eq 0` |
| `limit-moderate-clash` | `moderate-clash-count` | `le 3` |
| `deduplicate-sequence` | binder sequence | strategy内保留代表序列 |

`knowledge_class: product_invariant + version_specific_tool_fact`：hard gate先于综合排名；阈值只在该frozen profile内有效。

### 5.1 Stage 05 v1.6 advisory validation

Stage 05默认Protenix full-target复核的structure hard decisions是：binder pose RMSD `<=3.0 Å`、target Cα RMSD `<=3.0 Å`、severe clash `=0`、moderate clash `<=3`。

`pairwise target–binder iPTM >=0.50`、`minimum target–binder PAE <=15 Å`、`binder pTM >=0.70`是confidence reference signals；当前合同以OR形成`confidence_reference_pass`，不是promotion hard gates。一个strategy没有full-target structure通过者时，v1.6发布warning但不撤销已由pilot确定的Tier-A资格。Agent必须同时报告warning的科学风险，不能把“policy允许继续”写成“结构已验证”。

### 5.2 Stage 07默认final合同

当前Stage 07默认是`nanobody-final-v1.5` + Protenix。单seed/representative层的典型artifact decisions包括：pairwise iPTM `>=0.60`、minimum interface PAE `<=10 Å`、binder pose RMSD `<=3.0 Å`、target Cα RMSD `<=3.0 Å`、binder pTM `>=0.60`、full-target hotspot coverage `>=0.40`、severe clash `=0`、moderate clash `<=3`；consensus层再使用PAE `<=7 Å`、pose RMSD `<=2.5 Å`与至少2个individually passing seeds。仍须引用artifact实际rule，不能凭本段重算。

只有Stage 07 artifact显式绑定`nanobody-final-v1.6`、OpenFold3 runtime/config/model identity与相应multi-seed/sample合同，才解释OpenFold3 final semantics。不要将Stage 05 advisory、Stage 07 Protenix final与OpenFold3 final的同名metric decision表混用。

## 6. Score 与排名

### 6.1 Candidate screen score

当前screen将一部分fixed-normalized与group empirical percentile metrics按frozen权重组合。它用于同一profile/pool中的排序，不是物理能量或跨run绝对分数。

主要类别包括BSA/contact density、hotspot、CDR、polar contacts、confidence/RMSD等。empirical percentile依赖当前比较池：池改变，归一化也可改变。

### 6.2 Strategy score

当前strategy score使用：

- `final_gate_pass_rate`；
- `qualified_top_quartile_mean`；
- `all_candidates_median`。

Tier与promotion以frozen report为准。高`score_yaml`不能让非Tier-A或hard-gate失败strategy合法promotion。

### 6.3 不允许

- 跨run/profile直接比较score；
- 用score差异宣称affinity差异；
- 从top-1推断整组；
- 修改pool后仍把旧percentile当相同标尺；
- 用综合分补偿target drift/clash。

## 7. Missingness 与 fallback

### 7.1 三值逻辑

metric应区分`observed value`、`missing`与`not applicable`。missing不是0，也不是自动fail/pass，除非frozen rule明确规定。

### 7.2 分析顺序

1. 按metric与strategy统计missing count/rate；
2. 读取missing reason；
3. 判断是否有source-labeled fallback；
4. 比较missingness是否与scaffold/site/crop/operational status相关；
5. 只在可比较subset上做exploratory summary，并明确selection bias；
6. 若missingness可能颠覆group结论，标`not-comparable`。

### 7.3 BSA示例

EasyDesign structure BSA缺失时，pipeline可使用`delta_sasa_refolded`作为带source标记的fallback。报告必须保留：primary missing、fallback-used、fallback source/value；若正式report未暴露missing reason，则明确记为`not-exposed-in-pilot-filter-report`，不能把fallback改名成无来源BSA。

### 7.4 正例

某strategy 40% BSA缺失，而其他组5%。先检查structure parser/crop/asset差异；不把剩余60%的高BSA候选当无偏代表。

### 7.5 反例/误判

- `None → 0`后参与排名；
- 只报告有metric的candidate；
- fallback与primary直接混合计算而不标source；
- missing多的组直接判科学失败。

## 8. 组合解释

### 8.1 较强内部一致性

高iPTM、低interface PAE、target drift合格、hotspot coverage足够、无clash，可支持“在当前模型/profile内结构一致且命中条件位点”。仍不证明affinity、specificity或功能。

### 8.2 Target drift + high interface

优先解释为interface建立在变形target上；不得因BSA/contact/score高而晋级。比较全组drift、局部state与context。

### 8.3 High contact + low CDR dominance

提示framework-driven、mixed paratope、错误orientation或crop-edge吸附。必须看design mask与结构；不是自动fail，也不是自动好。

### 8.4 High dominance + low utilization

可能少数anchor主导，也可能设计空间未用或loop折叠限制。看per-CDR contacts、pose diversity与matched CDR experiment。

### 8.5 High BSA + clash

大界面不能补偿物理冲突；遵守hard gate。

### 8.6 Low BSA + high confidence

可能界面太小、窄anchor、BSA缺失/fallback或confidence calibration问题。保留alternative，不从单metric决定。

### 8.7 Coverage high但机制弱

hotspot命中只说明条件位点接触；若hotspot本身不是causal mechanism，不能宣称blocking/state effect。

### 8.8 全scaffold同一metric失败

候选嵌套在shared site/context/profile；优先检查共同原因，不把七组当七个完全独立反证。

## 9. 误判与停止条件

### 9.1 常见误判

- metric名相同就跨版本比较；
- threshold被当普适生物阈值；
- predictor confidence当实验truth；
- hard gate被aggregate score覆盖；
- high H-bond count当高affinity；
- high BSA当高specificity；
- missing当0；
- sequence duplicate当独立支持；
- global target RMSD合格就忽略局部state drift。

### 9.2 停止条件

- profile/source hash不匹配；
- metric definition/source/unit缺失且会影响解释；
- denominator无法重建；
- missingness强烈不平衡；
- hard-gate decision与本地重算冲突；
- candidate/strategy identity漂移；
- 分析需要当前artifact不存在的metric。

## 10. Metric report 模板

```yaml
metric_report:
  profile:
    profile_id: ""
    profile_sha256: ""
    metric_definition_version: ""
  denominators:
    planned: null
    generated: null
    metric_complete: null
    evaluable: null
    unique: null
  missingness:
    - metric_id: ""
      count: null
      rate: null
      reasons: []
      fallback_used: null
      group_bias: ""
  candidates:
    - candidate_id: ""
      hard_gates:
        - rule_id: ""
          metric_id: ""
          observed: null
          operator: ""
          threshold: null
          passed: null
      target_integrity: {}
      site_interface: {}
      cdr_framework: {}
      score:
        value: null
        scope: same-profile-same-pool-only
      supports: []
      does_not_support: []
  comparability_status: ""
```
