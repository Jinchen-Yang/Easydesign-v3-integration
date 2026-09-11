# Phase 2.2d — Agent Contract Hardening review, 2026-09-12

**FAIL / NOT FROZEN. Critical live acceptance stopped. Phase 3 and Phase 4 have not started.**

This is a closure/blocker report, not a successful Phase 2 freeze. Implementation began from
`4df3b2bd19f72a39f67ad40c3874b30323f0aafb`, on the existing v3 migration branch/worktree.
The original v2 checkout remains preserved. The pre-frozen five-case specification and factual
oracle were not changed. No new implementation or live retry followed the critical failure.

## 1. Result and exact blocker

Real `deepseek-flash` acceptance001 ran for 52.614 seconds. The persistent event ledger records
**32 model calls: Coordinator 2, Target 30, all within one execution**. Target made 32
`get_job_status` tool calls, including parallel duplicate calls, receiving `no-bound-job` each
time. It read its Skill once and `read_target_evidence` once. That response explicitly said the
target was not prepared and named the next action. The Target did not select/acquire a source,
propose canonical identity, prepare the target, or submit a typed assessment.

The next model invocation failed at the unchanged per-execution safety limit:
`Current turn model-call budget exhausted; worker remains detached`.
There was no actual scientific worker/job in this run. The error's generic worker wording does
not establish that one existed. The 32-call budget worked; increasing it is not a demonstrated fix.

The observed blocker is a **no-progress tool-call loop before scientific work**. The trace does
not isolate whether the model, tool/prompt interaction or structured-output integration caused
that behavior. No post-failure A/B experiment, prompt repair, provider switch or implementation
retry was performed. The failure is not a launcher/configuration error and was not cancelled.

The top-level streamed progress contained only two Coordinator calls while the delegated graph
failed. A preliminary progress update misread that partial stream; it was promptly corrected
using all persistent events and the decoded Target checkpoint (65 messages, including 30
distinct model reply IDs). Those replies report model name `deepseek-flash`. The full evidence
package retains both traces, rather than replacing the original partial trace.

### Second blocker: focused cards not delivered in full regression

The full-suite source-recovery fixture exposed an integration failure. Source selection repair
and acquisition succeeded; focused retrieval produced two cards. With the new binding metadata,
the exact projected page is 6,091 characters, over the existing 6,000-character tool-view limit.
The adapter therefore retained the full page but returned a narrower-field instruction: zero
cards reached the scripted specialist. The existing end-to-end card-delivery assertion fails.

This is not loss of the original source/corpus or failure of source selection. It is an unresolved
page-sizing/delivery interaction with new binding context. No threshold increase, fixture
weakening, runtime patch or retry was made after STOP. The complete failed offline fixture,
original 6,091-character page and post-adapter telemetry are exported for review.

## 2. Consequential contracts and ownership

See `V3_AGENT_CONTRACT_OWNERSHIP.md` for the complete ownership table and mechanism audit.

| Boundary | Model submission | Trusted authority |
| --- | --- | --- |
| Target / Gate 1 | `TargetInterpretation` | Kernel/source facts, exact refs, source binding, options and assessment envelope |
| Site / Gate 2 | Existing `SiteIntent` | Approved Target, residue/coordinate/topology facts, validators and old site service |
| Binder / Gate 3 | Existing `BinderIntent` | Approved hotspot, scaffold/backend constraints, compiler, native bytes and old strategy service |
| Independent Judge | `JudgeVerdict` | Exact delegated snapshot, request/source role, canonical refs and assessment identity |

Scientists retain consequential Gate decisions. No model-authored approval is accepted.
Runtime facts and model interpretation are distinct fields; Judge critique does not regenerate
facts or replace scientific authority.

## 3. Structured output and bounded recovery

Installed DeepAgents 0.7.13 / LangChain 1.4.0 / LangGraph 1.2.11 / langchain-openai 1.6.1 were
inspected. The existing provider-compatible function calling path uses LangChain's native
`ToolStrategy(PydanticSchema, handle_errors=...)`. Target and Phase 1 Judge no longer parse an
entire free-text response as JSON. Existing typed Site/Binder/Phase 2 Judge paths are retained.

