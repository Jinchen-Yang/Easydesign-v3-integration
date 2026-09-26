# EasyDesign Workbench prototype — closure report

**2026-09-17 update:** The optional, project-scoped Lab Order UI is documented in [LAB_ORDER.md](LAB_ORDER.md), with separate validation logs and screenshots. It adds local draft preparation and a blocked submission preview after Candidates. The September 13 report and review ZIP below describe the earlier platform-navigation delivery.

Date: 2026-09-13. **The latest user-approved UI keeps the white/violet style and English copy, with Projects, Agent Workspace, and Compute & Queue as its three main destinations.** All original P0/P1 capabilities remain available; Projects now replaces the bare-URL goal landing as the default entry, with the goal composer inside Agent Workspace. The complete Goal → Target → Site → Design → Pilot → Scale → Candidates journey is runnable, with explicit approvals and deterministic **8 → 24 → 6** results.

## Source and delivery

```text
Source: /Users/knitua/Documents/Easy Design/ui-prototype-20260913/ui-workbench
Branch: codex/ui-workbench-prototype-20260913
Dev URL: http://127.0.0.1:13180/
Production preview: http://127.0.0.1:13181/
Review ZIP: /Users/knitua/Documents/Easy Design/deliverables/EasyDesign-Workbench-full-review-20260913-platform-navigation.zip
```

This is an independent frontend repository. The existing DSH UI on port 13080 and all existing EasyDesign scientific repositories are unchanged. No SSH, model API, scientific backend, shell computation job or GPU job was used by the prototype. No scientific migration work was undertaken.

The ZIP includes the entire frontend project, lockfile, full source, tests, specifications, raw test logs, screenshots, public structure data, built `dist`, original input pack and Git bundle. It excludes reinstallable dependencies, browser caches, ephemeral test traces and private environment files. A file-by-file integrity manifest accompanies the archive contents. This is a full review package, not a patch package.

## Reproduce

Use Node.js 22+ and pnpm 11.19.0. The exact local-runtime PATH command is in the README if this Mac's default terminal cannot find Node/pnpm.

```bash
cd '/Users/knitua/Documents/Easy Design/ui-prototype-20260913/ui-workbench'
pnpm install --frozen-lockfile
pnpm dev
```

In another terminal in the same directory:

```bash
pnpm build
pnpm test
pnpm exec playwright install chromium
pnpm test:e2e --workers=2
pnpm test:production
pnpm format:check
```

`pnpm test:production` owns and stops a temporary preview server on port 13181. For an interactive build preview, use `pnpm preview` instead. Playwright reuses the dev server locally; CI should start with port 13180 free.

## Architecture delivered

React/TypeScript/Vite frontend with dedicated Projects and Compute pages around the existing Agent Workspace, which retains separate workflow, conversation, scientific context, viewer and decision components. `WorkbenchAdapter` is the sole product data/action boundary. `DemoAdapter` provides deterministic events, approval gates, editable choices and versioned localStorage replay. `DshAdapter` is an explicit unavailable stub with stage mapping for later transport integration. The lazy 3Dmol viewer uses the bundled public 1MEL reference and gracefully degrades if structure/WebGL loading fails.

The supplied fixture remains byte-for-byte unchanged. Target mmCIF label C maps to PDB author chain L; VHH uses author chain A. This is documented in the product/reference metadata. All candidates share that reference complex; selecting a candidate changes the selected metrics and view, not the underlying reference coordinates. Simulated scores, residue groups, candidate sequences and outcomes are labeled throughout.

## Validation results

Environment: macOS, Node 24.19.0, pnpm 11.19.0, Playwright 1.51.1 / Chromium 134 (build 1161). Browser tests use software WebGL for reproducible automation.

