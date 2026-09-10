# Execution Phases

## Phase 0 — Preflight
inspect repo、确认 v2.1 frozen、定位 GPU runner/evaluator、枚举 target、定义 method、冻结 evaluator、估算 cost。
输出 EVAL_PREFLIGHT.md。

## Phase 1 — Cheap harness benchmark
执行 50–200 个 synthetic/fixture fault episodes。
测 2a/2b/2g/2h。

## Phase 2 — Real-target no-generation workflow
建议 20–50 个真实 target/task，做到 executable plan / validated strategy。
测 time、completion、first-pass validity、correction、intervention。

## Phase 3 — GPCR controlled benchmark
4–8 targets。
每 target 锁 site/X。
methods：fixed pipeline / plain Codex / EasyDesign。
生成预算严格相同。

## Phase 4 — Non-GPCR generalization
BenchBB 7 target + 额外非 GPCR，使用同 evaluator。

## Phase 5 — Ablation
只在主 benchmark 稳定后：
no interpretation loop / no evidence gate / no redesign。
不要做过多 ablation。

## Phase 6 — Resource efficiency
GPU-hours、throughput、VRAM、accepted/GPU-hour。
Extended Data。

## Phase 7 — Optional wet-lab
只录真实实验。
