# Draft external-source claim index — not approved live knowledge

本文件尚未获得研究者 reviewer/approval，因此不是正式 Skill claim ledger。它只保存待审核的
external-source cards；正文引用稳定 `claim:ID` 时仍必须标为 `external_fact` 或 hypothesis proposal，
并补 current project evidence。`review_date`只是资料复核日期，不是批准日期。

## 目录

1. 使用规则
2. VHH geometry与paratope
3. Mechanism与特殊target
4. Imaging与assembly
5. Numbering
6. Claim审阅模板

## 1. 使用规则

- claim只能支持其`scope`内的判断；
- `scientific_prior`用于生成实验假设，不自动决定current target；
- 原始论文/官方数据库优先，review只作导航；
- 每次引用claim仍要补current target/project evidence；
- `does_not_support`中的越界结论明确禁止；
- source或工具版本变化时更新claim revision，而非静默改义；
- 本 index 是 draft；没有 `reviewer`、`approval_date` 和 source snapshot/revision 的 card 不得作为
  live Skill 已批准经验，也不得伪装成 project observation；
- 机器可执行的 project claim 使用 typed `ClaimReceipt`；本 Markdown 只是 source 展示层；
- confidence反映claim本身在scope内的支持，不是current design成功概率。

## 2. VHH geometry与paratope

### `claim:VHH-CLEFT-001`

- `claim_id`: `VHH-CLEFT-001`
- `knowledge_class`: `scientific_prior`
- `claim`: Camelid VHH可通过突出/延伸的CDR3识别酶cleft或active-site邻域，并产生竞争性抑制；因此deep-cleft项目可把CDR3 penetration作为一个可测试策略。
- `scope`: 已有结构/功能实例与相似几何的hypothesis generation。
- `evidence_type`: 原始结构研究 + 原始功能抑制研究。
- `primary_sources`:
  - De Genst et al., PNAS 2006, “Molecular basis for the preferential cleft recognition by dromedary heavy-chain antibodies”, PMID 16537393, DOI `10.1073/pnas.0505379103`: https://pubmed.ncbi.nlm.nih.gov/16537393/
  - Lauwereys et al., EMBO J 1998, “Potent enzyme inhibitors derived from dromedary heavy-chain antibodies”, PMID 9649422, DOI `10.1093/emboj/17.13.3512`: https://pmc.ncbi.nlm.nih.gov/articles/PMC1170688/
- `confidence`: high within demonstrated examples; medium as transferable prior.
- `counterexamples`: shallow/broad sites may use multiple CDRs; pocket mouth may be inaccessible to a full VHH; long loops can add search/folding risk.
- `does_not_support`: 所有酶/GPCR都必须long CDR3；任意pocket可达；极端CDR3范围；binding等于抑制。
- `tool_or_version_dependency`: none for biological claim; implementation must respect current scaffold/backend contract.
- `review_date`: `2026-08-11`

### `claim:VHH-PARATOPE-001`

- `claim_id`: `VHH-PARATOPE-001`
- `knowledge_class`: `scientific_prior`
- `claim`: VHH:antigen复合物显示paratope使用的结构片段、接触位置与化学类型高度多样，CDR3常具重要贡献，但CDR/framework角色不能由固定通用模板完全替代结构级attribution。
- `scope`: 解释CDR dominance、framework contact与scaffold/approach设计。
- `evidence_type`: 156个unique nanobody:antigen复合物的结构数据分析。
- `primary_sources`:
  - Mitchell & Colwell, Protein Engineering Design and Selection 2018, PMID 30053276, DOI `10.1093/protein/gzy017`: https://pmc.ncbi.nlm.nih.gov/articles/PMC6277174/
- `confidence`: high for dataset-level diversity; medium for any individual target.
- `counterexamples`: 个别VHH可能高度CDR3-dominant；有些framework contact可能为非特异或错误pose。
- `does_not_support`: framework-driven interface自动合格；low CDR dominance自动失败；不需要official design mask。
- `tool_or_version_dependency`: current metric attribution depends on official BoltzGen design mask.
- `review_date`: `2026-08-11`

### `claim:VHH-CDR-LENGTH-001`

