# Phase 2.2 unblock closure attempt — 2026-09-11

**Acceptance: FAIL / NOT FROZEN. Phase 3 and Phase 4 have not started.**

The three requested runtime adapters are implemented and have offline regression evidence.
The real-model acceptance path failed before Gate 1. This is reviewable implementation work,
not a completed scientific migration milestone. No new Phase 2 frozen tag was created and no
previous frozen/candidate tag was moved. The full repository is the review deliverable.

## Critical live finding and stopping decision

The first real soluble case used deposited 1MEL, the intended P00698 canonical reference and the
configured DeepSeek `deepseek-flash` model. Coordinator invoked Target Intelligence. Target read
its Skill, then attempted deep UniProt acquisition without a `SELECTED` source event.
`EvidenceCorpus.require_selected()` correctly refused the acquisition. However, the
`AgentBoundaryError` escaped the tool execution and terminated the entire Agent invocation.
There is no bounded model correction path for this otherwise recoverable prerequisite error.

This is an Agent runtime/interaction failure. It is neither evidence of bad lysozyme biology nor
an API credential failure. Weakening selection enforcement, automatically selecting a source on
behalf of the model, or swallowing integrity/authority errors would not be an acceptable fix.
A future resumed repair should distinguish a correctable prerequisite response from hard trust
violations, return a small typed correction to the specialist, and test bounded recovery from
an omitted or misordered selection before repeating all real goldens.

The user's critical-failure rule was applied immediately: no further live cases, implementation
progression or Phase 3 work. The already running full offline regression is allowed to finish
for an accurate review record. No scientific job was created by this live attempt; no human
card response, generation, prediction or production computation occurred.

Live evidence directory on Suzhou2:
`runtime/tmp/phase22-live-goldens-20260911T055919Z`.
The complete isolated workspace, event records, checkpoint database and failure report are in
the review package's `evidence/phase22/live-goldens/` directory.

| Required live case | Result |
| --- | --- |
| Soluble Agent → active evidence → Judge → Gate 2 | **FAIL before Gate 1**: unselected acquisition terminates the Agent |
| GPCR/membrane Agent → evidence/specialization → Gate 2 | NOT RUN after critical failure |
| Real canonical/construct trap → proper Gate 1 → authoritative bundle | NOT COMPLETED; first attempt failed before source acquisition |
| Standard structured design → real validation/Judge → Gate 3 | NOT RUN after critical failure |
| Expert native strategy → real validation/Judge → Gate 3 | NOT RUN after critical failure |

## Evidence-context measurements and limits

| Measurement | This live attempt |
| --- | ---: |
| Model calls | 4: Coordinator 2, Target 2 |
| System/message characters per call | 6,925; 7,328; 6,658; 13,348 |
| Peak system/message characters | 13,348 |
| Peak estimated characters including compact tool schemas | 20,725 |
| Search results / selected sources | 0 / 0 |
| Full evidence sources acquired / retained source bytes | 0 / 0 |
| Current-binding corpus documents / chunks | 0 / 0 |
| Focused cards supplied to a specialist | 0 |
| Judge calls / Gate 1–3 completion | 0 / none |

The configured guard remains **60,000 system/message characters** and the safety budget remains
**32 calls per Agent execution**. Tool schemas, including structured output, are measured
separately; the combined value is an explicit character estimate, not provider token billing.
No input limit was raised. Every reserved model attempt and structured-output repair is metered.

Before this patch, the Phase 2.1 soluble and GPCR cases stopped at the 60,000-character guard
after 12 and 15 model calls respectively, before Gate 2. This attempt stops much earlier for a
different reason. **13,348 is not an end-to-end improvement benchmark and does not establish
that the evidence-consumption blocker is resolved.** The synthetic corpus/pagination tests prove
mechanical retention and bounded reading only. All evidence-context acceptance criteria still
require a completed real scientific path with comparable evidence consumption.

## CatMaster review and adopted patterns

The mandatory source review was completed before implementation at CatMaster commit
`5246749f8d20cce144faa12f4535a5c9a4de4427`.
See `PHASE22_CATMASTER_EVIDENCE_PATTERN_REVIEW.md` for the exact-source decision table.

