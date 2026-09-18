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

## F2-CONTROL-002 — Skill-free control expected a Skill loader

- Project: `figure2-nk2r-source-r2`
- Thread: `thread-figure2-nk2r-generic-r1`
- Failure boundary: Generic Agent Site middleware admission, before the provider/model call.
- Before: the Generic control correctly supplied only scientific tools and no domain Skill loader. `RoleBoundary`, however, inherited the production Site allowlist containing `read_file` and required the actual tool surface to equal that set. Runtime therefore rejected the correctly reduced control surface as unexpected.
- Root cause: `domain_skills=False` disabled Skill paths and prompts but did not remove `read_file` from the authoritative allowed-tool set. The same latent mismatch existed for the skill-free Binder control.
- Repair: copy the role allowlist into an instance-owned set and remove `read_file` whenever `domain_skills=False`, for both Site and Binder roles. No scientific tool, validator or model prompt is added.
- Verification before rerun: explicit Site and Binder control tests assert the skill-free allowlist excludes `read_file`; benchmark control regressions, static checks and type checks pass.
- Measurement disposition: no provider call occurred (`model-call=0`); the thread contains only setup/execution metadata and no scientific proposal. It is excluded as infrastructure preflight. A new code commit and fresh thread are required.
- Scientific-state disposition: no Site/Design output exists and nothing is reused.

## F2-HARNESS-004 — R5 GPCR context acquisition was separated from required receptor analysis

- Project: `figure2-nk2r-full-r5`
- Thread: `thread-figure2-nk2r-full-r5`
- Gate 2 execution: `turn-a020dbce99ab4f4198c4c3eff3f031ec`
- Failure boundary: Gate 2 candidate formation, before Scientist approval.
- Before: Gate 1 completed and chain R was approved. Site research successfully resolved the authoritative GPCRdb context to `nk2r_human` / P21452, but this acquisition occurred at the final bounded research turn. Working-memory compaction and the deterministic Site research ceiling then forced `SiteResearchHandoff` before `analyze_receptor_context` ran. The synthesis therefore received the generic surface scan but not the existing GPCR topology, signed membrane-frame, chain-graph and mapped candidate kernel. It emitted one extracellular A candidate and two cytoplasmic candidates; the requested deeper outer-pore B was absent. Runtime preserved exact residue facts and did not silently approve the unsuitable sites.
- Root cause: a successful GPCRdb source acquisition and the required deterministic receptor analysis were two independently scheduled model actions. The research budget could close in the gap between them, even though the second action contains no new scientific judgment.
- Repair: for Site research, a successful complete GPCRdb context acquisition now atomically invokes the existing deterministic receptor analysis with the Scientist-approved original auth chain. The resulting kernel card and full analysis artifact are persisted in the same evidence snapshot. Replays reuse an exactly source-bound existing analysis. Site still ranks the candidates, Judge still reviews the reasoning, and Scientist still owns Gate 2 approval.
- Verification before rerun: a focused regression proves that a Site `gpcrdb-context` acquisition automatically derives the receptor-analysis card with the approved auth chain and labels the result as deterministic evidence rather than approval. A no-model replay on an isolated copy of the real R5 project generated the deterministic 9W2H receptor card and recovered both the outer-vestibule primary hypothesis and the transmembrane/outer-pore backup hypothesis. Existing GPCR mapping, Site dossier, Harness and benchmark-control tests pass before the fresh run.
- Measurement disposition: R5 is a deliberate EasyDesign development/human-repair run and is excluded from formal Figure 2A effectiveness and efficiency measurements. The repair is counted as one human repair. R6 must start from the raw 9W2H input with a fresh project, thread and execution; no R5 prompt history, evidence selection, candidates or prose may be imported.
- Scientific-state disposition: the R5 Gate 2 card is an audit artifact only and remains unapproved. No R5 Site answer is reused by R6 or either frozen control.

## F2-HARNESS-005 — R6 required the model to guess a GPCRdb-specific receptor slug

- Project: `figure2-nk2r-full-r6`
- Thread: `thread-figure2-nk2r-full-r6`
- Gate 2 execution: `turn-dc8d087a069544ef88c89ba769e8f044`
- Failure boundary: GPCR context acquisition before deterministic receptor analysis.
- Before: fresh Gate 1 completed and chain R was approved. Site research then tried the biologically reasonable identifiers `TACR2_HUMAN` and `tacr2_human`; GPCRdb returned 404 because its receptor entry is `nk2r_human`. Runtime already held the approved canonical accession P21452, but the research contract required an exact database-specific entry and did not use that authoritative identifier to resolve the record. The Site research budget ended without a GPCR kernel card.
- Root cause: a database routing key was treated as model knowledge even though the approved target bundle already contained a stable cross-database accession and the GPCRdb adapter supports accession lookup with identity verification.
- Repair: on a GPCRdb entry 404 during Site research, Runtime retries once through the Scientist-approved canonical accession. The adapter must resolve exactly one record and independently verify its accession; the requested alias, resolved entry and resolution method are all retained. Non-404 source/network errors do not use this fallback.
- Verification before rerun: 115 related GPCR, Site, Harness, recovery and model-transport tests pass. A no-model replay on an isolated R6 copy resolved the exact failed request `TACR2_HUMAN` through P21452 to `nk2r_human`, atomically produced the receptor-analysis artifact, and recovered the outer-vestibule, transmembrane/outer-pore and intracellular-avoid candidate families with mapped design labels.
- Measurement disposition: this is one Codex-operated development/human-repair action. R6 remains excluded and no resolved entry or candidate is injected into a later run.

