# Target 与 site：从功能目标到可审批位点

本章是 `prepare` phase 的核心。目标不是“找到一个表面 patch”，而是得到一个能被功能 assay 证伪、身份可追踪、结构上可接近、并能转成 pilot 假设的 site dossier。

## 目录

1. 输入与完成标准
2. 决策总流程
3. Design goal 与 assay 合同
4. Target identity、state 与 context
5. 五类机制分支
6. 文献与结构证据调查
7. Site candidate 生成与比较
8. Site designability 与风险
9. 正例、反例与停止条件
10. Target/site dossier 模板
11. 审批边界

## 1. 输入与完成标准

### 1.1 最小输入

- 用户要改变或测量的 biological function；
- target 名称或 sequence；
- species、isoform、construct、状态、亚细胞侧向与 assembly 中已知部分；
- assay/readout、样品环境、允许和禁止的 perturbation；
- 已知 ligand、partner、mutation、PTM、glycan 或结构 ID；
- 当前 project 的 immutable target artifact（若存在）。

输入不完整不是停止所有工作：可先形成问题树、检索计划和 provisional candidates。但不得给出可冻结 residue list。

### 1.2 完成标准

输出必须同时回答：

1. 设计要实现什么机制，什么 assay 结果算成功；
2. 应该结合哪个 biological state、哪一侧、哪个 assembly context；
3. primary、backup 和 avoid site 各是什么；
4. 每个 site 的 evidence、numbering mapping、可接近方向与主要风险；
5. 什么新结果会推翻排序；
6. 用户实际批准的究竟是哪一个 site revision。

## 2. 决策总流程

按以下顺序执行，不得由扫描工具直接跳到 residue list：

1. 恢复 current project identity 与 phase；
2. 把用户语言改写成 `desired_effect`、`forbidden_effect`、`assay`；
3. 锁定 target identity/state/context；
4. 将目标归入一个主机制与至多两个备选机制；
5. 主动检索直接结构、mutagenesis、competition、state 和 assay 证据；
6. 独立运行可用 site/geometry scan，产生 computational proposals；
7. 将 literature-derived 与 scan-derived candidates 分列；
8. 比较机制相关性、证据强度、几何可设计性、context 稳健性和风险；
9. 形成 primary/backup/avoid；
10. 展示 dossier，等待 `site approve`。

`knowledge_class: product_invariant`：未批准 site 之前，Agent 应完成调查、比较与 dossier 草案；不得代替研究者越过 site gate。

## 3. Design goal 与 assay 合同

### 3.1 决策问题

“做一个能结合 target 的 VHH”不是完整目标。必须判断结合是终点、测量手段，还是干预机制。

### 3.2 必需证据

- `desired_effect`：blocking、state stabilization、recognition、capture、chaperoning 等；
- `forbidden_effect`：不阻断 native partner、不改变 signaling、不识别错误 state 等；
- `assay_object`：purified construct、cell surface、intracellular target、tissue 或复合物；
- `readout`：competition、activity、signaling、localization、fluorescence、thermal shift、cryo-EM particle quality 等；
- `success_criterion` 与必要 negative controls；
- binder 最终 format、delivery route 和 epitope accessibility。

### 3.3 条件分支

- 功能干预：site 必须有可解释的因果路径连接到 readout；
- 纯识别/成像：优先 state-invariant、可接近、低扰动表面，而非功能热点；
- 构象传感：需要两个或更多状态中差异暴露的 epitope，并在 assay 中验证选择性；
- 结构伴侣：允许故意稳定某状态，但必须声明该结构不是未扰动天然 ensemble；
- capture/purification：可优先稳定外露 epitope，但需检查 tag、surface immobilization 与 oligomer context。

### 3.4 正例

目标是阻断 A–B 结合，competition assay 直接测 A–B，已有复合物结构和界面 mutagenesis。primary site 覆盖 A 上必需界面 hotspot，backup site 覆盖相邻可产生 steric occlusion 的 patch。

### 3.5 反例/误判

目标是荧光成像，却选择 catalytic pocket，仅因为扫描得分最高。即使结合成功，也可能改变活性或只识别非生理构象，违背 `forbidden_effect=low perturbation`。

### 3.6 反证或停止条件

- assay 无法区分 binding 与目标功能；
- 用户同时要求相互矛盾的 desired/forbidden effect；
- 目标 format 使候选 site 不可接近；
- 当前 target identity 不能唯一映射。

### 3.7 输出字段

`design_goal_id`, `desired_effect`, `forbidden_effect`, `mechanism`, `assay`, `readout`, `success_criterion`, `negative_controls`, `format_constraints`, `open_questions`。

## 4. Target identity、state 与 context

详细映射按 [evidence-and-numbering.md](evidence-and-numbering.md)。本阶段至少冻结：

