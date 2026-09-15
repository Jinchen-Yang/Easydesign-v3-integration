# Phase 3/4 execution contract

This additive contract uses Phase 2 at `fce5d886849edf575ec1765f7226064291857d49`
as authority. Ranked Site Portfolio, Scientist selection of B/C, runtime-owned facts,
GPCR templates/exclusions and lightweight Judge behavior remain unchanged. The donor
is a source of standalone downstream contracts, not an alternative Phase 2 runtime.

## Responsibilities

The existing Runtime compiles, dispatches, predicts, measures, persists and recovers.
The Pilot Ranking & Recovery Specialist interprets the approved arm hypotheses and
native measurements (the historical internal name remains `pilot-diagnosis`). Final
Selection proposes a panel from a global shortlist. Phase 3 Judge is an optional second
opinion; Phase 4 review remains unchanged. Only a persisted Scientist response chooses
a consequential Gate route.
There are no separate generation, prediction, filtering or metrics agents.

`easydesign-agent` accepts `--through pilot` and `--through handoff`; the ordinary
`--through design` scope preserves the Phase 2 path. Both new specialists use the
existing model configuration, SDK, context guard and persisted 64-call execution budget.
They receive one structured submission tool and no execution/approval tools.

## Gate 3 and Pilot

A formal Pilot requires approval of a current Gate 3 card containing the exact Pilot
plan. An older frozen Design that did not include this plan requires a new plan review;
its historical approval is not silently expanded. The authority binds project, Target,
Site, Design, compiled strategies, arm intent, runtime backend policy and allocation.
Every execution checks these identities again. One authority creates one run; process
recovery attaches to that run and verifies its original configuration and worker receipt.

Arm intent retains hypothesis, rationale, changed/held factors, expected result, failure
interpretation, binding/exclusions, scaffold/CDR settings and target context. A micro
projection changes only candidate counts and selected scaffold membership. It does not
change the scientific YAML or replace the approved Site.

`formal-pilot` executes the approved allocation. `validation-micro` requires explicit
trusted harness registration, is limited to six candidates, and has a distinct validation
context with no fabricated Gate 3 card/decision. It is always scientifically INCONCLUSIVE.
Zero passing candidates in a micro run cannot establish Site or Design failure.

The default Design budget remains unchanged. An explicit runtime `pilot_allocations`
proposal can reduce the scientific Pilot count within the compiled Design budgets,
preserving all strategies and equal counts within each standard Arm. Gate 3 displays
the exact resulting per-strategy/per-Arm counts and total; approval binds that complete
Pilot scope. It is not a hidden micro projection or permission to execute the larger
Design budget. A new pending Design is reviewed before any historical frozen plan.

Generation uses the existing Stage 04 worker and native BoltzGen design, inverse folding,
Boltz2 refold, analysis and filtering. The default Phase 3 adapter consumes those native
outputs without independent prediction or Stage 05's historical automatic expansion.
AFO remains available through explicit independent prediction; it is not a prerequisite
for native PASS, ranking or Gate 4. The bound prediction backend policy remains available
for that optional path and Phase 4. Each checkout owns its runtime, environment and models.

Active native filters come from each execution attempt's saved configuration and the
pinned source implementation, reconciled with recorded per-rule and aggregate flags.
All original native metric names and values are retained. Runtime additionally measures
refold heavy-atom hotspot/avoid contacts with separate whole-binder and design-mask scopes.
The calculation-only reference is loaded into the existing Pilot Skill; no lulu policy,
project heuristic cutoffs or universal biological fitness score are installed.

Pilot evidence separates planned, generated, valid, predicted and metric-evaluable
counts, metric missingness, failed attempts and operational failures. An incomplete
generation can retain verified partial products without inventing metrics. Terminal
prediction exhaustion retains verified successful predictions and marks failures as
missing; checksum, identity and other hard consistency errors are still errors. A
terminal measured outcome is immutable and does not silently launch another retry loop.

