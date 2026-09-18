# NK2R Figure 2 execution ledger

This ledger records operator-visible execution defects and repairs for the fresh NK2R benchmark. Failed or repaired runs are retained for audit and excluded from clean performance measurements.

## F2-SETUP-001 — R1 runtime profile absent

- Project: `figure2-nk2r-full-r1`
- Thread: `thread-figure2-nk2r-full-r1`
- Execution: `turn-4679b7a1b3954983b2ee3c20702121cb`
- Failure boundary: Gate 1 target preparation, before a decision card existed.
- Before: the new benchmark worktree had a self-contained Python environment, but no clone-relative `runtime/profile.yaml`. `prepare_target` submitted `job-6c94d563b2574412`; the worker raised `ConfigurationError`, while the job record remained `queued`. The Target Agent had already made 10 model calls and emitted no valid Gate 1 card.
- Root cause: worktree creation and Python dependency setup did not provision the non-versioned runtime profile and component receipts required by the local worker.
- Repair: created a clone-relative runtime profile; rebound all worktree paths; hard-linked immutable model/environment payloads from the authoritative backend; copied and rebound small component receipts; verified the BoltzGen, BoltzGen validation, and OpenFold3/AF3-JAX backends load from the new profile.
- After: runtime profile loading and backend discovery pass in the benchmark worktree.
- Measurement disposition: R1 is a setup smoke/failure record only. It is excluded from Figure 2 effectiveness and efficiency measurements because repair occurred after model calls had begun. A clean R2 starts from the raw target after the fix.
- Scientific-state disposition: no Gate 1 decision was approved and no R1 scientific output is imported into R2 or any control.

## F2-HARNESS-001 — R2 Target evidence replay exceeded the hard context guard

- Project: `figure2-nk2r-full-r2`
- Thread: `thread-figure2-nk2r-full-r2`
- Execution: `turn-2673cd71a8fc49e19ee19eb8027c3ef7`
- Failure boundary: Gate 1 Target interpretation, after successful target preparation and before a decision card existed.
- Before: `read_target_evidence` exposed only a 3,823-character partial view of a 12,718-character losslessly compactable Gate 1 decision packet. The model then issued 95 scoped `read_evidence_result` calls, largely paging the same immutable target result. At model call 28, tool messages occupied about 63k characters and the next request reached 102,859 characters, exceeding the 100k hard guard.
- Root cause: the prior capacity patch correctly stopped provider total tokens from causing false summaries, but Target specialists had no actual-input working-memory middleware. In addition, the output adapter treated a naturally bounded Target gate as a generic large artifact and withheld its complete decision view, inducing exhaustive field paging.
- Repair: deliver a complete losslessly range-encoded Target gate decision view when it is at most 24k characters; mark that declared scientific scope complete; preserve the immutable full result for provenance and optional focused reads. Add actual-input working-memory compaction to Target as a safety boundary, using the active Target model configuration and compact non-reasoning summary budget.
- Verification before rerun: focused unit tests pass, including preservation of all chain alternatives, exact reconstruction of compressed missing-position ranges, bounded generic large-artifact behavior, role-specific summary budgets, and framework summary accounting.
- Measurement disposition: R2 is a Harness failure case and is excluded from successful-run effectiveness/efficiency estimates. Its failure and recovery count remain eligible for the robustness analysis under the prespecified protocol. A clean R3 starts from the raw target after this patch.
- Scientific-state disposition: no Gate 1 card was emitted or approved; no R2 scientific result is imported into R3 or controls.

## F2-HARNESS-002 — R3 Site Skills were reloaded after working-memory compaction

