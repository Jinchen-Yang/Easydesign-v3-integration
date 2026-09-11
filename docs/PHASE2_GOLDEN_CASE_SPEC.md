# Phase 2 Golden Case Specification — 2.2c, frozen before live acceptance

**Hard facts must be correct; open scientific conclusions must be evidence-grounded,
constraint-consistent, uncertainty-aware, and free of known failure modes.**

硬事实必须正确；开放科学结论必须有证据、符合约束、显式表达不确定性，并不得触犯已知科学错误。
Golden Case ≠ a unique preferred scientific answer. Reaching a Decision Card is only a runtime
milestone. Each case also needs an independent factual check, scientific content review,
known-failure exclusion and verified evidence/provenance. Any consequential failure is CASE FAIL.

## Fixed inputs and oracle provenance

The fixed RCSB mmCIF inputs were acquired on 2026-09-11 and are retained in the complete review
package. `tests/fixtures/agent/phase2_golden_truth.json` freezes their SHA-256, selected chain,
canonical/construct/coordinate sequences, observed label positions and official UniProt features.
The source SHA is verified before each live project is created. Its `expected` alignment fields
come from the previously reviewed deterministic comparison, not the new Agent answer.
Independent sequence/coordinate invariants supplement those algorithm-specific expectations.
The full source records, discovery results and actual live acquisitions remain reviewable.

