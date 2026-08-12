# VHH pilot failure atlas

本章用于把典型现象转成竞争解释和最小判别实验。它不是自动诊断器：每个模式都必须绑定current artifact、denominator、profile与representative structures。

## 目录

1. 使用合同
2. 全部/多数 scaffold共同失败
3. 单一 scaffold失败或成功
4. Target drift + 高interface score
5. 正确target + 低hotspot coverage
6. 高coverage + 弱interface
7. Framework-driven interface
8. Long-CDR3 tradeoff
9. Crop artificial surface
10. Full vs fragment冲突
11. Fixed/refold/relax不一致
12. Missing metric与版本漂移
13. Diversity collapse
14. 阈值敏感与top-1幻觉
15. Operational/scientific/empty result
16. Failure card模板

## 1. 使用合同

每个模式按：

`观察 → primary hypothesis → credible alternatives → 必查证据 → 最小判别实验 → 不支持的结论 → safe action`

至少引用一个candidate/group artifact和一个comparator。若没有comparator，只能给hypothesis，不能归因。

## 2. 全部/多数 scaffold共同失败

### 观察

七个registry scaffold在同一baseline的dominant hard gate、pose或site模式相似失败。

### Primary hypothesis

shared factor更可疑：site/hotspot、target state/context、crop、adapter/backend/profile或experiment representation。

### Credible alternatives

- registry对current geometry确实共同不适配；
- candidates per group不足导致sampling failure；
- shared CDR defaults限制reach；
- metric/parser对某类结构系统偏差；
- operational failure被误作scientific failure。

### 必查证据

denominator/missingness、target drift分布、hotspot coverage、pose families、per-scaffold operational status、full context、CDR/framework attribution。

### 最小判别实验

优先改变一个shared high-level factor：backup site、hotspot topology或target context；保持全registry/CDR/count/profile不变。若deep pocket有强geometry证据，可另做matched CDR3 arm。

### 不支持的结论

“七个scaffold都永远不适合这个target”或“只需第八个scaffold”。

### Safe action

返回prepare/strategize检查共同假设，不直接scale或逐个微调scaffold。

## 3. 单一 scaffold失败或成功

### 3.1 单一失败

**观察**：一个scaffold明显更低pass/更高missing/clash/framework contact。

**Primary**：scaffold geometry或asset/override与site approach不匹配。

**Alternatives**：任务失败、sampling波动、该组candidate/metric缺失、asset hash或override错误。

**必查**：asset diff/backend logs、denominator、pose、CDR ranges、target integrity。

**判别实验**：同一immutable条件独立确认；若override存在，加入asset-default control。

**不支持**：一次pilot后从未来所有site永久删除该scaffold。

### 3.2 单一成功

**观察**：一个scaffold有少量高质量候选，其他组弱。

**Primary**：scaffold×site geometry compatibility。

**Alternatives**：top-1 outlier、duplicate family、metric fallback、sampling、framework-driven假阳性。

**必查**：分布而非top-1、unique sequences、pose diversity、CDR dominance、full target。

**判别实验**：same scaffold confirmatory rerun + 一个nearby comparator scaffold，保持其他因素。

**不支持**：直接把scaffold provenance解释为普适稳定优势。

## 4. Target drift + 高interface score

### 观察

candidate有高iPTM/BSA/contact/aggregate score，但`target-ca-rmsd`超过frozen gate或局部state改变。

### Primary hypothesis

interface建立在错误/变形target representation上。

### Alternatives

- global alignment受远端flexible domain影响，site局部仍正确；
- reference与candidate state本就不同；
- mapping/alignment实现问题；
- binder真实稳定另一个生物state。

### 必查证据

FilterDecision、global与site-local alignment、state markers、full/crop、ligand/partner、per-group drift。

### 最小判别实验

full-context或state-constrained confirmatory prediction，预先定义local state readout；不要仅放宽RMSD threshold。

### 不支持的结论

“高score证明binder好”或“target被binder有益稳定”。

### Safe action

不promotion；先解决representation/state解释。

## 5. 正确target + 低hotspot coverage

### 观察

target integrity合格，binder fold尚可，但coverage普遍低或off-site contacts多。

### Primary hypothesis

hotspot topology/approach不适合，或site对VHH不可设计。

### Alternatives

- binding residue过多/过分散，比例稀释；
- residue mapping错误；
- CDR reach不足；
- context遮挡；
- metric contact cutoff不适合某边界pose；
- sampling不足。

### 必查证据

具体contacted residues、hotspot total、3D distances、full-body approach、framework/off-site contacts、mapping。

