# Workflow authority audit — Phase 2, 2026-09-13

> **Historical audit with current consolidation (2026-09-20).** The original baseline was
> `a2c17ce50a182474bb3ccbf9ac69aa44faf678c9`. Its Phase 2 findings remain regression requirements,
> while Gate 4/5 are now active through the Phase 3/4 runtime. For the current end-to-end topology,
> Judge optionality and enabled scopes, use [ARCHITECTURE.md](ARCHITECTURE.md) and
> [PHASE34_EXECUTION_CONTRACT.md](PHASE34_EXECUTION_CONTRACT.md).

This audit did not itself declare scientific acceptance or enable Phase 3. Runtime owns state and authorized dispatch;
specialists own scientific interpretation; Judge independently critiques; Scientist
decides consequential Gates. A model's final message is not a workflow transition.

## Authority and scope

The next action is the **first unfinished, valid, authorized action within the thread's
immutable scope**, not a static mapping from the last approval. Gate 1 approval alone
does not mean preparation finished; Gate 1 approval after Research finished must not
restart Research. `through=site` stops after Gate 2; `through=design` stops after Gate 3.
The Phase 1 `through=target` compatibility harness is separate and cannot enter Site.

Project manifests, verified artifacts/configuration and existing scientific services own
scientific state. SessionStore owns bound proposals, Judge assessments, human outcomes,
delivery and execution accounting. Neither overrides the other's domain: persisted human
intent is not applied scientific approval; a historical pending snapshot is not the current
Gate. Approval reuse requires exact revision/input binding and the applied scientific result.
Thread-local pending proposals do not supersede another thread's accepted project proposal;
continuation reuses accepted state and requires explicit adoption of another pending proposal.
`latest(kind)` is only a lookup candidate: existing binding, artifact and lineage validators
must succeed before it determines current state. Invalid newer state fails closed; it does
not silently fall back to an older approval. No new authoritative store is introduced.

## Transition matrix

In the table, “recommend only” means scientific recommendations are allowed but an LLM
cannot authorize the transition. Every automatic edge is conditional on its preconditions.
All backward edges require an explicit trusted reason, preserved history and downstream
binding invalidation. Resume never grants a new approval or renews an execution budget.

