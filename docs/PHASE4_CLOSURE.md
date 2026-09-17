# Phase 4 — engineering closure

Historical 2026-09-15 acceptance. Current native Scale product semantics and acceptance
are recorded in [Phase 4 product closure](PHASE4_PRODUCT_CLOSURE_20260917.md).

Status: **ENGINEERING ACCEPTANCE PASS** for the bounded scope documented below.
Closure checkpoint: `checkpoint/easydesign-v3-phase34-integration-complete-20260915`.

Integration branch: `codex/easydesign-v3-phase34-integration`, based on current Phase 2
`fce5d886849edf575ec1765f7226064291857d49`. Donor reuse is selective; current Phase 2
semantics and the deterministic scientific kernel remain authoritative.

See [the complete acceptance record](PHASE34_INTEGRATION_ACCEPTANCE.md),
[execution contract](PHASE34_EXECUTION_CONTRACT.md), and
[checked evidence manifest](validation/phase34-integration-20260915.json).

## Accepted implementation

Scientist Gate 4 promotion binds exact strategy allocations and the Design/revision.
Runtime manages immutable batch plans, recoverable worker state and a single global
candidate pool. Every evaluable candidate competes globally. A deterministic shortlist
and candidate dossiers feed one Final Selection Specialist. Judge critiques the panel;
Scientist Gate 5 approves exact primary/backup membership or requests revision/STOP.

| Acceptance requirement | Evidence |
| --- | --- |
| Bound Scale authority | Gate 4 native promotion and allocation/identity tests. |
| Exact-scope execution and recovery | Scale adapter verifies original config/worker, resumes the same batch and rejects tampering. |
| One global pool with provenance and missingness | Pool/projection/batch tests; real NK2R measurement projection replay. |
| 50k synthetic disk/restart stress | 50 batches and 50,000 candidates, failed/resumable recovery, duplicate ingestion and fresh-process reconstruction. |
| Auditable ranking and diversity | Deterministic global ordering, synthetic cluster cap and shortlist hashes. |
| Real Final Selection and light Judge | Frozen native DeepSeek v4 Pro test with an explicitly synthetic candidate pool. |
| Authoritative Gate 5 panel | Native approval/revision/STOP, stale-card retirement and idempotent handoff tests. |
| Validation cannot authorize experiments | Synthetic and micro provenance retain validation-only handoff and `not-ordered`. |

## Frozen native Gate 4 → Gate 5

The native Harness test on `d366a903a2b01741639fb492f8fcd9143ed8052b` passed promotion,
Final Selection, Judge, Gate 5 and repeated handoff application on synthetic evidence.
Final Selection needed one schema repair; Judge submitted first try and highlighted
sequence-identical backups. Three real DeepSeek v4 Pro calls used 8,506 tokens, maximum
input 7,538 characters. The handoff contains two primaries and two backups with status
`validation-only-not-authorized-for-experiment` and ordering status `not-ordered`.
These are workflow/model checks, not evidence of biological candidate performance.

Records: `runtime/tmp/phase34-live-native-final-result-01.json` and
`runtime/tmp/phase34-live-native-final-usage-01.json`.
The later partial-reference measurement adapter also passes real NK2R projection replay
and the final complete regression; it does not change the selection/Judge contract.

## Synthetic global-pool stress

PASS: 50,000 retained, 49,949 evaluable, 51 unevaluable, 50 batches. The initial checkpoint
has 48 complete, one failed and one resumable batch; all recover. Fifty duplicate batch
replays add no duplicate candidates. A fresh process reconstructs the same persisted
pool and 30-candidate shortlist, with synthetic cluster cap two.

Pool SHA:
`64b582e1f7ce37131c59f46d8b4f3c8fb7d6017e6c67c24fb5c2e6376d21f168`.
Record: `runtime/tmp/phase4-50k-stress-02.json`.
This is software stress evidence, not a biological or GPU-throughput benchmark.

## Validation boundary

Final post-correction coverage: **1,201 passed, 11 skipped / 1,212 collected**.
Eleven fixture-setup errors from file-list sharding were rerun with normal directory
collection and all passed, without source edits; both attempts remain in the manifest.
Exact-sequence groups detect duplicates; structural/pose diversity remains unverified.
Development score is an engineering ordering signal, not biological fitness. External
GPU/MSA dependencies and model repair remain operational considerations.

No production Scale, 50k protein generation, wet-lab order or experiment was performed.
No existing scientific approval was expanded to cover new work. Gate 5 validation
responses belong to isolated test contexts. The assignment stops at this engineering
handoff milestone and does not start later roadmap items.
