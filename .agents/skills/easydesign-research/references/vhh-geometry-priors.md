# VHH geometry、CDR、scaffold 与 crop 先验

本章把 approved site 转成可测试的 VHH geometry hypotheses。先验用于生成实验组，不用于预先宣告 winner。具体 YAML 合同见 [strategy-yaml.md](strategy-yaml.md) 与 [boltzgen-contract.md](boltzgen-contract.md)。

## 目录

1. 核心原则
2. Site geometry 分类
3. Approach direction
4. CDR1/2/3 功能假设
5. Long-CDR3 决策
6. Scaffold 作为实验因素
7. Scaffold asset authoring snapshot
8. Crop 与结构 context
9. Framework contact 与 paratope attribution
10. Matched diagnostic designs
11. 输出模板

## 1. 核心原则

`knowledge_class: scientific_prior`：VHH paratope 可由 CDR3 主导，也可广泛使用 CDR1/CDR2/framework 邻域；不能把经典抗体的“只有 CDR 接触”当 VHH 普遍事实。`claim:VHH-PARATOPE-001`

`knowledge_class: product_invariant`：首轮每个显式 condition 都必须按 `PI-FIRST-PILOT-001` 覆盖 registry；baseline、diagnostic 或 integrated condition 均不得凭 scaffold 名称、来源药物或单个结构先验预筛或缩量。

每个 geometry 决定都要包含：

- 对 target 表面形状的可复核观察；
- 预期 approach direction；
- 哪个 CDR/组合承担 anchor 或 penetration；
- 什么结果会否定该假设；
- 与 baseline 可比较的 diagnostic arm。

## 2. Site geometry 分类

### 2.1 Flat / broad surface

**决策问题**：如何在缺少深 anchor 的表面建立足够 shape complementarity 与 specificity？

**必需证据**：patch continuity、electrostatic/hydrophobic pattern、neighboring protrusions、partner footprint、full-target clearance。

**条件分支**：

- 使用空间聚焦的多 residue hotspot 控制 approach；
- 保留 CDR1/2/3 共同参与的可能，不强制长 CDR3；
- scaffold orientation 与 framework edge contact 可能成为重要差异；
- 若表面高度保守，加入 specificity/off-target arm。

**正例**：PPI blocking 的平面界面选少量机制 anchor，baseline 全 scaffold；diagnostic 仅改变 hotspot 子集以测试 approach。

**反例**：将整个 30-residue footprint 全设 hotspot，导致 orientation 约束模糊且难归因。

**反证/停止**：所有生成 pose 只靠 framework 大面积吸附或 off-site 接触；应返回 site/geometry，而不是只加长 CDR3。

**输出**：`geometry=flat`, `anchor_pattern`, `expected_multicdr_role`, `orientation_risk`。

### 2.2 Groove / cleft

**决策问题**：是需要 loop 进入 groove，还是在 groove 两侧建立桥接？

**必需证据**：groove width/depth/curvature、入口、完整 VHH clearance、functional residues。

**条件分支**：