- ADOPT: explicit selected/deferred/excluded sources, reasons and progressive disclosure.
- ADAPT: complete source retention, section/chunk retrieval, scoped cursors and tool output
  offloading onto existing EasyDesign ArtifactRefs and events. Retrieval is small lexical
  matching, not an evidence-entailment model or a universal retrieval platform.
- REJECT: a second corpus database, generic literature/browser platform, bibliography workflow,
  new provider stack, scheduler, ORM or workflow engine.

CatMaster's generic adapter does not itself bound all tool-authored model content. EasyDesign
therefore bounds its own working views instead of assuming that offloading an artifact is enough.

## Implemented evidence contract

`agent/evidence_corpus.py` stores derived JSON sections/chunks through the existing artifact
mechanism while retaining complete original HTTP response bytes. Windows are at most 1,500
characters with 120-character overlap. Ten protein-design EvidenceNeeds map to the existing
scientific topics. Only a thread's selected source/need can be acquired deeply or retrieved.
Project-level durable source documents can be selected independently by another thread; its
current retrieval view and scientific proposal remain separate.

Focused retrieval supplies source identity, access depth, scientific eligibility, passage and
section/chunk locator. Its cursor binds the thread, target configuration, question and source
snapshot. Supporting/contradicting/scope-limiting claim uses retain exact excerpts, evidence
strength and transfer limitations. Acquisition receipts cannot replace focused passages in
scientific conclusions. Source-byte verification does not imply scientific entailment.

`agent/evidence_output.py` offloads large tool results using the existing SessionStore and
ArtifactRef. Ordinary previews are small and explicitly partial. Named-field and array/text
reads are role/execution scoped. Already scoped retrieval/read pages are not truncated again;
a cursor advances only by the entries or text actually delivered. An oversized indivisible item
requests a narrower named field. Earlier detailed model views become references; their full
checkpoint/source data remain durable. No second storage layer or scheduling state is added.

The Judge receives all items in the bound scientific projection, including cited support,
contradictions and limitations. Mechanical binding fields are removed from model work and remain
owned by runtime. A scientific projection over 32,000 characters is rejected for narrowing,
rather than silently dropping counterevidence. Archived Judge results also require the exact
current delegation binding; another proposal in the same execution cannot reuse that view.

## Canonical identity implementation and remaining acceptance gap

`agent/target_identity.py` verifies an acquired official UniProt record, then copies its
accession/species through the existing project configuration revision service. It cannot
replace a scientist-configured accession/species or silently retarget an existing prepared
Target. An exact repeated proposal after the configuration binding changes verifies the prior
source and only confirms the identical configured reference; it does not create another job.

The existing Stage 01 service owns canonical/construct alignment, coordinate mapping and
Gate 1 requirements. Runtime exposes canonical/construct lengths, edit counts, ambiguity and
mapping status for pending review. The existing decision service applies the scientist response
and publishes the authoritative bundle. No replacement residue mapper or identity engine exists.

Offline regressions exercise actual old Stage 01 jobs with deterministic cached source fixtures:
clean canonical match, a clean exact subsequence accepted by the old engine, a construct with
incomplete coordinate mapping requiring review, multiple eligible chains, a canonical sequence
substitution, declared-species conflict, source acquisition and proposal replay. Project-global
Target state is checked against the resulting verified bundle.

These establish implementation behavior, **not real-model identity-trap acceptance**. The real
case did not acquire UniProt or publish an approved canonical bundle. The parity status remains
PARTIAL. Native state, biological function and experimental efficacy are never inferred from
canonical reference approval. Existing design-scope and legacy decision semantics are preserved;
this patch does not claim to repair every pre-existing multi-decision edge case in the old engine.

## Standard/native design implementation and narrow old-service exception

`--native-strategy` accepts a scientist-provided, project-local ResearchStrategy only after an
approved Gate 2 foundation. Native YAML must bind the approved target/mapping/hotspot and an
official VHH scaffold. Runtime verifies stable input paths, source bytes, crop/binding/avoid
labels, framework and bounded loop design/exclusion/insertion constraints. Binder returns a
scientific opinion with `strategy_source=expert-native` and `arms=[]`; it cannot rewrite the
expert YAML or replace it with standard arms. Replacement requires scientist REVISE.

