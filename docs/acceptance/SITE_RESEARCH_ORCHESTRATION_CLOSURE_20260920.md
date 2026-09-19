# Site Research orchestration closure — 2026-09-20

## Decision

The Site Research orchestration work is accepted on the fresh human NK2R Gate 1 → Gate 2 run
`figure2-nk2r-site-orchestration-r28`.

Authoritative implementation:

- worktree: `/data/easydesign-worktrees/figure2-ab-20260918`
- branch: `codex/site-intelligence-latency-20260919`
- implementation commit: `ea797db5747d92e85951bd922f9dbd1a4a3553aa`
- fresh thread: `thread-37df5cbdc57b4810af1c58d2ba08e19e`
- Gate 1 card: `81b07f4a17b525481de0d44b0e1b9b71b532cbf9f8e4b7d5e6530107e6aa3619`
- Gate 2 card: `51425f29f2a6732d721cac84df17141b4cb54eca0c5f6f27d9bb679ca28f8fb3`

The result is a durable Runtime-owned Site lifecycle. It projects approved receptor context,
bounds every model request before admission, separates scientific calls from auxiliary work,
forces a compact handoff at a deterministic stopping condition, and restarts from persisted
state without repeating science or creating a second card.

## Failure-to-fix ledger

| Run | Observed failure | Durable correction |
|---|---|---|
| R18 | Site lifecycle counted prior Gate 1 evidence as current Site work. | Scoped lifecycle, evidence, counters and milestones to the current execution. |
| R19 | GPCRdb/kernel navigation was repeatedly delegated to the model. | Bound approved GPCR context and projected the deterministic receptor kernel once from Runtime. |
| R20 | The first Site request reached the 100k guard before an admission decision. | Applied proactive admission to the first Site request as well as later turns. |
| R21 | Repeated facts and evidence metadata grew the next request beyond the guard. | Added compact working/finalization packets, shared columns, evidence catalog deduplication and bounded notes. |
| R22 | Target prose recommended chain R while structured `recommended_option` was empty. | Required a structured Target recommendation whenever selectable chains exist. |
| R23 | A mixed intracellular/transducer-facing candidate remained selectable. | Added deterministic compartment conflict checking from canonical topology plus signed membrane geometry. |
| R24 | Phase 2 could proceed with requested canonical identity still unresolved. | Required the official record/proposal/current identity view before Target prepare in Phase 2. |
| R25 | The identity prerequisite was applied to a deliberate Phase 1-only launch without Phase 2 source tools. | Scoped the prerequisite to Phase 2 and documented the correct `--through site` launch. |
| R26 | Gate 2 passed, but a rejected handoff plus full prior opinion raised repair input to 98,748 chars. | Replaced rejected handoff replay with a compact Runtime repair outline; exact facts remain in the dossier. |
| R27 | Model-authored avoid suggestions for default A silently hard-blocked the otherwise valid outer-pore B. | Made ranked exclusions advisory: overlap with any Runtime-hard-valid candidate is removed and cannot change A/B/C eligibility. Runtime-hard-invalid intracellular residues remain available for downstream `not_binding`. |
| R28 | Fresh acceptance. Two malformed evidence-tool arguments occurred. | Existing deterministic tool repair corrected both in the same execution; no code or human repair was needed. |
| Final regression | Proactive Site context projection kept the compact Runtime packet but omitted the newest complete, unconsumed tool-result batch. | Preserve that complete batch exactly once whenever `compact packet + batch` remains inside both character and model-token guards; otherwise retain the bounded Runtime packet. Added exact-batch and admission-event regression coverage. |

## Fresh R28 scientific result

Gate 1 resolved official human TACR2/NK2R identity `P21452`, prepared deposited chain R, and
received a `SUPPORTED` Target Judge assessment before Scientist approval.

Gate 2 returned this selectable portfolio without a routine Site Judge:

| Rank | Candidate | Exact design labels | Eligibility |
|---|---|---|---|
| A | ECL2/ECL3 outer vestibule (`site-3e00282b73ccf138`) | 175, 176, 178, 180, 182, 278, 280, 281 | selectable |
| B | TM2/TM6/TM7 outer pore (`site-c75478b162146a60`) | 86, 266, 269, 270, 289, 293, 296, 297 | selectable |
| C | upper/core pore (`site-fae212da41ee94b2`) | 75, 117, 120, 121, 124, 263, 299, 303 | selectable |

All three are Runtime-hard-valid. Exposure, activation risk and whole-VHH access uncertainty
affect their rank and confidence; none is converted into a hard block. The exact residues and
canonical/design correspondence shown to the Scientist are Runtime-rendered facts.

## R28 execution evidence

Site lifecycle state after a new-process reopen:

- current phase: `site-synthesis-ready`
- persisted milestones: 10, from `initialized` through `site-synthesis-ready`
- Site scientific model calls: 8
- auxiliary Site model calls: 0
- research queries: 15
- literature discovery queries: 4
- focused passages: 7
- finalization reason: `query-budget`
- provider/model errors: 0
- structured-output repair attempts: 0
- evidence-tool argument repairs: 2, both recovered automatically
- maximum actual Site request: 83,845 chars
- maximum pre-projection Site request: 268,197 chars
- maximum projected admission estimate: 85,070 chars
- Site provider latency recorded in responses: 382.80 seconds

The maximum request remained below the 100,000-character hard guard with more than 16,000
characters of actual headroom. Query-budget finalization produced a valid handoff on its first
submission. Site synthesis produced a valid `RankedSiteDecision` on its first submission.

## Restart and idempotency

A separate process reopened the R28 project with `easydesign-agent status`. Counts were identical
before and after the read:

| Durable object | Before | After |
|---|---:|---:|
| events | 229 | 229 |
| cards | 2 | 2 |
| model calls | 26 | 26 |

A newly constructed `SessionStore` and `Phase2Bridge` recovered the same Site execution ID,
kernel card, ten milestones, query/passages counts, finalization reason and dossier hash. No model
call, research query, proposal or Scientist card was duplicated.

## Verification

- focused Site/context regression: `31 passed`
- repository checks: PASS (structure check, viewer assets, compileall, Ruff, strict mypy over 237 source files)
- full regression: `1330 passed, 11 skipped, 3 warnings` in `5531.69s (1:32:11)`

## Known limits

This closure establishes engineering control and fresh Gate 2 completion; it does not claim that
the three NK2R sites are experimentally validated epitopes. Remote model latency remains the
largest wall-time component. The evidence-rich GPCR case required eight Site scientific calls,
but the count and context are bounded, no auxiliary summarizer call consumed the scientific
budget, and failures in tool argument formatting recovered without changing scientific state.