For optional independent prediction and the unchanged Phase 4 adapter, an experimental
reference may resolve only part of the full requested target. v3 verifies
the shared residue identities and complete predicted chains; it retains backend confidence
and clashes across the full prediction. The complete-target alignment RMSDs are explicitly
unavailable in that case. It neither crops away predicted terminal residues nor substitutes
zero RMSD. The strict complete-reference kernel remains unchanged. Partial-reference
collection uses one bounded attempt per candidate because repeating the missing-reference
metric cannot resolve it. All original worker attempts remain auditable. Measurement v2
is a new immutable projection, preserving earlier records. A generated candidate can still
fail prediction, so generated counts and operational-failure counts are not disjoint.

## Gate 4

One scientific Arm can contain all seven scaffold strategies. Complete/evaluable Arms
with native PASS candidates enter promotion: rank every PASS, compare scientific Arms,
and propose exact Scale allocations for Scientist review. Weak scientific evidence
affects ranking, allocation, risks and uncertainty. It does not replace this proposal
with a model veto. Failed candidates remain denominators and audit evidence.

Only complete/evaluable zero-native-PASS Arms receive deterministic failure dossiers
and bounded recovery recommendations. Runtime binds their identities in
`completed_zero_pass_arm_ids`, allowing sufficient evidence for recovery steering
without fabricating a passing candidate. This never permits zero-support promotion.
Incomplete Arms receive no final yield or scientific failure conclusion; verified partial
PASS candidates can be ranked provisionally. Validation-micro remains validation-only.

The Scientist can choose PROMOTE_TO_SCALE, RUN_ANOTHER_PILOT, REVISE_DESIGN,
REVISE_SITE or STOP. Runtime validates the selected option and applies it idempotently.
Another Pilot requires a new explicit Gate 3 plan approval. Design/Site revisions return
through the existing upstream gates. STOP retains evidence and schedules no computation.
No autonomous multi-Pilot loop is implemented.

Promotion binds the reviewed strategy allocation, total Scale intent and upstream
identities. Test-only promotion cannot authorize production compute. Judge cannot
rewrite the route, and technical Judge failure is visible on the card instead of
removing the Scientist review. An explicit runtime fact conflict is not an unavailable
review fallback. Normal Phase 3 directly publishes its Gate 4 card with optional review
explicitly marked `not-requested`. An explicitly requested second opinion remains
available, but does not choose a route or become a prerequisite.

## Scale and global selection

An immutable batch manifest partitions exactly the authorized allocation. Batch receipts
use the existing append-only runtime journal, retain source run and candidate lineage,
and support original-worker/resume verification. Completed evidence cannot be overwritten
by a retry. All batches contribute to one global pool; batch-local winners are not
concatenated. Missing/failed batches remain visible.

The bounded shortlist is review priority, not a scientific hard filter. Development
score is an engineering ordering signal, never biological fitness. Real adapter sequence
clusters currently identify exact sequence duplicates; pose diversity is unverified and
must remain an uncertainty. Synthetic 50k clustering tests validate software behavior,
not protein-family clustering accuracy, biological performance or GPU throughput.

Final Selection receives candidate metrics, sequence, provenance, risk, uncertainty,
strategy/diversity context and requested primary/backup counts. Runtime rejects unknown,
duplicate or overlapping choices. Judge critiques the proposal without reranking it.

## Gate 5, recovery and handoff

Only an explicit current Gate 5 response can publish the selected primary/backup panel.
REVISE creates a new review identity even if the candidate IDs remain unchanged. STOP
publishes no handoff. Repeated application of the same outcome is idempotent.

When worker recovery or new measurements supersede an outstanding Gate 4/5 card, Runtime
rejects responses to that stale card, retires its graph interrupt without inventing a
human response, and prepares the current evidence for review. Historical pending state
cannot override current object authority.

Any validation/development input keeps the handoff status
`validation-only-not-authorized-for-experiment`, even if some upstream authority was
formally approved. The package contains exact selected sequences and provenance and
records `not-ordered`. This assignment performs no production-scale generation or
wet-lab ordering. See the integration progress and closure records for validated scope.