- `claim_id`: `VHH-CDR-LENGTH-001`
- `knowledge_class`: `scientific_prior`
- `claim`: 一个基于600个PDB VHH结构/序列的数据集显示CDR1/2长度较集中、CDR3长度更可变，常见CDR3长度包括12、15和18 residues；CDR3长度可作为实验因素。
- `scope`: library/design prior与matched CDR3 hypothesis。
- `evidence_type`: 结构/序列数据集分析与合成库实验。
- `primary_sources`:
  - Nakakido et al., Scientific Reports 2024, DOI `10.1038/s41598-024-70513-4`: https://www.nature.com/articles/s41598-024-70513-4
- `confidence`: medium-high for analyzed dataset; limited by database/library/numbering selection.
- `counterexamples`: target-specific optimal length可在常见分布之外；不同numbering scheme给出的CDR长度可能不同。
- `does_not_support`: 任意target的最优CDR3；15–50默认范围；将insertion count等同final CDR length。
- `tool_or_version_dependency`: current override semantics are BoltzGen 0.3.2 asset-specific.
- `review_date`: `2026-08-11`

### `claim:VHH-PPI-001`

- `claim_id`: `VHH-PPI-001`
- `knowledge_class`: `scientific_evidence`
- `claim`: VHH覆盖天然PPI footprint可通过直接空间遮挡阻止partner结合；Ty1–SARS-CoV-2 RBD结构是一个明确的direct-occlusion实例。
- `scope`: 为PPI blocking提供机制实例，不是任意target的site证据。
- `evidence_type`: 原始cryo-EM结构 + competition/neutralization实验。
- `primary_sources`:
  - Hanke et al., Nature Communications 2020, PMID 32887876, DOI `10.1038/s41467-020-18174-5`: https://pubmed.ncbi.nlm.nih.gov/32887876/
- `confidence`: high for该实例; medium as generic steric mechanism.
- `counterexamples`: blocking也可通过adjacent steric或allostery；footprint overlap未必足以产生功能阻断。
- `does_not_support`: scan-only site必然阻断；结构overlap等于实验potency；忽略assembly/glycan。
- `tool_or_version_dependency`: none.
- `review_date`: `2026-08-11`

## 3. Mechanism与特殊target

### `claim:GPCR-STATE-001`

- `claim_id`: `GPCR-STATE-001`
- `knowledge_class`: `scientific_evidence`
- `claim`: 同一GPCR可被不同VHH选择active或inactive相关构象；intracellular VHH还可通过稳定状态或竞争effector改变signaling。
- `scope`: GPCR state-selective intrabody/site/assay设计。
- `evidence_type`: β2AR VHH家族的state-selective binding与cell signaling实验。
- `primary_sources`:
  - Staus et al., Molecular Pharmacology 2014, PMID 24319111, DOI `10.1124/mol.113.089516`: https://pubmed.ncbi.nlm.nih.gov/24319111/
  - Staus et al., Nature 2016, PMID 27409812, DOI `10.1038/nature18636`: https://pubmed.ncbi.nlm.nih.gov/27409812/
- `confidence`: high for β2AR examples; medium as transferable GPCR prior.
- `counterexamples`: 不同GPCR、side、ligand与transducer context可能完全不同；state selection和state induction可同时发生。
- `does_not_support`: 任意GPCR都用相同intracellular site；高interface score证明state specificity；无需counter-state assay。
- `tool_or_version_dependency`: representation must include verified state/context; current standard adapter may not express all components.
- `review_date`: `2026-08-11`

### `claim:GPCR-CHAPERONE-001`

- `claim_id`: `GPCR-CHAPERONE-001`
- `knowledge_class`: `scientific_evidence`
- `claim`: Nb80可表现G-protein-like作用并稳定agonist-bound β2AR active state，使active-state结构解析成为可能。
- `scope`: structural chaperone与binder-induced state stabilization实例。
- `evidence_type`: 原始结构与功能/配体结合研究。
- `primary_sources`:
  - Rasmussen et al., Nature 2011, PMID 21228869, DOI `10.1038/nature09648`: https://pubmed.ncbi.nlm.nih.gov/21228869/
