# Phase 2.2b recovery hardening — blocked acceptance, 2026-09-11

**FAIL / PHASE 2 NOT FROZEN. Phase 3 and Phase 4 have not started.**

The original source-selection crash is fixed and the real model successfully used its repair
path. Final Phase 2 acceptance is still blocked: the same soluble case later terminated on an
invalid scoped-result field path. The remaining real goldens were not run after that critical
failure. This is a complete repository review delivery, not a frozen migration milestone.

## Scope and error semantics

The implementation changes only Agent contracts, the existing corpus prerequisite check,
RoleBoundary and the existing execution event counter. It does not redesign evidence storage,
canonical identity, native strategy, scientific services, backends or compute recovery.

| Category | Runtime meaning | Handling |
| --- | --- | --- |
| RECOVERABLE_PREREQUISITE | The one implemented case, SOURCE_NOT_SELECTED | `SourceSelectionRequired`, distinct from `AgentBoundaryError`; a structured REQUIRES_ACTION ToolMessage |
| HARD_BOUNDARY_VIOLATION | Forbidden tools/files, invalid authority, cross-project access, integrity and budget failures | Existing `AgentBoundaryError` or integrity exceptions remain fatal; no blanket catch |
| SCIENTIFIC_UNRESOLVED | Search finds no evidence, unavailable sources, contradictions or uncertain interpretation | Existing SEARCHED_NO_EVIDENCE / UNRESOLVED / CONFLICTING_EVIDENCE data; no new exception framework |

An acquisition missing selection performs no network I/O or scientific mutation. Only the
Target/Site `research_evidence` callback may turn `SourceSelectionRequired` into a correction.
The response identifies the provider, exact source, evidence need, required `select_evidence`
action and remaining bounded opportunity. The model must decide whether the source is relevant
and supply a scientific selection reason. Runtime does not select it automatically.

The correction response uses tool status `error` with structured status `REQUIRES_ACTION`.
DeepAgents can continue the same execution with select → retry acquire. The runtime does not
replay the acquisition itself, manufacture a successful result or reset the model-call budget.

At most **two prerequisite corrections per persisted Agent execution** are allowed across
roles/delegations. A third raises a clear hard error. The allowance uses existing events in
SessionStore; no schema migration, scheduler, recovery DAG, workflow engine or new registry was
added. Restart/redelegation cannot renew it; a legitimate new execution can. Even replayed
prerequisite failures consume the allowance, which is deliberately conservative.

The audit also found that a forbidden tool was previously rejected with a soft error message.
It now raises `AgentBoundaryError` before its handler runs. File scope, source allowlist,
scientific approval and existing artifact/identity enforcement remain fail closed.

## Explicitly named human sources

**Decision: defer automatic `selected_by_user` inference.** The current input is an ordinary
research-goal/clarification string, not a trusted typed source-selection command. Interpreting
arbitrary mentions as human selection would require distinguishing directives from exclusions,
citations, examples and quoted source text. Allowing the LLM to mark its own selection as human
would misattribute authority. This narrow patch adds neither parser nor new CLI workflow.

An exact user-named source is still valid input to `select_evidence`, with the same validation
and allowlist, but its selection remains an Agent action. It is not human scientific approval.
The regression deliberately names PMC123 in the user goal and confirms that selection still
occurs explicitly after the correction. A future typed human source-selection entry point can
record human provenance without changing this rule; it is not implemented here.

## Real soluble attempt: original recovery succeeded, later field read failed

The configured model was DeepSeek `deepseek-flash`, with the unchanged baseline of 60,000 input
characters and 32 calls per execution. The real input was deposited 1MEL with the requested
UniProt P00698 canonical reference and auth chain L. The actual sequence was:

1. Coordinator delegated Target Intelligence.
2. Target requested UniProt acquisition before selection.
3. Runtime returned SOURCE_NOT_SELECTED / REQUIRES_ACTION, repair attempt 1.
4. Target explicitly selected P00698 and retried. The complete real response was retained.
5. Target proposed the canonical reference and invoked the existing Stage 01 preparation.
6. The old service produced a pending chain/identity decision. Target read that evidence.
7. Target passed sibling field names as one nested path to `read_evidence_result`:
   `field=["chains", "identity_evidence", "options", "limitations"]`.
8. The reader reached the `chains` list and tried to interpret `identity_evidence` as its numeric
   index. `Unknown scoped result field` escaped as `AgentBoundaryError`, ending the invocation.

The artifact is a valid dictionary and its `identity_evidence` field exists at the root.
The defect is the mismatch between the model's multiple-field request and the reader's nested
path semantics, followed by fatal handling of that navigation error. It is not a lost source,
credential failure, domain-policy violation or scientific negative result.

The old identity evidence reports P00698, taxonomy 9031, canonical length 147 and chains L/M as
129-residue exact subsequences with 18 deletions, zero substitutions and human review required.
These are verified **pending** comparisons. No Judge assessment or Agent Gate 1 card completed,
no human response was recorded, and no authoritative approved Canonical Target Bundle was
published. A configured canonical reference is not equivalent to completed identity approval.

The user's critical-failure stop was applied. No second live attempt, GPCR run, standard/native
Gate 3 acceptance or new recovery implementation followed this failure. The one existing
Stage 01 job remains `awaiting-human-approval`; no Stage 02+, generation or prediction started.

Evidence root on Suzhou2:
`runtime/tmp/phase22b-live-goldens-20260911T063724Z`.
The package retains the complete isolated workspace, sources, pending job, events, checkpoints,
failure traceback and exact failed tool call under `evidence/phase22b/`.

