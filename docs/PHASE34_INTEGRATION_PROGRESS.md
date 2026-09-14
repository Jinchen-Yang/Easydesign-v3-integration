# Phase 3/4 integration — active engineering record

This assignment forward-ports downstream capability onto the current Phase 2
architecture. It does not merge the historical donor branch or grant scientific
approval to any existing project.

## Authority recorded before implementation

- Integration base: `fce5d886849edf575ec1765f7226064291857d49`.
- Base branch: `codex/easydesign-v3-phase2-4`; verified clean.
- Donor: `07d2a6a24d1a3d622f01ac58d3e983aafbcbd3e4` on
  `codex/easydesign-v3-phase34`; its untracked `archives/` is untouched.
- Integration branch: `codex/easydesign-v3-phase34-integration`, created directly
  from the base above on 2026-09-15.
- Current Phase 2 wins: ranked Site selection, Judge resilience, GPCR templates,
  verified intracellular/transducer exclusions, scientific authority and budgets.

## Required milestones

1. Forward-port standalone downstream contracts, projections and validation tools;
   reconcile shared steering without changing ranked Site behavior.
2. Bind current Gate 3 approval to Pilot authority, immutable arm hypotheses,
   execution scope and current Target/Site/Design/Pilot-plan identities.
3. Add one Pilot Diagnosis Specialist and one Final Selection Specialist to the
   existing Harness, with compact independent critique and visible unavailable review.
4. Implement deterministic Gate 4 routes, resumable global Scale evidence and Gate 5
   selection/handoff authority; no autonomous multi-Pilot loop.
5. Validate contracts, replay, 50k synthetic pool, bounded real backend micro chain,
   frozen E2E and regression/integrity. Update Phase 3/4 closure documents with results.

## Execution limits

Development approval permits bounded micro validation and synthetic steering only.
Existing pending scientific cards remain pending. Validation evidence cannot authorize
formal scientific promotion, production compute, ordering or experiments. All packages
created by validation retain `validation-only-not-authorized-for-experiment`.

## Initial inspection

The donor includes useful standalone data contracts, Stage 04–07 projections, global
pool/replay/stress code. Its shared ledger only partially enables downstream Gates;
it has no real Gate 3 authority producer, no Harness diagnosis/selection specialist,
and no successful true-backend micro run. Those remain required integration work,
not completed acceptance inherited from donor documentation.

## Milestone 1 — downstream foundation and Pilot authority

Forward-ported the five standalone donor modules, three validation scripts and related
fixture/tests. Manually reconciled option selection in the current decision ledger and
CLI, preserving ordinary ranked Site approval and its no-override rule. Gate 3 planning
now has a typed, runtime-produced context carrying every compiled strategy, arm hypothesis,
binding/exclusions, target context and exact execution allocation. A producer verifies a
current explicit human outcome and the existing Design freeze before publishing Pilot
authority; the consumer rechecks that authority immediately before use.

Added small downstream opinion contracts and a bounded model-call adapter using the
existing context guard and persisted model budget. No generation or approval tools are
offered to either scientific role. Judge technical failure retains its classified cause
and readable warnings; a structured runtime-fact conflict cannot become an unavailable pass.

Validation in the isolated integration workspace:

- `runtime/tmp/port-tests-02.log`: 51 passed (donor projections, steering and control-flow).
- `runtime/tmp/authority-tests-02.log`: 5 passed (real Design freeze bridge on synthetic
  project inputs, stale/cross-project/changed-plan rejection, restart and idempotency).
- `runtime/tmp/foundation-tests-01.log`: 22 passed (contract/pool/projection/model tests;
  overlaps part of the earlier suites).
- `runtime/tmp/foundation-ruff-02.log`: PASS.
- `runtime/tmp/foundation-mypy-02.log`: PASS, 41 Agent source files.

The first authority test attempt exposed the compiler manifest metadata envelope; the
reader now validates declared compiled records rather than passing envelope fields into
`StrategyRecord`. The rerun above passed. No scientific kernel change was required.

Still pending: Harness integration, deterministic executable routing, live specialist
validation, real backend micro chain, 50k integration stress, final full regression and
Phase 3/4 closure. This checkpoint is not a completed phase or a scientific approval.
