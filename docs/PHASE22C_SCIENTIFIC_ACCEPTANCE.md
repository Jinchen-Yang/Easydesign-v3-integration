# Phase 2.2c — Tool Interface Hardening + Scientific Golden Acceptance

**FAIL / NOT FROZEN — critical real acceptance stopped before Gate 1.**
Date: 2026-09-11. Baseline: `2527135dc971ddec7188609ce009034cecf7b4e4`.
Branch: `codex/easydesign-v3-phase2-4`; the existing v3 worktree is retained.
No Phase 3/4 implementation, new frozen tag or production generation/prediction was started.

The tool-interface repair passes both offline regression and a real model correction. The actual
Target specialist then emitted explanatory prose followed by a valid JSON code block. The existing
Target callback expects the entire response to be JSON and raised `JSONDecodeError` before a
Target assessment, Judge delegation or Agent Gate 1 card could be registered. The raw response
also confuses canonical/construct/observed lengths. Extracting the embedded JSON would not by
itself make the scientific content acceptable. No parser change or additional live retry was made
after this critical failure.

## 1. Scientific acceptance principle and frozen spec

**Hard facts must be correct; open scientific conclusions must be evidence-grounded,
constraint-consistent, uncertainty-aware, and free of known failure modes.**

硬事实必须正确；开放科学结论必须有证据、符合约束、显式表达不确定性，并不得触犯已知科学错误。
Reaching a Gate is not sufficient, and a fixture approval cannot repair a false fact. Open site
and strategy questions allow multiple reasonable answers; no unique preferred hotspot is imposed.

The complete eight-part definition for each case is in `PHASE2_GOLDEN_CASE_SPEC.md`.
It covers hard facts, acceptable answer spaces, required evidence/Gates, uncertainty, alternatives,
known failures and independent review. Before live invocation the spec was frozen by SHA-256
`96ead11b3f071dce05780dd1f6fba6ee353d2346aa5a53438ac4ef0e8a850a49`.
The fixed-source oracle `tests/fixtures/agent/phase2_golden_truth.json` was frozen at
`2e367355d197d541df7f77b87f6b505659a81997dc79db7a97a0b0e0ff3258c9`.
Neither was relaxed after observing the result.

## 2. Final field / fields / path API and compatibility

| Selector | Exact meaning | Example |
| --- | --- | --- |
| `field: str` | One top-level field | `field="identity_evidence"` |
| `fields: list[str]` | Distinct existing sibling fields; no silent omission | `fields=["chains","identity_evidence","options","limitations"]` |
| `path: list[str]` | Nested object keys / nonnegative list indices | `path=["identity_evidence","construct_comparisons"]` |
| Legacy `field: list[str]` | Retains nested traversal, with deprecation notice | `field=["identity_evidence","canonical"]` |

Only one selector may be supplied. Omission or an empty path retains the existing bounded root
view. The old list form is never silently reinterpreted as sibling projection. Existing in-repo
scoped-read calls were singleton paths in tests; they still pass. A genuine nested legacy path
and the historical malformed sibling list are covered explicitly. Undocumented Python negative
indices now receive a correction instead of selecting from the array tail. Navigation hints use
`path` and `available_fields`; list/text pagination preserves exact delivered offsets. Oversized
objects ask for narrower scope without pretending the object was read or consuming array rows.

## 3. Recovery semantics and real correction

`InvalidFieldProjection` is separate from `AgentBoundaryError`. The harness verifies role,
current execution, reference syntax, SHA-bound artifact and delegated Judge snapshot **before**
returning any recoverable projection/schema diagnostic. Conflicting selectors, unknown fields,
bad list navigation and selector/pagination syntax in this tool return
`REQUIRES_ACTION / RECOVERABLE_TOOL_ARGUMENT / INVALID_FIELD_PROJECTION` with precise instructions.
This precheck runs before framework validation could emit an unbudgeted syntax response.

| Category | Handling |
| --- | --- |
| `RECOVERABLE_PREREQUISITE` | Explicit source selection required before acquisition |
| `RECOVERABLE_TOOL_ARGUMENT` | Correct navigation of an already verified, authorized result |
| `HARD_BOUNDARY_VIOLATION` | Fatal: unauthorized role/tool/project, stale execution, forged authority or invalid scientific constraint |
| Integrity / wrong Judge snapshot | Fatal; no correction allowance or evidence disclosure |
| Scientific `UNRESOLVED`, `SEARCHED_NO_EVIDENCE`, `CONFLICTING_EVIDENCE` | Domain data, not runtime exceptions or proof of negative biology |

Both recoverable categories share **two corrections total per Agent execution** across roles and
delegations. Existing `events` rows hold the count; no schema migration, scheduler, DAG, ORM or
workflow abstraction was added. Restart/replay cannot reset it; a new follow-up execution can.

The real model first corrected SOURCE_NOT_SELECTED (attempt 1). Later it called:

```json
{"field":"identity_evidence","path":["identity_evidence","construct_comparisons"],"ref":"/result-e5b0bc569cdb4654a94b25b55b422182.json"}
```

The runtime returned INVALID_FIELD_PROJECTION (shared attempt 2). The model corrected this to:

```json
{"path":["identity_evidence","construct_comparisons"],"ref":"/result-e5b0bc569cdb4654a94b25b55b422182.json","limit":5}
```

All four A/B/L/M comparison records were returned successfully. This is real repair evidence,
not a synthetic claim. The exact call/response pair is in `evidence/phase22c/real-tool-argument-recovery.json`.

## 4. Five fixed real inputs and scientific oracles

| Case | Input / hard truth | Acceptable answer space | Actual result |
| --- | --- | --- | --- |
| 1 Soluble → Gate 2 | Inhibitory VHH for hen lysozyme, 1MEL auth L/label C, P00698; canonical 147, mature construct 129, observed 127; positions 128–129 lack coordinates | Evidence-supported cleft/adjacent or other justified accessible inhibitory hypothesis, alternatives and enzyme assay controls | Gate 2 NOT RUN after shared identity-prefix failure |
| 2 GPCR → Gate 2 | Extracellular VHH for ADRB2, 3P0G A/P07550; canonical 413, engineered fusion construct 501, observed 284; active agonist/nanobody-stabilized state; full-construct alignment ambiguous | Multiple extracellular mapped candidates with topology, membrane geometry, state, glycan/missing-region limits and signaling controls | NOT RUN after critical stop |
| 3 Identity trap → Gate 1 + bundle | Same real 1MEL L input; construct p maps to canonical p+18, not a human-selected arithmetic convention | Verified canonical identity/mapping and honest limitations; exact hard-fact oracle | FAIL before Agent Gate 1; old Stage 01 pending, authoritative bundle not approved |
| 4 Standard → Gate 3 | Reviewed/approved Case 1 Target/Site; supported VHH, full target, one condition, seven official scaffolds × 40 planned candidates | Supported structured design, controls and uncertainty, preserved hotspot/exclusions | NOT RUN; approved prerequisites not created |
| 5 Native → Gate 3 | Same approved Target/Site; pre-invocation expert YAML fixture with seven variants, exact source bytes and supported framework/CDR constraints | Critique actual expert intent without silent rewriting; same Judge/Gate 3 | NOT RUN; no native import/backend check in this live attempt |

Full source sequences, observed positions, topology features and source-file hashes are retained
in the machine-readable oracle. The live input hash matched before project creation. The spec
lists source URLs and forbidden failures: wrong chain/identity/numbering, nonexistent residues,
intracellular/extracellular or membrane/state confusion, invented citations, unjustified absence
claims, changed approved hotspot, unsupported binder modality, rewritten/native Gate bypass,
and overinterpreted validation_micro yield. No evidence is replaced with a mock to complete a case.

## 5. Actual Agent result, hard-fact review and Judge result

**Hard Facts:** The old deterministic comparison returned canonical_length=147 for every chain.
A/B have deposited construct_length=148; L/M have construct_length=129, zero substitutions,
18 deletions and exact-subsequence mapping. The model's raw summary instead calls A/B “132
canonical residues” and speaks of “147/148” canonical lengths. It conflates observed/construct
counts with the canonical length, despite having the correct comparison in its scoped result.
This violates the hard-fact standard for a chain-comparison/identity decision.

**Scientific Interpretation:** The 18-aa precursor/construct difference is a legitimate
interpretive subject, but the model also frames numbering as a human choice rather than using
the deterministic map. That suggested question is not the old chain-selection request. These
are unregistered Target statements; no incorrect human decision was actually applied.

**Evidence:** Real UniProt P00698 was selected/acquired, canonical reference configured, and
`prepare_target` submitted once. The unchanged service produced run `20260911t152716z` and job
`job-0e0fe89634e94fa0`, awaiting chain approval. The repaired read returned all comparison rows.

**Uncertainty:** Three focused retrievals returned UNRESOLVED with zero cards. The retained
record includes Signal 1–18 and Chain 19–147 features. Diagnostics show the canonical proposal
changed the target binding: the selected/acquired source remains in the prior binding and no
corpus document is visible in the current binding. Empty retrieval is therefore not evidence
that UniProt lacks those facts. The model's generic “access limitation” is not an adequate
diagnosis of this binding transition. Nothing was rebound or reacquired after failure.

**Alternatives:** The raw Target compared L/M with A/B, but a scientifically acceptable Site
alternative/assay discussion was not reached. The original paper/site/GPCR/design reasoning was
not performed in this run. The fixed spec defines the later acceptable alternatives.

**Decision:** Identity case FAIL; other four acceptance stages NOT RUN. The terminal exception is
the strict Target JSON parser receiving prose plus a fenced JSON object. Diagnostic extraction
shows that the embedded object validates as `TargetAssessment`, but it was **not registered**,
and its factual errors remain. No Judge was invoked, no Agent Decision Card was produced, no
independent Gate review receipt or scripted approval was issued, and no approved bundle exists.
No biological inference about lysozyme, binding or strategy efficacy follows from this failure.

## 6. Evidence-context and model usage

Model: official DeepSeek `deepseek-flash` (current V4.1 Flash alias), unchanged configuration,
thinking disabled, max_output_tokens=2048, max_model_calls=32 per execution,
max_input_chars=60000 unchanged. This run did not exhaust either budget.