Standard structured DesignArm remains available. Both paths use the old compiler, backend schema
validation, strategy-freeze plan, independent Judge and Gate 3. Native source bytes remain
unchanged in compiled design YAML and all source inputs stay verifiable. A fresh thread can
inherit the exact approved native specification. The live backend/model rerun remains missing.

One narrow change is outside Agent source:
`orchestration/research.py::_validate_first_pilot_strategy`.
The old StrategyVariant contract requires exactly one provenance scaffold for a native variant,
while the old first-pilot facade required that same variant to contain all seven scaffolds.
Consequently a legal seven-native-variant first pilot could not pass. The pre-fix failure is
retained in `phase22-native-coverage-before.log`.

The fix groups native variants by their **existing hypothesis/condition identity**, checks coherent
experimental factors, then calls the unchanged first-pilot validator. Exactly seven unique
official scaffolds and 40 candidates per scaffold are still required for each condition. Missing,
duplicate, inconsistent or wrong-count coverage is rejected. Standard strategy behavior is
unchanged. This is a demonstrated facade bug fix, not a new workflow abstraction or altered
BoltzGen/Pilot/filtering/recovery semantics. Its before/after and invalid-coverage regressions are
included. Core mapping, scientific stages and backends remain byte-identical to Phase 1 frozen.

## Verification ledger

Final full integration regression **012: PASS — 730 passed, 11 skipped, 0 failed/error**
from 741 collected tests, 989.13 seconds of pytest execution. The skipped tests are eight
optional PyMOL integration tests and three opt-in live Agent tests. The separate real-model
acceptance attempt above is a FAIL; these skips do not turn it into a PASS.

Within that same complete run, all **115 Agent unit tests** passed, including **9 multi-turn,
resume and ownership tests** and **15 new Phase 2.2 context/identity/native tests**. Existing
Phase 1 and Phase 2 regressions were run together with old scientific service/stage regressions.
Repository structure, vendored viewer assets, compileall, Ruff and mypy (184 source files)
passed. Raw evidence: `phase22-full-012.log`, `phase22-full-012.xml`, and
`final-regression-summary.json` in the package's `evidence/phase22/validation/`.

No runtime or test source changed after this final run began. Closure documentation was
updated afterward with its actual results. The final wheel independently verified byte-equal
modules/Skills and installed imports. The source-boundary audit compared 187 non-Agent package
files with Phase 1 frozen: only the explicitly documented research facade fix differs.

Completed targeted evidence before final full regression:

| Check | Result / scope |
| --- | --- |
| Identity + Site/Binder multi-turn harness 006 | 19 passed, 249.82 s; before final small hardening |
| Evidence/native/old research focused 007 | 38 passed, 64.05 s |
| Isolated final species/schema hardening | 15 passed, 103.25 s |
| Final context + identity 011 | 11 passed, 21.90 s |
| Final wheel | PASS: new modules and Skills byte-equal; isolated installed imports and role surfaces verified |
| Live API/model | Credentials worked; 4 actual calls; scientific path FAIL as described above |
| Real generation/prediction/backend compute | NOT STARTED |

Full run 008 stopped at repository preflight because a previous wheel build had left an ignored
`build/` directory. Its contents were moved intact under `runtime/tmp/phase21-retained-build-before-phase22`.
Full run 009 was cancelled and superseded when final source review added species protection and
exact page/cursor handling. Its interruption-induced fixture error is not presented as a product
regression, and the run is not a full PASS. Final full run 012 is the acceptance regression.
All iterative logs are retained, with final and superseded results distinguished.

## Remaining work and delivery boundary

The first unresolved issue is bounded recovery from source-selection prerequisites in the real
Agent harness. Then all five real goldens, scientific-content review, evidence-context metrics
and the full regression must pass together. Prepare/Strategize entries cannot be relabeled
COMPLETE based solely on implementation or synthetic tests.

The package contains the complete current repository, tests, resources, documentation and
independent Git history, plus the Phase 2.2 failure workspace, test evidence and prior comparison
evidence. It excludes private credentials, local model configuration, environments, weights,
global caches and unrelated scientific projects. Configuration templates remain in source.

There is no Phase 2 freeze, Phase 3/4 implementation, production compute, storage migration,
Workbench, Figure 2, old orchestration deletion or wet-lab ordering in this attempt.
