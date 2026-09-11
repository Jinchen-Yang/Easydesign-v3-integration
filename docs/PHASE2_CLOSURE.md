# Phase 2 acceptance — Phase 2.2b review, 2026-09-11

**FAIL / NOT FROZEN. Phase 3 and Phase 4 have not started.**

The source-selection prerequisite is now a typed, bounded correction, separate from fatal
boundary violations and scientific uncertainty. The real soluble Agent used the correction,
selected UniProt P00698, retained the complete source and invoked old Stage 01 identity mapping.
It then terminated while reading pending identity evidence: it supplied sibling JSON field names
as a single nested field path. That navigation error remains fatal in the scoped reader.

There were 11 real model calls, one acquired source (384,043 characters), one corpus document,
3,062 chunks and a peak input of 18,562 characters. Focused retrieval/Evidence Cards and Judge
were not reached. The old Stage 01 job awaits human approval; no approved canonical bundle,
Agent Gate 1 card or Gate 2 was completed. The other real cases were not run after critical stop.
These measurements do not establish end-to-end evidence-context acceptance.

Final full integration regression 004: **PASS — 736 passed, 11 skipped, 0 failed/error**
(747 collected, 877.37 s). All 121 Agent unit tests passed, including 6 new recovery tests
and 9 multi-turn/resume/ownership tests. The skips are eight optional PyMOL and three opt-in
live tests; the separate real acceptance remains FAIL. Repository/static checks, mypy
(184 source files) and final2 wheel verification passed.

See **`PHASE22B_RECOVERY_CLOSURE.md`** for the exact failed request, error taxonomy, bounded repair,
selected_by_user decision, raw metrics, validation/source versions and next required repair.
`V2_TO_V3_CAPABILITY_PARITY_MATRIX.md` retains consequential PARTIAL entries. Earlier
`PHASE22_UNBLOCK_CLOSURE.md` and `PHASE21_CLOSURE_20260911.md` are preserved historical reports.

No `easydesign-v3-phase2-frozen` tag was created. Existing milestones remain unchanged.
Production `/data/Easydesign` remains at `c93da74660639c095d3de252cddb88a00fd3671d`.
This Phase 2.2b patch changes only Agent runtime/contracts and tests/docs. It adds no scientific
kernel, backend, filtering, recovery, identity-engine or native-strategy changes.

The deliverable is the complete repository and independent Git history with raw evidence.
The review commit is not a frozen scientific milestone. Phase 3/4 must wait for complete real
acceptance and capability parity.
