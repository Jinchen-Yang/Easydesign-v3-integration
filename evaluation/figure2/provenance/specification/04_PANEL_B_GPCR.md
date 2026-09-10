# Panel C/D — GPCR Challenge Metric Bank

## Target selection
优先 4–8 个 GPCR，覆盖：
- extracellular epitope binder
- state-specific binder
- pocket-proximal binder
- flexible extracellular loop
- glycosylated / engineering-heavy target
- active/inactive conformational pair（若可得）

不要只选已调得最好的 target。冻结 inclusion criteria。

## Primary endpoint
computational_HQ_yield =
n_candidates_passing_frozen_independent_profile / n_generated_candidates

candidate 不是统计独立 replicate。

## Structure confidence
- interface pLDDT
- interface PAE
- ipTM
- ipSAE（若可得）
- pDockQ/pDockQ2（若适用）

## Interface geometry
- BSA / ΔSASA
- shape complementarity
- interface contact count
- contact density
- H-bond count
- salt bridge count
- severe clash count
- buried unsatisfied polar count

## Interface physics
- Rosetta interface ΔG
- ΔG/ΔSASA
- hydrophobic burial
- electrostatic complementarity（若可得）

## Target/site fidelity
- hotspot coverage
- hotspot contact fraction
- forbidden-contact fraction
- target local RMSD
- full target RMSD
- site backbone RMSD

## GPCR state（仅适用）
- TM6 state deviation
- microswitch deviation
- active/inactive state consistency
- counterstate score margin

## Pocket/CDR（仅适用）
- CDR3 pocket engagement
- minimum CDR3-site distance
- pocket penetration depth
- CDR dominance fraction

## VHH developability
- TNP risk
- surface hydrophobicity
- charge patches
- aggregation liabilities
- sequence liability count
- CDR3 hydrophobicity
- net charge

## Robustness
- multi-seed pass fraction
- score CV across seeds
- ranking stability
- evaluator disagreement
- top-k overlap across evaluators

## Diversity
- pairwise sequence identity
- cluster count at 70/80/90%
- positional entropy
- unique CDR3 fraction
- structural binder RMSD diversity
- epitope/contact-pattern diversity

## 主文推荐
1. HQ yield per target / method
2. paired ΔHQ yield
3. hotspot coverage
4. target deformation
5. interface confidence/PAE
6. quality–diversity Pareto
7. 代表性 GPCR 的 state/pocket metric

## Counterstate / specificity
如任务包含 active/inactive、NK2R vs NK1R/NK3R、desired vs forbidden：
报告 target score、counterstate/offtarget score、computational selectivity margin、forbidden-contact rate。
没有实验时不要称 affinity selectivity。
