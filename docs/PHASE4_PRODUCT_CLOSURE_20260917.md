# Phase 4 product closure — 2026-09-17

Status: implementation complete; current-mainline real-model acceptance and full protected
regression are pending. This document is updated with observed results before closure.

Starting authority: `35a0ae231aa07001592ffc1c0562468814a52552`, the current Phase 3 product
branch, including Ranking Capacity Hardening. The older integration worktree is historical.
Worktree: `/data/easydesign-worktrees/v3-phase4-product-20260917`.
Branch: `codex/easydesign-v3-phase4-product-v1`.
Original source worktree and scientific history remain unchanged.

## Product boundary

Scale shares the existing Pilot native evidence/filter adapter. Each run retains its own
actual BoltzGen profile, rule values, decisions and provenance. Complete native PASS is
eligible without AFO; complete native FAIL is evaluated but unranked; missing evidence
is operational and prevents premature finalization. AFO is optional enrichment. Legacy
Stage 07 scores remain in their historical/advisory path and never redefine native PASS.

Gate 4 binds exact strategy IDs, counts and upstream identities. New approvals explicitly
record the native policy; old approval serialization and legacy behavior remain compatible.
Immutable batches preserve successful evidence through failure/restart/replay. All PASS
rows compete globally. Exact sequence deduplication affects the bounded review shortlist,
while all source rows remain in the audit pool. Cross-Arm coverage is review visibility,
not a final panel quota or proof of pose diversity.

Final Selection receives shared context/profiles and compact metric rows for up to 30
shortlisted candidates. Full facts remain in Runtime. It proposes primary/backup panels;
Scientist Gate 5 owns approval. Normal and interrupted-card recovery paths do not require
Judge. Optional review failure cannot remove the card or bypass a hard runtime conflict.

## Validation plan and preserved evidence

The latest real NK2R Phase 3 proposal is copied into an isolated validation workspace,
with exact source hashes. Its three selected strategies span two Arms with five candidates
each. The full proposed allocation remains unchanged: 15 candidates, nine validation
batches, using existing structures/native evidence. There is no new generation.

Preparation receipt: `runtime/tmp/phase4-precomputed-prepared-01.json`.
Source-copy receipt: `runtime/tmp/phase4-precomputed-copy-01.json`.
The prepared pool contains 3 native PASS and 12 native FAIL, all retained; the shortlist
contains 3 candidates. Controlled batch failure/recovery and duplicate receipt replay pass.
The initial compact Final Selection packet is 18,406 characters before prompt/schema.

Targeted tests cover no-AFO eligibility, optional enrichment, native FAIL, incomplete
evidence, separate profiles, source tampering, global competition/dedup, restart/replay,
Judge absence/failure, exact Scientist panel choice, card recovery and 30-row repair capacity.

## Scope limits

This assignment validates product integration, not biological performance. Precomputed
Pilot evidence is explicitly labeled validation-only Scale-like input. It is not a new
Scale result. No production-scale BoltzGen, AFO sweep, experiment or ordering is performed.
Pose/contact-mode clustering, biological fitness optimization and UI changes are excluded.
