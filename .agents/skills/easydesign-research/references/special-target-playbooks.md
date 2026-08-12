# 特殊 target playbooks

只有 target 命中本章条件时才加载。本章不是按蛋白类别套参数，而是提醒哪些 context 会改变 site、representation、CDR/crop 假设与 assay。每个 playbook 都必须回到当前 design goal。

## 目录

1. 使用方法
2. GPCR 与构象态受体
3. 一般膜蛋白与 glycosylated target
4. 酶、深凹槽与通道
5. IDR、柔性 loop 与条件折叠
6. Beta-rich、amyloid 与重复表面
7. Multimer、复合物与跨亚基 epitope
8. 成像、识别与低扰动设计
9. Structural chaperone 与瞬态状态
10. 特殊 target 输出模板

## 1. 使用方法

1. 先读 [target-and-site.md](target-and-site.md) 确定机制；
2. 选择适用 playbook，可同时选择多个；
3. 把 playbook 的额外 evidence/context requirement 写入 dossier；
4. 不把 playbook 中的 prior 直接变成 residue 或 CDR 参数；
5. 在 strategy phase 再结合 [vhh-geometry-priors.md](vhh-geometry-priors.md) 形成 matched experiment。

`knowledge_class: conditional_heuristic`：target class 只改变必须检查的问题，不自动决定 site、hotspot、long CDR3 或 crop。

## 2. GPCR 与构象态受体

### 2.1 决策问题

- binder 位于 extracellular 还是 intracellular side？
- 要识别/稳定 active、inactive、intermediate 或 ligand-biased state？
- 目标是阻断 ligand、G protein、arrestin、GRK，还是作为 state sensor/chaperone？
- assay context 是否允许 intrabody？

### 2.2 必需证据

- 同 receptor 的 active/inactive/state ensemble；
- agonist/antagonist/allosteric ligand；
- G protein/arrestin/GRK 或 mimic 的复合物；
- TM helices、ECL/ICL、N/C termini、膜法向；
- construct mutation、fusion、truncation、thermostabilization；
- extracellular glycan、cholesterol/lipid 或 nanodisc context；
- state-selectivity 和 signaling assay。

### 2.3 条件分支

- intracellular effector cavity：VHH 可能直接竞争 effector，也可能稳定特定 state；两种机制必须分开验证。`claim:GPCR-STATE-001`
- extracellular ligand blocking：检查 ligand footprint、ECL flexibility、glycan 与膜上 approach；
- allosteric modulation：site 与 output 的因果路径必须有 state/functional readout支持；
- state sensor：优先差异表面，同时设置“binder 是否改变 state”的独立 assay；
- structural chaperone：用目标 ligand/transducer context；bound structure 解释为 stabilized state。`claim:GPCR-CHAPERONE-001`

### 2.4 正例

目标是 active-state intrabody：比较 agonist-bound 与 antagonist-bound结构，选择 active state 新形成的 intracellular cavity；同时测 state-selective binding 与 cAMP/effector coupling，承认 binder 可能同时选择并稳定该状态。

### 2.5 反例/误判

- 仅凭“GPCR”就强制 15–50 aa CDR3；
- 用 extracellular design 结构讨论 intracellular delivery；
- 删除膜后认为所有 TM 周围表面可达；
- 把 thermostabilized mutant 的一个构象当天然 ensemble；
- 用高 interface score 宣称 agonist/antagonist specificity。

### 2.6 反证或停止条件

- desired state 没有定义或 assay 不区分 state；
- design structure 与 assay ligand/transducer context 不一致；
- candidate site 被膜、glycan 或必要 partner 阻挡；
- target construct 的 stabilizing mutation 正位于 candidate；
- extracellular/intracellular delivery 不可实现。

### 2.7 输出字段

`receptor_state`, `counter_state`, `side`, `ligand_context`, `transducer_context`, `membrane_model`, `state_defining_features`, `competition_risk`, `state_shift_assay`。

## 3. 一般膜蛋白与 glycosylated target

### 3.1 决策问题

完整膜、glycocalyx、domain arrangement 和运输状态下，VHH 是否真的能以所需方向接近 site？

### 3.2 必需证据

- topology 与 membrane normal；
- extracellular/cytosolic/periplasmic side；
- full-length assembly、domain/linker arrangement；
- glycosylation sites、占有率/异质性与可用 glycoform；
- lipid/detergent/nanodisc 条件；
- target 在 cell surface 的成熟/加工状态；
- binder format、linker、label 或 multivalency。

### 3.3 条件分支