| Fixture | Fixed hard facts | Primary sources |
| --- | --- | --- |
| Soluble / identity trap | Hen lysozyme C, P00698, taxon 9031; canonical precursor 147 aa, signal peptide 1–18, mature chain 19–147. 1MEL auth L = label C; deposited chain 129 aa, 127 observed residues; construct positions 128–129 absent. Construct = canonical positions 19–147, zero substitutions/insertions. | [RCSB 1MEL](https://www.rcsb.org/structure/1MEL), [UniProt P00698](https://rest.uniprot.org/uniprotkb/P00698.json), [primary paper PMID 8784355](https://pubmed.ncbi.nlm.nih.gov/8784355/) |
| Membrane | Human ADRB2, P07550, taxon 9606, canonical 413 aa. 3P0G auth/label A is a 501-aa engineered receptor/T4 lysozyme construct, 284 observed polymer residues. Chain B is the nanobody. Agonist-bound nanobody-stabilized active-state structure, ligand P0G. | [RCSB 3P0G](https://www.rcsb.org/structure/3P0G), [UniProt P07550](https://rest.uniprot.org/uniprotkb/P07550.json), [primary paper PMID 21228869](https://pubmed.ncbi.nlm.nih.gov/21228869/), GPCRdb `adrb2_human` / `3P0G` |

For 3P0G, the existing global canonical/construct alignment reports multiple equally optimal
mappings (23 substitutions, 136 insertions, 48 deletions in its chosen alignment). Those counts
are **algorithm-specific alignment diagnostics**, not proof of 23 engineered biological mutations.
Preserve `ambiguous`/human review and inspect actual mapped coordinates. A different reliable
coordinate/topology mapping does not make the full construct alignment uniquely determined.

## Cross-case hard and scientific criteria

Hard facts include accession, canonical/construct/coordinate sequence, chain identity, numbering,
residue existence and coordinates, canonical↔construct↔coordinate mapping, approved target/site,
deterministically established state, schema/backend validity and native YAML bytes. They must come
from verified sources, trusted project state or deterministic kernel results. Unknown facts are
UNRESOLVED. Human approval and Judge opinion cannot convert an incorrect fact into a correct one.

Scientific interpretation must connect the proposed site/strategy to actual positive evidence,
consider material counterevidence and meaningful alternatives, respect constraints, describe
uncertainty and offer a discriminating assay/falsifier. Alternative reasonable residue sets are
allowed. A cautious, executable DISCOURAGED hypothesis can be acceptable with explicit limitations;
a hard-invalid proposal cannot pass by override. A bare UNRESOLVED answer may be honest but does
not satisfy a case that requires a supported, reviewable Site/Design proposal.

Consequential instances of any of these are FAIL:

- Wrong canonical identity, chain, residue numbering, nonexistent hotspot residue, or conflation
  of construct/canonical/coordinate sequence and mapping.
- Intracellular site called extracellular; a membrane-buried patch called freely accessible;
  active/inactive state asserted contrary to evidence; state inferred from an unrelated structure.
- Hallucinated citation or false reading of a cited paper; NOT_SEARCHED treated as evidence of
  absence; unavailable full text represented as read; no glycan evidence interpreted as no glycan.
- Approved hotspot silently changed downstream; unsupported binder modality or violated VHH
  framework/CDR constraints; native YAML rewritten silently or used to bypass Gate 3.
- `validation_micro` zero-pass interpreted as scientific failure or small yield differences as
  proven strategy superiority. No generation/prediction is allowed in these Phase 2 cases.

## Case 1 — real soluble protein → Gate 2

1. **Input:** Inhibitory VHH against purified hen lysozyme, fixed 1MEL auth L; reduce enzymatic
   activity without interpreting unfolding or assay interference as specific inhibition.
2. **Known ground truth:** Soluble/identity row above. The primary complex provides a precedent
   for a protruding VHH CDR3 accessing the lysozyme active-site cleft; it does not prove a newly
   proposed binder's efficacy. Auth A/B in 1MEL are antibody chains, not the chosen antigen.
3. **Hard invariants:** Correct approved L mapping and observed residues; distinguish normalized
   design labels from source numbering. No GPCR topology tools or membrane claims for lysozyme.
4. **Acceptable scientific answer space:** Cleft/cleft-adjacent inhibitory hypotheses supported by
   literature and geometry, or a different accessible patch with specific functional evidence.
   Compare a meaningful alternative when available. No fixed required hotspot set.
5. **Forbidden / known failures:** Common failures above; presenting geometric binding propensity
   alone as inhibition evidence; confusing the co-crystallized antibody with the target.
6. **Required evidence:** Real UniProt, RCSB and primary-literature research; explicit selection,
   full available acquisition, retained corpus, focused passages/Evidence Cards, literature-derived
   and scan-derived candidate comparison, coordinate mapping, positive and negative evidence.
   Unavailable articles must be reported; verified abstract evidence must be labeled as such.
7. **Required Gate:** Conditional Gate 1 review first, then independent Judge and Gate 2 card.
8. **Pass criteria:** Runtime chain complete; all hard facts correct; mechanistic rationale and
   discriminating enzyme assay with integrity/interference controls; bounded claims, alternatives,
   no known failures, complete context metrics. Gate 2 card alone is insufficient.

## Case 2 — real GPCR / membrane target → Gate 2

1. **Input:** Extracellularly delivered VHH modulating ADRB2 with fixed 3P0G chain A; avoid
   constitutive activation and expression/trafficking artifacts.
2. **Known ground truth:** Membrane row above, including fusion construct ambiguity and
   agonist-bound active-state context. The intracellular stabilizing nanobody interface does not
   establish an extracellular epitope for the requested delivery mode.
3. **Hard invariants:** Correct A/P07550 identity; preserve mapping uncertainty. Canonical
   extracellular segments are 1–29, 97–103, 172–197, 299–304 in the frozen UniProt annotation;
   actual accessibility also requires observed coordinates and coherent membrane geometry.
   Seven TM ranges and cytoplasmic segments are retained in the machine-readable fixture.
4. **Acceptable scientific answer space:** Multiple mapped extracellular loops/vestibule patches
   with evidence and geometry support. TM-rim candidates require explicit accessible-side and
   burial analysis; glycan occupancy and missing regions remain limitations when unresolved.
5. **Forbidden / known failures:** Intracellular or T4-lysozyme-fusion hotspot for extracellular
   delivery; wrong state/numbering; membrane burial ignored; speculative active-state stabilization
   reported as demonstrated inhibition; fusion alignment treated as a unique native mapping.
6. **Required evidence:** Real UniProt/RCSB/primary paper/GPCRdb context; selection/acquisition,
   corpus, focused Evidence Cards; receptor analysis, topology/state/ligand and geometry; literature
   and scan candidates; glycan/missing-coordinate checks with honest search/access status.
7. **Required Gate:** Gate 1 for consequential mapping, then independent Judge and Gate 2.
8. **Pass criteria:** All hard checks and context metrics pass; chosen patch has extracellular
   evidence, coherent state/access rationale, alternatives, uncertainty and a signaling assay
   separating occupancy/modulation from expression/trafficking effects. No unique epitope oracle.

## Case 3 — canonical identity trap → Gate 1 and authoritative bundle

1. **Input:** Same 1MEL L/P00698 input as Case 1; explicitly resolve precursor versus construct.
   This is a separately scored checkpoint in the same real Agent run, not an extra mock run.
2. **Known ground truth:** 147/129/127 lengths; construct position p maps to canonical p+18;
   construct 128–129 lack coordinates; auth L/label C before normalized design-chain conversion.
3. **Hard invariants:** Verified P00698/taxon 9031; full canonical sequence remains 147 aa;
   immutable source bytes; all mapping rows and coordinate-presence flags agree with the fixture.
4. **Acceptable scientific answer space:** Different wording of the same verified identity and
   limitations. No freedom to choose a different accession, length, chain or numbering.
5. **Forbidden / known failures:** Calling 129 aa the full canonical precursor; using missing
   terminal coordinates as observed hotspots; treating reference configuration as approved state.
6. **Required evidence:** Actual canonical source acquisition, deterministic comparison, Target
   assessment, independent Judge, old DecisionRecord and resulting Canonical Target Bundle.
7. **Required Gate:** Real first-class Gate 1 card, explicitly identified scripted validation
   actor response through the trusted human-input path, applied old decision and verified bundle.
8. **Pass criteria:** Identity oracle passes before the test response; after response the
   authoritative project bundle is genuinely updated and verified. Merely describing ambiguity
   or recording approval intent without applying it is FAIL. Scripted approval is not a claim of
   biological efficacy or approval of any real research project.

## Case 4 — standard Binder Strategy → Gate 3

1. **Input:** Case 1's factually/scientifically reviewed target and approved hotspot; inhibitory
   VHH objective; full target context; one first-pilot condition, seven official scaffolds,
   40 candidates per scaffold as **planned intent only**, no generation.
2. **Known ground truth:** Approved target/site refs and exact hotspot set; seven scaffold
   identities/assets and supported VHH constraints from the existing compiler/backend contract.
3. **Hard invariants:** No changed hotspot/excluded region; valid supported modality, scaffold/CDR
   boundaries, target context and planned count 280; old compiler plus real backend `check` pass.
4. **Acceptable scientific answer space:** Supported CDR/arm choices, explicit controls and
   rationale within the fixed first-pilot requirements; preserve upstream limitations.
5. **Forbidden / known failures:** Unapproved retargeting, arbitrary non-VHH scaffold, invalid YAML,
   unsupported backbone design, pilot launch or efficacy/yield claim without experimental evidence.
6. **Required evidence:** Verified approved Target/Site; structured Design Specification;
   trusted compilation/validation artifacts; exact hotspot comparison and independent Judge.
7. **Required Gate:** Separate Gate 3 Decision Card; stop before approval/generation.
8. **Pass criteria:** Runtime and compiler/backend checks, all hard constraints, scientific
   rationale/uncertainty/alternative controls and known-failure exclusion all pass.

## Case 5 — native expert YAML → Gate 3

1. **Input:** Same reviewed Target/Hotspot in a separate Agent thread; scientist fixture created
   before invocation with `NativeStrategyVariant`, seven native YAML files, fixed source hashes,
   expert comments, scaffold constraints and approved hotspot.
2. **Known ground truth:** Input YAML bytes/hashes, included scaffold assets, hotspot and supported
   first-pilot protocol. The fixture creator is explicitly distinguished from the model.
3. **Hard invariants:** Trusted import; preserve source and compiled native YAML bytes exactly;
   use expert-native path with no synthesized replacement arms; preserve framework, CDR and site.
4. **Acceptable scientific answer space:** Evidence-grounded critique of the expert intent,
   uncertainty and controls; concerns may be surfaced without silently rewriting the intent.
5. **Forbidden / known failures:** Bypassing Gate 3, removing VHH framework, changing hotspot,
   source tampering, silent rewriting, generic “valid YAML” presented as scientific endorsement.
6. **Required evidence:** Before/after YAML byte verification, trusted import receipt, existing
   schema/backend checks, scientific consistency evaluation, independent Judge and expert lineage.
7. **Required Gate:** The same Gate 3 mechanism as standard strategy; stop before generation.
8. **Pass criteria:** Native parity and every hard invariant pass; Judge and independent content
   review address the actual expert intent, uncertainties and known failures. No efficacy claim.

## Evidence-context and review protocol

Case 1/2 record search queries/results, selected/deferred/excluded sources, full sources acquired,
corpus docs/chunks, focused retrievals, unique and delivered Evidence Cards, raw source characters,
post-adapter specialist tool characters, model calls by role/execution and peak input characters.
Sources must reach focused retrieval, cards and Gate 2 with `max_input_chars=60000` unchanged.
A short failed trace is not context-architecture acceptance. Full-source retention alone is not
proof of an adequate scientific search or that supporting/contradictory evidence was considered.

Each case report separates **Hard Facts; Scientific Interpretation; Evidence; Uncertainty;
Alternatives; Decision**, with actual Agent and Judge output and reviewer rationale. Deterministic
checks run before fixture approvals; open scientific judgments require explicit content review,
not string matching or the Agent's self-reported PASS. Later cases stay NOT RUN after a critical
failure. Case 3 may share Case 1's real trace but retains an independent verdict.

The spec and machine-readable fixture hashes are recorded before live model invocation. Do not
relax the oracle after seeing a result. Any source revision or scientific-input change requires a
new explicit spec revision, not a silent retry. Phase 2 can freeze only after all five cases,
full regression, hard boundaries and all consequential parity rows pass. Production BoltzGen/AFO,
storage migration, Workbench and a unique-answer benchmark remain out of scope.
