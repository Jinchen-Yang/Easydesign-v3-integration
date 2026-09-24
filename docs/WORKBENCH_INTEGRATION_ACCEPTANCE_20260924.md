# Workbench integration acceptance — 2026-09-24

## Scope

The accepted Gate-3 backend at
`e0e9a73e2a8cf4fa5fbdbd9c923a45743d843e26` was integrated with the existing
white/violet Workbench without changing its primary layout. The integration adds
the Product API, background command journal, native Runtime adapter, safe progress
projection, Gate controls, verified artifacts and live frontend adapter.

The browser remains a projection. Scientific state, rankings, compiled YAML,
candidate evidence and Gate transitions are owned by the existing v3 Runtime.

## Final verification

| Boundary | Result |
| --- | --- |
| Gate/control-flow + Site + Design + steering + Phase 3/4 + Product regression | **108 passed** |
| Final Product API regression after progress/job reconciliation | **26 passed** |
| Product static analysis | Ruff passed; mypy passed for 11 files |
| Frontend unit regression | **43 passed** |
| Frontend TypeScript, formatting and production build | Passed |
| Original demo browser suite at 1440, 1366 and 1728 px | **42 passed, 3 live-only skipped** |
| Built demo 8 → 24 → 6 production smoke | Passed; no page errors or external requests |
| Fresh live Product browser replay | Gate 1–5 passed; no page errors |
| Python wheel and `easydesign-workbench` entry point | Built and verified |
| `uv.lock` consistency | Passed |

The production build retains the upstream 3Dmol warning about an unused string
callback containing `eval`; application code does not invoke that helper. No other
build or browser error was observed.

## Fresh live acceptance facts

The final live browser run created a new isolated project and exercised real HTTP,
same-origin session authentication, the Product request journal, detached workers,
the native Runtime, all five Gate cards and checksum-verified artifacts. The run:

- selected Site B through ordinary Gate-2 approval;
- preserved the Gate card and revision while answering a read-only Site question;
- projected hotspot residues and the approved Site after reload;
- reached the compiled Design/YAML review at Gate 3;
- reached Gate 4 and Gate 5 using typed synthetic downstream evidence;
- finalized a six-candidate panel with three native pass and three native fail;
- retained production intent of 30 while executing only six synthetic validation
  candidates;
- recorded `authorizes_production_compute = false` and `validation_only = true`;
- produced zero browser page errors.

The replay driver refuses to initialize outside `runtime/tmp/` and uses scripted
providers plus synthetic downstream kernels. It did not call a production model,
launch BoltzGen, reserve a GPU, authorize scientific Scale, execute an experiment
or place a lab order. These results validate transport and product behavior only.

## Robustness findings closed during integration

1. A Gate-1 approval and the succeeding native manifest are separate durable
   writes. A snapshot in that narrow interval now returns a bounded
   `reconciling` view instead of a product-level 500.
2. Native job receipts can remain at `awaiting-human-approval` after a later
   Scientist approval is durably recorded. The UI now reconciles those historical
   receipts with the later Gate authority and does not label them as active work.
3. Raw event names such as `task` or `read_file` no longer dominate the chat/task
   view. The server emits deterministic summaries for specialists, evidence,
   contract validation, Site/Design milestones and Gates while keeping raw model
   and tool payloads private.
4. Runtime polling is serial and request submission is idempotent. A slow model
   call cannot create overlapping browser requests; uncertain transport retries
   retain the exact request identity.
5. The original browser test and production-smoke entry points now select
   `?mode=demo` explicitly, because live mode is the product default.

## Evidence locations

Browser acceptance outputs are intentionally kept outside Git in the local test
workspace. The final fresh live run wrote:

```text
/Users/knitua/Documents/Easy Design/workbench-integration-staging/
  test-results/fresh-product-gates-20260924-02/
```

That directory contains Gate 1–5 screenshots, the final handoff, hotspot rendering,
layout geometry and `product-gates-browser.json`. A separate final layout run is at:

```text
/Users/knitua/Documents/Easy Design/workbench-integration-staging/
  test-results/final-live-layout-20260924-01/
```
