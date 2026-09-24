# Architecture

> **Historical prototype record.** This document describes the original standalone
> demo architecture delivered on 2026-09-13. The integrated repository now starts
> in live mode through `LiveWorkbenchAdapter` and the native EasyDesign Product API;
> the authoritative current contract is
> [`../../../docs/WORKBENCH_INTEGRATION.md`](../../../docs/WORKBENCH_INTEGRATION.md).
> The `DemoAdapter` material below remains accurate only for explicit
> `?mode=demo` use. Statements below that backend integration is absent are retained
> as provenance, not current product authority.

## Product structure

React 19 + TypeScript + Vite provide three English destinations with one collapsible 58/252 px navigation rail. Projects is a searchable project center. Agent Workspace retains the workflow/task column, Design Scientist conversation, phase-dependent Scientific Context and decision bar. Compute & Queue displays optional live GPU telemetry and the demo’s separate current Pilot/Scale activity. CSS is split into global, landing, workspace, context, navigation and platform-page files; icons use Lucide and the EasyDesign mark is original SVG.

```text
src/main.tsx → DemoAdapter → App
                            ├─ ProjectSidebar (three platform destinations)
                            ├─ ProjectsPage (create, search, rename, delete, open)
                            ├─ Landing (new project goal, in Agent Workspace)
                            ├─ Workspace
                            │    ├─ Current project selector
                            │    ├─ Workflow / Agent Tasks
                            │    ├─ Conversation
                            │    ├─ ScientificContext → MolecularViewer
                            │    ├─ DecisionBar
                            │    └─ LabOrderPage (optional request preparation after Candidates)
                            └─ ComputePage (live resources + separate demo runs/filters)

WorkbenchAdapter ← DemoAdapter ← unchanged fixture + scripted stage events
                         └─ localStorage + bounded UI animation timer
DshAdapter implements the boundary but intentionally cannot load or approve.

LiveResources → GET /api/compute/resources → Vite local middleware
                  → single-flight 10s telemetry cache → fixed SSH/nvidia-smi reads
                  (independent of DemoAdapter and scientific job authority)
```

## Adapter contract

`WorkbenchAdapter.ts` defines typed workflow tasks, conversation events, specialists, candidates, context and decisions. Components use snapshots and typed actions, never import fixture JSON or DSH internals. `load` and `subscribe` provide state; `sendMessage`, `approve` and `edit` handle product actions. Snapshots include typed project summaries and the active project ID; `createProject`, `selectProject`, `renameProject` and `deleteProject` manage the local project collection through the same adapter boundary. Reset, replay and skip are explicit demo controls. `dispose` cancels timers and subscriptions.

`DemoAdapter` owns only the frontend demo lifecycle. Its 480 ms timer emits prewritten events. Approvals are bound to the current project, run and phase, reject stale/double submissions, and never cross a human approval automatically. Goal transitions into Target; Scale automatically completes its three batches and then exposes Review candidates. Pilot revision increments the run identity before returning to Design. This is not a scientific scheduler, workflow engine, command ledger or recovery service.

The initial research goal is preserved. Follow-ups become notes with a clear fixed-demo response. Versioned localStorage stores current phase, event index, messages and choices. Fresh loads validate the saved shape and resume the remaining animation; corrupt state resets safely. Persistence is optional and has no server authority.

Platform navigation uses three hash destinations through `app/navigation.ts`, independent of saved scientific/demo state. The bare URL opens Projects; Back/Forward and reload retain named pages. New project remounts a blank goal composer; submitting creates another project and preserves older ones. The Agent Workspace navigation entry returns to the selected project. Project cards and the workspace selector call the same adapter action. Selection saves the current event index, cancels its animation timer, switches state, and resumes only the selected project's timer. Reset and Replay act only on the selected project. Conversation/viewer state is remounted on project changes so unsent text cannot leak into another project.

`WorkbenchSnapshot.compute` is a read-only projection of each saved project's current replay. It identifies demo-only mode and lists Pilot/Scale stages already reached, keyed by project/run/phase. Candidate counts follow existing generation/batch events. Inactive unfinished animations are paused; completed stages stay complete. Replay/reset discard only the selected project's current activity. The demo projection has no queue mutation, scheduler, parallel scientific execution or second job store. Optional live resource sampling is a separate read-only transport described below; it cannot submit jobs or infer job ownership from GPU activity. Future scientific job integration still requires an authoritative adapter contract.

The small versioned localStorage envelope (`easydesign-workbench-projects-v1`) holds project records, a monotonic project number and the active ID. IDs and saved state are validated on load; a legacy single-demo record can become the first project without rewriting its original key. This change is confined to browser demo persistence and is not an EasyDesign scientific storage migration. Project names do not modify research goals. Confirmed project deletion persists the filtered collection before publishing the change. Deleting the active project cancels its demo timer and selects a remaining project, or the empty state. The empty envelope is retained to prevent legacy re-import, and project numbers remain monotonic. A write failure leaves the project intact. Cloud synchronization and multi-tab merge policy are not introduced.

## Read-only resource monitor