- 膜近端 patch：即使 SASA 高，也要放置完整 VHH 检查 body/membrane clash；
- glycan 邻近：把“无 glycan model”和“有合理 glycan envelope”作为两种 context；
- glycan-dependent recognition：需指定 glycoform，并避免把 protein-only model 当充分条件。`claim:GLYCAN-VHH-001`
- transporter/channel：state 与 alternating access 可能改变外露面；设计与 assay state一致。`claim:MEMBRANE-STATE-001`
- soluble ectodomain：只在证明其构象与 cell-surface target 可转移时作为 design representation。

### 3.4 正例

低扰动 cell-surface imaging：以 full ectodomain+membrane proxy+glycan envelope 检查 approach，primary site 位于膜远端稳定域并远离 native ligand footprint；在 cell-based binding 与 function assay 中共同验证。

### 3.5 反例/误判

- 去掉跨膜与 glycans 后，选择被膜面遮挡的“高暴露”底面；
- 将未建模 glycan 当不存在；
- 在 purified ectodomain binding 成功后直接声称 cell-surface 可达；
- 用 crop 新截面作为 epitope。

### 3.6 反证或停止条件

- topology 不明；
- glycan/膜 envelope 完全阻断所有合理 approach；
- assay target 的 maturation/cleavage 与结构 construct 不同；
- design site 只存在于 detergent-induced 或 truncated construct。

### 3.7 输出字段

`membrane_side`, `membrane_normal_source`, `glycan_context`, `maturation_state`, `full_length_check`, `approach_clearance`, `cell_surface_validation`。

## 4. 酶、深凹槽与通道

### 4.1 决策问题

抑制应由 CDR penetration、入口封堵、substrate path 遮挡，还是 allosteric state shift 实现？

### 4.2 必需证据

- apo 与 substrate/ligand/cofactor-bound structures；
- catalytic residue 与 essential mutation；
- pocket depth、mouth width、path 与动态 gate；
- substrate 尺寸与进入方向；
- homolog selectivity；
- kinetic/activity assay，可区分竞争/非竞争/折叠损伤。

### 4.3 条件分支

- 深而窄：CDR3 penetration 是一个 experiment arm；rim-blocking 是必要 alternative。VHH 的长 CDR3 确有识别 cleft 的实例，但不保证 current target 成功。`claim:VHH-CLEFT-001`
- 浅而宽：多 CDR/完整 paratope 可能更合适，不必追求极长 CDR3；
- 通道具有 gate：用正确 state/context，避免把 closed state 的不可达结论外推到 open state；
- active site 高保守：若 selectivity 是首要目标，评估 adjacent nonconserved surface 或 allosteric patch；
- catalytic pocket 埋藏且 VHH body 无法接近：停止 direct-pocket 方案。

### 4.4 正例

三组可归因 pilot：标准 CDR baseline；仅延长 CDR3 的 penetration arm；保持 CDR、改为 rim hotspot 的 blocking arm。所有组保持 scaffold/context/count 可比较。

### 4.5 反例/误判

- 把小分子 docking cavity 当 VHH 可达 cavity；
- 直接把所有 catalytic residues 设为 hotspot；
- 同时改 hotspot、crop、CDR3 与 scaffold 后将成功归因于 long CDR3；
- activity 降低但没有 target integrity control。

### 4.6 反证或停止条件

- pocket mouth 对完整 VHH 不可达；
- catalytic residue 在 crop 中变成新截面；
- CDR3 arm 成功结构显示其实结合 rim，不能继续宣称 penetration；
- 活性变化与 unfolding/aggregation 同步。

### 4.7 输出字段

`pocket_geometry`, `substrate_path`, `penetration_arm`, `rim_arm`, `allosteric_arm`, `kinetic_prediction`, `target_integrity_control`。

## 5. IDR、柔性 loop 与条件折叠

### 5.1 决策问题

目标是识别 sequence motif、特定 bound conformation、ensemble，还是诱导/稳定新构象？

### 5.2 必需证据

- disorder prediction 与实验 disorder evidence；
- partner/PTM-dependent folding；
- motif accessibility、proteolysis、NMR/HDX/crosslink；
- construct 与 flanking context；
- assay 是否容许 binder-induced folding；
- monomer/condensate/aggregate state。

### 5.3 条件分支

- 仅 sequence motif：structure-conditioned fixed epitope 可能错误；优先 peptide/ensemble compatible strategy，并明确当前 backend 能力缺口；
- coupled folding/binding：使用 partner-bound state作为一种 representation，同时保留 unbound ensemble 风险；
- PTM-specific：必须包含正确 modification 或使用能验证 modification specificity 的 assay；
- flexible loop 连接稳定 core：可以把 core 作为 anchor、loop 作为差异性 contact，但不能假定单一 loop pose。

