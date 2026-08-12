# 证据、结构身份与 residue numbering

本章规定如何检索、分级、引用和映射证据。目标是让每个 site residue 都能追溯到正确 species/isoform/construct/assembly/chain/state，并把事实、计算 proposal 与研究判断分开。

## 目录

1. 证据问题与最低合同
2. Target identity lock
3. 结构清单与适用性
4. 检索协议
5. 证据等级与陈述角色
6. 冲突证据处理
7. `auth_seq_id → label_seq_id`
8. 预测结构与缺失结构
9. Evidence table 模板
10. 停止条件与输出

## 1. 证据问题与最低合同

每个重要决定必须能回答：

- 这条信息来自哪个 source/artifact？
- 它直接测量了当前问题，还是只提供 prior？
- source 使用的 target 与 current target 是否同一 identity/state/context？
- residue/chain 是否已经映射到 current artifact？
- 什么反例或新证据会降低该信息权重？

`knowledge_class: product_invariant`：未完成 identity lock 与 numbering mapping 时，文献 residue 只能作为 provisional evidence，不能直接进入 approved hotspot。

## 2. Target identity lock

### 2.1 必填身份字段

- `preferred_name`, `gene_symbol`；
- `species`, 必要时 strain；
- `sequence_accession`, `isoform`, `sequence_version`；
- `construct_start/end`, deletion, mutation, tag, fusion；
- `biological_assembly`, stoichiometry, target chain；
- `state`, ligand, nucleotide, cofactor, pH 等关键条件；
- `subcellular_side`, membrane orientation；
- PTM、glycan、disulfide、cleavage；
- current target artifact path 与 SHA-256。

### 2.2 条件分支

- 文献只给 gene name：回到 sequence/construct supplement 或数据库记录；
- PDB construct 含 stabilizing mutations/fusions：逐项记录，不能当 wild type；
- 多 isoform：优先与 assay material 一致者，并将 shared/unique residue 分开；
- heteromer/multimer：锁定 assembly 与 chain role，不以 asymmetric unit 猜 biological assembly；
- precursor/protein cleavage：明确 numbering 是 precursor、mature chain 还是 construct。

### 2.3 正例

记录“human isoform 2、mature residues 25–410、PDB construct 删除 loop X、chain A、ligand-bound dimer”，并把文献 residue、UniProt residue 与 current `label_seq_id` 放入 mapping table。

### 2.4 反例/误判

用 mouse homolog 的 author residue 直接写入 human predicted monomer；两者编号相同并不证明 sequence、state 或 assembly 相同。

### 2.5 停止条件

- 两个 accession 均可能是 assay target；
- current sequence 与声明 accession 差异无法解释；
- chain/assembly 不能唯一确定；
- construct mutation 位于候选 site 且无法评估影响。

## 3. 结构清单与适用性

### 3.1 每个结构记录

- structure ID、method、resolution 或 map/model quality；
- experimental/predicted；
- sequence identity、coverage、missing residues；
- construct、mutation、fusion、tag；
- assembly 与 chain mapping；
- ligand/partner/cofactor/nucleotide；
- state 与 state assignment 的依据；
- membrane mimetic、detergent、nanodisc 或 crystal contact；
- PTM/glycan 是否建模；
- candidate site 的 local quality；
- 与 current artifact 的映射与适用范围。

### 3.2 结构角色

- `mechanism_structure`：最能回答目标机制；
- `design_structure`：最适合几何设计与编译；
- `counter_state_structure`：用于检测 state-specific 风险；
- `assembly_context_structure`：用于检查遮挡与 approach；
- `negative_control_structure`：揭示非目标构象或同源 off-target。

一份结构可承担多个角色，但不得默认“最高分辨率”就是最佳 design structure。

### 3.3 结构选择反例

高分辨率 apo domain 缺少膜与 partner，而中等分辨率 cryo-EM 全复合物显示 candidate patch 被 glycan/邻域遮挡。若只按 resolution 选择，会产生虚假可达性。

## 4. 检索协议

### 4.1 Query families

以 target/isoform/species 为核心，至少组合：

- `structure`, `complex`, `cryo-EM`, `crystal`, `NMR`；
- `binding site`, `epitope`, `interface`, `mutagenesis`, `alanine scan`；
- `ligand`, `substrate`, `cofactor`, `partner`, `competition`；
- `active`, `inactive`, `open`, `closed`, `prefusion`, `postfusion`；
- `glycosylation`, `PTM`, `membrane`, `oligomer`, `assembly`；
- `nanobody`, `VHH`, `antibody`, `intrabody`, `conformation-specific`；
- assay 名称与 desired effect。

### 4.2 Source priority

1. current immutable project artifact 与原始实验数据；
2. 原始研究论文及其 structure/database deposition；
3. 官方数据库记录与格式规范；
4. 高质量 review 用于发现线索，不承担精确 residue claim；
5. predictor、scan、docking 与二手摘要仅作 proposal/prior。

引用 review 时应追到 primary source。精确 residue、state 或 causal mechanism 不应只引用搜索摘要。