`server/compute.ts` is a small Vite dev/preview middleware, not a scientific backend. It reads the server-only `WORKBENCH_COMPUTE_SSH_HOST` setting. A fixed, bounded SSH command queries `nvidia-smi` on that host using existing local credentials and strict host-key checking. The browser cannot supply hosts, paths or commands. The endpoint accepts only local same-origin GET requests with no query parameters. It returns allowlisted hardware metrics and process counts, never command lines, PIDs, usernames, credentials or SSH diagnostics.

A single in-flight sample and 10-second cache avoid overlapping SSH calls. Successful readings use local receipt time, so GPU-host clock skew cannot invalidate freshness. Failed refreshes retain the last sample with `stale`; no successful sample yields `unavailable`. The UI also marks readings older than 25 seconds as stale, displays missing metrics as unavailable, polls only while the Compute page is visible, and aborts requests on unmount. This adds no queue, scheduler, reservation, job control or storage layer. See [configuration and verification](COMPUTE_AND_PROJECTS.md).

## Viewer and scientific honesty

### Optional Lab Order preparation

After the scientific panel is finalized, the workspace can show `LabOrderPage` in place of conversation/context. This is a project-scoped product view, not an eighth scientific kernel phase: the existing `PHASES`, stage fixtures and DSH stage mapping remain unchanged. The workflow adds a locked/unlocked Lab Order entry, with checkmark substeps synchronized to the form's numbered tabs. The completed-panel bar offers **Prepare Lab Order** explicitly; finalization never creates or submits a provider order.

`domain/labOrder.ts` describes a bounded local draft. `WorkbenchSnapshot.labOrder` and `saveLabOrder` use the existing adapter and project persistence envelope. Selected samples are restricted to current finalists, with stars used only to seed the initial selection. Input edits invalidate the user's review acknowledgement; navigation does not. Draft fields and the selected step survive refresh and project switching. Replay/reset remove only that project's draft. Older records without this optional field load normally; a malformed lab draft is ignored without discarding the scientific panel. No scheduler, request transport, credentials, provider order ID or production status is introduced. The DSH implementation explicitly rejects the new action until an integration is configured.

The central Samples / Requirements / Review form preserves full field labels, sequence-readiness notices, a collapsible Design Scientist summary and an Order Summary. Advanced expression/QC requirements remain available, and all entered requirements appear at final review. The footer can save a draft or preview the confirmation dialog. It cannot submit a request: candidate sequences are only truncated demo previews, account profiles are illustrative, and no real lab transport exists. Quotation and production authorization remain separate unresolved integration concerns. Price and turnaround remain unconfirmed; no binding assay or lab result is claimed. This feature is detailed in [LAB_ORDER.md](LAB_ORDER.md).

`MolecularViewer` loads the bundled `public/structures/1MEL.pdb` first, with a timed RCSB fallback if the local file is unavailable. If both requests fail or WebGL is unavailable, it shows a retryable fallback and never blocks approval. Network and WebGL cleanup are confined to the component. 3Dmol is lazy-loaded; fonts and structure are bundled so the normal journey requires no external requests.

The supplied fixture names the target chain **C**, a mmCIF label identifier. In the deposited PDB format the corresponding author chain is **L**. The selected reference pair is target L (label C) and VHH A. `public/structures/1MEL.cif` and `SOURCE.json` preserve that mapping. The app labels the reference explicitly and uses the actual PDB author IDs for rendering. SEQRES target length is 129; 127 target residues have resolved C-alpha atoms. The reference VHH SEQRES is 148 residues; 132 have resolved C-alpha atoms. Demo candidate lengths/scores are fixture values, not derived validated sequences.

Site buttons update colored residue groups. Candidate selection updates metrics, ID and a distinct view orientation of the **same public reference complex**; no candidate-specific structure is claimed. Ribbon/atom modes, chain selection, rotate, zoom and reset are functional. The 8/24/6 counts and all scores, mock residue sets, sequence previews and outcomes remain visibly marked as Demo/Simulated.

## Future DSH connection

`DshAdapter.ts` is a typed unavailable stub, not a simulated production connection. It throws explicit errors on load and actions. The mapping is recorded without changing primary visible labels:

| Workbench phase    | Existing DSH stage concept |
| ------------------ | -------------------------- |
| Goal, Target, Site | prepare                    |
| Design             | strategize                 |
| Pilot              | pilot                      |
| Scale              | scale                      |
| Candidates         | select                     |

Later integration should normalize structured server snapshots/events into the product contract, forward authoritative decision IDs through an authenticated transport, and supply resolved artifact URLs to the viewer. It must not infer stage progression, approval authority, or specialist acceptance from assistant prose. Demo-only controls should be capability-gated for a real adapter. The current `mode: 'demo'` and demo controls intentionally describe this delivery; extend those types when introducing real capabilities. The feature components can keep the same snapshot/action boundary.

## Intentional limits

- Single-browser local project collection; no collaboration, auth or cross-tab synchronization guarantee. Clearing browser data removes these local demos.
- Fixed lysozyme/VHH content even when a user enters another goal; Landing, help and follow-up response disclose this.
- Research trace contains prewritten public summaries, not raw chain-of-thought or model output.
- No scientific validation, real design computation, architecture migration or backend integration.
- Desktop acceptance covers Chromium at 1366×768, 1440×900 and 1728×1117. Narrow-screen drawers exist but mobile/Safari/Firefox certification is outside this delivery.