### 5.4 正例

目标是识别 partner-bound helix：以复合物提供 state hypothesis，另用 unbound/alternative structure 检查 specificity；输出明确说明设计可能稳定该 helix。

### 5.5 反例/误判

- 对低置信 IDR 的单一预测构象做精确 residue geometry；
- crop 掉所有 flanking region 后声称保持 native motif accessibility；
- 把 binder-induced ordering 当作 target 原本稳定构象；
- 忽略 condensate/oligomer 中可达性。

### 5.6 反证或停止条件

- 当前 backend 只能固定单结构且研究问题依赖 ensemble；
- target motif 在 assay 中被 partner/PTM 遮挡；
- sequence/construct 缺少必要 flanking context；
- 不能区分 binding 与 binder-induced conformational artifact。

### 5.7 输出字段

`disorder_evidence`, `ensemble_states`, `conditional_folding_partner`, `ptm_state`, `representation_limit`, `induced_structure_risk`, `orthogonal_assay`。

## 6. Beta-rich、amyloid 与重复表面

### 6.1 决策问题

要识别 monomer、oligomer、fibril side、fibril end，还是阻止延伸/聚集？

### 6.2 必需证据

- polymorph、stoichiometry、protofilament 与 sample condition；
- monomer/oligomer/fibril state；
- repeat spacing、groove/ridge/end geometry；
- epitope 在重复 assembly 的 multiplicity；
- avidity、crosslink 与 aggregation risk；
- functional/toxicity assay 与 species specificity。

### 6.3 条件分支

- fibril end capping：必须选择具体 end/polymorph，且验证对 elongation 的影响；`claim:AMYLOID-END-001`
- fibril side imaging：选择重复 surface 但评估 multivalent clustering 和 polymorph cross-reactivity；
- oligomer-specific：单一 fibril或monomer结构不能代表目标；
- beta-edge：暴露边缘可能有 nonspecific beta-association risk，需 sequence/developability 与 negative assemblies 对照。

### 6.4 正例

目标是 fibril-end inhibition：把 groove-end 与 ridge-end 作为两个不同 site hypotheses，在指定 polymorph 上设计，并用 elongation kinetics 与 side-binding control 区分。

### 6.5 反例/误判

- 将任一 beta-rich target 都视为同一平坦 epitope；
- 忽略 fibril polarity 与两端几何差异；
- 在一种 polymorph 高分后声称跨病人样品识别；
- 把强 apparent binding 与 avidity/aggregation 混为 affinity。

### 6.6 反证或停止条件

- assembly/polymorph 未定义；
- design representation 不含重复 context；
- assay 无法区分 side binding、end capping 与 nonspecific aggregation；
- candidate 只在制样 artifact 中出现。

### 6.7 输出字段

`assembly_species`, `polymorph`, `epitope_multiplicity`, `end_or_side`, `avidity_risk`, `aggregation_control`, `cross_polymorph_test`。

## 7. Multimer、复合物与跨亚基 epitope

### 7.1 决策问题

site 位于单 protomer、native interface、跨亚基 composite epitope，还是某 partner presence 才形成？

### 7.2 必需证据

- biological assembly 和 stoichiometry；
- asymmetric unit 与 biological assembly 的差别；
- chain identity、symmetry 与 heterogeneity；
- assembly dynamics 与 concentration dependence；
- target format 是否保留 assembly；
- 结合后是否会解聚、交联或锁定异常 stoichiometry。

### 7.3 条件分支

- 跨亚基 epitope：可提高 assembly specificity，但可能锁住一个 state；
- native interface blocking：VHH 必须能在已装配或装配路径中接近；
- 重复同源亚基：明确 chain mapping，不把 symmetry copy 当独立序列；
- heteromer：检查 off-target homolog 与 partner dependence；
- soluble monomer assay：不能验证 assembly-specific epitope。

### 7.4 正例

结构伴侣目标是稳定 trimer：选择只在目标 trimer state形成的 composite site，并用 SEC/native MS/EM 验证 stoichiometry和结构改善。

### 7.5 反例/误判

- 从单 chain crop 设计跨亚基位点；
- 将 crystal packing interface 当 native oligomer interface；
- 把 binder-induced oligomerization 当稳定 native assembly；
- 忽略 bivalent format 的 crosslink。

### 7.6 反证或停止条件

