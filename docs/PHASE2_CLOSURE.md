# Phase 2 acceptance — Phase 2.2 review, 2026-09-11

**FAIL / NOT FROZEN. Phase 3 and Phase 4 have not started.**

Phase 2.2 implements selected-source corpus/scoped retrieval, trusted canonical-reference
proposals routed to old Stage 01/Gate 1, and native expert strategy import routed to the existing
compiler/validator/Judge/Gate 3. Offline tests cover these contracts. The required real-model
acceptance is still incomplete.

The first soluble live case stopped before Gate 1: Target requested deep UniProt acquisition
without selecting the source. Runtime correctly refused, but the prerequisite error terminated
the Agent instead of permitting bounded correction. There were four real model calls and no
scientific job. The 13,348-character peak is from an early failed path and cannot establish
end-to-end evidence-context improvement. GPCR and standard/native Gate 3 cases were not run
after the critical-failure stop.

The full technical closure, measurements, validation ledger, known limits, narrow legacy-facade
bug exception and next required repair are in **`PHASE22_UNBLOCK_CLOSURE.md`**. The exact CatMaster
source review is in `PHASE22_CATMASTER_EVIDENCE_PATTERN_REVIEW.md`, and capability statuses are in
`V2_TO_V3_CAPABILITY_PARITY_MATRIX.md`.

Final full integration regression 012: **PASS — 730 passed, 11 skipped, 0 failed/error**
(741 collected, 989.13 s). All 115 Agent unit tests passed, including 9 multi-turn/resume/
ownership tests and 15 new Phase 2.2 tests. The 11 skips are optional PyMOL and opt-in live
tests; the separate live acceptance remains FAIL. Repository/static checks, mypy (184 files)
and final wheel verification passed.

No `easydesign-v3-phase2-frozen` tag was created. Existing Phase 1 frozen and Phase 2 candidate
tags are unchanged. Production `/data/Easydesign` remains at
`c93da74660639c095d3de252cddb88a00fd3671d`. Core mapping, stages, backends and old compute recovery
are unchanged; the separately documented native first-pilot facade bug is the sole non-Agent
production source exception.

Prior reports are preserved: `PHASE21_CLOSURE_20260911.md` and
`PHASE2_CLOSURE_20260911_BASELINE.md`. Their results are historical, not current acceptance.
The review deliverable is the full repository and Git history with evidence, not an incremental
file package. This review commit is not a frozen scientific milestone.