### 4.3 检索完成条件

不是“找到一篇支持文章”即完成。必须覆盖：

- 支持 primary site 的直接证据；
- 至少一个可行 alternative；
- 与当前 target identity/context 的差异；
- 公开的 negative、conflicting 或 scope-limiting evidence；
- 无证据的空白。

### 4.4 精确引文身份校验

DOI、PMID、PMCID、论文标题、期刊和年份是同一条 source identity，不得从不同搜索结果拼接。任何承担精确 residue、定量数值、state 或 causal mechanism 的 primary source，在交付前必须：

1. 在 publisher 原文、PubMed/PMC 或等价官方记录上核对 \`title + journal + year + DOI/PMID\`；
2. 打开交付的 URL，确认持久标识符确实指向所声称的论文；
3. 定量值回到正文、图表或 supplement，记录 assay/construct/format，不仅依赖搜索摘要；
4. 若字段无法核实，宁可省略 DOI/PMID 并标记 \`source_metadata_status: provisional\`，不得猜测或补全。

**反例**：一个搜索结果给出 KN035 标题，另一条给出相似 PD-L1 论文的期刊和 DOI，将它们合并为一条 E1 source。这属于 source identity drift，即使生物学方向正确也必须停止或降级。

## 5. 证据等级与陈述角色

### 5.1 Evidence tier

`E1_direct`：当前 identity/context 的 complex、functional mutagenesis、competition、activity 或项目 assay 直接支持。

`E2_near_direct`：同 target 的不同 construct/state，或高相似 homolog 中机制与结构共同支持；必须声明转移假设。

`E3_computational`：structure prediction、scan、docking、SASA、conservation、metric；产生候选或一致性证据。

`E4_speculative`：缺少可定位 source 的经验或机制猜想；只能作为 hypothesis。

证据等级不是简单分数：一个 E1 unfolding mutation 可能不能证明 interface；一个 E2 homolog complex 可能比无 context 的 E3 scan 更有机制价值。

### 5.2 Evidence role

- `supports_identity`
- `supports_state`
- `supports_mechanism`
- `supports_site`
- `supports_accessibility`
- `supports_numbering`
- `supports_tool_contract`
- `contradicts`
- `scope_limit`

### 5.3 陈述角色

对外写作使用 `fact`、`inference`、`hypothesis`、`decision`。示例：

- fact：PDB complex 中 residue X 与 partner 原子接触；
- inference：因此覆盖 X 附近可能阻断 partner；
- hypothesis：VHH 从该方向结合会降低 competition readout；
- decision：将其作为 primary，因其机制证据优于 scan-only backup。

## 6. 冲突证据处理

### 6.1 先检查是否其实不是同一问题

按以下顺序解释冲突：

1. species/isoform/sequence；
2. construct/mutation/tag；
3. state/ligand/cofactor；
4. assembly/chain/partner；
5. assay endpoint 与时间尺度；
6. numbering；
7. structure/model quality；
8. 真正 biological heterogeneity。

### 6.2 不允许的处理

- 按论文数量投票；
- 只保留支持当前偏好的证据；
- 用 predictor confidence 消除实验冲突；
- 把“未观察到”自动写成“不存在”；
- 把 homolog 的机制当 current target 的 fact。

### 6.3 可判别输出

对每个冲突写：`competing_explanations`、各自 predictions、最小可区分 experiment、在结果出来前的 conservative decision。

### 6.4 正例

mutagenesis 指向 patch A，scan 指向 patch B。检查后发现 A mutation 同时降低 expression。保留 A 为“可能界面或折叠效应”，B 为 computational alternative；用 surface expression-normalized competition assay 区分。

## 7. `auth_seq_id → label_seq_id`

`knowledge_class: version_specific_tool_fact`：PDBx/mmCIF 同时存在 author-supplied `auth_seq_id` 与 PDB-assigned sequential `label_seq_id`；二者不可互换。`claim:NUMBERING-PDB-001`

### 7.1 映射流程

1. 锁定 mmCIF 文件 checksum、model、assembly 与 chain；
2. 用 `_atom_site.auth_asym_id`, `_atom_site.auth_seq_id`, insertion code 和 comp ID 定位文献 residue；
3. 映射到 `_atom_site.label_asym_id`, `_atom_site.label_seq_id`；
4. 对 alternate location/model 做一致选择；
5. 与 `_entity_poly_seq` 和 current target sequence 对齐；
6. 标记未观测 residue、engineered residue、noncanonical residue；
7. 输出唯一 mapping artifact；
8. 在 approved site 与 strategy 中使用 current artifact 所需的 `label_seq_id`。

### 7.2 值状态协议

residue mapping 中任何 nullable 字段都必须保存“值”和“认识状态”，禁止让 `null` 同时表示
多个含义。允许的 `value_status`：

- `verified`：值由锁定的 source artifact 直接验证；
- `verified_none`：source 明确表达该字段不存在，例如该 residue 经核验没有 insertion code；
- `not_provided`：受控输入或文献没有给出，尚未查询权威 source；
- `unresolved`：已查询但存在冲突、歧义或无法唯一映射；
- `not_applicable`：该字段对该对象没有语义。

`null` 只有与上述 status 同时出现才可解释。`not_provided`/`unresolved` 不得改写成
`verified_none`；只要 insertion code、chain、construct offset 或 residue identity 仍未锁定，就不能
将该 residue 写入 approved hotspot 或 runnable strategy。

### 7.3 映射表

| source_artifact | source_sha256 | auth_chain | auth_seq_id | ins_code | ins_code_status | residue | label_chain | label_seq_id | current_seq_id | mapping_status | note |
|---|---|---|---:|---|---|---|---|---:|---:|---|---|
| `paper-1/PDB-X.cif` | `SHA256` | A | 123 | null | `not_provided` | TYR | null | null | null | `blocked` | 必须读取锁定 mmCIF 后再映射 |

正例：mmCIF 中 residue 的 insertion code 字段经核验为空，写
`ins_code: null, ins_code_status: verified_none`，并记录 mmCIF SHA-256。

反例：任务包没有 insertion code，于是写 `ins_code: null` 并继续声称 mapping complete。

### 7.4 必须保留的异常

- author numbering 缺口、负数、0、insertion code；
- signal peptide/mature-chain offset；
- deletion、engineered insertion、mutation；
- multiple auth chains map to repeated entity；
- unresolved residue 没有 atom record；
- PDB 与 UniProt sequence conflict；
- symmetry-related copy 或 alternate assembly。

### 7.5 反例/误判

文献写 `Y123`，viewer 显示 `101`，于是选择 label 123。正确做法是以 mmCIF 显式映射并验证 residue identity。

### 7.6 映射停止条件

- 一个 author residue 映射到多个 current residues 且无法消歧；
- residue type 不一致且不能由 mutation/processing 解释；
- candidate 只存在于缺失 segment；
- 文献链与 biological target chain 不确定；
- mapping 文件或 structure checksum 发生漂移。

## 8. 预测结构与缺失结构

### 8.1 可支持什么

预测结构可支持：局部折叠候选、表面暴露 proposal、domain boundary 草案、缺实验结构时的几何探索。

### 8.2 不支持什么

单一预测不能独立证明：

- functional state；
- ligand/partner-induced geometry；
- glycan/膜/assembly 遮挡；
- flexible loop 的精确构象；
- 跨域相对取向；
- binding affinity 或机制。

### 8.3 条件分支

- local confidence 高、跨域 PAE 高：可使用 domain 内 patch，不可依赖 domain 间 approach；
- loop 低置信且是机制核心：寻找 homolog/experimental evidence 或将 loop-specific 方案降级；
- 只有 monomer prediction 但 target 是 obligate multimer：先建立 assembly representation；
- glycoprotein/membrane protein：补入生物学 context 后再判断可达性。

## 9. Evidence table 模板

```yaml
target_identity_lock:
  preferred_name: ""
  species: ""
  accession: ""
  isoform: ""
  sequence_sha256: ""
  construct: ""
  assembly: ""
  state: ""
