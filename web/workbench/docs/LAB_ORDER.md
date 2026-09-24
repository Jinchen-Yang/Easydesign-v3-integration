# Lab Order UI — 2026-09-17

User-approved addition to the standalone frontend, in the existing source tree and branch. The scientific repositories and historical DSH UI are untouched. The provider document was used to understand request fields; no provider API is called.

## Open the page

Run `pnpm dev` and open `http://127.0.0.1:13180/#workspace`. Open or complete a project through **Finalize panel**, then choose **Prepare Lab Order** or **Lab Order** in Workflow. Existing completed projects are compatible. New projects must reach finalization normally; there is no automatic approval or order submission.

The three platform destinations remain Projects / Agent Workspace / Compute & Queue. Workflow adds the optional Lab Order entry after Candidates. Main and subordinate labels use checkmarks with pending/completed styling. The sidebar's Samples / Specs / Review and the central numbered Samples / Requirements / Review tabs are synchronized.

The central page retains the approved title/subtitle, Design Scientist disclosure, full candidate rows, sequence-readiness labels and detailed requirements form. The Order Summary sits to the right on desktop and below the form in narrow windows. The bottom action bar stays available while the form scrolls.

## Behavior and boundary

- The initial selection uses starred finalists when present, otherwise the six finalists; the user can change it. Pilot candidate IDs cannot enter an order draft.
- Format, amount with units, host, buffer, example delivery/billing profile, requested date and PO reference are editable. Advanced fields include SDS/SEC purity, endotoxin, concentration and additional packaging/delivery requirements. All entered requirements appear in Review.
- Input changes autosave through `WorkbenchAdapter.saveLabOrder`. Save Draft also retains the draft explicitly. Samples, fields and current step survive refresh, project switching and reopening the same project.
- Changes to samples or requirements invalidate the review acknowledgement. Navigation alone preserves it. Missing selection or required preparation fields blocks forward confirmation; it does not hide edit/review tabs.
- Preview confirmation opens a native accessible dialog with Escape/focus restoration. **Request Quote is disabled.** No credentials, remote address IDs, full expression sequences, transport or submission method are supplied. The sample profile is illustrative.
- All candidate sequences remain truncated demo previews. Selecting VHH-Fc does not silently append an Fc sequence. No synthesis, expression, functional testing, payment or real order occurs.
- Price and turnaround remain unconfirmed. Quotation submission, acceptance and production authorization still require agreement with the provider before real integration. No granular lab progress or assay result is invented.
- The draft is an optional field in the existing project envelope; old projects need no migration. A malformed draft is discarded without losing the scientific panel. Reset/replay clears only the selected project's draft. Storage remains browser-local with the existing in-memory fallback and no cross-tab merge guarantee.
- There is no new scientific stage, scheduler, DAG, compute job, server storage or backend dependency. Existing PHASES, scientific fixture and DSH phase mapping retain their seven-stage meaning.

## Source

- `src/domain/labOrder.ts`: bounded draft contract, validation, initial finalist selection and preparation progress.
- `src/features/lab-order/LabOrderPage.tsx`: editable form, summary and preview dialog.
- `src/styles/lab-order.css`: scoped desktop/narrow styling.
- `WorkbenchAdapter` / `DemoAdapter`: per-project draft action and persistence; `DshAdapter` rejects the unconfigured operation.
- App / Workflow / DecisionBar: explicit entry, synchronized navigation and project restoration.

## Validation

Exact commands from this directory:

```bash
pnpm test
pnpm build
pnpm test:e2e
pnpm test:production
pnpm format:check
```

Current run results are recorded in `validation/lab-order-*.txt`. Browser coverage includes the full original 8 → 24 → 6 journey and the added lab preparation, field retention, project isolation, acknowledgement invalidation, confirmation keyboard behavior, narrow-screen navigation and absence of external requests. Production smoke also exercises draft creation, confirmation blocking and reload.

Completed results: **27/27 state tests**, **30/30 browser tests** (4.7 minutes), successful TypeScript/production build, successful production smoke and a clean formatting check. Browser acceptance covers 1366×768, 1440×900 and 1728×1117, with added 642/480 px lab navigation checks. Screenshots were visually inspected at all three desktop sizes and in the narrow layout. The build retains the existing upstream 3Dmol warning documented in THIRD_PARTY.md.

The browser regression caught and resolved two issues during development: native select/textarea labels could include field contents after reload, and project selection could overwrite a restored lab view with Candidates. Controls now have stable accessible names, and reopening uses the selected adapter snapshot. These cases pass in the final suite.

Screenshots: `screenshots/lab-samples-*.png`, `lab-requirements-*.png`, `lab-review-*.png` and `lab-narrow-*.png`. The dated September 13 review ZIP in the original report predates this addition; it is not a delivery of the current changes.