| Measured quantity | Actual |
| --- | ---: |
| Model calls | 16: Coordinator 3, Target 13; Site/Judge/Binder 0 |
| Discovery search queries/results | 0 / 0 |
| Selected sources / full acquisitions | 1 / 1 (P00698) |
| Corpus docs / chunks, all bindings | 1 / 3,062 |
| Corpus docs / chunks, current binding | 0 / 0 after canonical configuration |
| Focused retrieval calls / cards returned | 3 / 0 |
| Unique/delivered focused Evidence Cards | 0 / 0 |
| Unique retained raw source characters | 384,043 |
| Post-adapter specialist tool-result characters | 14,399 |
| Summed specialist context over calls | 213,322 (repeated history counted) |
| Summed specialist tool-message context | 122,838 (repeated history counted) |
| Peak guarded system/message characters | 21,655 |
| Peak estimated input including tool schemas | 29,710 |
| Prerequisite / projection repairs | 1 / 1, shared attempts 1 and 2 |

Characters are not billed tokens. The 60k guard's existing definition covers system/message
content; tool schemas are recorded separately. Complete per-call metrics and definitions are
included. This failed trace is **not** an end-to-end evidence-context PASS: no focused cards,
primary-literature search or Gate 2 was completed. Raw retention and a small peak do not replace
those requirements.

## 7. Full regression and test evidence

Final integration run `phase22c-full-006`: **753 passed, 11 skipped, zero failure/error**;
764 collected; pytest 1080.217 s. Repository/viewer asset checks, compileall, Ruff and mypy
(184 source files) all passed. Agent unit tests: **138 PASS**; prerequisite/projection recovery:
**17 PASS**; fixed-source Golden oracles: **6 PASS**; multi-turn/resume/ownership: **9 PASS**.
The 11 skips are eight optional PyMOL and three opt-in live tests; the separate real live run
above was executed and failed. No successful live coverage is inferred from a skipped test.

- DETERMINISTIC TEST: fixed actual-source sequences, coordinate presence and existing mapping;
  injected wrong chain/accession/offset/nonexistent-coordinate claims are rejected.
- MOCK / SYNTHETIC TEST: real DeepAgents graph with scripted model responses proves correction,
  legacy traversal, exact pagination, shared bounds, restart/follow-up and fail-closed boundaries.
- REAL MODEL LIVE TEST: 16 actual invocations, real P00698 acquisition and old Stage 01 job;
  both corrections succeeded; later Target output/scientific acceptance failed.
- REAL SCIENTIFIC BACKEND MICRO TEST: not reached; no generation/prediction was launched.

Development runs are retained: targeted001 exposed four new mock final replies missing the
required JSON envelope; that test fixture was corrected. Oracle003 had a missing remote fixture
after a failed rsync parent-directory creation; corrected copying, unchanged facts. Targeted002
then passed 22/22 and oracle005 passed 6/6 before final full006. No runtime/test/Skill changed
between full006 and live001. No additional wheel build was required or claimed for this patch.
The remote verifier completed with both make commands returning 0 and a passed report. Its SSH
transport retained an open descriptor afterward; only that completed transport was closed, not
the regression or any scientific job.

## 8. Scope, parity and remaining limitations

All **187 non-Agent source files** match the preceding reviewed commit. The original v2 checkout
remains clean at `c93da74660639c095d3de252cddb88a00fd3671d`. No new worktree, environment,
model setting, kernel/stage/backend/filter/recovery change, storage migration, Workbench or
production compute was introduced. `session_store` still owns Agent replay only; the old job
runtime owns the pending scientific job. The failure and evidence are retained, not resubmitted.

`V2_TO_V3_CAPABILITY_PARITY_MATRIX.md` records completed argument recovery but retains consequential
PARTIAL real-acceptance rows. Phase 2 is not eligible for `easydesign-v3-phase2-frozen`.
Future work requires an explicitly resumed task: make Target's final-output contract reliable,
address selected/acquired evidence across the verified canonical-binding transition without
weakening source scope, and repeat independent scientific acceptance of all five cases. These
are documented findings only; no such changes were started after this STOP.

## 9. Complete delivery and audit trail

The review package contains the **entire current repository and independent Git history**, all
tests/resources/docs, this report, the Golden spec, fixed-source oracle, complete failed live
workspace/checkpoints/source, decoded original output, full regression log/JUnit, exact recovery
trace, implementation/protected-file hashes, and prior Phase 2.2b/2.2/2.1 comparisons. Its patch is
only a navigation aid, never a substitute for the repository. Private credentials, local llm.yaml,
virtual environments, model weights and unrelated scientific projects are omitted.

`evidence/phase22c/` contains `real-tool-argument-recovery.json`,
`corpus-binding-diagnostic.json`, `live-metrics-summary.json`, `checkpoint-integrity.json`,
`protected-source-audit.json`, `pre-live-spec-freeze.json`, complete `live-goldens/` and
`validation/final-regression-summary.json`. The review commit is not a frozen scientific milestone.