- canonical name、gene/protein、species；
- sequence accession 与 isoform；
- construct 起止、mutation、tag、fusion；
- biological assembly、target chain 和 partner chains；
- functional state、ligand/cofactor/nucleotide、pH 或重要环境；
- membrane orientation、glycan/PTM、缺失 segment；
- residue mapping 的 source 和 checksum。

`knowledge_class: scientific_evidence`：同名蛋白不等于同一个设计对象。isoform、state、construct、assembly 或 chain 任一漂移，都可能把正确 residue 变成错误 site。

对预测结构必须记录 local confidence、跨域 PAE/相对取向不确定性。高局部置信不自动证明多域装配、loop state 或 oligomer 界面正确。

## 5. 五类机制分支

### 5.1 PPI blocking / competition

**决策问题**：VHH 是否应直接占据 partner footprint，还是相邻 steric blockade 已足够？

**必需证据**：complex structure、crosslink/competition、alanine scan 或 mutagenesis、partner stoichiometry、界面保守性、site 在目标 assay state 的暴露。

**条件分支**：

- 有高质量复合物与必需 hotspot：优先覆盖 causal footprint；
- 只有 partner model：保留 direct-overlap 与 adjacent-occlusion 两个假设；
- partner footprint 平坦且宽：不把全部界面都设为 hotspot，选择能控制 approach 的 anchor；
- partner 与 VHH 尺寸/方向不同：必须做整分子 steric review，不能只比较 residue overlap。

**正例**：目标是阻断受体–配体，primary site 命中已验证的受体界面核心，并在完整 assembly 上保留 VHH 接近通道。`claim:VHH-PPI-001`

**反例**：仅因为 scan 把某暴露 loop 排第一，就声称可阻断 partner；该 loop 与 footprint 空间相距较远。

**反证/停止**：site 在 biological assembly 中被 partner-independent subunit 遮挡；mutagenesis 仅影响折叠而非特异界面；numbering 无法可靠映射。

**输出**：`partner`, `footprint_source`, `direct_overlap`, `steric_path`, `mechanism_prediction`, `discriminating_assay`。

### 5.2 Conformational/state selection

**决策问题**：要识别、稳定还是排斥哪个 state？结合本身是否会推动 state？

**必需证据**：至少两个 state 的结构或构象 readout、state ligand/partner、差异表面、functional assay。

**条件分支**：

- state-specific cavity/patch：以该 state 的完整 context 建模；
- epitope 在状态间都存在但 geometry 改变：明确预期选择性来自 shape，而非 residue identity；
- 目标是传感而非扰动：选择远离 effector/active site 的差异表面，并设置功能无扰动对照；
- 目标是稳定：把 binder-induced shift 当预期机制，不把 bound structure 称为无扰动 state。

**正例**：GPCR active-state intrabody 以 agonist-bound intracellular state 为输入，预期既竞争 effector 又稳定 active-like conformation，assay 同时读 state preference 和 signaling。`claim:GPCR-STATE-001`

**反例**：用 inactive apo structure 设计 active-state binder，却未比较 TM/loop rearrangement。

**反证/停止**：可用结构不能代表 assay state；state marker 与 functional readout相互矛盾；目标表面在状态间没有可分辨差异。

**输出**：`desired_state`, `counter_state`, `state_defining_evidence`, `expected_shift`, `perturbation_risk`, `state_selectivity_assay`。

### 5.3 Stable recognition / imaging / capture

**决策问题**：怎样获得稳定识别，同时尽量不改 target 的功能、定位或 assembly？

**必需证据**：多 state 表面可及性、功能/partner/active-site 地图、cell/tissue context、标签与成像 format。

**条件分支**：

- 低扰动成像：优先远离 known functional surfaces、稳定折叠域上的 state-invariant patch；
- 构象成像：接受 state-specific patch，但必须单独测扰动；
- extracellular target：检查 glycocalyx、膜面距离与 multivalent format；
- intracellular intrabody：检查 expression/localization 和持续占位效应。

**正例**：选择跨多结构保持、远离 catalytic/partner interface 的凸面 patch；用 localization 与 activity 双 readout 验证“看见但不改变”。

**反例**：把“稳定区”理解为高 pLDDT 即可，不检查它是否是 native partner interface。

**反证/停止**：任何候选都与必要功能面重叠；成像 format 使 target crosslink/cluster；target 在 assay 中目标 epitope 不暴露。`claim:IMAGING-PERTURB-001`

**输出**：`recognition_mode`, `state_invariance`, `functional_distance`, `format_perturbation`, `orthogonal_control`。

### 5.4 Ligand/substrate/cofactor blocking

**决策问题**：VHH 要直接伸入 pocket，封住入口，还是从邻近位点变构调节？