### 最小判别实验

在同site比较更聚焦hotspot topology；或比较approved backup site。只有cleft/障碍证据时再加入CDR3 reach arm。

### 不支持的结论

直接判target不可结合，或直接扩大hotspot到整个site。

### Safe action

返回strategize；若full context显示不可达，返回site选择。

## 6. 高coverage + 弱interface

### 观察

hotspot coverage达标，但iPTM/PAE/BSA/contact或clash表现弱。

### Primary hypothesis

conditioning让binder触达site，但没有形成稳定、物理合理的完整interface。

### Alternatives

- hotspot只产生窄anchor，BSA偏小但可能真实；
- BSA missing/fallback；
- scaffold/loop geometry不匹配；
- target site本身过平/缺少complementarity；
- confidence calibration不适用。

### 必查证据

hard gates、BSA source、pose、per-CDR contacts、clashes、sequence/pose diversity。

### 最小判别实验

保持site/hotspot，测试scaffold/CDR geometry的matched改变；或在相同site增加方向性anchor而非扩大面积。

### 不支持的结论

“site正确所以只要生成更多一定成功”。

### Safe action

先区分geometry与sampling，再决定是否扩大搜索。

## 7. Framework-driven interface

### 观察

total contacts/BSA高，但`cdr-dominance`低，interface由framework或非设计残基主导。

### Primary hypothesis

orientation错误、site geometry与CDR不匹配或非预期表面吸附。

### Alternatives

- 真实mixed VHH paratope；
- design mask/CDR attribution错误；
- framework邻域合理参与；
- crop edge吸附；
- 单个scaffold特有geometry。

### 必查证据

official design mask、per-residue contact、site/off-site、crop edge、clash、跨scaffold模式、代表结构。

### 最小判别实验

同site改变hotspot approach；或同scaffold恢复/改变CDR策略。若mixed interface仍命中机制site且full-target重现，可保留但需developability/实验验证。

### 不支持的结论

低dominance自动淘汰，或高BSA自动接受。

### Safe action

结构复核后分类：wrong-orientation、mixed-paratope、attribution-gap、crop-artifact。

## 8. Long-CDR3 tradeoff

### 观察

long-CDR3组coverage/reach提高，但clash、target drift、binder fold、framework contact或diversity变差；或完全无改善。

### Primary hypothesis

额外reach有局部收益，但所测试range增加构象/搜索/物理代价；或reach并非主要限制。

### Alternatives

- override在不同scaffold不等价；
- design_res_index与insertion语义误用；
- pocket/rim hotspot错误；
- sampling不足；
- 真实成功来自CDR1/2或framework。

### 必查证据

每asset diff、backend check、final loop/design mask、per-CDR contacts、pose、matched baseline。

### 最小判别实验

缩窄range或只在有penetration evidence的scaffold上做confirmatory，同时保留default controls；或转向rim-blocking site。

### 不支持的结论

“GPCR/酶必须更长”或“long CDR3永远不好”。

### Safe action

只对被测试range和context下结论。

## 9. Crop artificial surface

### 观察

crop组score/coverage高，interface接近新N/C端、暴露core或本应由neighbor domain遮挡的表面。

### Primary hypothesis

candidate利用了artificial crop surface。

### Alternatives

- crop boundary确实是天然加工/独立domain；
- contacts虽接近边界但主要位于native surface；
- full target仍允许相同approach。

### 必查证据

full/crop superposition、edge residue contacts、domain boundary evidence、neighbor context、full-target pose。

### 最小判别实验

full target confirmatory prediction/assay；或扩大crop恢复遮挡并保持site/hotspot/CDR/scaffold。

### 不支持的结论

crop winner可直接推广full-length target。

### Safe action

在full context通过前不promotion。

## 10. Full vs fragment冲突

### 观察

fragment/crop通过，full target失败或pose显著漂移；反之亦然。

### Primary hypothesis

domain/assembly/membrane/glycan context改变site可达性或target state。

### Alternatives

- full prediction计算难度/metric calibration不同；
- alignment/chain mapping问题；
- fragment构象不稳定；
- sampling差异。

### 必查证据

same candidate sequence、same site mapping、pose RMSD、target local state、missingness、full-context blockers。

### 最小判别实验

matched representation test，保持sequence与profile；实验上比较fragment与full/cell-surface binding。

### 不支持的结论

任意一个representation被自动指定为truth。

### Safe action

以实际assay material决定外推边界。

## 11. Fixed/refold/relax不一致

### 观察

initial design pose、filter/refold或后续full-target pose不一致。

### Primary hypothesis

