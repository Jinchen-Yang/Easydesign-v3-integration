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

## Milestone 2 — native Harness and exact-scope execution

Added `Phase34Runtime`, compiled Pilot Diagnosis and Final Selection nodes, compact
downstream Judge routing and native interrupt tools. CLI downstream scopes are `pilot`
and `handoff`; ordinary `design` retains the current Phase 2 route. The shared scientific
task envelope now accepts Gate 4/5. Gate 4 revisions invalidate the appropriate current
objects, carry diagnosis back to Binder, and retain explicit response identity. A second
Pilot requires a new Gate 3 plan approval tied to the accepted Gate 4 request.

The existing Stage 05 service automatically expands candidates after provisional
thresholds pass. The v3 adapter therefore stops generation at Stage 04 and reuses the
existing prediction and metric kernels on the exact approved population. Its new plan
states no additional generation and independent prediction of execution candidates.
Legacy threshold outputs remain audit evidence. No scientific kernel was rewritten.

The native graph tests now cover STOP, REVISE_SITE, REVISE_DESIGN and
RUN_ANOTHER_PILOT, including restart and explicit next-plan approval. A separate native
graph enters Gate 4 promotion with synthetic evidence, runs Final Selection/Judge,
revises the same panel at Gate 5, creates a new review identity, and approves an
idempotent validation-only handoff. Read scopes avoid repeated nested verification
within one synchronous observation and are discarded before each new operation or
model await; ledger changes invalidate them immediately.

Scale now has an append-only disk batch journal, exact allocation partitioning,
generation/prediction adapter using the same kernels, resumable worker recognition,
namespaced candidate lineage and a true global pool. Worker changes invalidate old
review routing. Failed/unevaluable observations retain operational context. Exact
sequence clusters are an engineering redundancy signal; pose diversity remains
explicitly unverified. A failed Pilot generation can still produce an operational
evidence dossier without invented scores or a scientific failure conclusion.

Latest checks, all under `runtime/tmp/`:

- `runtime-tests-06.log`: 6 passed in 226.08 seconds (native routes and read scope).
- `final-runtime-tests-05.log`: 1 passed in 62.39 seconds (native Gate 4 to Gate 5).
- `model-cards-tests-02.log`: 12 passed (compact/recovery/unavailable review contracts).
- `scale-contract-tests-04.log`: 26 passed (execution recovery, contracts, batch/pool).
- `failure-scope-tests-01.log`: 10 passed (failed worker evidence and validation scope).
- `milestone2-ruff.log`: PASS; `milestone2-mypy.log`: PASS, 52 Agent source files.

The stronger `phase4-50k-stress-02.json` persists 50 batches and 50,000 synthetic
candidates (49,949 evaluated, 51 unavailable), resumes one failed and one incomplete
batch, rejects duplicate ingestion effects, and reconstructs the same pool in a fresh
process reading only disk files. Pool SHA:
`64b582e1f7ce37131c59f46d8b4f3c8fb7d6017e6c67c24fb5c2e6376d21f168`.
The persisted 30-candidate shortlist uses a synthetic cluster cap of two. This is a
software stress test, not a biological benchmark or a measured GPU throughput result.

Backend preparation is isolated in this checkout. AFO 3.1.4 / OpenFold3 P2 is installed
from the verified current release bundle (`runtime/tmp/afo-install-02.log`). BoltzGen
assets were copied and inventory-verified without borrowing another checkout's model
paths; Miniforge was installed from the hash-verified pinned installer. BoltzGen's own
environment installation has passed (`boltzgen-install-03.log`).

An isolated `phase34-nk2r-micro-20260915-01` project reuses verified NK2R input bytes,
the previously selected Site B and the current three-arm GPCR Design. All 398 mapping
rows match the source; all 21 compiled YAMLs pass the existing compiler/backend
validation, retaining 87/87/93 exclusions by arm (`nk2r-design-compile-verification-03.log`).
The original project and its pending Gate 3 remain untouched. A development authority,
not fabricated scientific approval, will permit only a few candidates.

Remaining: bounded real BoltzGen/AFO generation/prediction/metrics, real model role
validation, Scale adapter integration and failure recovery checks, frozen replay/E2E,
final regression, protected-kernel integrity and closure documents. This checkpoint
does not establish Phase 3/4 completion or any new scientific/experimental approval.
