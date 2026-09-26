# Acceptance closure — 2026-09-13

This records the original demo acceptance. The approved 2026-09-19 extension adds read-only SSH GPU telemetry and local project deletion; see [current extension validation](COMPUTE_AND_PROJECTS.md). Original “no shell/compute service” statements below describe the initial scope, not the optional monitor. No scientific job is launched.

All 28 P0 and all 8 P1 items below are closed for this standalone demo. Evidence follows the checklist.

## P0 — Must pass

- [x] `pnpm install` / equivalent succeeds
- [x] one documented dev command starts the app
- [x] white EasyDesign goal landing remains available in Agent Workspace; the approved three-destination extension makes Projects the default entry
- [x] user can submit the default lysozyme/VHH prompt
- [x] Workbench opens without full page reload
- [x] left column shows Goal / Target / Site / Design / Pilot / Scale / Candidates
- [x] current phase and subtasks update correctly
- [x] center column renders user messages, agent summaries, tool cards and specialist states
- [x] no raw chain-of-thought is displayed
- [x] right panel changes for every phase
- [x] Target/Site includes a functioning structure viewer OR a robust viewer adapter with graceful fallback
- [x] Site A/B/C click changes selection/highlight state
- [x] Approve Target advances
- [x] Approve Site B advances
- [x] Approve Design advances
- [x] Pilot always produces 8 demo candidates
- [x] Promote advances
- [x] Scale simulates 24 candidates only
- [x] Candidates displays 6 finalists
- [x] Finalize panel reaches completed state
- [x] Replay demo works
- [x] Reset demo works
- [x] refresh does not corrupt app state
- [x] no real BoltzGen/AFO/Protenix/GPU job is launched
- [x] all simulated scientific outputs carry a Demo / Simulated marker
- [x] page is visually light, white, restrained and consistent with the supplied Latent-Y references
- [x] no Latent-Y logo or proprietary copy is reused
- [x] existing scientific backend is not refactored

## P1 — Strongly preferred

- [x] tool cards expand/collapse
- [x] selected sentence/card can focus related right-panel content
- [x] Site selection updates structure
- [x] candidate selection updates structure
- [x] keyboard focus states are usable
- [x] 1366×768 and 1440×900 both work
- [x] screenshot regression or Playwright smoke test exists
- [x] adapter boundary is covered by small tests

## Evidence mapping

| Requirement group                                                          | Evidence                                                                                                                                                                                                                                                   |
| -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Install, dev command, TypeScript and bundle                                | `README.md`, `pnpm-lock.yaml`, `validation/install.txt`, `validation/build.txt`                                                                                                                                                                            |
| White Landing, no full reload, seven phases, approvals, 8/24/6, completion | `e2e/journey.spec.ts` entire-product-journey test at all three desktop resolutions; `validation/browser-tests.txt`                                                                                                                                         |
| Workflow/subtasks and specialist states                                    | `DemoAdapter.snapshot`, `stages.ts`, `Workflow.tsx`, phase screenshots. Agent Tasks show specialist activity; center tool cards show completion and concise research summaries.                                                                            |
| User messages and preserved research goal                                  | Adapter tests and browser refresh/follow-up test; `Conversation.tsx`                                                                                                                                                                                       |
| Phase-specific context and structure                                       | `ScientificContext.tsx`, actual rendered Site/Pilot/Candidates screenshots, browser assertions of viewer ready and selected chains/sites/candidates                                                                                                        |
| Site, candidate and context-linked interaction; expand/collapse            | Entire-product-journey test and keyboard/context/revision test                                                                                                                                                                                             |
| Viewer failure                                                             | `viewer failure cannot block completion` deliberately aborts both local and remote structure requests and still finalizes six candidates at each viewport                                                                                                  |
| Replay, reset, stale approval, revision and refresh                        | 24 adapter tests; browser journey, interrupted-animation refresh, corrupt-storage and revision tests                                                                                                                                                       |
| Keyboard focus                                                             | Keyboard-only help dialog open/close, forward and reverse focus trap, Escape, focus restoration and visible focus outline asserted in all three viewports                                                                                                  |
| No actual computation, no raw chain-of-thought, simulation marking         | Fixture/stages and component source review; DemoAdapter test spies on fetch and verifies zero calls; browser journey sees no requests outside localhost. No production backend modules are imported. No code calls a model, shell, compute or GPU service. |
| Restrained visuals, original identity                                      | 12 Playwright screenshots (four screens × three viewports), visually inspected; `Brand.tsx` and own CSS. All ten supplied visual references were inspected; none are imported into the app.                                                                |
| Existing backend unchanged                                                 | All changes are confined to the new independent local frontend repository. Parent tracked diff is empty. No SSH or backend mutations in this assignment.                                                                                                   |
| Production output                                                          | `scripts/smoke-production.mjs`, `validation/production-smoke.txt`: built bundle completes the full journey with a real reference viewer and zero external requests/page errors                                                                             |

## Visual review

Reviewed Landing, Site, Pilot and Candidates at 1440×900, plus Site/Candidates at 1366×768 and Candidates at 1728×1117. Additional screenshots for all four screens at all three sizes are included. The navigation follow-up also verifies Home, fresh drafts and resume, with screenshots at 1440×900 and 642×948. Landing was also inspected directly in the Codex in-app browser. At shorter desktop heights, conversation, workflow and context panels scroll independently while the decision bar remains accessible. There is no horizontal page overflow at the tested desktop sizes.

## Remaining P1 gaps

None in the supplied P1 checklist. Candidate changes select a distinct view of the shared 1MEL reference, not a generated structure. Actual DSH integration, real scientific validation, collaboration and cross-browser/mobile certification remain explicitly outside this prototype's scope.

## User-requested project sidebar extension

The original P0/P1 scope remains closed. The added outer project navigation preserves the inner phase workflow. Independent goals, notes, choices, approvals and finalists; per-project reset/replay; legacy single-demo import; project rename/switch/refresh; same-phase stale approval rejection; desktop collapse and narrow drawer behavior are covered by adapter and browser regressions. See `REPORT.md` and the `projects-*` screenshots. Project persistence is local Demo data only.

## Three-destination navigation extension

The latest user-approved structure keeps all UI copy in English and the white/violet visual style. The former sidebar project list is now a dedicated Projects page. Agent Workspace retains the research layout and has a current-project selector. Compute & Queue explicitly discloses no real compute connection; it lists only simulated Pilot/Scale activity already reached by projects.

`e2e/platform.spec.ts` covers exactly three navigation destinations, empty and populated project states, creation/search/rename, independent project notes and Site choices, project switching/refresh, abandoned draft navigation, browser Back/Forward, compute filters and owning-project links, and narrow-window layouts. Adapter regression covers event-derived counts, paused inactive projects, snapshot persistence, and per-project replay/reset. Original scientific journey and linked-context regressions remain in the suite. See REPORT.md for final results and current screenshots; earlier sidebar screenshots are retained as historical design evidence.