| Validation                                            | Result                                                                   | Evidence                                                                                        |
| ----------------------------------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| Frozen-lockfile install                               | Passed                                                                   | [install log](validation/install.txt)                                                           |
| TypeScript + production build                         | Passed                                                                   | [build log](validation/build.txt)                                                               |
| Adapter/state unit regression                         | **24/24 passed**                                                         | [unit log](validation/unit-tests.txt)                                                           |
| Browser journeys, refresh, failure, keyboard/revision | **24/24 passed**, 1.7 minutes                                            | [browser log](validation/browser-tests.txt), [JSON results](validation/playwright-results.json) |
| Built production full journey                         | Passed; actual viewer ready, 8/24/6, no page errors or external requests | [production smoke](validation/production-smoke.txt)                                             |
| Formatting                                            | Passed                                                                   | [format log](validation/format.txt)                                                             |
| Visual review                                         | Passed at requested desktop sizes                                        | [screenshots](screenshots/)                                                                     |

The browser suite exercises full SPA navigation, all approvals, Site A/B/C highlight changes, chain selection, comparison/editing, tool expansion, pilot/candidate selection, stars, finalization, reset, replay, refresh during an animation, corrupted storage recovery, follow-up goal preservation, keyboard focus trap/restoration and a reversible design revision. The failure scenario blocks both structure sources and still completes the full journey. The normal full journey and production smoke make no requests outside localhost and record no page errors.

A switching regression found duplicate React keys on sibling conversation/context panels during implementation; their keys are now separately namespaced by project, and the regression asserts one panel of each type, an empty new-project composer, and no console/page errors. The final results above supersede the intermediate failure log retained as `validation/project-sidebar-before-fix.txt`.

The build has one retained upstream 3Dmol string-callback `eval` warning; the application does not invoke that helper. See [third-party notes](THIRD_PARTY.md). It does not affect the demonstrated viewer or completion.

## Required screenshots

| Screen     | 1440×900                                         | 1366×768                                         | 1728×1117                                        |
| ---------- | ------------------------------------------------ | ------------------------------------------------ | ------------------------------------------------ |
| Landing    | [Image](screenshots/landing-desktop-1440.png)    | [Image](screenshots/landing-desktop-1366.png)    | [Image](screenshots/landing-desktop-1728.png)    |
| Site       | [Image](screenshots/site-desktop-1440.png)       | [Image](screenshots/site-desktop-1366.png)       | [Image](screenshots/site-desktop-1728.png)       |
| Pilot      | [Image](screenshots/pilot-desktop-1440.png)      | [Image](screenshots/pilot-desktop-1366.png)      | [Image](screenshots/pilot-desktop-1728.png)      |
| Candidates | [Image](screenshots/candidates-desktop-1440.png) | [Image](screenshots/candidates-desktop-1366.png) | [Image](screenshots/candidates-desktop-1728.png) |

At shorter heights, the content panels scroll independently so the action bar stays accessible. The in-app browser Landing was also inspected directly.

## Earlier project-sidebar follow-up (superseded navigation)

The user requested the old UI's expandable project navigation inside the new white Workbench. The outer rail now expands into a project list with New Design, Home, per-project phase/status/goal preview, selection and rename controls. The existing inner Workflow/Agent Tasks, conversation, Scientific Context and decision bar remain project-specific. Desktop can keep the list open or collapse to 58 px; narrow screens use an overlay drawer with Escape and outside-click dismissal.

New designs create independent local project records rather than replacing the previous run. Goals, sent messages, site approvals, completion, stars and candidate selection survive switching and refresh. Only the active project's deterministic animation runs. Approval IDs include project identity, preventing an action from one project being accepted at the same phase of another. Reset/replay affect only the selected project. Legacy single-demo data is retained and imported as the first project when needed. No model API or server project integration is added.

Dedicated regression covers three named projects, same-phase stale approvals, switching mid-animation, independent notes and finalists, rename/refresh, selected-project reset/replay, legacy import, invalid actions and narrow-drawer keyboard interaction. Screenshots: [three projects at Home](screenshots/projects-home-desktop-1440.png), [project-specific Site review](screenshots/projects-site-desktop-1440.png), [narrow sidebar](screenshots/projects-narrow-642.png).

The navigation behavior requested earlier remains covered: fresh drafts are visibly empty/focused and Home preserves progress. Its initial single-run replacement behavior is superseded by this explicitly requested multi-project extension.