## Real evidence/context measurements

| Measurement | Observed |
| --- | ---: |
| Search queries / search results | 0 / 0; exact source was already requested |
| Selected / deferred / excluded sources | 1 / 0 / 0 |
| Full source responses acquired | 1 |
| Unique retained source characters / bytes | 384,043 / 384,043 |
| Corpus documents / chunks across recorded bindings | 1 / 3,062 |
| Corpus documents under the final current binding | 0 after canonical configuration revision; prior source remains durable |
| Focused retrieval calls / chunks returned | 0 / 0 |
| Focused Evidence Cards produced / delivered | 0 / 0 |
| Prerequisite repairs | 1, successfully followed by select/acquire |
| Real model calls | 11: Coordinator 2, Target 9 |
| Peak system/message input characters | 18,562 |
| Total specialist tool-result characters delivered | 11,120, including Skill text |
| Sum of specialist input characters across calls | 130,083, counting repeated history per call |
| Sum of specialist tool-message context characters across calls | 64,370, counting repeated history per call |
| Judge calls / Agent Gate 1–3 completions | 0 / none |

Per-call system/message counts, in order:
6,925; 7,285; 7,055; 13,775; 14,374; 14,732; 15,090; 15,342; 15,513; 15,640; 18,562.
Compact tool-schema characters are recorded separately. These are character counts, not provider
token billing. The new tool telemetry records post-adapter characters and focused cards actually
present in model-visible results. It does not log secret provider requests or copy full sources
into events. Repeated deliveries and per-call history sums are explicitly distinguished.

Compared with Phase 2.2's 13,348-character failure before acquisition, this attempt demonstrably
completed source selection, retention and corpus construction. It still did **not** complete
scoped retrieval → Evidence Cards → Site → Judge. Neither peak establishes end-to-end context
closure against Phase 2.1's over-60k failures. The evidence-consumption acceptance remains PARTIAL.

## Five required real acceptance cases

| Case | Result |
| --- | --- |
| Soluble protein through Gate 2 | FAIL: invalid scoped field path terminates Target before the Agent Gate 1 card |
| GPCR/membrane through Gate 2 | NOT RUN after critical stop |
| Canonical identity trap to approved authoritative state | PARTIAL: real reference acquired and deterministic mismatch exposed; approval not completed |
| Standard structured Binder Strategy through Gate 3 | NOT RUN after critical stop |
| Native expert YAML through Gate 3 | NOT RUN after critical stop |

No runtime fallback, fixture-only direct function call or previous successful case is counted
as a substitute for these missing real acceptances.

## Offline verification and source provenance

Final complete integration regression **004: PASS — 736 passed, 11 skipped, 0 failed/error**
from 747 collected tests, 877.37 s of pytest execution. All **121 Agent unit tests** passed,
including **6 new recovery tests**, **9 multi-turn/resume/ownership tests** and the 15 existing
Phase 2.2 context/identity/native tests. Existing Phase 1/2 and old scientific regressions ran
in the same complete suite. The skips are eight optional PyMOL tests and three opt-in live
Agent tests. The independently executed live acceptance is a FAIL, not covered by these skips.

Repository structure, vendored viewer assets, compileall, Ruff and mypy (184 source files)
passed. The final2 wheel passed byte equality for nine relevant modules and all four Skills,
plus isolated installed imports and tool-surface checks. No runtime/test source changed after
full 004 began; only closure documentation was updated with the result. Raw log, JUnit XML
and per-module summary are under `evidence/phase22b/validation/`.

- Targeted 001: 20 passed in 6.12 s, including the new actual DeepAgents repair loop and existing
  boundary/context tests.
- Targeted 002: 6 passed in 3.69 s after focused-card delivery telemetry was added.
- The new cases verify acquire-before-select repair, repeated-error exhaustion, persistence
  across graph/process reopening, legitimate new-execution renewal, stale-execution rejection,
  forbidden tool/file/domain failures, and nonfatal empty-search scientific conclusions.
- Full attempt 003 stopped in mypy **before pytest started**: telemetry passed ToolMessage's
  string-or-content-block union to `json.loads`. A string guard corrects that preflight issue.
  The final full run is 004; attempt 003 is retained and is not a full passing regression.
- Live 001 ran just before that final telemetry type guard. It failed on the unchanged scoped
  reader. An attempted interruption found that the process had already exited: the live run
  is recorded as an actual critical failure, **not a cancelled or successful acceptance**.
- The initial wheel preceded the final type guard. The final2 wheel is the final source build;
  both build records are retained with their distinct source provenance.

The final guard affects only telemetry inspection of string tool content. It does not implement
the missing scoped-field recovery or alter source/authority validation. No further scientific
implementation was undertaken after the critical stop.

## Remaining blocker and delivery boundary

The next bounded repair needs to distinguish an invalid field/index navigation **within an
already verified, role/execution-bound result** from unauthorized result access. It can return
available child-field/index hints and a clear single-path example, sharing the small execution
repair budget. It must not soften unknown/foreign result references, delegation mismatches,
path escapes, artifact tampering or scientific approval constraints. This is a recommendation
for a resumed task, not an implementation in this commit.

All five real goldens, scientific-content review, full regression and consequential parity rows
must pass before Phase 2 is frozen. This delivery contains the complete repository and independent
Git history, all tests/docs/resources, current failure evidence and prior comparison evidence.
Private credentials, local model configuration, environments, weights and unrelated projects
are excluded; configuration templates remain complete.

No old tag moved, no new Phase 2 frozen tag exists, and Phase 3/4, production compute, storage
migration, Workbench and Figure 2 remain unstarted.