- `confidence`: high for β2AR/Nb80.
- `counterexamples`: chaperone可能稳定非目标或非天然population；其他GPCR不必具有同样cavity/geometry。
- `does_not_support`: bound structure等于unperturbed ensemble；任何thermal stabilization都是正确state；任意GPCR使用Nb80-like approach。
- `tool_or_version_dependency`: state/context representation required.
- `review_date`: `2026-08-11`

### `claim:GLYCAN-VHH-001`

- `claim_id`: `GLYCAN-VHH-001`
- `knowledge_class`: `scientific_evidence`
- `claim`: VHH可以通过protein contacts与CDR3介导的glycan sensing共同实现glycoform specificity；因此glycan既可能是遮挡，也可能是epitope的决定部分。
- `scope`: glycosylated target的context与glycoform-specific hypothesis。
- `evidence_type`: anti-afucosylated IgG VHH复合物结构与功能研究。
- `primary_sources`:
  - Gupta et al., Nature Communications 2023, PMID 37202422, DOI `10.1038/s41467-023-38453-1`: https://pmc.ncbi.nlm.nih.gov/articles/PMC10195009/
- `confidence`: high for X0/IgG1实例; medium as transferable prior.
- `counterexamples`: 多数protein-targeting VHH不需要glycan contacts；不同glycoforms和occupancy会改变可达性。
- `does_not_support`: 未建模glycan可忽略；所有glycan邻近site不可设计；long CDR3自动产生glycoform specificity。
- `tool_or_version_dependency`: current standard strategy has no glycan semantic field; glycan must be present/validated in structure context.
- `review_date`: `2026-08-11`

### `claim:MEMBRANE-STATE-001`

- `claim_id`: `MEMBRANE-STATE-001`
- `knowledge_class`: `scientific_evidence`
- `claim`: 针对膜转运蛋白特定构象免疫/筛选得到的VHH可稳定并识别该构象；LacY periplasmic-open复合物说明膜侧向、state与入口几何必须共同定义。
- `scope`: dynamic membrane protein的state/context设计prior。
- `evidence_type`: LacY–nanobody crystal structure与biochemical data。
- `primary_sources`:
  - Jiang et al., PNAS 2016, PMID 27791182, DOI `10.1073/pnas.1615414113`: https://pubmed.ncbi.nlm.nih.gov/27791182/
- `confidence`: high for LacY实例; medium as general membrane-state prior.
- `counterexamples`: 某些epitope state-invariant；soluble domain可在有证据时代表full protein。
- `does_not_support`: 所有膜蛋白必须state-specific VHH；去膜模型足够；任意暴露residue可达。
- `tool_or_version_dependency`: membrane context is not a standard semantic field.
- `review_date`: `2026-08-11`

### `claim:AMYLOID-END-001`

- `claim_id`: `AMYLOID-END-001`
- `knowledge_class`: `scientific_prior`
- `claim`: Aβ(1–42) fibril结构显示由subunit staggering产生几何不同的groove与ridge ends；fibril-end设计必须指定polarity/end/polymorph，而不是把两端视为同一site。
- `scope`: beta-rich/amyloid assembly的geometry reasoning；不是VHH成功证据。
- `evidence_type`: 原始cryo-EM + solid-state NMR fibril structure。
- `primary_sources`:
  - Gremer et al., Science 2017, PMID 28882996, DOI `10.1126/science.aao2825`: https://pubmed.ncbi.nlm.nih.gov/28882996/
- `confidence`: high for该Aβ polymorph结构; low-medium for跨polymorph迁移。
- `counterexamples`: 其他polymorph/protein可能有不同ends；目标可能是oligomer或fibril side。
- `does_not_support`: 任意amyloid fibril使用同一end site；end binder必然阻止elongation；VHH一定能接近。
- `tool_or_version_dependency`: assembly representation required.
- `review_date`: `2026-08-11`

## 4. Imaging与assembly

### `claim:IMAGING-PERTURB-001`

