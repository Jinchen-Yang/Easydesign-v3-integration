# Phase 2.1 closure / Phase 2 acceptance — 2026-09-11

**Acceptance: FAIL. Phase 2 is NOT newly frozen. Phase 3 and Phase 4 were NOT started.**

The autonomous master task requires architecture correctness, scientific correctness and legacy
capability parity simultaneously. The implementation below is reviewable work, not an accepted
migration milestone. The earlier Phase 2 candidate report is preserved verbatim in
`PHASE2_CLOSURE_20260911_BASELINE.md` and in its original tag. This report supersedes it for
current acceptance; the old tag was not moved.

## Implemented in this closure attempt

- Explicit thread-owned pending Site/Design proposals and project-owned approved science.
  Approved state resolves the exact historical owner proposal, then verifies original scientific
  artifacts and authority. A second thread's pending proposal is not substituted on resume.
  A local unconsumed proposal remains pending even if another thread approves a different one.
- A bounded shared Evidence Research worker for Target and Site, on existing HTTP/cache,
  ArtifactRef and event storage. It supports literature discovery, primary PMID/PMCID retrieval,
  UniProt, PDB structure/complex records and relevant GPCRdb context. It neither approves nor
  mutates canonical target identity, and does not schedule scientific jobs.
- Explicit NOT_SEARCHED, SEARCHED_NO_EVIDENCE, UNRESOLVED, CONFLICTING_EVIDENCE and VERIFIED
  contracts. Retrieval verifies source bytes; source verification is not biological entailment.
  Mechanistic Site intents declare material questions and cite bounded source passages.
- Literature/scan candidate origins, primary/backup/avoid/unresolved roles, and a frozen source
  snapshot for independent Judge review. Candidate-only citations also enter the Judge snapshot
  and remain protected against source tampering. Reviews and computational projections cannot
  be promoted to direct primary evidence merely by selecting E1/E2.
- Read-only reuse of the existing identity comparison and GPCR topology/membrane/candidate kernels.
  No replacement mapping, filtering, generation or compute-recovery algorithms were introduced.
- Scientific guidance migrated from all 16 legacy research reference files. Large temporary tool
  results use readable JSON lines for the existing paginated file tool; there is no storage migration.

## Acceptance axes

| Axis | Result | Evidence and limits |
| --- | --- | --- |
| Architecture | PARTIAL | Ownership, role separation, source binding and minimum ledger are implemented and tested. Real-model evidence consumption still fails its context bound. |
| Scientific correctness | FAIL for freeze | Public source retrieval and deterministic identity/topology checks succeeded, but neither real golden reached a reviewable Gate 2. No successful mechanistic Agent/Judge closure is claimed. |
| Legacy Prepare/Strategize parity | FAIL | Formal canonical-reference Target configuration and trusted native-expert strategy input remain unavailable in the first-class path. Compatibility code being present is not first-class parity. |
| Protected kernel | PASS | All 187 non-Agent source files are byte-identical to Phase 1 frozen baseline; `/data/Easydesign` is unchanged. |

## Critical failed conditions

1. **Real soluble and GPCR Agent goldens failed.** With the configured DeepSeek model
   (`deepseek-flash`, 32 model calls per execution, 60,000 input-character limit), both hit
   `Model context budget exceeded` while reading evidence. Soluble used 12 calls
   (Coordinator 3, Target 9); GPCR used 15 (Coordinator 3, Site 12). Neither reached Judge/Gate 2.
   The runtime stopped before exceeding its bound. This is an Agent evidence-consumption failure,
   not a scientific failure of lysozyme, ADRB2, any site, or any VHH strategy.
2. **Formal canonical identity remains a capability gap.** A valid local-structure configuration
   with P00698 is rejected by the current Target boundary: “Remote identity lookup and prediction
   are outside this vertical slice”. The new read-only comparison does not populate and review a
   canonical Target Bundle through the old decision service. It cannot be counted as parity.
3. **Native expert design remains a capability gap.** The existing legacy `StrategyVariant`
   supports verified native YAML, but first-class `DesignArm` has no trusted import/binding path.
   Current standard binding/avoid/crop/CDR controls do not cover every legacy context requirement.
4. **Scientific golden coverage is incomplete.** Deterministic identity traps were retained, but
   a completed real-model trap/independent Judge critique and current Gate 2/Gate 3 live acceptance
   are not established by this attempt. Prior synthetic-structure live tests do not fill this gap.

The first-class formal identity and native-expert gaps were reproduced by a capability acceptance
probe. These FAIL results are not presented as passing unit tests. They cannot be silently mapped
to Phase 3, because the master task requires Prepare/Strategize parity before Phase 2 freeze.