**必需证据**：ligand-bound structure、catalytic residues、pocket depth/入口、substrate size/path、activity assay。

**条件分支**：

- 深窄凹槽：long CDR3 是待测试策略，不是默认答案；同时保留 rim-blocking arm；
- 浅槽/大底物：优先连续 rim 与 steric occlusion；
- 高度保守 active site：若选择性重要，考虑邻近非保守 loop 或 allosteric site；
- cofactor 口袋埋藏：不得把小分子可达性等同 VHH 可达性。

**正例**：enzyme complex 显示 CDR3 可进入 cleft 并靠近 catalytic site，因而建立 penetration 与 rim-block 两组 matched hypotheses。`claim:VHH-CLEFT-001`

**反例**：看到 docking pocket 就设置 30 个口袋底部 residue 为 binding residues，忽略整个 VHH 无法接近。

**反证/停止**：蛋白表面没有允许 VHH 接近的入口；crop 暴露了人工 pocket；activity loss 可由 target unfolding 解释。

**输出**：`pocket_class`, `entry_path`, `catalytic_overlap`, `cdr3_hypothesis`, `rim_hypothesis`, `activity_control`。

### 5.5 Structural chaperone / stabilization

**决策问题**：要稳定哪个构象或 assembly，稳定是否服务于 cryo-EM/X-ray 或功能研究？

**必需证据**：构象异质性、已知稳定 partner、sample condition、目标结构 state、particle/thermal readout。

**条件分支**：

- 稳定单体 state：寻找只在目标 state 形成的复合表面；
- 稳定多亚基：可选择跨亚基 epitope，但必须确认 stoichiometry；
- 增加 cryo-EM fiducial：兼顾刚性连接与远离关键运动轴；
- 捕获瞬态 state：assay 需证明 binder 改变 ensemble 的方向和程度。

**正例**：针对 active GPCR intracellular cavity 的 nanobody 模拟 G protein、稳定 active state 并支持结构解析。`claim:GPCR-CHAPERONE-001`

**反例**：只因 binder 提高 melting temperature 就声称保留天然活性态。

**反证/停止**：binder 诱导非目标 oligomer；stabilized state 与 assay functional state 不一致；结构改善来自 aggregation selection。

**输出**：`chaperone_goal`, `desired_state_or_assembly`, `rigidity_path`, `ensemble_shift_assay`, `interpretation_limit`。

## 6. 文献与结构证据调查

当 site 未批准时，文献调查是必做项，不是可选增强。详细协议见 [evidence-and-numbering.md](evidence-and-numbering.md)。至少覆盖：

- target identity/isoform/construct；
- biological mechanism 与 assay；
- experimental complex structures；
- mutagenesis、competition、crosslink 或 functional mapping；
- state、ligand、cofactor、partner、assembly；
- PTM/glycan/membrane/缺失 segment；
- target family 的失败反例。

文献搜索与扫描工具分工：

- 文献/数据库回答“什么 site 与目标机制有关”；
- 结构几何回答“这个 site 是否在目标 context 可接近、如何接近”；
- scan 回答“模型认为哪些区域值得检查”；
- 三者冲突时保留冲突，不用 scan 分数覆盖直接 experimental evidence。

## 7. Site candidate 生成与比较

### 7.1 两条独立候选流

`literature-derived`：从复合物 footprint、functional mutations、state marker、known ligand/partner、published epitope 得到。

`scan-derived`：从表面可达性、几何 patch、pocket/concavity、conservation、prediction tool 得到。

每个 candidate 都记录来源，禁止在汇总时丢失 provenance。若两条流重合，这是交叉支持；若冲突，形成需要判别的假设。

### 7.2 比较维度

按 target-specific 权重评价，不机械相加：

- `mechanism_relevance`：与 desired effect 的因果距离；
- `direct_evidence`：complex/mutagenesis/competition 等；
- `state_context_match`：是否来自目标 state/assembly；
- `accessibility`：整个 VHH 的接近通道，不只是 residue SASA；
- `geometry`：平面、凹槽、凸起、膜近端和可用 approach；
- `continuity`：3D 空间是否形成可聚焦 patch；
- `specificity`：与同源物的差异及 off-target 风险；
- `representation_robustness`：full-length/crop、不同结构和模型间是否保留；
- `perturbation_fit`：是否符合 forbidden effect；
- `numbering_confidence`：能否稳定映射为 `label_seq_id`。

### 7.3 排序输出

- `primary`：当前证据下最有希望实现目标且可验证；
- `backup`：机制、approach 或风险与 primary 有实质差异；
- `avoid`：看似高分但违反 identity/context/perturbation/geometry 的区域；
- `unresolved`：需要新证据才能在 primary/backup 间选择。

