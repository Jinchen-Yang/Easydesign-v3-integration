# v3 state ownership — Phase 2.2d

Status: ownership regressions passed; overall Phase 2 acceptance failed (see PHASE2_CLOSURE.md). No new scheduler, graph, ORM, schema migration or
scientific state store is introduced. LangGraph owns conversation execution/checkpoints;
the existing scientific services own runs, jobs, decisions and approved artifacts.

| State | Owner and source | Read/write rule |
| --- | --- | --- |
| Original research goal | Thread, `threads.goal` | Immutable; follow-up never replaces it |
| Current message, clarification, revision | Thread, existing execution/response events | Runtime injects these separately from the original goal |
| Conversation history, subagent execution | Thread, LangGraph | Context only; not scientific evidence or compute recovery |
| Model/research call budget | Agent execution within thread | A genuine new user execution renews the budget; replay/resume preserves it; lifetime counts are telemetry |
| Source-selection and scoped-argument repairs | Agent execution, existing `prerequisite-repair` / `tool-argument-repair` events | Four model correction rounds shared across error categories/roles/delegations; each native batch shares a round while every diagnostic is retained; exact batch replay keeps its attempt, new model messages spend new rounds; stale executions cannot spend a fresh allowance. Role, artifact integrity and Judge binding remain hard constraints; no scientific job scheduling ownership |
| Structured-output corrections | Agent execution, existing contract-repair events | Two total across roles/redelegations; restart cannot reset; separate from the source/projection allowance |
| Target facts and interpretation | Verified kernel/source facts plus thread Target interpretation event | Runtime attaches facts/refs/options; changed interpretation invalidates old Judge binding |
| Pending Site/Design proposal | Thread, `site-proposal` / `design-proposal` events | `thread_latest`; another conversation cannot replace its pending proposal |
| Pending decision/card/response/Judge opinion | Thread, existing SessionStore rows | Exact card, snapshot, actor and response binding; no approval from model text |
| Explicit biology context import | Project, `biology-context` event + existing ArtifactRef | Trusted CLI input is a project scientific assumption, not a chat clarification. Values retain user-supplied authority; coordinates are validated, biological assertions are not automatically verified |
| Deterministic Site facts | Project evidence, `site-facts` | Content keyed to Target and adopted biology; all consumers verify ArtifactRef |
| Research queries, discovery and pending conclusions | Thread, existing events + ArtifactRef | Source bytes are durable project evidence; a thread's search agenda and interpretation are local. Retrieval cannot alter canonical identity or topology |
| Durable source corpus and chunks | Project, existing ArtifactRefs/events | Complete raw responses remain durable; corpus existence is independent of current binding; exact verified canonical revision can carry only its chosen UniProt source; other thread/need reuse requires explicit selection |
| Evidence selection/current passages/tool views | Thread/execution, existing events | Explicit source/need selection; query-bound cursor; exact pages; no other thread's pending reasoning |
| Judge offload view | Exact runtime delegation within thread/execution | Full result bytes verified; previous proposal's result cannot satisfy the current snapshot |
| Canonical reference proposal | Trusted runtime + existing config revisions | Source record verified; configured species/accession protected; proposal is not approval and does not replace the mapper |
| Expert native input | Scientist CLI input + thread import event | Gate 2 required; source bytes/constraints verified; Binder cannot rewrite the supplied YAML; approved output becomes project-global |
| Approved Target/Structure | Project, original Stage 01 manifest/decision services | Shared only through existing verified Target Bundle/mapping; chain approval alone is not canonical identity confirmation |
| Approved Site/Hotspot | Project, old site foundation and exact `site-approved` receipt | `project_latest` approval resolves its exact historical owner proposal, never the requesting thread's latest draft; old hotspot bytes/numbering/foundation are revalidated |
| Approved Design | Project, old frozen strategy/plan/approval | Exact approved owner proposal and input binding are revalidated; any thread can consume valid approved science |
| Run/job/attempt/recovery | Project, original scientific runtime | Agent ledger only reattaches commands to exact jobs; does not schedule or recover compute itself |

`project_latest` and `thread_latest` are explicit adapters over the existing event table.
There is no ambiguous `latest(kind)` at this boundary. `approved_proposal` resolves the exact
proposal ID, originating thread and event order preceding the approval. Old records without
new fields remain readable through that same historical lookup; unrelated drafts are never substituted.

An explicit project biology change invalidates downstream Site/Design binding while retaining
Target. A trusted Gate 3 request to revise WHERE invalidates Site/Design project authority;
an ordinary CDR/crop/arm revision stays with Binder. Existing science pointers and manifests
remain authoritative: if an intervening change makes an old freeze plan stale, application
fails rather than silently freezing a different plan.

Two threads may retain different Site proposals simultaneously. Their old scientific review
requests remain separately run-bound. A's resume uses A's request even after B proposes B;
approval calls the old service with A's run-bound review file. B may then inherit the approved
project Site while retaining B's separate draft. A pending proposal is not approved truth.

Regression: `tests/unit/agent/test_state_ownership.py` covers two pending conversations,
follow-up/resume, inherited Site evidence for Binder, and project biology invalidation.
Existing Site/Design replay and steering regressions cover exact old-service authority.


## Explicit recovery of an unreviewed Site proposal (2026-09-12)

Pending proposals still do not appear automatically in another conversation. The trusted
`Phase2Bridge.transfer_unreviewed_site` recovery API is an explicit exception for a stopped
source Agent whose completed Stage02 proposal has no Judge assessment or Decision Card yet.
The caller names the source thread and exact proposal ID within the same project. The runtime
checks current Target/biology/facts, immutable research/review artifacts, original pending job
and empty destination execution; reviewed/responded proposals must use ordinary steering.

One existing SQLite transaction records source transfer, the exact original proposal in the
destination and receipt provenance. The original scientific owner, proposal ID, job, snapshot,
source events/checkpoint, fingerprints and execution budgets remain unchanged. Source current
proposal lookup then excludes that transferred proposal. New independent Judge review and the
existing Gate2 service are still mandatory; no approval or hard fact is created by transfer.
Replay of the same explicit transfer is idempotent; conflicting or stale requests fail closed.
This is not exposed as an LLM tool. The autonomous validation runner invokes it only for a
recorded failed attempt after its process has stopped, and reports both threads' actual calls
and evidence metrics. There is no second scheduler, checkpoint or decision store.