## F2-HARNESS-006 — R6 Site handoff spent every retry on hidden reasoning

- Project: `figure2-nk2r-full-r6`
- Thread: `thread-figure2-nk2r-full-r6`
- Gate 2 execution: `turn-dc8d087a069544ef88c89ba769e8f044`
- Failure boundary: required `SiteResearchHandoff` submission after the deterministic Site reading ceiling.
- Before: three consecutive finalization calls each consumed the full 16,384-token output allowance. The first and third returned no typed submission; the second reached `SiteResearchHandoff` only with an empty argument object. Each call retained about 77-82k input characters and thinking remained enabled. Two contract repairs were exhausted, so the run failed before dossier synthesis or a Gate 2 card.
- Root cause: max-token recovery was implemented for Judge but not for the equally structured Site research handoff. Repeating the same reasoning-enabled request could reproduce the same failure without reserving output capacity for the typed payload.
- Repair: after a Site research finalization stops for `max_tokens` or `length`, subsequent bounded corrections use a transient non-thinking copy of the same configured model and output allowance, expose only `SiteResearchHandoff`, and instruct the model to place required fields in the tool arguments before prose. The original model client/settings and all scientific validators remain unchanged.
- Verification before rerun: an SDK-level regression reproduces a first-call `max_tokens` response, verifies that the second request disables thinking while preserving the same model and 8,192-token output allowance, exposes only `SiteResearchHandoff`, and accepts a complete typed recovery. The broader related suite passes.
- Measurement disposition: this is a second Codex-operated development/human-repair action. R6 produced no Site handoff, SiteDecision or Gate 2 card and is excluded. R7 must start from raw 9W2H with no R6 evidence, prompt history or prose.

## F2-HARNESS-007 — R7 bounded Site finalization did not enforce the typed citation contract

- Project: `figure2-nk2r-full-r7`
- Thread: `thread-figure2-nk2r-full-r7`
- Gate 2 execution: `turn-0e1c890564ac4328975925023ca761e3`
- Failure boundary: typed `SiteResearchHandoff` finalization after the 12-call deterministic Site reading ceiling.
- Before: fresh Gate 1 completed and chain R was approved without code repair. Site independently resolved P21452 to `nk2r_human`, acquired the remote GPCRdb/RCSB evidence and produced the deterministic receptor analysis. When the reading ceiling closed, the first finalization still used the reasoning-enabled provider model; because the Anthropic-compatible transport cannot force a tool while thinking is enabled, it attempted the unavailable `read_file` tool. The first correction produced a scientifically coherent three-candidate handoff, including outer-vestibule and deeper outer-pore candidates, but copied internal kernel `evidence-*` claim handles into `evidence_card_ids`. Runtime correctly rejected those values because only `receptor-*` and focused `passage-*` cards are citable. The final correction again attempted `read_file`, exhausting the two contract repairs before SiteDecision or Gate 2.
- Root cause: the non-thinking typed-submission path activated only after a `max_tokens`/`length` response, not when the deterministic reading ceiling itself forced finalization. In the receptor candidate view, internal kernel claim handles and the enclosing citable receptor card were also presented with names similar enough for the model to confuse their contract roles.
- Repair: every bounded Site handoff finalization now uses a transient non-thinking copy of the same configured model from its first submission call, exposing only `SiteResearchHandoff` and retaining the unchanged output allowance and all validators. The Site receptor view now labels internal values as `kernel_claim_ids`, supplies the exact `receptor-*` value as `citable_evidence_card_ids`, and states the citation rule in both runtime output and the Site Skill. Runtime citation validation remains strict.
- Verification before rerun: provider-transport regressions must prove both first-call bounded finalization and post-truncation recovery disable thinking, expose only `SiteResearchHandoff`, preserve the model/output allowance and leave the original model unchanged. Receptor-view regressions must prove internal claim IDs remain visible but cannot be mistaken for citable card IDs. The related Site/GCPR/Harness suite and repository checks must pass before R8.
- Measurement disposition: R7 is excluded from clean Figure 2A effectiveness and efficiency measurements. This patch is one Codex-operated human-repair episode with two local implementation corrections at the same finalization boundary. R8 must start from raw 9W2H with a new project, thread and execution; no R7 evidence, candidate ranking or prose may be imported.
- Scientific-state disposition: R7 produced no accepted SiteResearchHandoff, SiteDecision or Gate 2 card. Its model-authored candidate draft remains an audit artifact only.
