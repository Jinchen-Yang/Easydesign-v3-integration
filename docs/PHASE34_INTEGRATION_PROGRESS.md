# Phase 3/4 integration — completed engineering record

**Current status: ENGINEERING ACCEPTANCE PASS.** See [the final acceptance record](PHASE34_INTEGRATION_ACCEPTANCE.md), [Phase 3 closure](PHASE3_CLOSURE.md), and [Phase 4 closure](PHASE4_CLOSURE.md). The milestone entries below preserve historical intermediate status; their old pending items are resolved by the final closure entry.

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

## Milestone 3 — recovery boundaries and live final review

Milestone 2: `34feb1d42af9fd9c0d584407a1a87fc3976f82b0`.
Scale adapter dispatch/recovery passes (`scale-adapter-tests-01.log`, 1 test).
Terminal prediction exhaustion now preserves verified successful records and missing
outcomes. Other integrity errors propagate. The new test found an invalid producer
attempt label in the adapter; its evidence now uses the actual authority path/role
without claiming a nonexistent Stage 05 attempt. Partial-success/integrity validation
passes (`measurement-tests-04.log`, 1 test).

Native Gate 5 approval and STOP passed (`downstream-guards-tests-01.log`, first two
cases; the third fixture was subsequently corrected). External worker recovery now
invalidates old review authority immediately. Native stale interrupts are retired
without a fabricated Scientist response; new evidence receives a new review. Both
new tests pass (`stale-interrupt-tests-01.log`, 2 tests).

The initial full regression found an upstream CLI factory incompatibility: the Phase 2
path unnecessarily received the new downstream keyword. It now uses the original call.
Existing new-process CLI recovery passes (`target-cli-tests-02.log`, 2 passed, 1 opt-in
live skip). Full regression is running in `integration-full-tests-02.log`. Whole-repo
Ruff, repository structure and mypy pass (`integration-full-ruff-02.log`,
`integration-repository-check-01.log`, `integration-full-mypy-03.log`; 223 source files).

Real DeepSeek v4 Pro Final Selection and Judge each submitted on their first call over
a dedicated synthetic pool: 4,918/6,482 input chars including schemas; provider totals
2,169/2,956 tokens. The two-primary/one-backup Gate 5 package is validation-only and
not ordered. See `phase34-live-final-result-01.json` and its separate usage record.
This verifies SDK/review/handoff behavior, not biological performance. Saved standard
and native replays pass (`phase34-replay-m2-standard.json`, `phase34-replay-m2-native.json`).

NK2R micro worker `job-958e5b5944814abe`, run `pilot-v3-4ada156a63bc109782615809`,
exhausted its approved 600-second GPU wait before generating any candidate. External
processes occupied all devices; the same run remains recoverable. Its actual failure
state was projected successfully (`nk2r-operational-evidence-01.log`). No candidate,
metric result or biological conclusion was fabricated.

Cases 1/3/4/5 receipts and applicable milestone tags remain intact
(`accepted-cases-integrity-01.json`, `accepted-gate3-fixtures-01.json`). All 461 protected
tracked kernel/resource/example files are unchanged from Phase 2
(`protected-kernel-integrity-01.json`). Mainline is clean at `fce5d886`; donor remains
at `07d2a6a2` with only its original untracked archives.

Still required: real generation/prediction/metrics when a GPU is available, frozen
Pilot Diagnosis/Judge/native Gate 4 validation, complete regression and final closure.

## Pilot packet correction before live submission

The actual three-arm/seven-scaffold NK2R packet audit measured 146,873 characters,
so no Pilot model call was made. Repeated compiled evidence/configuration fields are
now factored losslessly into common settings plus per-strategy values; identical target
context is referenced once. The real packet is 47,610 characters, with all 21 compiled
records and target contexts reconstructed exactly (`nk2r-diagnosis-packet-audit-03.json`).
The original authority and full stored Design/Diagnosis DTOs are unchanged. Judge and
coordinator messages no longer repeat the full Design arm payload already in runtime facts.
The preservation test passes (`working-set-tests-02.log`, 1 test).

