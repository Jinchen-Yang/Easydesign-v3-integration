# Phase 3 — integration in progress, not yet closed

Current authority is Phase 2 `fce5d886849edf575ec1765f7226064291857d49`.
Integration is on `codex/easydesign-v3-phase34-integration`; donor
`07d2a6a24d1a3d622f01ac58d3e983aafbcbd3e4` was selectively forward-ported.
See `PHASE34_EXECUTION_CONTRACT.md` and `PHASE34_INTEGRATION_PROGRESS.md`.

Gate 3 plan authority, exact-scope dispatch, arm hypotheses, measurement contracts,
native Pilot Diagnosis/Judge and all five Gate 4 route semantics are implemented.
Contract and native graph tests cover explicit approval, revision, restart, idempotency,
unavailable Judge and validation-only evidence. Protected scientific kernels are unchanged.

The isolated NK2R micro project reuses the current selected Site B and three-arm GPCR
Design. All 21 YAMLs passed existing compiler/backend validation. Its first three-candidate
run initially exhausted its bounded GPU wait, then resumed on the same authority and
generated all three candidates. Real AFO 3.1.4 predictions completed. Their full target
has 398 residues while the experimental reference resolves 297; complete-target alignment
RMSDs are therefore unavailable. The v3 adapter retains verified confidence and full-target
clash metrics with explicit missingness, without changing the protected kernel or rerunning
generation. Measurement v2 replay and idempotency pass
(`runtime/tmp/nk2r-micro-measurement-02.json`). No biological conclusion is inferred.

Outstanding closure criteria: frozen real Diagnosis/Judge to Gate 4 and final regression
after the partial-reference correction. No production Pilot or
new scientific approval has occurred. This document is an active status record, not an
acceptance certificate.