Only a validated framework `structured_response` reaches the callback. Pure JSON prose,
fenced JSON and incidental explanatory text are not a substitute. A final submission mixed
with action tools is rejected before executing those actions. Schema errors, malformed typed
tool JSON and missing final submissions receive exact bounded corrections. Two output-contract
corrections are persisted per execution across roles; restart/redelegation cannot reset them.
The separate existing source/projection correction budget remains two per execution.

Every attempt consumes the original model-call/context budget. Unauthorized tools, stale
delegation and integrity violations remain fatal. No generic contract framework was introduced.
The real failed run never reached final submission, so native submission and its recovery are
**offline validated, live NOT EXERCISED in this acceptance**.

## 4. Hard facts and scientific consistency

Canonical accession/length, chain-specific construct/observed lengths, mappings, missing
positions and options are projected from verified existing runtime objects. The model cannot
supply facts, refs or eligible options in `TargetInterpretation`. The Agent inventory's former
`canonical_residue_count` field, which actually represented observed amino acids, is now named
`observed_amino_acid_count`; the scientific inventory implementation itself is unchanged.

Explicit incorrect known Target count statements produce `HARD_FACT_CONTRADICTION`, retain
the rejected content as a scientific finding, and cannot create a consequential proposal.
Target, Site, Binder and approving Judge callbacks check these claims after delegation checks.
A rejecting Judge may quote a bad claim in its critique. A changed Target interpretation changes
the Judge snapshot binding; an old Judge cannot approve its replacement.

This is deliberately a narrow check for explicit known numerical claims, not a universal
natural-language fact verifier. All other scientific claims still require evidence, independent
Judge review and Golden content acceptance. The live run produced no authoritative assessment;
absence of wrong committed facts in that empty run is not scientific acceptance.

## 5. Stable evidence and canonical revision

Existing project ArtifactRefs/corpus retain verified full sources independently of the current
target binding. Runtime adds stable source/project evidence identity and explicit acquisition
versus current relevance context. Discovery leads and verified acquisitions remain distinct.

Only an exact verified canonical-reference-proposal can carry its chosen UniProt source and
selection across that precise old/new binding. Unrelated historical sources do not automatically
support the current target. A separate thread/need must select its source before focused reuse.
Source bytes/corpus can then be reused without another download. Stale view cursors, tampered
refs and cross-project access remain rejected. Zero selected documents is distinguished from
absence of project sources. No second evidence store, graph or schema migration is added.

Offline tests acquire P00698, retrieve cards, revise canonical configuration, retrieve the same
verified source again, reject unrelated/stale/cross-project access and verify no redownload.
The real runner required actual before/after cards with the same project evidence identity.
That checkpoint was **NOT REACHED**; real binding stability remains unaccepted.

## 6. Ordinary presentation

Finished replies attach runtime Target facts and separately bound interpretation. Ordinary
Coordinator sentences restating identity/count/chain facts are omitted to avoid a second
untrusted factual rendering. Original Coordinator prose remains in the audit event. This is
a small output adaptation, not Workbench or a new scientific state layer.

## 7. Five fixed Golden cases

| Case | Result | Hard facts / scientific content review |
| --- | --- | --- |
| 1 Soluble → Gate 2 | NOT RUN TO REQUIRED BOUNDARY | Shared initial Target path failed; no sources, Site proposal or Judge |
| 2 GPCR → Gate 2 | NOT RUN AFTER CRITICAL STOP | No GPCR project/Agent acceptance was launched |
| 3 Identity trap → approved Target | FAIL | No canonical proposal, Gate 1 or approved authoritative bundle |
| 4 Standard Binder → Gate 3 | NOT RUN AFTER CRITICAL STOP | No approved upstream science or compiler/Gate 3 acceptance |
| 5 Native expert YAML → Gate 3 | NOT RUN AFTER CRITICAL STOP | No native live acceptance was launched |

For the failed shared Target prefix: **Hard Facts:** fixed structure input verified, no new
authoritative facts produced. **Scientific Interpretation:** no submitted interpretation.
**Evidence:** no research acquisition, corpus or passages. **Uncertainty:** no scientific
opinion available to review. **Alternatives:** none proposed. **Decision:** FAIL; incomplete
required scientific path. Every other case retains NOT RUN, not a synthetic or inferred PASS.