- biological assembly 无法确定；
- candidate 仅在 crystal mate 出现；
- assay material 是 monomer 而设计目标是 multimer；
- binder format 会产生无法解释的 crosslink。

### 7.7 输出字段

`assembly_id`, `stoichiometry`, `site_chain_members`, `interface_type`, `assembly_dependence`, `crosslink_risk`, `stoichiometry_assay`。

## 8. 成像、识别与低扰动设计

### 8.1 决策问题

能否在目标环境中报告位置/丰度/state，同时不显著改变 target 的活性、运动、partner、降解或聚集？

### 8.2 必需证据

- target functional interfaces 与 dynamics；
- epitope 在目标环境中的可达性；
- binder affinity/residence 对 function 的潜在影响；
- fluorescent fusion、label、linker、valency；
- expression level、localization、delivery；
- unbound/bound function 与 morphology controls。

### 8.3 条件分支

- abundance/localization：优先稳定、非功能、state-invariant surface；
- state imaging：选择 state-specific surface，但低扰动必须实测；
- intracellular imaging：持续 intrabody 占位可能干扰 target，必要时考虑可控/低表达 format；`claim:IMAGING-PERTURB-001`
- extracellular imaging：检查 receptor clustering、internalization 与 Fc/valency effect；
- super-resolution：label geometry 与 linkage error 也属于 design constraint。

### 8.4 正例

候选 site 在多 state 中保留、远离 known partner/active site；pilot 后除了 structure metric，还要求 target activity、localization、turnover 和 dose-dependent perturbation controls。

### 8.5 反例/误判

- 只要荧光变亮就认为是低扰动 probe；
- 高 affinity 自动等于更好 imaging reagent；
- 忽略 binder-induced internalization/cluster；
- 将 GFP 当作要设计的 binder：GFP 常是 reporter/fusion，site 决策仍针对被观察 target。

### 8.6 反证或停止条件

- 所有高可达 site 都参与关键功能；
- reporter format 改变 localization/assembly；
- binding signal 与 overexpression artifact 无法区分；
- 缺少 unbound/irrelevant-binder/function controls。

### 8.7 输出字段

`imaging_question`, `reporter_format`, `epitope_invariance`, `functional_exclusion_map`, `perturbation_controls`, `dose_window`, `localization_validation`。

## 9. Structural chaperone 与瞬态状态

### 9.1 决策问题

VHH 应稳定哪个 state、增加粒子质量/晶格接触，还是提供 fiducial？

### 9.2 必需证据

- desired state 的定义和 population；
- sample heterogeneity/flexibility；
- potential site 到运动轴、domain interface 的关系；
- binder 是否模仿或竞争 native partner；
- downstream structural method 与 quality readout；
- bound state 的功能/生化验证。

### 9.3 条件分支

- state stabilization：选能连接 state-defining elements 的 surface；
- fiducial：优先刚性 attachment 与可见质量，但不遮挡关键区域；
- crystallization chaperone：可利用非功能稳定面，同时警惕 crystal packing artifact；
- transient complex：考虑跨组分 site，但必须保留正确 stoichiometry；
- native partner mimic：明确 binder 可能改变 ligand affinity 或 signaling。

### 9.4 正例

主动选择目标状态、使用对应 ligand/context 设计，并用 particle orientation、resolution、state markers 和 function 共同判断成功。

### 9.5 反例/误判

- 仅用 thermal shift 决定“正确 state”；
- 结构分辨率提高就忽略生物状态漂移；
- 把 binder-stabilized state 当未结合 ensemble 的直接证据；
- 将 cryo-EM fiducial 的 flexibility 归因于 target。

### 9.6 反证或停止条件

- desired state 无独立 marker；
- binder 使样品更均一但进入错误 state；
- site 与必要 ligand/partner 不相容；
- structure quality 改善无法与 aggregation/selection bias 区分。

### 9.7 输出字段

`structural_goal`, `state_marker`, `binding_role`, `rigidity_path`, `native_partner_overlap`, `quality_readouts`, `biological_validation`。

## 10. 特殊 target 输出模板

```yaml
special_target_assessment:
  applicable_playbooks: []
  target_context:
    state: ""
    side: ""
    membrane_or_assembly: ""
    ligand_partner_cofactor: []
    glycan_ptm: []
  class_specific_hazards: []
  required_representations: []
  required_controls: []
  strategy_hypotheses:
    - hypothesis_id: ""
      site_implication: ""
      cdr_or_crop_implication: ""
      evidence_refs: []
      prediction: ""
      falsifier: ""
  unsupported_by_current_backend: []
  stop_conditions: []
```