structure_inventory:
  - structure_id: ""
    source: ""
    checksum: ""
    role: [mechanism_structure]
    method_quality: ""
    identity_match: ""
    state_context: ""
    missing_or_engineered: []
    candidate_site_quality: ""
evidence_items:
  - evidence_id: ev-001
    claim_or_question: ""
    evidence_tier: E1_direct
    evidence_role: supports_site
    source: ""
    target_identity: ""
    observation: ""
    supports: ""
    does_not_support: ""
    contradictions: []
    mapping_artifact: ""
    confidence: medium
residue_mapping:
  source_structure_sha256: ""
  mapping_artifact_sha256: ""
  rows:
    - auth_chain: null
      auth_chain_status: not_provided
      auth_seq_id: null
      auth_seq_id_status: not_provided
      insertion_code: null
      insertion_code_status: not_provided
      residue: null
      residue_status: not_provided
      label_chain: null
      label_chain_status: unresolved
      label_seq_id: null
      label_seq_id_status: unresolved
      current_seq_id: null
      current_seq_id_status: unresolved
      mapping_status: blocked
      evidence_ref: ""
conflicts:
  - conflict_id: conflict-001
    evidence_refs: []
    competing_explanations: []
    discriminating_experiment: ""
open_evidence_gaps: []
```

## 10. 停止条件与输出

### 10.1 全局停止条件

- current target 不是唯一 identity；
- design/assay state 未定义且会改变 site；
- source residue 不能唯一映射；
- 证据冲突可由不同 construct/context 解释，但这些字段未知；
- 必要结构或原始 source 不可访问，只剩二手断言；
- 需要把 E3/E4 写成 E1 才能支持结论。

### 10.2 最小交付

即使停止，也要输出：

- 已锁定 identity 与未锁定字段；
- structure inventory；
- evidence table；
- mapping status；
- primary conflicts；
- 获取下一条判别证据的具体 query、database、artifact 或 assay；
- 在证据补齐前哪些动作明确禁止。
