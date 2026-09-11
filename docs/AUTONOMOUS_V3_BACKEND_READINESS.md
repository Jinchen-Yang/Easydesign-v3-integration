# Autonomous v3 backend readiness — 2026-09-12

This is an engineering checkpoint, not a Phase2/3/4 closure.

## BoltzGen

Clone-local locked 0.3.2 environment installed and import probe passed, including Torch CUDA
build and cuequivariance imports. Source a3149cf18eeb58648d1abbb27539bd73f746cdda, molecule
dataset and all five weight assets match exact catalog sizes/SHA. Final installation068 returned
ok=true and registered the existing runtime profile. CLI --help passed in check-readiness053.
Real standard YAML check passed in live157: seven compiled official-scaffold strategies,
280 planned candidates, backend0.3.2/sourcea3149cf18eeb, generation_started=false. This is
backend executability evidence only: the independent Gate3 scientific content review failed
and remains pending after repair. Native-YAML golden and generation acceptance remain due.
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