- Project: `figure2-nk2r-full-r3`
- Thread: `thread-figure2-nk2r-full-r3`
- Gate 2 execution: `turn-721f7db3e76346198c0ebb4b55df1e1a`
- Failure boundary: Gate 2 efficiency acceptance after a scientifically valid ranked Site card was created.
- Before: Gate 1 completed and chain R was approved. Gate 2 produced selectable A/B/C candidates, including the requested deeper outer-pore option B, with no hard context-guard event. However, each working-memory compaction removed the old `read_file` messages from the active model history. Because completed immutable Skill reads were not represented in durable execution state, the Site specialist reread the same four Site Skill files after compaction. The accepted trace contained 25 model calls, 40 tool calls, a 77,441-character maximum request, four summaries and 4,096 summary-output tokens.
- Root cause: Skill-loading completion was inferred only from transient message history. Scientific evidence and approvals were durable, while the process fact “this role already loaded this immutable Skill in this execution” was not.
- Repair: persist a role- and execution-scoped `skill-read` receipt after each successful authorized Skill read. Later model calls expose only unread Skill paths; after all required files are loaded, `read_file` is removed and the runtime states that the immutable Skills were already loaded. Target preparation also recognizes the durable receipt. No Skill content, scientific evidence, recommendation or Gate authority is cached or changed.
- Verification before rerun: focused tests prove the four Site Skill receipts survive an empty/summarized message history, prevent re-exposure of `read_file`, and preserve the existing Target tool-admission behavior.
- Measurement disposition: R3 is retained as a scientifically successful but efficiency-nonconforming Harness run. It is excluded from the prespecified set of accepted clean Harness replicates because summaries exceeded the `max_summaries=2` and `max_summary_output_tokens=2048` thresholds. Its trace remains available for robustness and repair analysis. A clean R4 starts from the raw target after this patch.
- Scientific-state disposition: the R3 Gate 2 card is an audit artifact only. No R3 Site answer, ranking, evidence selection or generated prose is imported into R4 or either control.

## F2-HARNESS-003 — R4 Site reads were not bounded by the shared execution budget

- Project: `figure2-nk2r-full-r4`
- Thread: `thread-098bcb6ab0b04d44a144799a67379fd4`
- Gate 2 execution: `turn-0cfbc370b3b34bb58db684d5ff0371bf`
- Failure boundary: Gate 2 Site research before a typed handoff was submitted.
- Before: durable `skill-read` receipts worked: the four Site Skill files were loaded once and never reloaded after compaction. The model nevertheless continued focused evidence paging because only new source-query reservations, rather than all Site model/read turns, could close the research phase. At operator stop the execution had 27 Site model calls, 58 tool calls, 24 stored tool views, six summaries, three new research reservations and a maximum request near 96k characters. No hard context guard fired and no Site handoff or proposal was accepted.
- Root cause: the 12-query acquisition ceiling did not bound an execution dominated by retrieval, mapping and evidence-result reads. The shared 64-call execution limit left too much room for one Site research role and the advisory “leave capacity” prompt did not create a deterministic phase transition.
- Repair: add a role/stage-owned ceiling of 12 Site research model calls. When either the source-query ceiling or this call ceiling is reached, Runtime removes every reading/action tool and requires only the typed `SiteResearchHandoff`; remaining questions must be represented as unresolved. The downstream dossier, synthesis, Judge and hard validators remain unchanged and can reject insufficient science. The ceiling applies equally to the full Harness and autonomous Generic Agent control.
- Verification before rerun: focused tests prove the Site research call ceiling forces a typed handoff before the global execution limit, records `model-call-budget` as the transition reason, retains the pre-existing query ceiling, and preserves durable Skill receipts.
- Measurement disposition: R4 is a deliberate EasyDesign development/repair run under the investigator-authorized policy. It is excluded from formal Figure 2A measurements. The next EasyDesign result must be a fresh project from raw input; this checkpoint will not be resumed.
- Scientific-state disposition: R4 stopped before SiteResearchHandoff, SiteDecision or Gate 2. No R4 scientific output is imported into a fresh run or either control.

## F2-CONTROL-001 — Control runner reused the Gate 1 thread scope

- Project: `figure2-nk2r-source-r2`
- Requested measurement thread: `thread-be3ccf84de9f42a5855f600fc269d865`
- Failure boundary: Generic Agent runner initialization, before `begin_execution` and before any model or scientific tool call.
- Before: the source thread had correctly been frozen with scientific scope `target`. The control runner attempted to reopen that same thread as scope `site`, and Runtime rejected it with `Thread scientific scope is immutable; create a new thread to extend it`. The runner would also have reached a second scope mismatch when moving from its initial `site` bridge to the Gate 3 `design` bridge.
- Root cause: the runner confused a project-level approved Target snapshot with the conversation thread that originally created it. Target authority is project-level, while pending Site/Design state and scientific scope are thread-local.
- Repair: create a new method/replicate-specific thread with a control-specific immutable fingerprint, initialize its scope as `design` from the start, and reuse only the project-level approved Target state. Site and Design remain isolated in that new thread.
- Verification before rerun: static checks, a direct initialization smoke against the approved Target snapshot, and the benchmark control regressions must pass before starting a new thread.
- Measurement disposition: no formal Generic Agent run started. The failed command made zero model calls and emitted no Site or Design proposal, so it is an infrastructure preflight failure rather than a first-pass scientific result. The replacement run uses a new thread and a new code commit.
- Scientific-state disposition: no control scientific state was created and nothing is imported into the replacement thread.
