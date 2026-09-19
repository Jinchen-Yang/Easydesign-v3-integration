# NK2R Site latency repair ledger — 2026-09-19

## Scope

This ledger records fresh human-NK2R Gate 2 attempts used to validate the Site
latency hardening branch. Every accepted attempt must start from Gate 1 in a new
project and thread. Earlier NK2R dossiers, candidate residues, rankings and
decisions are not supplied to the scientific Agent.

- Repository: `/data/easydesign-worktrees/figure2-ab-20260918`
- Branch: `codex/site-intelligence-latency-20260919`
- R5–R10 baseline: `8efc930c218c96d5ea1eb31a36975c8dc891cd00`
- Initial latency commit: `58a389d01a8d1665cd7a2484183f141e739cfb65`
- Provider/profile: `deepseek / deepseek-v4-pro`
- Target: fresh RCSB 9W2H mmCIF, SHA-256
  `33ff56e619b30fbb1edeba2d58726aaf78006ad1b2480416b97bb4892e488e51`

## R10 read-only equivalence replay

The saved R10 authoritative dossier was opened read-only. The compact v2 decision
working set preserved all three candidate IDs, every exact hotspot design label,
and all three research findings.

- Full immutable dossier: 98,999 compact characters.
- Decision working set: 26,420 compact characters.
- Reduction: 73.3%.
- Source project mutation: none.

## Attempt R11 — invalidated

- Project: `figure2-nk2r-site-fast-r11`
- Thread: `thread-335f7e94d6ae45c1b1b4e0d391866302`
- Start commit: `58a389d01a8d1665cd7a2484183f141e739cfb65`
- Gate 1: independently resolved human NK2R P21452 and auth chain R / label chain B.
- Gate 1 wall time: 147.55 seconds.
- Status: stopped during Gate 2 Site synthesis; retained as defect evidence.
- Manual scientific answer injection: none. Gate 1 chain R approval used the
  standing Scientist authorization.

### SITE-LATENCY-001 — synthesis did not enter compact structured submission

Trigger:

- Site synthesis received a 32,700-character input including its schema.
- The first response ran for 167.82 seconds, consumed 16,384 output tokens, and
  returned no `RankedSiteDecision` tool call.
- The second identical repair call was stopped once the generic cause was proven.

Before:

- Compact/non-thinking submission was enabled for Site Research finalization and
  Judge truncation recovery.
- Normal Site synthesis was marked submission-only but retained the role's high
  reasoning model.
- The Anthropic-compatible SDK dropped forced tool choice when thinking remained
  enabled.

Root cause:

- `compact_site_submission` omitted `site_stage == synthesis`.

Repair:

- Every Site synthesis call now uses the same model/provider with thinking
  disabled from its first call.
- The only offered output remains `RankedSiteDecision`; all existing hydration,
  citation, hard-fact and contract validation remains unchanged.

After:

- Wire-level tests verify high-reasoning DeepSeek configuration is converted to
  `thinking=disabled`, removes `output_config`, and retains forced structured
  tool choice for Site synthesis.

### SITE-LATENCY-002 — atomic GPCR kernel existed but was not deliverable

Trigger:

- GPCRdb acquisition correctly produced one
  `research-receptor-analysis` artifact.
- The Harness then hid `analyze_receptor_context` merely because that artifact
  existed.
- The Agent received only an `analysis_ref`, could not read the compact kernel,
  paged raw GPCRdb source content, and reached the Research call boundary without
  usable topology/candidate context.

Before:

- Atomic kernel computation avoided one duplicate analysis but also removed the
  model-facing compact read.

Root cause:

- Kernel computation and kernel delivery were treated as the same operation.

Repair:

- GPCRdb acquisition still computes the deterministic kernel once.
- The Harness offers one scoped `analyze_receptor_context` call after acquisition.
- `EvidenceResearch.analyze_receptor` verifies current Target binding and auth
  chain, then reuses the stored analysis without calling `analyze_structure`.
- After the successful compact delivery, the Harness removes the tool for the
  remainder of the execution.

After:

- Regression tests prove the second model-facing call returns the identical
  artifact/card and the structure analysis call count remains one.
- The Site model receives the compact topology, membrane, chain graph, candidate
  and approved design-mapping projection.

## Validation

- Initial latency patch affected suite: 144 passed.
- R11 repair focused suite: 107 passed.
- Ruff: passed.
- Mypy before R11 repair: 213 source files passed.
- R11 is invalidated because product code changed after it started.
- The next accepted validation must use a new project and thread from Gate 1.