| Transition | Preconditions / completion | Authoritative owner | Next action | Invalidation / rollback | Restart / resume | LLM recommendation / authorization |
| --- | --- | --- | --- | --- | --- | --- |
| Input → Target | Explicit project input, valid config; no completed current Target | Project/config + TargetBridge command journal | Delegate Target reasoning; prepare through existing idempotent command | Changed input/config requires explicit revision; corrupt refs block | Reconcile existing command/job, never relaunch ambiguous dispatch | Recommend identity/construct / no |
| Target → Gate 1 review | Current pending chain request and bound Target interpretation | Verified request + Target assessment | Independent Judge of exact snapshot | Changed source or revised opinion invalidates old review | Reuse only matching review after current revision | Recommend chain / no |
| Judge → Gate 1 card | Current reviewable Judge verdict and eligible proposed option | Decision service + bound Judge assessment | Present one real interrupt/card | REVISE creates fresh owner/review/card; REJECT stops proposal | Same response/card is idempotent; conflicting response rejected | Recommend option / no |
| Gate 1 → prepared Target → Site | Applied valid approval (or existing deterministic no-ambiguity policy), successful preparation, Site in scope, no current Site result | Stage 01 manifest and TargetBundle; response delivery is separate | Observe active job, then dispatch Site Research | Stale revision receipt cannot authorize current Target; hard integrity mismatch blocks | Resolve current bundle; historical pending job/card cannot reopen Gate 1 | Report contradiction / no |
| Research → Handoff | Typed Handoff, validated evidence relations and candidate bounds | Existing native Research subgraph + validation | Accept Handoff into Dossier node | Invalid submission uses existing bounded correction; scientific uncertainty may remain | Resume native child checkpoint; completed Dossier bypasses repeated Research | Decide research questions/stopping hypothesis / no direct stage mutation |
| Handoff → Dossier | Accepted current Handoff and verified source/fact closure | Runtime Dossier builder | Persist exact immutable Dossier | Changed Target binding or trusted revision invalidates reuse | Verify owner/execution/binding before reuse | No / no |
| Dossier → SiteDecision | Valid current Dossier | Runtime graph | Isolated SiteDecision inference | Invalid output uses existing bounded schema correction | Reuse Dossier; do not restart acquisition | Select candidates and rationale / no |
| SiteDecision → hydration → proposal | Valid typed decision and exact candidate IDs | Runtime hydration + existing Site service | Hydrate facts, validate, publish proposal | Invalid membership or stale binding blocks; no model facts overwrite | Existing immutable proposal/result reused after completed publication | Scientific selection / no |
| Site proposal → Judge | Current validated proposal and no matching completed review | Runtime-bound independent Judge | Review exact packet | Proposal/revision change invalidates prior assessment | Matching review reused; negative verdict is a stop, not a retry loop | Critique / no |
| Judge → Gate 2 | `ready-to-ask`, valid site and current assessment | Existing Gate 2 adapter | Present warned card as appropriate | Hard BLOCKED cannot be overridden; existing qualification semantics unchanged | Reuse exact review/card; do not resynthesize | Recommend / no |
| Gate 2 → Binder | Applied current hotspot approval; design in scope and unfinished | Verified hotspot artifact + bound site approval | Dispatch Binder; otherwise finish site scope | Site invalidation invalidates dependent Design | Accepted project Site reused across threads | Scientific design strategy / no |
| Binder → Judge → Gate 3 | Valid compiled specification, current Site, independent review | Existing Design/compiler service + Gate adapter | Present Gate 3 | REVISE stays in Design by default; explicit Scientist Site target reopens Site | Reuse valid proposal/review; frozen receipt checked against compiler output | Propose HOW / no |
| Gate 3 → Pilot | Valid frozen Design, `through=pilot|handoff`, and separate resource authorization | Phase34 runtime + execution-plan/approval services | Execute the approved Pilot plan; never infer authorization from Gate 3 prose | Changed Design requires a new plan/approval | Resume exact plan/job and preserve completed work | Recommend Pilot composition / no |
| Pilot → Gate 4 | Completed native evidence with explicit evaluable/eligible states | Native evidence adapter + Ranking & Recovery Specialist | Rank the complete context-safe PASS population and present Gate 4; Judge is optional | Failed job differs from native scientific FAIL or missing optional AFO | Existing compute recovery owns job resume | Recommend promotion/recovery / no |
| Gate 4 PROMOTE_TO_SCALE → Scale | Explicit bound promotion, eligible strategies and approved production intent | Gate 4 outcome + Phase34 scale runtime | Execute exact production intent or an explicit validation projection | Evidence/plan change invalidates authorization | Exact receipt/plan prevents stale reuse | Recommend / no |
| Gate 4 RUN_ANOTHER_PILOT → Pilot | Explicit bound Scientist decision and valid new plan | Gate 4 outcome + Pilot runtime | Create a new authorized Pilot attempt | Preserve old evidence; new attempt has new identity | Never repeat the old Pilot on restart | Recommend / no |
| Gate 4 REVISE_DESIGN → Binder | Explicit Scientist revision target, valid upstream Site | Gate 4 outcome + Design owner | Reopen Design with bound instruction | Invalidate dependent plans, preserve Target/Site | Resume revision lineage | Recommend / no |
| Gate 4 REVISE_SITE → Site | Explicit Scientist revision target | Gate 4 outcome + Site owner | Reopen Site with bound instruction | Invalidate dependent Design/plans, preserve Target | Resume revision lineage | Recommend / no |
| Gate 4 STOP → terminal | Explicit bound stop decision | Gate 4 outcome | End the authorized campaign scope | A later request cannot overwrite the stop receipt | Remains stopped until a new authorized intent | Recommend / no |
| Scale → Final Selection → Gate 5 | Native-complete global PASS pool, dedup/provenance and valid final selection | Phase34 runtime + Final Selection Specialist | Compare all eligible candidates with shared multi-metric semantics and present Gate 5; Judge optional | Changed pool/profile/provenance invalidates review and card | Reuse exact global pool; partial batches remain explicit | Recommend candidates / no |
| Gate 5 APPROVE → wet-lab handoff | Explicit Scientist acceptance of exact primary/backup panel | Gate 5 outcome + idempotent handoff service | Publish the bound handoff package; do not trigger an experiment | Changed candidates require a new Gate 5 | Exact handoff receipt is idempotent | Recommend / no |

## Active-path findings and fix boundary

1. Coordinator receives `next_specialist` but could end instead of calling it. Runtime
   dispatch must execute through the existing native graph/tool/checkpoint path without a
   Coordinator model decision. Tests must assert actual specialist entry, including a
   hostile Coordinator returning the saved stale Gate 1 confirmation.
2. A graph with no next node returns `incomplete-turn` forever on ordinary resume. Within
   the same persisted execution, a valid unfinished runtime action must be resumable;
   operational waiting, scientific rejection and completed scope remain distinct.
3. Pending proposal state does not distinguish “needs Judge” from “Judge already ready”.
   Resolve a matching persisted assessment and open its card directly; do not repeatedly
   delegate Judge or infer readiness from prose.
4. The Research → Dossier → synthesis edges already are deterministic. Preserve them,
   including scientific autonomy within Research; verify Dossier reuse on interrupted
   publication and resume. Do not introduce a planner or evidence redesign.
5. `reopen_site` previously accepted any Gate 3 REVISE plus a model-written reason.
   Require an explicit trusted Site revision target. A label such as HARD_CONTRADICTION
   cannot revoke approval. Machine-verifiable binding/integrity failures block; scientific
   disagreements require independent review or Scientist input. No automatic Target
   revision creation is introduced in this task.
6. The original audit correctly required Phase 2 scope to reject Gate 4/5 actions. Phase 3/4 later enabled those handlers behind explicit `through` scope, plan binding and Scientist outcomes. Compatibility tests must still prove that target/site/design-only runs cannot cross their authorized boundary.

## Validation boundary

The original Phase 2 validation record is preserved in its acceptance documents. Current changes must run
focused control-flow/restart tests and the full automated suite before a frozen live case. A live acceptance
may intentionally stop at its declared `--through` boundary; a goal-only Gate 1 test does not claim that
Pilot or Scale ran in that case. Existing Phase 3/4 regression artifacts validate their handlers separately.