界面/loop缺乏几何鲁棒性，或不同阶段的模型定义/约束改变。

### Alternatives

- metric/chain alignment错误；
- target flexible region主导RMSD；
- refold找到更合理替代pose；
- seed/model stochasticity。

### 必查证据

`filter-rmsd`, `filter-rmsd-design`, `binder-pose-rmsd`, target-local alignment, exact model/profile/seed status。

### 最小判别实验

独立full-target/confirmatory prediction与pose cluster分析；不要把一次relax当实验稳定性。

### 不支持的结论

低RMSD证明affinity，或高RMSD必然表示sequence无效。

### Safe action

鲁棒pose优先，但必须满足site/mechanism与hard gates。

## 12. Missing metric与版本漂移

### 观察

某组metric大量missing，fallback比例异常，或profile/backend/source hash不同。

### Primary hypothesis

data collection/parser/profile identity问题使组不可比较。

### Alternatives

- 特定结构真实无法计算某metric；
- crop/chain/atom命名导致系统性缺失；
- backend升级改变definition；
- 仅高质量candidate产生完整metric的selection bias。

### 必查证据

missing reasons、source/unit/definition、stderr、profile hash、按组missing rate。

### 最小判别实验

修复后对同一immutable candidate set重算；若需代码修改，另开development任务并保留原report。

### 不支持的结论

missing=0、missing=fail、或只比较complete subset而不声明偏差。

### Safe action

标`not-comparable`，停止promotion。

## 13. Diversity collapse

### 观察

大量candidate sequence重复、pose高度单一，或top candidates来自同一sequence family。

### Primary hypothesis

search空间/conditioning/scaffold产生mode collapse，有效独立探索小于planned denominator。

### Alternatives

- 强真实energy funnel；
- dedup/sequence parsing错误；
- random seed不可控/重复；
- CDR design mask过窄；
- winner确实高度convergent。

### 必查证据

unique counts、duplicate mapping、sequence clusters、pose clusters、design mask、seed status。

### 最小判别实验

保持科学假设，改变经支持的search diversity因素或独立重复；不要删除duplicates后假装planned exploration完整。

### 不支持的结论

重复次数等于独立支持强度。

### Safe action

promotion时按unique/pose diversity约束，不只看top score。

## 14. 阈值敏感与top-1幻觉

### 观察

结论由一个靠近threshold的candidate或单个极高score决定；轻微阈值变化改变strategy排名。

### Primary hypothesis

结果脆弱、sampling/normalization主导。

### Alternatives

- 稀有但真实winner；
- 其他组因missing/duplicate压低分布；
- hard gate本身有明确产品安全意义，不应做连续敏感性替代。

### 必查证据

完整分布、pass counts、distance-to-threshold、unique sequences、score components、预先声明的gate。

### 最小判别实验

对candidate/strategy做confirmatory run和orthogonal structural/experimental test；不静默放宽frozen threshold。

### 不支持的结论

top-1代表strategy整体，或post hoc改threshold后仍称原profile结果。

### Safe action

报告sensitivity但遵守frozen gate；若更改profile，创建新版本/任务。

## 15. Operational/scientific/empty result

### 15.1 Operational failure

定义：任务未合法完成、artifact不全、backend/IO/GPU/parse失败。它不是target/scaffold的科学负结果。恢复时使用原immutable plan与新attempt/provenance。

### 15.2 Scientific stop

定义：数据完整可解释，但没有candidate/strategy满足frozen scientific/product gates，或证据明确否定当前site/context假设。保留run，形成下一轮或返回上游。

### 15.3 Empty result

定义：合法运行得到零candidate/零pass/零promotion；必须结合denominator与hard rules解释。empty可能是有价值的scientific negative，不为得到winner删除或覆盖。

### 15.4 分类正例

- 任务OOM，planned `N`中只有一部分生成→operational；
- planned `N`全部完整，但全部target drift fail→scientific stop；
- 全部完整，hard pass为0，report status停止→empty scientific result；
- metric parser坏导致无法评价→operational/data invalid。

## 16. Failure card模板

```yaml
failure_atlas_match:
  pattern_id: ""
  scope: ""
  observations:
    denominators: {}
    hard_rules: []
    metrics: []
    structures: []
  primary_hypothesis: ""
  credible_alternatives: []
  evidence_for: []
  evidence_against: []
  minimum_discriminating_experiment:
    comparator: ""
    changed_factors: []
    held_constant: []
    prediction: ""
    falsifier: ""
  conclusions_not_supported: []
  safe_action: ""
  approval_required: ""
```
