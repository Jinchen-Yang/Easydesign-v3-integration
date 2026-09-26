# Historical Pro edition documentation

This is the preserved Pro README at the fork point. It describes the separate Pro application, not the Easy entry point. For this branch, use the repository README and docs/easy/README.md.

# EasyDesign Workbench — UI prototype

A standalone, white EasyDesign product prototype with three simple English navigation destinations: **Projects**, **Agent Workspace**, and **Compute & Queue**. Follow **Goal → Target → Site → Design → Pilot → Scale → Candidates**, with explicit approvals, a scientist conversation, research/tool trace, and a molecular context panel.

All scientific outputs are deterministic demo fixtures: **8 pilot candidates → 24 scale candidates → 6 finalists**. No model API, DSH service or scientific backend is required or invoked. Optional read-only GPU monitoring uses the local server’s existing SSH connection; it never launches a scientific job.

## Location and quick start

Source on the development machine:

```text
/Users/knitua/Documents/Easy Design/ui-prototype-20260913/ui-workbench
```

This is a new independent Git repository on `codex/ui-workbench-prototype-20260913`. It does not change the existing EasyDesign v2/v3 repositories or the historical generated DSH UI. The existing service on port 13080 is separate.

Requirements: Node.js 22 or newer and pnpm 11.19.0. No credentials or `.env` file are needed. From the source directory (or the extracted `ui-workbench` directory):

```bash
pnpm install --frozen-lockfile
pnpm dev
```

Open **http://127.0.0.1:13180/**. The port is strict: a second server will report that it is already in use rather than silently changing the URL.

On this particular Mac, the installed Codex dependency runtime is outside the normal shell PATH. If `node` or `pnpm` is unavailable, use:

```bash
export PATH="/Users/knitua/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/knitua/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH"
cd '/Users/knitua/Documents/Easy Design/ui-prototype-20260913/ui-workbench'
pnpm install --frozen-lockfile
pnpm dev
```

## Demo walkthrough

1. Open **Projects → New project**, then choose the **Lysozyme · VHH** example and submit. Or open **Agent Workspace** for the default goal.
2. Review the target and approve it.
3. Click Sites A/B/C to compare the highlighted residues. Approve Site B, or deliberately choose another demo site.
4. Review the two design arms, optionally edit the scaffold label, and approve the 4 + 4 pilot.
5. Inspect eight candidates (six pass, two filtered). Promote the pilot, or use **Revise** to return to Design.
6. Watch three batches of eight complete. Choose **Review candidates**.
7. Explore six finalists, switch candidate views, star candidates, and **Finalize panel**.
8. Optionally choose **Prepare Lab Order**. Use **Samples → Requirements → Review** to prepare a local expression request. The left Workflow uses checkmarks and **Samples / Specs / Review** labels; both navigation areas stay synchronized. **Save Draft** retains the draft, and changes also autosave with this project. **Preview confirmation** opens the final review dialog; real **Request Quote** is disabled because this demo has only sequence previews and no connected lab account.

**Skip animation** finishes the current animation and pauses at the next approval. **Replay demo** restarts the original goal. **Reset** returns to Landing. Completed stages remain available in the workflow column. Notes in the conversation preserve the initial goal and do not perform arbitrary scientific work.

**View scientific context** and **Explore … context** open the relevant phase's panel, scroll it to the top and focus it with a violet highlight, including repeated clicks on the current phase. In a narrow window, the panel opens as a drawer; use its close button or **Esc** to return to the link. Viewing context does not approve a decision or change the saved project.

The outer sidebar contains only **Projects**, **Agent Workspace**, and **Compute & Queue**; use the panel icon to collapse it. **Projects** is the dedicated project center: search names/goals, create a project, use the pencil to rename it, or the trash icon at the top left to delete it after confirmation. Choose **Open workspace** to continue a project. Deletion removes only that device’s project, conversation, demo results and lab draft; server files and GPU jobs are unaffected. **New project** opens a blank, focused goal composer; submitting preserves earlier projects. The top **Current project** selector switches workspaces directly. Each project retains its original goal, sent notes, site choices, approvals, finalists, stars and lab request draft. Reset and Replay affect only the selected project. The inner Workflow shows the seven scientific stages plus optional **Lab Order**, which unlocks after panel finalization. Its pending checkmark does not mean an order has been submitted.

**Compute & Queue** can display live GPU resources from Suzhou2: utilization, memory, temperature, power, process counts and driver version. It refreshes every 10 seconds, has manual refresh, and labels retained readings as stale after an error or 25 seconds. The separate **Demo runs** list still shows only simulated Pilot/Scale stages reached through approvals, with project/status filters and links to their workspaces. Real job queues and job submission are not connected; hardware activity is not treated as EasyDesign job ownership or reserved capacity.

To enable monitoring, copy `config/compute.env.example` to `.env.local` without overwriting an existing file, set `WORKBENCH_COMPUTE_SSH_HOST=Suzhou2`, and restart the server. Existing SSH credentials and trusted host configuration must already work. No keys go in the frontend. See [resource monitoring and project deletion](docs/COMPUTE_AND_PROJECTS.md) for setup, boundaries and validation. Without configuration, the demo works normally and the resource section shows “Not connected”.

The three pages use `#projects`, `#workspace`, and `#compute`; browser Back/Forward and refresh retain the destination. The bare URL opens Projects. Existing local projects remain available unchanged. On narrow screens the navigation and scientific context use drawers.

Projects and the selected project are stored under `easydesign-workbench-projects-v1` in this browser's localStorage. An existing `easydesign-workbench-demo-v1` single demo is read as the first project when no project collection exists; its original stored bytes are retained. Refresh restores the selected project and resumes its interrupted animation. Switching projects pauses the inactive UI animation at its event index. These remain independent local lysozyme/VHH demos, not server projects or parallel scientific jobs. Invalid saved data gives a fresh workspace with an explanatory notice. The demo still runs in memory when storage is unavailable.

## Build and test

```bash
# TypeScript + production bundle
pnpm build

# Serve the production build on http://127.0.0.1:13181/
pnpm preview

# Adapter/state regression
pnpm test

# First-time browser installation, then browser acceptance
pnpm exec playwright install chromium
pnpm test:e2e

# Built application smoke (run pnpm build first; port 13181 must be free)
pnpm test:production

# Optional real GPU monitor smoke (SSH configured, build completed; port 13182 free)
pnpm test:resources-live

# Formatting
pnpm format:check
```

Playwright starts the dev server automatically when port 13180 is free, or reuses an existing server outside CI. Stop any existing server before using `CI=1`. Linux CI may need `pnpm exec playwright install --with-deps chromium` to install system libraries.

## Architecture and evidence

- [Resource monitoring and project deletion](docs/COMPUTE_AND_PROJECTS.md)
- [Lab Order UI addition, boundaries and validation](docs/LAB_ORDER.md)
- [Architecture and future DSH boundary](docs/ARCHITECTURE.md)
- [Acceptance checklist with evidence](docs/ACCEPTANCE.md)
- [Closure report and validation results](docs/REPORT.md)
- [Screenshots](docs/screenshots/)
- [Original assignment specifications](docs/spec/04_CODEX_PROMPT.md)
- [Third-party notices and structure provenance](docs/THIRD_PARTY.md)

The review ZIP contains this **entire project**, the production build, tests, screenshots, validation logs, a Git bundle, and the complete supplied input pack. Dependencies are reproducible from the lockfile; `node_modules`, local caches and credentials are excluded. The input pack is for review only and is not loaded by the app.
