# 03 — Adapter Contract

The UI must not bind directly to fixture JSON or DSH internals.

Create a narrow `WorkbenchAdapter` interface.

Suggested TypeScript shape:

```ts
type WorkflowPhase =
  | "goal"
  | "target"
  | "site"
  | "design"
  | "pilot"
  | "scale"
  | "candidates";

type TaskStatus = "locked" | "pending" | "running" | "complete" | "approval";

interface WorkbenchSnapshot {
  project: ProjectSummary;
  phase: WorkflowPhase;
  tasks: WorkflowTask[];
  messages: ConversationItem[];
  context: ScientificContext;
  decision?: DecisionState;
  runSummary?: RunSummary;
}

interface WorkbenchAdapter {
  load(): Promise<WorkbenchSnapshot>;
  subscribe(cb: (event: WorkbenchEvent) => void): () => void;
  sendMessage(text: string): Promise<void>;
  approve(decisionId: string, payload?: unknown): Promise<void>;
  edit(decisionId: string, payload: unknown): Promise<void>;
  resetDemo?(): Promise<void>;
  replayDemo?(): Promise<void>;
}
```

## Phase 0

Implement:

`DemoAdapter`

Data source:
`demo/demo-fixture.json`

Responsibilities:
- deterministic state machine
- timed event replay
- no model call
- no GPU call
- no EasyDesign CLI write
- always reaches completion after user approvals

## Phase 1 later

Implement:

`DshAdapter`

Map existing EasyDesign / DSH data into the same UI contract:
- project status
- DSH conversation
- tool events
- specialist activity
- approval
- viewer artifacts
- candidate results

Do not redesign the UI when moving from DemoAdapter to DshAdapter.

## Current EasyDesign mapping hints

Current backend phases:
- prepare
- strategize
- pilot
- scale
- select

User-facing projection:
- Goal -> prepare
- Target -> prepare
- Site -> prepare
- Design -> strategize
- Pilot -> pilot
- Scale -> scale
- Candidates -> select

Existing published UI contains:
- `TASK_PHASE_STEPS`
- project snapshot handling
- DSH tool metadata
- Campaign review
- structure artifact serving
- specialist reviews

Use the attached current code only as integration reference.

## Important

Do not parse conversational prose to infer authoritative workflow state.

The UI state must come from structured adapter state.
