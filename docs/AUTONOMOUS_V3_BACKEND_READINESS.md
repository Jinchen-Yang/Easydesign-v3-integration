# Autonomous v3 backend readiness — 2026-09-12

This is an engineering checkpoint, not a Phase2/3/4 closure.

## BoltzGen

Clone-local locked 0.3.2 environment installed and import probe passed, including Torch CUDA
build and cuequivariance imports. Source a3149cf18eeb58648d1abbb27539bd73f746cdda, molecule
dataset and all five weight assets match exact catalog sizes/SHA. Final installation068 returned
ok=true and registered the existing runtime profile. CLI --help passed in check-readiness053.
Real standard YAML checks passed in live157/158/160/162; standard Gate3 Case4 independently
passed in live162 after explicit validation-actor REVISE. Native checks and Case5 independently
passed in live163 after REVISE, preserving all seven original/compiled YAML byte sequences.
Both retain seven official-scaffold variants,280 planned candidates, backend0.3.2/sourcea3149cf18eeb,
and generation_started=false. These accepted engineering/scientific review boundaries do not
approve or launch a Pilot. See AUTONOMOUS_V3_PROGRESS.md and the two accepted Gate3 checkpoint tags.
No BoltzGen generation has been run in this autonomous attempt.

Environment lock: 016440a47ff80466ead66417de866dc463018ca5ac599095c7cf50b22afb2fac.
Inventory SHA: 6eeec9a9ac3313dc2edb64417b593753a63b542b029cf3cdb66a619ca871778f.

## AFO / OpenFold3

REAL SCIENTIFIC BACKEND INSTALLATION MICRO TEST: PASS.
Release afo-3-1-4-of3-p2-155k; runner3.1.4; pinned Python3.12.13/JAX environment.
Verified bundle83b6d8e895090a0c74d21e495d50b75a7cb031389386f5b7cd9843b6d3501afd.
GPU installation plan071: one 29-residue protein, seed101, one sample, one recycle, no MSA,
no templates, no data pipeline, one physical GPU, smoke timeout3600 seconds.

The real runner returned0, reported72.20 seconds inference, and produced the expected input,
CIF and confidence artifacts. Parsed CIF has chainA with29 residues. The single-chain iPTM is
null as expected; no affinity or biological success is claimed. The installation is independently
classified from the forthcoming Phase3 target-binder complex/prediction/filtering test.

Receipt SHA: ebe57dc14ef1fd8b5c00956e0698093b94e5425c95f725e66d501ac50d811ef3.
Environment inventory SHA: b30966df1dba9d20251f8b4a2f045c7e6d9dbf14e20d19bf43573b69d6e3fb6c.
Evidence root: runtime/tmp/autonomous-v3-20260912, files afo-install071-compute-plan.json,
afo-install071-smoke-started.json, afo-install071-result.json, afo-install071-micro-report.json.

Earlier AFO064 failed before GPU because pinned uv was missing. Own uv0.12.3 was then installed
under runtime/tools with its pip download report retained. All failed/quarantined staging and
network-recovery evidence are retained. Total GPU jobs for installation:1. Production jobs:0.
No other checkout's environment/model assets or running GPU processes were changed.


## Read-only execution review before Phase3 (not an execution plan)

The legacy pilot_run validates and executes the full frozen strategy. Its default first Pilot
is280 candidates; it must not be called unchanged for validation_micro. A future thin Agent
adapter must bind the formal scientific plan and the exact smaller validation configuration to
Gate3, preserve existing immutable ExecutionPlan/DecisionRecord and LocalStepJob recovery, and
verify both before dispatch. No Phase3 adapter or micro execution is implemented yet.

The existing Stage05 v1.7 path can expand a TierA strategy before de-novo and target-conditioned
prediction. Its default diagnostic expansion is100, so merely setting initial generation to1
is not a sufficient compute bound. Configuration requires expansion total strictly greater than
Stage04's required count (minimum2 if that count is1), and top-N cannot exceed that expansion.
Actual ceilings must cover both prediction branches and every possible downstream expansion.
These are source-inspection findings; no candidate/batch/GPU execution budget has been approved.

If initial filtering finds no TierA, the old kernel writes stopped-no-tier-a and returns before
those expansion/AFO branches. Software success with zero eligible candidates at validation_micro
must be interpreted as INCONCLUSIVE/insufficient evidence, not site/design failure, superiority,
or scientific promotion. An additional representative backend test, if necessary, must be
reported separately and bound to its real input; the installation-only29-aa AFO test cannot stand
in for target-binder prediction or the Pilot loop. No threshold or prediction semantics change.

The legacy Stage06 manual authorization contract can acknowledge a Stage05 scientific stop and
non-eligibility, but that does not create TierA promotion evidence. Any future tiny scale-mode
validation must use explicit Gate4 authority with honest validation-only scope. Synthetic50k
selection/competition evidence must remain separate from real tiny backend output. Phase4 has
not started, and no wet-lab ordering or production compute is authorized.