- `claim_id`: `IMAGING-PERTURB-001`
- `knowledge_class`: `scientific_prior`
- `claim`: Nanobody/intrabody可用于活细胞成像，但持续或高稳定性结合可能干扰target function；低扰动必须作为独立实验目标，而不能由“用于成像”自动推出。
- `scope`: intracellular imaging、chromobody与低扰动site/assay设计。
- `evidence_type`: photo-conditional intrabody方法与作者直接提出的premature/unrestrained binding干扰问题。
- `primary_sources`:
  - Joest et al., Chemical Science 2021, PMID 35342543, DOI `10.1039/D1SC01331A`: https://pubmed.ncbi.nlm.nih.gov/35342543/
  - Klein et al., Chemical Science 2018, PMID 30429993, DOI `10.1039/C8SC02910E`: https://pubmed.ncbi.nlm.nih.gov/30429993/
- `confidence`: high that live-cell imaging is feasible; medium that unrestrained binding creates a transferable perturbation risk; target-specific magnitude unresolved.
- `counterexamples`: 某些nonfunctional epitopes/low occupancy条件可能扰动很低；可控或瞬时binding可降低风险。
- `does_not_support`: 任意稳定surface都低扰动；高affinity总是更好；荧光signal证明function未改变。
- `tool_or_version_dependency`: none; reporter format must be part of project context.
- `review_date`: `2026-08-11`

### `claim:MULTI-MECHANISM-001`

- `claim_id`: `MULTI-MECHANISM-001`
- `knowledge_class`: `scientific_evidence`
- `claim`: 对同一capsid/target，不同nanobody epitopes可产生direct steric obstruction、allosteric interference或assembly/morphology disruption等不同机制；site选择必须绑定desired effect和forbidden effect。
- `scope`: multimer/capsid/PPI项目中建立alternative mechanisms。
- `evidence_type`: 多nanobody epitope crystal structures + EM/DLS/function研究。
- `primary_sources`:
  - Koromyslova & Hansman, PLOS Pathogens 2017, PMID 29095961, DOI `10.1371/journal.ppat.1006636`: https://pubmed.ncbi.nlm.nih.gov/29095961/
- `confidence`: high for研究panel; medium as generic multimer prior.
- `counterexamples`: 其他target不一定有这些机制；形态改变可能是undesired perturbation。
- `does_not_support`: 所有高affinitybinder同机制；allostery可由structure score证明；assembly disruption总是有益。
- `tool_or_version_dependency`: full assembly representation required.
- `review_date`: `2026-08-11`

## 5. Numbering

### `claim:NUMBERING-PDB-001`

- `claim_id`: `NUMBERING-PDB-001`
- `knowledge_class`: `version_specific_tool_fact`
- `claim`: PDBx/mmCIF为residue保存PDB-assigned sequential `label_seq_id`和author-supplied `auth_seq_id`；二者可不同，精确设计前必须显式映射。
- `scope`: PDB/mmCIF residue与chain identity mapping。
- `evidence_type`: 官方RCSB PDB格式/identifier说明。
- `primary_sources`:
  - RCSB PDB, “Identifiers in PDB”: https://www.rcsb.org/docs/general-help/identifiers-in-pdb
- `confidence`: high.
- `counterexamples`: 某些结构二者恰好相同，但仍应验证chain/insertion/construct。
- `does_not_support`: `auth_seq_id`可直接写入EasyDesign binding；viewer显示编号就是current sequence编号；忽略insertion code/未解析residue。
- `tool_or_version_dependency`: current EasyDesign binding contract uses `label_seq_id`.
- `review_date`: `2026-08-11`

## 6. Claim审阅模板

新增或更新claim必须使用：

```yaml
claim_id: DOMAIN-TOPIC-NNN
knowledge_class: scientific_evidence|scientific_prior|version_specific_tool_fact
claim: ""
scope: ""
evidence_type: ""
primary_sources:
  - citation: ""
    url: ""
confidence: low|medium|high
counterexamples: []
does_not_support: []
tool_or_version_dependency: ""
review_date: YYYY-MM-DD
```

claim进入正文前检查：

- [ ] source是原始论文或官方规范；
- [ ] claim没有超过source直接支持范围；
- [ ] counterexamples与does-not-support完整；
- [ ] current target仍有独立project evidence；
- [ ] 任何version/tool语义已锁定；
- [ ] review date与reviewer可追踪。