## Attempt R12 — invalidated

- Project: `figure2-nk2r-site-fast-r12`
- Thread: `thread-ded53e34f2a3408da1483bf70b568128`
- Start commit: `ec7374b996c68826e435b16abc1909bdf7f159ae`
- Gate 1: independently resolved human NK2R P21452 and auth chain R / label chain B.
- Gate 1 wall time: 130.98 seconds.
- Status: stopped during Gate 2 Site research; retained as budget-tuning evidence.
- Manual scientific answer injection: none. Gate 1 chain R approval used the standing
  Scientist authorization.

### SITE-LATENCY-003 — Site evidence budget converged before discovered sources could be read

Trigger:

- The first Site call selected and acquired GPCRdb in 6.21 seconds.
- The second call received the compact deterministic receptor kernel in 3.76 seconds,
  reusing the acquisition-time analysis rather than recomputing it.
- The third call launched three parallel targeted literature searches in 27.80 seconds.
- Those four reservations exhausted the Site-specific limit before the discovered
  literature records or focused passages could be acquired and read.

Before:

- Site Research inherited an initial latency reduction from 12 source operations to 4.
- Search and acquisition both consume reservations because both are real external
  evidence operations with recorded provenance.

Root cause:

- Four operations can cover one structured receptor source and three literature
  discoveries, but leave no capacity to resolve decision-relevant search leads.
  The limit optimized latency past the minimum evidence needed for accurate ranking.

Repair:

- The Site-specific evidence-operation budget is 8: one structured receptor context,
  one or more focused searches, and enough source acquisitions to read the strongest
  leads. This remains one third below the former generic limit of 12.
- The Site model-call ceiling remains 8, compact kernel reuse remains mandatory, and
  deterministic finalization still begins as soon as either bounded budget is complete.

After:

- A focused regression fills exactly eight Site reservations and verifies the Harness
  switches to typed handoff finalization with no further action tools.
- R12 is invalidated because product code changed after it started. R13 must begin in
  a new project and thread at Gate 1.

## Attempt R13 — completed Gate 2, superseded for latency validation

- Project: `figure2-nk2r-site-fast-r13`
- Thread: `thread-1579c54250e04591ae1537d16efa3fb7`
- Start commit: `a246785d4efe6684df1d1725f9ce052da6d20430`
- Gate 1: independently resolved human NK2R P21452 and auth chain R / label chain B.
- Gate 1 wall time: 112.84 seconds.
- Gate 2 wall time after approval: 344.35 seconds.
- Gate 2 result: successful ranked Site card
  `cfce11f3599f05e1d6ab4935e17617cf8f0e744d99d5247121f5f13e138845d5`.
- Manual scientific answer injection: none. The standing Scientist authorization approved
  the freshly resolved Gate 1 recommendation.
- One initial CLI approval command incorrectly supplied `--candidate chain-r`. The CLI
  rejected it before state mutation or model execution because candidate selection applies
  only to ranked Site cards. The same unconsumed card was then approved correctly.

### Successful scientific and integrity checks

- Runtime produced three selectable, exactly mapped candidates: ECL2/ECL3 outer vestibule,
  TM2/TM6/TM7 outer pore, and TM2/TM3/TM6/TM7 core pore.
- Site synthesis used a 30,081-character packet and submitted `RankedSiteDecision` on its
  first 16.20-second call with no repair.
- The Site Judge was not invoked on the normal hard-valid path.
- The 67,964-byte durable dossier and full Runtime residue facts remain available for audit.
- GPCRdb, UniProt and two targeted literature discoveries were retained; no old NK2R answer,
  dossier, candidate membership or ranking was supplied to the Agent.

### SITE-LATENCY-004 — kernel delivery competed with generic acquisition navigation

Trigger:

- GPCRdb acquisition had already atomically computed the receptor kernel.
- On the next two calls, the model chose `read_evidence_result` twice before eventually
  choosing `analyze_receptor_context`.
- The generic acquisition artifact was durable but did not add a second authoritative
  topology or candidate interpretation.

Repair:

- When a complete GPCRdb card has a current-binding kernel that has not yet been delivered,
  the Harness offers only the scoped `analyze_receptor_context` action.
- After that one successful compact delivery, the full research tool surface returns and the
  analyze action is removed. Full acquisitions remain durable and readable for audit.

### SITE-LATENCY-005 — the eight-call policy did not reserve its handoff call