There were no Gate cards, Judge assessments, scripted approvals, scientific jobs, generation or
prediction. Offline fixtures and advance reviewer reading are not real scientific acceptance.

## 8. Context metrics from the actual failed run

| Metric | Value |
| --- | ---: |
| Model calls, Coordinator / Target / Site / Binder / Judge | 2 / 30 / 0 / 0 / 0 |
| Search / selected / acquired sources | 0 / 0 / 0 |
| Raw source characters acquired / corpus docs / chunks | 0 / 0 / 0 |
| Focused retrievals / Evidence Cards delivered | 0 / 0 |
| Specialist tool-result characters supplied | 9,231 |
| Sum of specialist context characters over calls | 423,006 |
| Peak system + message context characters | 15,011 |
| Peak estimated context including tool schemas | 23,925 |
| Source/projection/output corrections | 0 / 0 / 0 |
| Scientific jobs / Gate responses | 0 / 0 |

Character measurements are not provider token billing. Repeated context is counted per call.
Limits remained 60,000 guarded input characters and 32 calls per execution. A short failed
trace with no retrieved source is **not end-to-end evidence compaction PASS**.

## 9. Regression and scope verification

Final integration007: **774 passed, 1 failed, 11 skipped**;786 collected,1152.498 s in JUnit.
Agent unit159PASS/1FAIL; new Phase 2.2d contract/binding22PASS; fixed Golden oracles6PASS;
multi-turn/resume/ownership9PASS; source/projection recovery16PASS/1FAIL. Repository structure,
vendored assets, compileall, Ruff and mypy185 source files PASS. The failure is
`test_harness_repairs_selection_then_acquires_and_reads_durable_source` at line 185: no post-adapter
`focused_cards_in_model_result > 0`. Eleven skips are3 opt-in live integration tests and8 PyMOL
integration tests lacking the separate environment. The separate real Golden attempt failed;
a skipped live test does not count as a live PASS.

Development evidence: initial focused002 35 PASS; broader Agent004 158 PASS and one explicit
live skip on the earlier implementation; final focused006 27 PASS on the final runtime;
final Agent mypy005 20 files PASS. Four intermediate static typing errors were corrected before
the final lock. The initial Ruff-before-format check was a development style check, not a final
full-suite result. Logs preserve these distinctions.

All 854 repository files matched local/Suzhou2 at the pre-final lock. Runtime, tests and Skills
remained identical for final full007 and live001; only result documentation is updated afterward.
All 187 non-Agent source files match baseline4df3b2b. In particular scientific kernel,
Stage 02–07, backends, filtering and old compute recovery are unchanged. Original v2 is preserved.

Frozen spec SHA-256: `96ead11b3f071dce05780dd1f6fba6ee353d2346aa5a53438ac4ef0e8a850a49`.
Frozen oracle SHA-256: `2e367355d197d541df7f77b87f6b505659a81997dc79db7a97a0b0e0ff3258c9`.

## 10. Parity, limitations and disposition

Consequential Phase 2 rows remain PARTIAL where real acceptance is incomplete. Offline tests
cannot upgrade them to COMPLETE. No `easydesign-v3-phase2-frozen` tag was created. Phase 3/4,
storage migration, Workbench, Figure 2 and production-scale compute have not started.

The remaining investigation is the real no-progress Target loop, including how valid read-only
tool repetition should be diagnosed within the existing execution budget. This report does not
authorize or implement another recovery mechanism, scheduler or retry. Separately, all new
typed/hard-fact/binding changes still need a successful real scientific path. The live failure
does not prove those unexercised paths correct or incorrect.

The complete review ZIP contains the entire current repository and independent Git history,
this report and ownership matrix, frozen oracles, final regression logs/XML, actual failed
workspace/SQLite checkpoints, decoded messages, source input and metrics, plus prior review
evidence. Credentials, private local model config, environments, weights and unrelated projects
are omitted. Package completeness, source hashes, ZIP entries and Git objects are verified.
Further implementation/live validation requires a newly resumed user task.