A preliminary suspicion about selection of an old Target run was investigated and **not confirmed**.
The exported diagnostic shows both original runtime and Phase 2 selected the same succeeded run.
The soluble Coordinator unnecessarily re-delegated Target; this does not prove incorrect run ownership.

## Validation ledger

| Evidence class | Result |
| --- | --- |
| DETERMINISTIC / MOCK-SYNTHETIC regression | Full run: 713 passed, 11 skipped, 1 fixture-construction failure (894.35 s); corrected evidence/ownership suite: 13 passed (35.49 s). No second whole-suite run; these are separate results, not a single green run. |
| Earlier full Agent unit snapshot | 95 passed, 574.94 seconds; superseded by the final regression for final-source claims |
| Targeted ownership/research snapshot | 12 passed, 30.18 seconds; before the added candidate-only citation regression |
| Static checks / package | Ruff passed; mypy passed for all 180 checked source files; wheel build, byte checks and isolated import/skill discovery passed |
| REAL SOURCE RETRIEVAL | UniProt, PDB, primary literature and GPCRdb records retrieved; successful open-fulltext identity verification; unavailable fulltexts retain explicit errors |
| REAL MODEL LIVE TEST | Two attempted goldens, both failed context budget; 27 actual model calls total |
| REAL SCIENTIFIC BACKEND MICRO TEST | NOT STARTED: Phase 2 acceptance failed before Phase 3; zero generation/prediction GPU jobs |
| Gate 4 / Gate 5 / 50,000-row synthetic stress | NOT STARTED: prerequisites not accepted |

Live Golden setup used original Stage 01 computation on real structures and an explicitly
**scripted validation actor** for chain selection. This is not a human biological approval or
production scientific authorization. No Gate 2 response was submitted and no GPU generation,
prediction, scale, purchase or wet-lab action occurred.

The single full-suite failure occurred before exercising runtime behavior: the new test assigned
a field on an intentionally frozen `SiteIntent`. Only the test construction was corrected to
`model_copy`; Agent runtime code stayed byte-identical. The subsequent 13-test run includes the
corrected candidate-only citation/tamper test and ownership cases. Both original and follow-up
logs/XML are included. The full integration command's failure is retained, not relabeled PASS.
The 11 skips were three opt-in live tests and eight tests requiring the separate PyMOL interpreter.
The separate real-source/model goldens above were actually run and failed; skips are not live passes.

## Source-case facts and their scope

- 1MEL / P00698 / PMID 8784355: deposited lysozyme chains L/M differ from antibody A/B.
  The deposited mature construct is 129 residues versus the 147-residue precursor, with 127
  observed positions. The unchanged identity kernel reports exact_subsequence with review
  required; it does not certify complete coordinates or native precursor equivalence.
- 3P0G / P07550 / PMID 21228869: receptor fusion construct A is 501 residues versus a 413-residue
  canonical reference. The unchanged identity kernel returns ambiguous alignment, human review
  required, with substitutions/insertions/deletions. Verified GPCRdb/geometry reports seven TM
  helices and an active-state annotation; this does not resolve canonical alignment ambiguity,
  validate extracellular accessibility of the intracellular nanobody interface, or prove efficacy.
- PMC13501898: full text retrieved and article PMCID/PMID/DOI bound using the enclosing JATS
  article metadata. Retrieval verifies the document, not a target-specific site conclusion.
- PMC3058308 and PMC1450215 returned unavailable fulltext responses from this source route;
  they were not fabricated or reclassified as negative biological evidence.

## Stop and follow-on work

The master task's critical-failure gate is triggered. Work stops at this Phase 2.1 review package.
There is no new Phase 2 frozen-candidate tag and no Phase 3/4 implementation, tag or success report.
The review commit preserves the partial implementation; it is not a frozen scientific milestone.

A future explicitly resumed closure must first solve bounded evidence consumption (typed, scoped
source views and reliable pagination), complete formal Target identity/old authority integration,
and provide a trusted validated native-expert input path. It must then rerun real soluble, GPCR,
identity-trap and Gate 2/3 acceptance plus full regression. Increasing limits or declaring readonly
source lookup equivalent to canonical approval is not a demonstrated resolution.

## Review package

The package contains the **full repository and Git history**, not only changed files, plus this
report, state ownership, full parity matrix, source/golden traces, regression reports, protected
source inventory and the Phase 2.1 patch. Runtime environments, model weights, global caches and
private credentials are not repository source and are excluded. Reproduction scripts and private
configuration templates are included. Original absolute artifact references are preserved for audit;
the evidence index maps them to the exported package tree.