- 中等 groove：CDR3 anchor + CDR1/2 rim contacts；
- 宽 groove：多 CDR bridge 可能优于极长 CDR3；
- 弯曲 groove：hotspot 应控制沿 groove 的方向，不只是中心点；
- 深 groove：进入 [Long-CDR3](#5-long-cdr3-决策) 决策。

**正例**：把 groove floor 与 rim 分成 matched arms，分别测试 penetration 与 cap。

**反例**：仅测 pocket depth，不检查 VHH body 在入口处的碰撞。

**反证/停止**：有效 pose 无法保持 target integrity；CDR3 未进入却仍被解释为 cleft penetration。

**输出**：`geometry=groove`, `mouth`, `floor`, `rim`, `bridge_or_penetrate`。

### 2.3 Deep pocket / channel

**决策问题**：CDR 是否能到达机制核心，同时 VHH body 保持合理 approach？

**必需证据**：pocket mouth、最小横截面、depth、state-dependent gating、ligand/substrate path。

**条件分支**：

- 设 long-CDR3 diagnostic 与 rim-blocking control；
- 不把 pocket floor 全部设为 binding residues；
- target crop 不得人为扩大入口；
- 活性 assay必须含 target fold/integrity control。

**正例**：只改变 CDR3 insertion range，其余 scaffold/site/context/count保持，检验深度假设。

**反例**：同时使用 crop、极长 CDR3、不同 scaffold 和另一 site，得到成功后无法归因。

**反证/停止**：完整 VHH approach 不存在；成功 pose 依赖 artificial crop edge。

**输出**：`geometry=deep-pocket`, `entry_axis`, `required_reach`, `rim_control`。

### 2.4 Protrusion / convex epitope

**决策问题**：怎样环抱凸起而不滑到邻近表面？

**必需证据**：protrusion height、周围 saddle、loop flexibility、neighbor domain。

**条件分支**：

- 多 CDR 围绕 anchor；
- hotspot 可置于凸起顶点与一侧方向性 residue；
- 避免只选顶点导致 rotational ambiguity；
- 若凸起为 flexible loop，评估 state/ensemble。

**反例**：把孤立暴露 loop 当稳定 anchor，却无结构或 functional evidence。

**反证**：候选对 loop pose 极敏感，或只在一种低可信 model 中存在。

### 2.5 Membrane-proximal / sterically restricted

**决策问题**：从哪一侧接近才能避开膜、glycan、domain 与邻近 subunit？

**必需证据**：membrane normal、glycan envelope、full assembly、binder body尺寸、format/linker。

**条件分支**：

- 优先显式 approach vector 和 full-context validation；
- long CDR3 可能扩大 reach，也可能增加不稳定/非目标接触，必须测试；
- crop 不能删除造成真实遮挡的 domain；
- extracellular 与 intracellular representation 不可互换。

**反例**：单看 residue SASA 选择贴膜 patch。

**停止**：完整 VHH 无无碰撞方向，或只有删除生理 context 后可达。

## 3. Approach direction

`knowledge_class: product_invariant`：方向性角色必须来自 current 3D coordinates、明确的
partner/ligand footprint 或可复现的几何计算。residue number、序列顺序、列表位置和“看起来在
中间”都不能证明 `center`、`edge`、`directional anchor`、surface normal 或 approach axis。
没有坐标时，把每个几何角色写为 `unresolved`，先请求 structure/checksum/chain mapping；不得以
“provisional”名义把这些角色写入 runnable hotspot 或 acceptance criterion。

### 3.1 表达方式

为每个 site 定义：

- `surface_normal`：局部表面外法向；
- `preferred_axis`：由机制/通道/partner footprint 推导的 approach；
- `forbidden_volume`：膜、glycan、partner、neighbor domain、symmetry；
- `rotational_anchor`：防止围绕法向自由旋转的第二/第三 anchor；
- `full_body_clearance`：整个 scaffold 的空间检查。

### 3.2 机制映射

- direct competition：approach 应产生 footprint overlap 或可信 steric blockade；
- pocket：axis 指向入口，不等于指向 pocket center；
- imaging：避开 partner path 与功能运动；
- state stabilization：approach 应接触 state-specific elements；
- cross-subunit chaperone：方向要同时容纳两个 chain。

### 3.3 正例

选择一个位于 partner footprint 中心的 anchor和一个位于界面边缘的directional residue，使VHH占据 partner接近空间；另以邻近非重叠 patch作为机制 backup。

### 3.4 反例

hotspot 空间分散在蛋白两侧，单个 VHH 不可能同时满足；或者全部 residue 共线，导致 rotational ambiguity。

## 4. CDR1/2/3 功能假设

### 4.1 CDR3

常作为 reach、penetration、central anchor 或 specificity 主体，但并非越长越好。其构象自由度、表达、fold、aggregation 与错误接触风险随设计空间改变。

### 4.2 CDR1/2

可提供 rim contact、shape complementarity、orientation 与亲和力贡献。对 flat/broad surface 或需要稳定 orientation 的位点，不应仅设计 CDR3。

### 4.3 Framework 邻域

VHH 接口可能包含 framework 邻近位置。observed framework contact 不自动等于失败；要区分：

- 合理 mixed paratope；
- orientation 错误导致 framework-driven interface；
- crop edge/疏水表面非特异吸附；
- design mask 与 contact attribution 错误。

### 4.4 决策模块

**决策问题**：哪些 loop 应改变、哪些应固定，才能让本轮结果可归因？

**必需证据**：site geometry、approach、scaffold asset 原始 ranges、baseline 结果或明确 prior。

**条件分支**：首轮先保留 registry baseline；若需要诊断，优先单因素改变一条 CDR 的设计/插入空间；integrated alternative 可多因素改变，但不能承担因果归因。

**正例**：baseline 对所有 scaffold使用 asset defaults；另设 CDR3-range diagnostic，`held_constant` 包括 site/hotspot/crop/scaffold/count。

**反例**：把“CDR3 可设计 15–50”当所有 GPCR 的默认字段；当前 asset/backend 未核验如此宽范围，且科学上也未由 target geometry支持。

**反证/停止**：backend validation 不支持 override；override 使 scaffold 关键 framework 被错误纳入设计；组间改变多个未知因素。

## 5. Long-CDR3 决策

`knowledge_class: scientific_prior`：VHH CDR3 比 CDR1/2 长度更可变，结构/序列数据可支持把长度作为实验因素；这不支持对任意 target 设极端范围。`claim:VHH-CDR-LENGTH-001`

### 5.1 采用条件

至少满足一个：

- deep cleft/pocket 需要额外 reach；
- membrane/glycan 限制要求跨越障碍；
- state-specific cavity 由狭窄入口形成；
- 直接结构/同类 VHH 显示 CDR3 penetration；
- baseline 显示正确 approach但 reach不足。

### 5.2 风险

- loop entropy 与构象不确定性；
- fold/表达/聚集与 proteolysis；
- 错误表面或自身 framework 接触；
- backend 搜索空间膨胀；
- 与 scaffold asset 的 anchor/numbering不兼容；
- success 实际来自其他 CDR 或 rim contact。

### 5.3 Matched design

- 对照组保留 asset default；
- diagnostic 只改变 CDR3 `design_res_index`/`insertion_num_residues`；
- 相同 site/hotspot/crop/context/scaffold/count；
- 明确预期：hotspot reach/coverage上升且 framework dominance不恶化；
- 明确反证：target drift、clash、missingness或off-site上升。

### 5.4 不采用条件

- flat epitope 且没有 penetration/clearance需求；
- 目标是低扰动 stable recognition，长 loop只增加未知；
- 当前 backend/asset 未验证所需 range；
- 已有结果显示主要问题是 target representation 或 site错误；
- 无 matched control。

## 6. Scaffold 作为实验因素

### 6.1 原则

scaffold identity 同时影响 framework geometry、CDR anchor、loop defaults、approach、表达与 metric missingness。首轮覆盖不是“七个都一样”，而是避免凭先验过早丢失支持。

### 6.2 解释模式

- 全 scaffold 共同失败：优先怀疑 shared site/context/hotspot/backend，不把七次结果当七个独立 site 证据；
- 单 scaffold 成功：可能是 geometry compatibility，也可能是 sampling/metric artifact；需 matched confirmation；
- 单 scaffold 失败：检查 asset/validation/target-specific geometry，不立即永久淘汰；
- scaffold × site interaction：需要有同 site 多 scaffold和/或同 scaffold多 site 才能初步解释；
- framework-driven contact：同时检查 geometry、design mask、crop edge与 sequence developability。

### 6.3 反例

看到某 scaffold 来自已有药物就把它定义为“最稳定”并只跑它；provenance 不证明在 current site 的 geometry最优。

## 7. Scaffold asset authoring snapshot

`knowledge_class: version_specific_tool_fact`：下表是 Skill authoring 时从 repository 中 BoltzGen
`0.3.2` / `official-vhh7-v1` reviewed asset 提取的 `documentation_snapshot`。数字是 native asset 的
`design.res_index` 与 `design_insertions.num_residues`，不是通用 IMGT CDR 长度，也不是最终序列长度。

该表可帮助形成需要核验的假设，但不能独立证明 current project/run 使用同一字节资产。任何精确
range 进入 runnable strategy 前，必须从 current registry/manifest 解析相应 YAML，记录
`asset_path`、`asset_yaml_sha256`、registry、BoltzGen version/commit 与 asset diff。无法访问 current
asset 时只能写 `asset-default` 或 `REQUIRES_ASSET_BINDING`，不得把下表称为“当前已验证范围”。

| scaffold_id | chain | design CDR1 | design CDR2 | design CDR3 | insertion CDR1 | insertion CDR2 | insertion CDR3 |
|---|---|---|---|---|---|---|---|
| `7eow` | B | `26..34` | `52..59` | `98..118` | `1..5` | `1..5` | `1..14` |
| `7xl0` | A | `26..33` | `51..57` | `97..110` | `1..5` | `1..5` | `1..12` |
| `8coh` | A | `26..33` | `51..58` | `97..115` | `1..5` | `1..5` | `1..14` |
| `8z8v` | B | `26..33` | `51..58` | `98..108` | `1..5` | `1..5` | `1..12` |
| `gontivimab` | A | `26..32` | `52..57` | `100..116` | `1..5` | `1..5` | `1..12` |
| `isecarosmab` | A | `26..32` | `52..57` | `99..108` | `1..5` | `1..5` | `1..12` |
| `sonelokimab` | A | `26..30` | `50..55` | `97..111` | `1..5` | `1..5` | `1..12` |

### 7.1 三种数值不可混淆

- `design_res_index`：native scaffold 中允许设计的 residue range；
- `insertion_num_residues`：在 anchor 处允许的插入数量范围；
- final CDR length：生成结果的实际 loop 定义与长度，需要按产物/numbering重新计算。

正则合法只说明字符串可解析，不证明科学合理、asset 相容或 backend 可运行。每次 override 都要检查 asset diff 与 backend validation。

### 7.2 精确值来源绑定

```yaml
asset_binding:
  status: not_run
  scaffold_id: ""
  registry: official-vhh7-v1
  boltzgen_version: ""
  boltzgen_commit: ""
  asset_path: null
  asset_yaml_sha256: null
  source_manifest_sha256: null
  extracted_defaults: null
  proposed_diff: null
  backend_validation_receipt: null
```

只有 `status: verified` 且 receipt 与 current config identity 一致时，才能把 `extracted_defaults` 或
`proposed_diff` 作为当前事实。Skill snapshot 与 current artifact 不一致时以 artifact 为准并报告
`contract_drift`，不得静默选择。

## 8. Crop 与结构 context

### 8.1 决策问题

full target 是否造成不必要的计算负担，crop 是否仍保留 native site geometry、approach和必要 context？

### 8.2 必需证据

- domain boundaries 与结构稳定单元；
- site 到 crop edge 的空间/sequence 距离；
- 需要保留的 partner、ligand、glycan、membrane与assembly；
- full vs crop 结构对齐；
- 新截面和暴露疏水 core；
- full-target validation计划。

### 8.3 可考虑 crop

- target 很大且 site 位于独立稳定 domain；
- 无关键 allosteric/assembly context依赖；
- crop边界有实验 construct 或结构域证据；
- 可以明确标记新截面并在 full target 上复核；
- pilot 将包含 full-context confirmatory arm。

### 8.4 不应 crop

- site 跨域或靠近 domain interface；
- mechanism依赖远端 state coupling；
- 膜/glycan/neighbor domain决定可达性；
- crop会产生靠近 hotspot 的新截面；
- target 是 multimer/复合物且 assembly 是机制的一部分；
- 只是为了让模型更容易给出高分。

### 8.5 正例

使用有实验依据的独立 ectodomain，site 远离边界；明确禁止 crop-edge contact，并设置 full-length structural validation。

### 8.6 反例/误判

删除遮挡 site 的 native domain后得到高 hotspot coverage，随后解释为 full target 可结合。

### 8.7 反证/停止

- representative passes 在 full target 上 pose漂移或不可达；
- interface主要位于新截面；
- full/crop site geometry显著不同；
- 必要 state/assembly无法保留。

## 9. Framework contact 与 paratope attribution

### 9.1 必需数据

- BoltzGen official `design_mask`；
- designed binder residue IDs；
- CDR/framework contact counts；
- representative 3D interface；
- scaffold asset 与任何 override；
- crop-edge/off-site contacts。

### 9.2 条件分支

- 高 `cdr-dominance` + 适当 utilization：支持 designed loops主导，但不证明 affinity；
- 低 dominance + 高 total contact：可能 framework-driven错向，也可能真实 mixed paratope；检查结构；
- 高 dominance + 低 utilization：少数 loop residues形成 anchor或搜索不足；
- 单 scaffold framework-driven：优先 scaffold/approach interaction；
- 全 scaffold framework-driven：优先 shared site/context/hotspot或 attribution问题。

### 9.3 误判

- 用固定 sequence ranges猜 CDR，而不是 official design mask；
- 一见 framework contact 就删除 candidate；
- 接触计数高就忽略clash与target drift；
- 把 mixed interface自动当 nonspecific。

## 10. Matched diagnostic designs

| 问题 | 只改变 | 保持不变 | 关键观察 | 可反证结论 |
|---|---|---|---|---|
| hotspot 是否过宽 | hotspot subset | site/scaffold/CDR/crop/count | coverage、orientation、off-site | 若无改善，问题不只在 hotspot |
| CDR3 reach 是否不足 | CDR3 override | site/hotspot/scaffold/crop/count | pocket reach、coverage、clash | 若 reach 不升或 framework恶化，否定该范围 |
| crop 是否引入 artifact | full vs crop | site/hotspot/scaffold/CDR/count | edge contact、pose、target drift | 仅 crop 成功则不可直接推广 |
| scaffold geometry 是否匹配 | scaffold identity | site/hotspot/CDR policy/context/count | pass pattern、pose family | 单次差异可能是 sampling |
| site 是否错误 | approved primary vs backup | scaffold/CDR/context/count | mechanism coverage、target integrity | 两 site共同失败指向 shared context/backend |
| state/context 是否错误 | representation | site/scaffold/CDR/count | state-specific pose/target drift | 改 context 无效则保留其他解释 |

## 11. 输出模板

```yaml
geometry_assessment:
  site_id: ""
  geometry_class: ""
  surface_observations: []
  preferred_approach_axis: ""
  forbidden_volumes: []
  rotational_anchors: []
  full_body_clearance: ""
cdr_hypotheses:
  baseline: "asset defaults"
  cdr1_role: ""
  cdr2_role: ""
  cdr3_role: ""
  long_cdr3:
    decision: test|do-not-test|unresolved
    evidence_refs: []
    expected_result: ""
    falsifier: ""
scaffold_plan:
  registry: official-vhh7-v1
  baseline_policy_ref: PI-FIRST-PILOT-001
  target_specific_preranking: forbidden-in-first-baseline
crop_context:
  representation: full|crop|complex
  rationale: ""
  retained_context: []
  artificial_surfaces: []
  full_target_validation: ""
diagnostic_arms: []
unsupported_assumptions: []
```
