# Autonomous v3 migration — resumed 2026-09-12

Status: Phase 2 repair in progress; no new phase freeze. Baseline efc9bbc8aaf4e12eee719ac42743e7069e09d8f2.
Authority: AUTONOMOUS_V3_ASSIGNMENT_20260912.md. Historical stop-after-first-failure is superseded.
Milestones remain sequential: Phase 2 full regression + five reviewed real goldens, then Phase 3
pilot loop + real backend micro + meaningful synthetic decisions, then Phase 4 tiny real scale +
synthetic 50k stress + Gate 5 handoff. Stop after Phase 4; no storage/Workbench/benchmark expansion.

## Resume context

The authorized branch is codex/easydesign-v3-phase2-4 in the existing worktree. The v2 baseline
and unrelated worktrees remain untouched. Developer context bundle:
533c6120621dd585d0711517f5541a74ab9bc6629871965705faf54658c6d775.
The context command's extra-worktree blockers are historical topology, explicitly retained by
this assignment. Run its verification checks within this branch; do not delete worktrees.

Read architecture/product, Phase 1 freeze, Phase 2.2d closure, five-gate, parity, Golden spec,
contract ownership, state ownership, development Skill/guides and DATA_SAFETY. The pre-existing
compute-bounded master contract was also read; current assignment restates its invariants.
The fixed Golden spec SHA is 96ead11b3f071dce05780dd1f6fba6ee353d2346aa5a53438ac4ef0e8a850a49;
oracle SHA is 2e367355d197d541df7f77b87f6b505659a81997dc79db7a97a0b0e0ff3258c9. Neither may be weakened.

## First repairs

Reproduced the failed focused-card regression before edits (baseline-test001). Added page sizing
after binding metadata, with cursor advancement only over delivered, untruncated cards. An
absent scientific job is excluded from model observation choices until a real receipt exists;
status observation itself remains read-only. Target Skill clarifies prerequisites. No budget,
provider, scientific algorithm, approval authority or compute recovery change.
Validation: targeted002 14 PASS; related004 42 PASS/1 FAIL exposed a new coordinator
observation lookup during Gate 3 Site revision. Restricting the absent-job model-surface check
to its Target owner fixes that regression (targeted006 includes the passing exact test).
Two local development failures in targeted006 (frozen DTO alias normalization and the old
fixed two-card page assumption) were corrected; targeted007 is 19 PASS. Agent mypy20 PASS;
Ruff PASS. Full regression is reserved for phase freeze.

Live003 (phase2-goldens-20260911T170453Z) exited with a recoverable query/cursor mismatch:
Coordinator2 + Target16 calls, 2 full sources and 7 delivered focused cards; the original
no-job loop is absent. The Target changed its question while reusing the exact prior cursor.
Only a verified current-thread, current-source, current-binding cursor with a reworded question
now receives a bounded argument correction. Foreign/unknown/tampered cursors remain fatal. Known owned stale cursors are rejected
without delivering data and receive a bounded instruction to open a current selected view.
The existing two source/projection corrections per execution are reused. PDB identifier/pdb_id
aliases are normalized before frozen DTO creation; conflicting explicit identifiers are rejected.
Tool descriptions clarify evidence need/topic mapping. No successful Golden boundary claimed.

Current-worktree Miniforge install started (miniforge005); installation is separate from Agent
validation and consumes no GPU. Existing scientific installations outside this clone remain unused.

Evidence root: runtime/tmp/autonomous-v3-20260912. Every attempt uses a fresh named log/XML/project;
old source inputs, jobs and failed runs remain intact. Pending actual content-review requests
are inspected by the developer against fixed truth before any scripted fixture Gate response.

## Runtime setup to resolve before backend checks

The historical external validation configuration names another clone's BoltzGen interpreter.
Do not use it for this resumed assignment. Establish and verify a current-worktree installation
for backend checks and later micro execution, using the existing installer/runtime contracts.
No backend has been invoked in this resumed task; source and environment ownership need validation.

## Compute plan

Phase 2: no generation/prediction. Phase 3/4: validation_micro only; minimal backend-legal count,
minimal representative prediction subset, explicit total candidate/batch/GPU-job ceilings before
launch. Preserve requested production plan separately (e.g. 50,000) from tiny execution scale.
Zero passes and tiny between-arm differences are INCONCLUSIVE, never scientific failure or
promotion evidence. Larger scientific decision branches use labeled synthetic/precomputed data.
No production compute, legacy deletion, unapproved real science or wet-lab ordering.

## Evidence navigation refinement

Live009 made Coordinator2/Target7 calls and acquired UniProt + RCSB, then reused an RCSB cursor
after canonical configuration invalidated its binding. Runtime still refuses that old view;
a known owned cursor now produces STALE_EVIDENCE_CURSOR and explicit restart/reselection guidance.
Foreign or unknown cursors and checksum failures cannot use this correction path. The existing
shared two argument/prerequisite corrections and 32 model calls remain unchanged.
Targeted011 24 PASS; Ruff and mypy20 PASS.

Live013 made Coordinator2/Target8 calls. It corrected its question/cursor mismatch successfully,
then tried to read identity_evidence from a source passage page before Target preparation and
exhausted the shared argument-correction limit. This motivated a source-reading improvement:
UniProt corpus now includes a deterministic contiguous identity section with actual accession,
organism, source sequence length, and Signal/Propeptide/Chain annotations in source numbering.
All original fields, response bytes and evidence references are retained; no structure mapping
or biological inference is created. Actual retained P00698 summary is 1,150 characters and
contains canonical 147, Signal1–18, Chain19–147. Targeted014 19 PASS, including exact frozen
source-feature checks and negative conflicting-source aliases. No scientific oracle changed.

Next: rerun the real Phase 2 cases from this source; independently inspect every Gate snapshot.
Do not claim Phase 2 frozen until five cases and full regression pass. Miniforge005 continues
its verified current-worktree download; no GPU jobs have been launched.
