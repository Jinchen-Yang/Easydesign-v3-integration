# Phase 3 — engineering closure

Status: **ENGINEERING ACCEPTANCE PASS** for the bounded scope documented below.
Closure checkpoint: `checkpoint/easydesign-v3-phase34-integration-complete-20260915`.

The implementation is based on current Phase 2
`fce5d886849edf575ec1765f7226064291857d49`, with selective reuse from donor
`07d2a6a24d1a3d622f01ac58d3e983aafbcbd3e4`.
Frozen implementation: `16fdf2519240e29eb67a575b896f347d6b34b75c` on
`codex/easydesign-v3-phase34-integration`.

See [the complete acceptance record](PHASE34_INTEGRATION_ACCEPTANCE.md),
[execution contract](PHASE34_EXECUTION_CONTRACT.md), and
[checked evidence manifest](validation/phase34-integration-20260915.json).

## Accepted implementation

Current Gate 3 approval binds an exact Pilot Plan to the current Target, selected Site,
Design, compiled strategies, arm hypotheses, runtime backend policy and allocation.
Runtime executes generation, prediction, filtering and metrics. Pilot Diagnosis
interprets the trusted dossier; Judge supplies independent critique; Scientist Gate 4
chooses the next route. No separate execution-stage agents or autonomous Pilot loop
were introduced.

| Acceptance requirement | Evidence |
| --- | --- |
| Real Gate 3 → ScientistPilotAuthority bridge | `test_phase34_authority.py`: current approval, stale Design, changed allocation/backend, reject and validation boundaries. |
| Design Arm identity and scientific intent survive | Authority tests plus lossless 21-strategy packet round-trip; real three-arm NK2R diagnosis. |
| Correct lineage, denominators, missingness and failure classification | Measurement, failure and partial-reference tests; actual NK2R measurement v2. |
| Real Pilot Diagnosis and lightweight Judge | Frozen native DeepSeek v4 Pro → Gate 4 receipt. |
| All five Scientist Gate 4 choices | Native graph tests cover STOP, another Pilot, Design/Site revision; native final-runtime test covers promotion. |
| Deterministic restart, resume and idempotency | Worker/config tamper tests, new-plan approval, stale interrupt retirement and same-authority micro recovery. |
| Bounded real generation/prediction/metrics | Three BoltzGen candidates; three verified AFO 3.1.4 predictions with confidence/clash metrics. |
| Phase 2 and protected kernel preserved | Final full regression, accepted Cases 1/3/4/5 hashes, 461 unchanged protected files. |

## Real validation_micro result

Project: `phase34-nk2r-micro-20260915-01` in the isolated integration checkout.
Run: `pilot-v3-4ada156a63bc109782615809`.
Selected Site B remains `C167 I202 Y206 W263 Y266 F270 Y289`.
All 21 GPCR YAMLs passed compiler/backend validation with 87/87/93 exclusions by arm;
the micro executed only one 7eow candidate for each of the three arms.

Generation and independent prediction are 3/3. The experimental target resolves
297 of 398 residues. The protected complete-target alignment kernel cannot supply
two RMSDs against that partial reference. v3 retains verified full-chain predictions,
confidence and full-target clashes, and explicitly marks both RMSDs unavailable.
Six historical AFO attempts are preserved; recollection starts no new GPU task.
No sequence, mapping or scientific kernel assumption was changed to make this pass.

Measurement SHA:
`42c425244feabb02bfcf34cbaa3d3e2f508956b9c1461725eb4b23b18e7a25d0`.
Frozen repeat measurement returns the same hash without dispatch. Each arm has one
generated/predicted/evaluable candidate, no failed prediction slot, and two missing
alignment metrics. Legacy policy pass is zero and remains an audit annotation.

Diagnosis submitted first try; Judge completed after two bounded repairs. Four real
DeepSeek v4 Pro calls used 137,188 provider-reported tokens. The largest request was
90,629 characters, below the unchanged 100,000 hard context limit. Gate 4 displays
`INCONCLUSIVE`, a `CONCERNS` review and `RUN_ANOTHER_PILOT` recommendation. Scientific
Scale promotion is disabled. No Gate 4 choice was approved or executed.

Records: `runtime/tmp/nk2r-micro-frozen-measurement-03.json`,
`runtime/tmp/nk2r-micro-gate4-01.json` and
`runtime/tmp/nk2r-micro-gate4-usage-01.json`.

## Validation boundary

Final post-correction coverage: **1,201 passed, 11 skipped / 1,212 collected**.
Eleven fixture-setup errors from file-list sharding were rerun with normal directory
collection and all passed, without source edits; both attempts remain in the manifest.
This closure establishes the Phase 3 engineering workflow, not NK2R binding/inhibition,
arm superiority, Site failure or a validated production success rate. Micro zero-pass
is insufficient scientific evidence. Another Pilot needs a new explicit plan approval.
The original NK2R scientific Gate 3 remains pending. No production Pilot was performed.
