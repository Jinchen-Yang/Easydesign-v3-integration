# Figure 2 evaluation preflight

Frozen v2.1 source: `22206ede700f02bc63a5a88075ddb2f567a96cc3` with dirty source tree `6d45afff988bdaea4356c2b1e02720e326fc4e3b5989fc3df48a78a4b8b72fea`.
Core science and 7 × 40 × X remain unchanged. Evaluation instrumentation is separate.

## Target and budget queue

6 GPCR: ADRB2, CXCR4, MC4R, GLP1R, ADORA2A, DRD2.
7 non-GPCR: PD-L1, EGFR, IL7Ralpha, BHRF1, SpCas9, BBF-14, MBP.
All three primary methods have X=1, 280 candidates/campaign, 3 campaigns/target.
GPCR: 54 campaigns / 15,120 candidates. Non-GPCR: 63 / 17,640.
Total: 117 campaigns / 32,760 generated candidates, plus 98,280 independent Protenix seed predictions.
No 50k scale jobs are included. Every target remains in the manifest, including acquisition failures.
Methods: EasyDesign Full, Plain Codex (gpt-6-astra/high for both), deterministic fixed pipeline.
Controlled site and condition manifests are not yet approved or hash-bound; these queue entries are planning records.

## Hardware and cost

Host observation: 8 × A100 PCIe 40GB, all about 97–100% utilized by existing work; 96 logical CPU cores;
data filesystem 4.46 TB (4.05 TiB) available at initial inspection. Hardware receipt records exact bytes and time.
Runtime doctor passed: BoltzGen 0.3.2, Protenix 2.0.0, AFO/OpenFold3 3.1.4, PyMOL, CPU ScanNet and TNP.
Registry snapshots contain package locks/checkpoint identities. This is not an independent-evaluator smoke test.

Measured benchmark GPU-hours: **0**. Reliable projected GPU-hours: **UNMEASURED**.
Planning sensitivity only: if generation costs 30–120 GPU-seconds/design and independent evaluation
20–90 GPU-seconds/design/seed, the 32,760-candidate queue costs approximately 819–3,549 GPU-hours,
before additional AFO internal screening, MSA, warm-up, retries and TNP. These are assumptions, not measured throughput.
Full SpCas9 and receptor constructs may exceed these assumptions or 40GB capacity.
Storage sensitivity: assuming 1–10 MB per generated/evaluated structure set and four sets/design,
about 131–1,310 GB, excluding trajectories and intermediate caches. Measure a bounded pilot before reserving space.
Do not translate GPU-hours to USD without an explicit dated hardware pricing source.

## Evaluator and seed policy

Independent profile SHA: `171c5a6389928de34ce649aabc3c2adbee6f4ede4df56162ca997dcdb3923cb3`.
Predict with independent Protenix seeds 11/29/47 and apply common interface confidence, contact-pair PAE,
hotspot engagement, severe-clash, target-deformation and 2-of-3 consistency gates.
Profile is prospectively specified, not experimentally calibrated. Its runtime and geometry mapping still require smoke validation.
BoltzGen 0.3.2 does not expose reproducible generation seed control; pairing is by target/replicate block,
not identical random samples. Never claim exact stochastic coordinate replay.

## Commands

```sh
.venv/bin/python evaluation/figure2/runners/run_cpu.py verify
.venv/bin/python evaluation/figure2/runners/run_cpu.py tier0
.venv/bin/python evaluation/figure2/runners/run_cpu.py acquire
.venv/bin/python evaluation/figure2/runners/run_cpu.py tier1
.venv/bin/python evaluation/figure2/runners/gpu_gate.py --queue evaluation/figure2/manifests/GPU_TASK_QUEUE.json
```

The last command deliberately exits blocked and never launches GPU. Production Full method, once an actual
project and strategy are frozen: `easydesign pilot plan PROJECT --strategy REVISION --prediction-backend afo --json`;
then use the returned exact plan-bound run intent after explicit GPU authorization.
Plain/fixed native backend commands cannot be called executable before their target/site/native YAML and equal-budget
manifests are bound and validated. No fake ready-to-run command is supplied for these unresolved inputs.

## Gate disposition

GPU **NOT AUTHORIZED / NOT STARTED**. Needed: exact sites and scope reviews, baseline isolation,
independent evaluator smoke, measured cost and available capacity. Tier 0/1 diagnostic work is authorized and recorded.