The mutable-source full test run was interrupted: its three Design restart failures
were the expected Harness fingerprint guard after source files changed between test
turns, not accepted-case failures. The isolated reproduction confirmed the same cause.
Those runs are not acceptance evidence. Source is frozen before restarting regression;
no source edits will be made while that regression runs.

## Real backend completion and partial-reference measurement correction

The frozen `d366a903` full regression completed: 1,197 passed, 11 opt-in skips,
two existing SDK warnings, 2,652.83 seconds (`integration-full-tests-03.log`).
The browser regression passed five checks with two optional historical-report skips
(`web-browser-tests-02.log`). Final Selection and Judge also passed a frozen native
Gate 4→5 validation with synthetic candidates, two primaries/two backups and idempotent
validation-only handoff: three real DeepSeek v4 Pro calls, 8,506 provider tokens,
maximum input 7,538 characters (`phase34-live-native-final-result-01.json`).

NK2R generation completed all three candidates on the original resumed micro run.
The target MSA has 9,330 records and the exact bound target sequence hash. AFO produced
full 398-residue target predictions, but the experimental/reference and generated target
contain only residues 25–321 (297 observed residues). All shared residue identities
agree. The protected complete-target RMSD collector rejected this incomplete reference,
so each of the three exit-zero backend predictions was retried once by the old collector.
No production allocation was executed; all six prediction attempts are retained.

The v3 partial-reference adapter now validates the journaled population, input JSON,
backend command, device, release identity, complete predicted chains and confidence
token identities before retaining the first complete backend product. It does not crop
the full prediction or change the protected RMSD kernel. Confidence and full-target
clashes remain measured; the two alignment RMSDs remain unavailable with explicit reasons.
Future partial-reference collection uses one attempt per candidate, avoiding a repeated
complete-reference error. Failed backend slots and missing metrics remain separate.

Measurement v2 preserves the old evidence and publishes a new immutable prediction
projection. Replaying the saved NK2R outputs passed with 3/3 predictions, explicit RMSD
missingness and no additional backend invocation. Measurement SHA:
`42c425244feabb02bfcf34cbaa3d3e2f508956b9c1461725eb4b23b18e7a25d0`.
The Scale projection adapter also accepted these real measurements without launching
Scale (`scale-real-measurement-projection-01.json`). Six focused tests pass; whole Ruff
and the configured mypy check pass (224 source files). Source was edited only after the
frozen full regression finished. Final post-correction regression/native Gate 4 remain.


## Final closure — frozen implementation and validated handoff

Implementation: `16fdf2519240e29eb67a575b896f347d6b34b75c`.
Closure checkpoint: `checkpoint/easydesign-v3-phase34-integration-complete-20260915`.

Frozen real NK2R measurement replay returns the same v2 hash without any backend call.
Native Pilot Diagnosis submits first try; Judge resolves an unknown fact reference and
an output-limit repair, then completes a CONCERNS review. Four actual DeepSeek v4 Pro
calls use 137,188 provider tokens, maximum input 90,629 characters. Gate 4 is reached with
INCONCLUSIVE and no scientific Scale eligibility. No human choice is synthesized.
The recommendation to run another Pilot remains unapproved.

Final regression covers all 1,212 collected node IDs: 1,201 passed, 11 skipped. Eleven
initial setup errors came from fixture resolution under explicit file-list sharding.
Standard directory collection and exact selection passed all eleven without source
changes (8/1/2 recovered by shard). The original errors and replays are preserved, not
presented as a single clean invocation. The checked manifest records disjoint initial
coverage, each recovery and all final outcomes.

Whole Ruff and configured mypy pass (224 source files). Browser regression is 5 passed,
2 optional report skips. The 50k synthetic disk/restart stress and real-model native
Gate 4→5 validation-only handoff passed. Current Phase 2 mainline remains clean at the
original base, donor remains at its recorded HEAD, all 461 protected files are unchanged,
accepted Cases 1/3/4/5 identities remain intact, and the original NK2R Gate 3 is pending.

No production generation, scientific Scale run, wet-lab order or experiment occurred.
Phase 3/4 engineering acceptance is complete within this scope; no later roadmap work
is started. Detailed results, limitations and evidence hashes are in the acceptance
record and `docs/validation/phase34-integration-20260915.json`.