Trigger:

- The R13 Site path recorded eight normal Research responses, two framework-summary calls,
  and one synthesis response. The bounded Research session reached call 10 before its typed
  handoff because finalization began only after eight calls had already been reserved.
- Site provider wall time, including summaries and synthesis, was 258.83 seconds; input/output
  usage was 121,305 / 21,030 tokens. No repair or Judge call occurred.

Repair:

- The eight-call Site Research policy now reserves its final counted provider call for the
  typed handoff. Seven prior counted calls, including framework summaries, trigger compact
  finalization on the eighth call.
- This changes orchestration only. Evidence validation, citation requirements, hard-fact
  checks, Runtime dossier construction and independent synthesis remain unchanged.

R13 proves scientific completion but is superseded for latency acceptance because these two
orchestration defects were repaired afterward. R14 must start from Gate 1 in a new project and
thread.

## Attempt R14 — invalidated

- Project: `figure2-nk2r-site-fast-r14`
- Thread: `thread-49dfee0bf21a4090bb72d207dd4db300`
- Start commit: `599272399a8ee0e9a05286ef5150428d460d1882`
- Gate 1: independently resolved human NK2R P21452 and auth chain R / label chain B.
- Gate 1 wall time: 142.81 seconds.
- Status: stopped during Gate 2 Site research after a durable-delivery defect was proven.
- Manual scientific answer injection: none.

### Confirmed improvement

- The first Site call acquired GPCRdb in 4.46 seconds.
- The second call offered only `analyze_receptor_context`, returned the already-computed
  current-binding kernel in 2.71 seconds, and did not page the acquisition artifact.
- The third call used the delivered kernel to launch focused evidence work. The R13 generic
  result-navigation detour was removed.

### SITE-LATENCY-006 — framework summary forgot that the kernel was delivered

Trigger:

- A framework summary compressed the Site message history after the first successful kernel
  delivery.
- Delivery detection inspected only live `ToolMessage` objects. Once that message was absent,
  the fifth counted call offered `analyze_receptor_context` again and the model called it.
- Runtime correctly reused the existing analysis, so no structure computation or hard fact was
  duplicated, but one model call and a 30k-character projection were wasted.

Repair:

- Kernel delivery is now recognized from the execution-scoped durable `tool-view` event whose
  artifact is `research-receptor-analysis`, with the live successful ToolMessage retained as an
  immediate-path check.
- Framework summaries and restart projections therefore cannot make the same execution forget
  that the authoritative kernel was already delivered.

R14 is invalidated because product code changed after it started. R15 must begin in a new project
and thread at Gate 1.

## Attempt R15 — invalidated

- Project: `figure2-nk2r-site-fast-r15`
- Thread: `thread-27517c16dbba43588c6e60cd6e9cea08`
- Start commit: `696fab1311ada38ab9888b3b5582b248a4b5d7c8`
- Gate 1: independently resolved human NK2R P21452 and auth chain R / label chain B.
- Gate 1 wall time: 113.09 seconds.
- Gate 2 failed safely after 194.11 seconds.
- Manual scientific answer injection: none.

### Confirmed improvement

- Exactly one model-facing receptor-kernel delivery occurred, and it reused the
  acquisition-time analysis. Framework summarization did not re-offer the tool.
- The normal evidence phase stayed within the intended seven pre-finalization counted calls,
  including one framework summary, then entered compact handoff finalization on call eight.

### SITE-LATENCY-007 — typed finalization replayed withdrawn acquisition actions

Trigger:

- Finalization correctly exposed no action tools and only the `SiteResearchHandoff` schema.
- Its message history still contained prior assistant tool-call structures. Across three bounded
  submission attempts, the model copied withdrawn `retrieve_evidence`, `research_evidence`, then
  `acquire_evidence` actions instead of submitting the handoff.
- The role boundary rejected the unavailable action; no unauthorized source operation ran and no
  dossier or Site decision was created.

Repair:

- Submission-only Site Research now receives an inert projection of completed visible scientific
  notes and exact tool results. Prior assistant tool-call structures and arguments are excluded.
- Query IDs, evidence result contents, limitations and model-visible scientific notes remain in
  the projection; the original checkpoint and durable evidence are unchanged.
- The isolated message explicitly states that reading is closed and unresolved evidence belongs
  in the typed handoff rather than another operation.

R15 is invalidated because product code changed after it failed. R16 must begin in a new project
and thread at Gate 1.