## Scientific context link follow-up

The reported link set the selected phase and the panel's open flag, but did not move focus or reset the panel's independent scroll position. When that phase was already visible, the click could appear to do nothing. Each explicit context request now reveals the correct phase, returns its context to the top, and focuses the panel with a restrained violet border/header highlight. Changing phases also resets the context scroll position. This is UI navigation only; project data and approvals remain unchanged.

Tool-card links and summary links identify the controlled panel. On narrow screens the context header control uses the same reveal behavior; the close button and Escape restore focus to the original link/control. Project switching does not inherit an old focus request. The viewer, fixture, adapter and backend boundaries are unchanged.

The dedicated [browser regression](../e2e/context-links.spec.ts) checks repeated clicks after scrolling, correct Site content, visible focus, drawer opening at 1180 px and 642 px, keyboard reopening, close/Escape focus restoration, a ready molecule and unchanged saved project data. An initial run reproduced the missing focus on the old behavior. The final [targeted run](validation/context-links.txt) passes all three desktop configurations, each exercising both narrow sizes. Screenshots: [desktop context focus](screenshots/context-link-desktop-1440.png), [narrow context drawer](screenshots/context-link-642-desktop-1440.png).

## Three-destination English navigation

The latest request replaces the sidebar's long project list with three fixed destinations while retaining the restrained white/violet design:

- **Projects** is the default entry and dedicated project center. Empty state, new project, name/goal search, project cards with current stage/status, rename and Open workspace use existing adapter project records.
- **Agent Workspace** retains the scientific product layout. The current-project selector switches all project context together. New project opens a blank, focused goal composer. Returning from Projects or Compute retains the selected project's goal, decisions and messages.
- **Compute & Queue** shows an explicit unconnected compute service and a filtered list of simulated Pilot/Scale runs. Only stages actually reached by project approval are listed. Each row opens its owning project's current workspace; viewing rows never approves a decision.

`#projects`, `#workspace` and `#compute` support browser Back/Forward and refresh. The local project storage format, original fixture, source references, scientific backend and DSH boundary are unchanged. The compute snapshot is only a read-only projection of existing demo stage events, with no API call, scheduler, GPU sampling or additional job persistence. Inactive incomplete demo animations appear paused. Reset/replay affect only the selected project's current activity.

The new adapter regressions cover prepared counts, paused projects, reload, read-only snapshot access and scoped reset/replay. Browser platform regressions cover three navigation entries; project search/rename/create/switch; preserved Site C and notes; abandoned drafts; direct project selection; route history; compute filters and project links; and narrow-window layouts. An initial implementation test caught a new-project composer remaining open after submission; the draft flag is now cleared on successful creation. `platform-initial.txt` is intermediate evidence, superseded by the passing targeted and final full results.

Current screenshots:

| Page            | Desktop                                                        | Narrow window                                                       |
| --------------- | -------------------------------------------------------------- | ------------------------------------------------------------------- |
| Projects        | [Project center](screenshots/project-center-desktop-1440.png)  | [Projects](screenshots/project-center-narrow-desktop-1440.png)      |
| Agent Workspace | [Site workspace](screenshots/agent-workspace-desktop-1440.png) | [Navigation drawer](screenshots/navigation-narrow-desktop-1440.png) |
| Compute & Queue | [Demo activity](screenshots/compute-queue-desktop-1440.png)    | [Demo activity](screenshots/compute-queue-narrow-desktop-1440.png)  |

The corresponding images at 1366 and 1728 px are also included. Earlier sidebar screenshots are retained as historical design evidence; the `project-center-*`, `agent-workspace-*`, `compute-queue-*`, and `navigation-narrow-*` images describe the current product.

## Remaining P1 gaps and stopping boundary

**No remaining items in the supplied P1 checklist.** DSH integration, real model/scientific execution, generated candidate-specific structures, scientific validity of fixture scores, multi-user persistence and mobile/cross-browser certification are outside this delivery. The requested frontend prototype is complete; no later architecture/scientific phase is started.
