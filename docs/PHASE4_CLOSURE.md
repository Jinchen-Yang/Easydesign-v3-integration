# Phase 4 — integration in progress, not yet closed

Phase 4 is integrated additively onto current Phase 2. See
`PHASE34_EXECUTION_CONTRACT.md` and `PHASE34_INTEGRATION_PROGRESS.md` for authority,
code milestones and detailed validation evidence.

Implemented: Gate 4 allocation binding, persistent resumable batch state, exact-scope
kernel dispatch, global competition, diversity-aware review shortlist, Final Selection,
lightweight Judge, authoritative Gate 5 and validation-only handoff. Native graph tests
exercise revision, approval, STOP and duplicate outcome application. Saved standard/native
strategy control-flow replays pass. No real production Scale was executed.

The 50,000-candidate synthetic disk/restart stress passes with one reconstructed pool,
duplicate-ingestion idempotency and failed/resumable batch recovery. This is solely a
software stress test (`runtime/tmp/phase4-50k-stress-02.json`).

Real DeepSeek v4 Pro Final Selection and Judge each submitted successfully on their first
call over a dedicated synthetic pool: 2,169 and 2,956 provider-reported total tokens.
The resulting Gate 5 package contains two primaries and one backup, status
`validation-only-not-authorized-for-experiment`, and `not-ordered`.
Evidence: `runtime/tmp/phase34-live-final-result-01.json` and
`runtime/tmp/phase34-live-final-usage-01.json`. These calls validate the real model adapter
and handoff contract; the input candidates do not establish biological performance.

Outstanding closure criteria: completion of the shared real backend micro validation,
final frozen native E2E/regression and integrity review. Exact sequence clusters are
currently duplicate groups, not validated structural-diversity clusters. No wet-lab
action or scientific efficacy claim has been made. This is not a final acceptance certificate.
