# EasyDesign Workbench — Codex Assignment

Treat this as a focused autonomous frontend/product engineering assignment.

## Objective

Build a runnable **Latent-Y-inspired, white, minimal EasyDesign Workbench prototype** that demonstrates the full user journey:

**Goal → Target → Site → Design → Pilot → Scale → Candidates**

For this assignment, **UI, interaction, flow, structure visualization, state transitions, and polish matter more than scientific correctness**.

Do **not** attempt to make the scientific pipeline real in this round.

The attached package is the product specification and visual reference. Read, in order:

1. `00_README_FIRST.md`
2. `01_UI_PRODUCT_SPEC.md`
3. `02_DEMO_FLOW_SPEC.md`
4. `03_ADAPTER_CONTRACT.md`
5. `05_ACCEPTANCE_CHECKLIST.md`
6. inspect `references/latent-y/`
7. inspect `references/current-easydesign/`
8. inspect the selected `references/dsh-ui/` packages only as integration reference

## Critical scope freeze

### Do

- create a **new maintainable frontend source tree**;
- use a deterministic demo fixture;
- build the full browser flow;
- implement the left workflow, center conversation/research trace, right scientific context, and bottom decision bar;
- use a real molecular viewer when reasonably possible;
- keep a clean adapter boundary so the fixture can later be replaced with a DSH/EasyDesign adapter;
- create tests and screenshots;
- make the page feel as clean and calm as the supplied Latent-Y screenshots.

### Do not

- do not refactor EasyDesign scientific kernel;
- do not migrate v3 architecture;
- do not run real BoltzGen/AFO/Protenix;
- do not require a GPU;
- do not make scale large — demo scale is exactly 24 candidates;
- do not hand-edit the historical generated `ui-plugin/lib/client.js` as the main implementation;
- do not expose raw chain-of-thought;
- do not expose hashes/manifests/checksums in the normal UI;
- do not clone Latent-Y branding, logo, wording, or assets.

## Recommended implementation shape

Prefer a fresh TypeScript + React frontend with a normal source layout, e.g.:

```text
ui-workbench/
  src/
    app/
    components/
    features/
      workflow/
      conversation/
      context/
      decisions/
      viewer/
    adapters/
      WorkbenchAdapter.ts
      DemoAdapter.ts
      DshAdapter.ts        # stub only for now
    demo/
    styles/
  tests/
  package.json
  vite.config.*
```

If the current repository already has a clearly better compatible frontend build convention, you may adapt to it, but keep the same architectural boundary.

The first milestone must run standalone in development mode. Do not block P0 completion on deep DSH integration.

## Demo data

Use `demo/demo-fixture.json`.

Demo project:

- name: Lysozyme VHH
- badge: UI Demo Fixture
- reference structure: PDB 1MEL
- target: hen egg-white lysozyme
- expected target chain: C
- VHH chain for final complex visualization: A
- UniProt display: P00698

If network is available, load 1MEL in the molecular viewer.

If loading the remote structure fails:
- do not block the workflow;
- show a well-designed viewer fallback state;
- preserve the viewer component API;
- continue the demo.

Do not silently reinterpret mock residue sets or scores as scientific truth.

## Interaction specification

### Landing

Match the supplied Latent-Y visual hierarchy:

- large whitespace;
- EasyDesign name/logo mark;
- one centered natural-language input;
- minimal surrounding UI.

Default example prompt:

`Design a VHH binder against hen egg-white lysozyme and prioritize a compact accessible epitope.`

Submitting transitions into the Workbench.

### Workbench

Use four visual zones:

1. very narrow app rail
2. workflow/task column
3. conversation/research trace
4. scientific context

At decision points, show a bottom action bar.

### Workflow labels

Exactly:

- Goal
- Target
- Site
- Design
- Pilot
- Scale
- Candidates

Do not use `prepare`, `strategize`, or `select` as the primary visible labels.

### Conversation

Render:
- user messages;
- short Design Scientist summaries;
- collapsible tool cards;
- specialist activity;
- warnings/completion.

Render **high-level rationale only**. Never render hidden model reasoning / chain-of-thought.

### Scientific Context

Change the whole right panel by phase.

Especially important:
- Target: target structure and identity
- Site: A/B/C site comparison and interactive highlight
- Pilot: 8 candidates
- Scale: 24 candidates / 3×8 batches
- Candidates: 6 finalists with selectable structures/metrics

### Demo state machine

The flow must pause for explicit user actions:

- Approve target
- Approve Site B
- Approve design
- Promote pilot
- Finalize panel

Scale may auto-complete after a short deterministic animation.

### Replay

Implement:
- Reset
- Replay demo
- Skip animation

## Visual style

Use the supplied Latent-Y screenshots as the primary aesthetic reference.

Desired qualities:
- white / very light canvas;
- restrained violet accent;
- thin neutral borders;
- soft rounded corners;
- almost no shadow;
- lots of whitespace;
- compact scientific typography;
- no neon gradients;
- no black/dark main theme;
- no giant dashboard metric cards;
- no “AI startup” visual clichés.

Use EasyDesign identity, not Latent-Y identity.

## Existing EasyDesign code

The attached `references/current-easydesign/ui-plugin/` is useful because it already contains:
- current phase/task concepts;
- current project snapshot logic;
- current tool metadata;
- current host bridge;
- current artifact viewer serving;
- current specialist review concepts.

Treat it as an integration reference, not as the place to keep adding UI code.

The selected `references/dsh-ui/` packages show how the installed DSH renders conversation, tools, trajectory, layout, theme, workspace and subagents. You do not need to reproduce all of DSH for the standalone P0 prototype.

## Adapter requirement

The UI must depend on a `WorkbenchAdapter`, not directly on fixture JSON.

Implement `DemoAdapter` now.

Create a typed `DshAdapter` stub or mapping note for the later connection.

The future replacement of DemoAdapter with DshAdapter must not require redesigning page components.

## Testing

Use the repository's available browser/UI testing tools. If none exist, add a lightweight Playwright smoke flow if practical.

At minimum test:

1. landing loads
2. submit prompt
3. Target approval
4. Site B approval
5. Design approval
6. Pilot promotion
7. Scale completion
8. Candidates finalization
9. reset/replay

Also test at 1366×768 and 1440×900 if screenshot tooling permits.

## Definition of done

`05_ACCEPTANCE_CHECKLIST.md` P0 must be fully closed.

Do not return control merely because of an intermediate dependency, CSS, viewer, or build issue. Diagnose and repair autonomously.

Only return after:
- the app is runnable;
- the full demo can be completed from landing to final candidates;
- P0 acceptance is checked;
- tests have run;
- you provide the exact commands and paths;
- you provide screenshots for Landing, Site, Pilot and Candidates.

If an external dependency blocks the molecular viewer, degrade the viewer gracefully and finish the rest of P0 rather than stopping the assignment.