backup 不能只是 primary 平移两个 residue；它应覆盖替代机制或替代接近方向。

## 8. Site designability 与风险

### 8.1 整体可接近性

对完整 VHH body 做空间推理：膜、邻近 domain、glycan、partner、symmetry mate、oligomer 和 tag 是否阻挡 approach。单个 residue solvent exposed 不代表 VHH 可达。

### 8.2 结构稳定性与状态

检查 candidate 是否落在：

- 高度柔性或未解析 loop；
- state-dependent rearrangement；
- predicted domain 相对取向不确定区域；
- cleavage/PTM/glycan 邻近；
- assembly interface 或由 sample construct 人工暴露的表面。

### 8.3 机制相关几何

- blocking：覆盖 functional footprint 或产生可信 steric path；
- imaging：避开关键功能面和运动铰链；
- pocket：有 VHH approach 入口，CDR3 长度作为可测试因素；
- chaperone：连接或锁住构象相关结构元件；
- multimer：明确目标是单 protomer、界面还是跨亚基 epitope。

### 8.4 Crop 风险预告

本阶段不决定最终 crop，但必须标记：site 与 domain 边界距离、是否依赖完整 assembly、潜在人工截面、需要保留的 partner/glycan/ligand。详细设计见 [vhh-geometry-priors.md](vhh-geometry-priors.md)。

## 9. 正例、反例与停止条件

### 9.1 Scan 与文献冲突

**正例**：scan 的最高 patch 不在 PPI 界面；complex 与 alanine scan 明确支持另一 patch。将后者列 primary，将 scan patch 作为 nonblocking backup，并设计 competition 与 binding 双 assay。

**误判**：因 scan 有数值排名，直接删除 literature site。

**停止条件**：文献结构与 current sequence/isoform 无法映射，先解决 identity。

### 9.2 稳定区不等于无扰动区

**正例**：高置信稳定 domain 上选择远离 active/partner surface 的 patch，并比较 bound/unbound activity。

**误判**：把高 pLDDT 或低 B-factor 当作“不会干扰功能”的证据。

### 9.3 GPCR 不是“必须 long CDR3”

**正例**：先决定 extracellular/intracellular、active/inactive、ligand/transducer context，再根据 cavity depth 测试 CDR3 arm。

**误判**：仅凭 target 类型就把 CDR3 设到极长。

### 9.4 全局停止条件

- target identity、sequence 或 chain 无法唯一确定；
- residue mapping 有未解释的一对多/缺口；
- 目标 site 仅存在于非目标 state 或错误 assembly；
- 所有候选都与 forbidden effect 冲突；
- 核心机制证据只是 predictor 输出，且无可区分 assay；
- 用户尚未看到精确 site revision 与主要风险。

## 10. Target/site dossier 模板

```yaml
schema_version: "0.3-draft"
project_identity:
  project_id: null
  target_artifact: null
  target_sha256: null
design_goal:
  design_goal_id: goal-001
  desired_effect: ""
  forbidden_effect: ""
  primary_mechanism: ""
  alternative_mechanisms: []
assay_contract:
  assay: ""
  readout: ""
  success_criterion: ""
  negative_controls: []
target_identity:
  protein: ""
  species: ""
  accession: ""
  isoform: ""
  construct: ""
  assembly: ""
  target_chain: ""
  state: ""
  ligands_partners_ptms: []
  mapping_artifact: ""
evidence_summary:
  direct: []
  indirect: []
  computational_proposals: []
  contradictions: []
site_candidates:
  - site_id: site-primary
    role: primary
    source_class: [literature-derived, scan-derived]
    auth_seq_ids: []
    label_seq_ids: []
    mechanism_rationale: ""
    approach_direction: ""
    context_dependencies: []
    risks: []
    confidence: medium
    falsifier: ""
  - site_id: site-backup
    role: backup
    source_class: []
    auth_seq_ids: []
    label_seq_ids: []
    mechanism_rationale: ""
    differentiating_value: ""
avoid_sites: []
open_questions: []
approval_request:
  exact_revision: ""
  proposed_cli: "easydesign site approve ... --confirm"
  status: awaiting_user_approval
```

## 11. 审批边界

Agent 可以在批准前完成检索、结构比较、扫描、编号映射和 dossier 草拟；但只有研究者能批准 site。批准前必须显示：

- current target artifact/checksum；
- exact primary/backup residue lists，且同时给 author 与 label mapping；
- site 来源、机制、state/context；
- scan 与 literature 是否冲突；
- avoid 区域、主要不确定性和反证实验；
- 将被批准的文件路径与 revision。

任何新的 structure、isoform、state 或 mapping 使 residue identity 改变，都要创建新 revision，而不是静默修改已批准 site。
