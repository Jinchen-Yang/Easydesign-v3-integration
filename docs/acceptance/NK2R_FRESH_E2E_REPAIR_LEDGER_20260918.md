# NK2R fresh end-to-end acceptance and repair ledger

## Acceptance objective

Run a new human-NK2R extracellular inhibitory VHH case from Gate 1 through Gate 5 using a fresh EasyDesign project and model thread. Previous NK2R project state, dossiers, ranked sites, residues, YAML, candidates and decisions are excluded from the scientific Agent context. Product-native retries are allowed and recorded. Any developer code, contract or state repair invalidates that attempt; the final accepted attempt must restart from Gate 1 on the repaired frozen commit.

## Fixed interpretation

- Expected Scientist Gate approvals and choices are part of the product contract and are not developer intervention.
- No prior NK2R project artifacts may be imported or read by the scientific Agent.
- Fixes must be generic; no P21452, 9W2H, prior site residue or prior ranking special cases may be added.
- A fresh RCSB 9W2H mmCIF is supplied as the local structure input because the current public Agent entry point requires `--target`. Target identity, chain, state, sites and strategies remain for the new Agent to determine.
- Pilot uses native BoltzGen design, inverse folding, Boltz2 refold and native analysis. AFO is optional and is not requested for the acceptance path.
- Gate 4 production intent and any bounded validation execution projection remain distinct.

## Run identity

- Host: `suzhou2` (`ailuoyun-GPUBMS`)
- Repository: `/data/easydesign-worktrees/Final-backends`
- Baseline branch: `codex/easydesign-final-backends`
- Acceptance branch: `codex/nk2r-fresh-e2e-20260918`
- Baseline commit: `0298f53bba3e620c28d50cf48cccaca9ba2d63d9`
- Model provider/profile: `deepseek / deepseek-v4-pro`; secret values are excluded
- Fresh target retrieval: `https://files.rcsb.org/download/9W2H.cif`
- Target SHA-256: `33ff56e619b30fbb1edeba2d58726aaf78006ad1b2480416b97bb4892e488e51`
- Fresh project prefix: `nk2r-fresh-e2e-20260918-aNN`

## Blind-isolation controls

- New project and thread IDs for every attempt.
- Empty Final-backends workspace before Attempt 001.
- No import from `nk2r-inhibition-20260914-01`, `phase34-nk2r-micro-20260915-01`, `phase34-nk2r-ranking-20260917-01`, or exported NK2R cases.
- No prior candidate residues, rank order, SiteDecision, DesignIntent or candidate pool in prompts.
- New clone-local scientific HTTP cache; authoritative remote sources may be fetched again.
- Codex may operate infrastructure and repair generic code, but may not supply remembered scientific answers to the EasyDesign Agent.

## Setup findings

### SETUP-001 — pure-backend copy lacked an executable scientific runtime profile

- Detected before Attempt 001: yes
- Expected: `Final-backends` can load its clone-local runtime profile and validate BoltzGen configuration before starting a scientific case.
- Before state: `/data/easydesign-worktrees/Final-backends/runtime/profile.yaml` was absent; loading the runtime profile raised `ConfigurationError`.
- Root cause: the earlier pure-backend separation copied the frozen source and Agent Python environment but intentionally did not copy the large scientific backend runtime registration.
- Repair: created a clone-local runtime snapshot containing the installed BoltzGen and OpenFold environment/model files plus OpenFold component receipt. Paths and `runs_root` were rebound to `Final-backends`; no old project, run or scientific evidence was copied.
- Storage method: hard-linked immutable environment/model bytes on the same filesystem; new clone-local profile and state paths satisfy the runtime escape guard.
- Runtime profile SHA-256: `058570518e4febcb7e682399c9292838ac5ee3d7c28793a3b0d38737e116c4a2`
- After state: profile loads as `final-backends-nk2r-e2e`; available backends are `boltzgen`, `boltzgen_validation`, and `openfold3_af3_jax`; runs root is clone-local.
- Attempt invalidated: no, because no scientific attempt had started.

## Attempts

### Attempt 001

- Project: `nk2r-fresh-e2e-20260918-a01`
- Thread: pending creation
- Start commit: pending ledger commit
- Status: environment preflight
- Developer repairs after start: none
- Final autonomy eligibility: pending

## Issue template

For each issue record: attempt; Gate/stage; trigger; expected and observed behavior; before-state artifact paths and hashes; root cause; generic fix; changed files; fix commit; targeted/full tests; after state; manual project-state changes; attempt invalidation; restart project/thread.
