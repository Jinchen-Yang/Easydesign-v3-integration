# EasyDesign v3 Phase 3 Product Closure — 2026-09-16

本轮 Phase 3 v1 的实现、真实 NK2R 正例、两组有界 CDR3 对照和保护性全量回归均已完成。停在 Scientist Gate 4；没有启动生产 Scale 或自动多轮 Pilot。

## Repository and provenance

- Authoritative clean integration base: `a5d5dead9b572dfa1e65aa6b1c8c4fe824bcd35c`.
- Tested implementation: `2c013dc5d69772bb4667785e4cc3688dcb785866`.
- Branch: `codex/easydesign-v3-phase3-product-v1`.
- Worktree: `/data/easydesign-worktrees/v3-phase3-product-20260916` on Suzhou2.
- The final report-only commit is identified in the exported closure receipt/header. This tracked report records the exact tested implementation, avoiding a self-referential Git hash.
- Original positive generation: `5d574de6a46a18fd229ae3a664f613cfcb3d79af`.
- New control generation snapshot: `ca3bd3bd35d2bfe211cebd5f37a16c95cea6b8f1` (clean at dispatch).
- Current code descends from the current Phase 2 baseline and clean integration base; the historical Phase 3/4 donor was not used as authority.
- All original integration files and NK2R outputs remain intact. No commits were pushed.

## Final product flow

Gate 3 approved Design/explicit Pilot allocation → BoltzGen design → inverse folding → native Boltz2 refold → native analysis/filtering → deterministic evidence → scientific Arm decision → Specialist recommendation → Scientist Gate 4.

| Arm evidence | Product behavior |
| --- | --- |
| Complete/evaluable, native PASS > 0 | Rank every native PASS; Candidate and Arm boards; exact proposed Scale mix. |
| Complete/evaluable, native PASS = 0 | Failure dossier and bounded Recovery recommendation. |
| Incomplete, missing or inconsistent evidence | Operational/incomplete; no scientific failure, final yield or Scale eligibility. |
| Explicit micro/backend validation | Validation-only, even when that small execution completes. |

Seven scaffolds within a scientific Arm are aggregated as one Arm. Candidate failures contribute denominator/failure evidence; they do not make a passing Arm a Recovery case. Complete passing and zero-pass Arms can coexist without the zero-pass Arm vetoing promotion of the passing Arm.

## Metric authority and Skill

Maintained reference: `src/easydesign/agent/skills/pilot-diagnosis/references/boltzgen-pilot-ranking.md`; it is loaded into the actual Specialist prompt. The research Skill links to it through `.agents/skills/easydesign-research/references/boltzgen-pilot-ranking.md`. Legacy Tier/AFO material is explicitly scoped as legacy.

Only calculation definitions were taken from the supplied manual. No lulu-specific thresholds, policies, secondary filters or results enter the product.

Hard-filter truth comes from each task attempt's saved `config/filtering.yaml`, pinned BoltzGen source and recorded candidate decisions. Every candidate retains profile identity, rule, threshold, observed value, decision, aggregate PASS and source references. The validated backend is BoltzGen 0.3.2, source `a3149cf18eeb58648d1abbb27539bd73f746cdda`.

The NK2R profile enabled `has_x`, two configured RMSD aliases, CYS and selected composition filters. Its RMSD threshold was 2.5 Å. That profile is run-specific, not a new universal EasyDesign policy. iPTM, pTM, PAE, ipSAE, contacts, SASA, chemistry and pLDDT remain ranking evidence.

Important preserved definitions:

- `design_mask` follows actual generated/changed/inserted residues; whole binder uses `chain_design_mask`.
- `bb_rmsd_design` aligns the design subset; target-aligned design RMSD separately measures pose retention.
- `design_to_target_iptm` and `design_iptm` have distinct masks; minimum PAE alone is not interface confidence.
- Native `delta_sasa_refolded` measures target area occluded by design-mask atoms; it is not automatically whole-VHH BSA or affinity.
- Native hydrogen bonds use the source Hydride/Biotite geometry; salt bridges count charged atom pairs. They are not replaced by an identically named distance proxy.
- Supplementary refold contacts report whole-binder and design-mask hotspot/avoid membership separately, using the existing 5 Å heavy-atom contact kernel. Clashes remain supporting evidence.
- Missing values stay missing. Raw native confidence scales are preserved. No unverified per-CDR area decomposition was fabricated.

## Real positive acceptance: existing 5/280

The existing seven-scaffold × 40 Pilot was consumed without regeneration. Explicit import verified Suzhou2 7eow/40 and Xiamen six-scaffold/240 artifacts, YAML identities, exact candidate IDs, structures, metrics, profiles and checksums. The original Suzhou2 aggregate still records incomplete execution; the combined evidence is a declared derived import, not a rewritten source job.

DeepSeek V4 Pro ranked all five PASS candidates and generated one PROMOTION Arm plus a four-scaffold Scale proposal on `84aa03bb7354d3568d2c5ada411a745fbe251d04`. Current implementation replay reverified source integrity and rebuilt the dossier/Gate 4 card without new generation or model calls.

The proposed allocation was 10 each for 7eow, 8coh, 8z8v and gontivimab (40 total). It remains unapproved and unexecuted. Scientific cautions are retained; the other 275 failures are not misrepresented as an Arm failure.

### Positive Candidate Leaderboard

| Rank | Scaffold / backend ID | Complex RMSD (Å) | Target-aligned design RMSD (Å) | Design-to-target iPTM | Hotspot contacts |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | 8coh / design_12 | 1.84629 | 2.87374 | 0.58583 | 3/7 |
| 2 | 8z8v / design_15 | 2.23908 | 2.38689 | 0.51448 | 3/7 |
| 3 | gontivimab / design_11 | 2.16841 | 2.86002 | 0.48349 | 3/7 |
| 4 | 7eow / design_07 | 2.33662 | 2.62994 | 0.46337 | 3/7 |
| 5 | gontivimab / design_18 | 2.32734 | 3.95436 | 0.22187 | 3/7 |

## Real bounded CDR3 controls

Both controls derive from the successful approved NK2R Arm/YAML. Short insertion = `1..3`; aggressive insertion = `45..55`. These are insertion ranges, not universal final CDR3 lengths. Each ran seven scaffolds × ten candidates = 70; total new candidates = 140. The Design's default 40/scaffold remains unchanged; the explicitly approved Pilot allocation limits this execution to ten/scaffold.

Target, Site B/full seven-hotspot set, 87 avoid residues, seven scaffolds, CDR1/2, remaining CDR3 design/exclude semantics and insertion anchors, crop and backend were held constant. All 14 real YAMLs passed compiler/backend validation. No thresholds were relaxed and no controls were repeatedly mutated to force failure.

| Scaffold | Source insertion | Short retained + inserted | Aggressive retained + inserted |
| --- | --- | --- | --- |
| 7eow | 1..37 | 14–16 | 58–68 |
| 7xl0 | 1..46 | 5–7 | 49–59 |
| 8coh | 1..37 | 14–16 | 58–68 |
| 8z8v | 1..42 | 9–11 | 53–63 |
| gontivimab | 1..36 | 15–17 | 59–69 |
| isecarosmab | 1..43 | 8–10 | 52–62 |
| sonelokimab | 1..38 | 13–15 | 57–67 |

“Retained + inserted” counts the declared retained design region plus insertions, not an anatomical CDR numbering assignment. The existing 8coh anchor at 98 is preserved even though its declared CDR3 design region starts at 99.

### Observed Arm results

| Arm | Insertion | Generated / evaluable / planned | Native PASS | PASS scaffolds | Mode | Specialist rank |
| --- | --- | --- | --- | --- | --- | --- |
| arm-2 | 45..55 | 70 / 70 / 70 | 2 (2.86%) | 2/7 | PROMOTION | 1 |
| arm-1 | 1..3 | 70 / 70 / 70 | 1 (1.43%) | 1/7 | PROMOTION | 2 |

Both controls naturally produced PASS candidates. They are interpreted through promotion/ranking, not relabeled as zero-pass Recovery. No expansion beyond 140 was made. Small reconnaissance denominators and overlapping metric tradeoffs do not establish that one insertion prior is universally better.

### Control Candidate Leaderboard

| Rank | Arm / scaffold / backend ID | Complex RMSD (Å) | Target-aligned design RMSD (Å) | Design-to-target iPTM | Hotspot contacts |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | arm-2 / isecarosmab / design_0 | 1.5861 | 1.63061 | 0.53144 | 4/7 |
| 2 | arm-2 / 7eow / design_2 | 2.31985 | 3.76988 | 0.54273 | 4/7 |
| 3 | arm-1 / gontivimab / design_4 | 2.3894 | 2.1501 | 0.24908 | 3/7 |

Native RMSD stress counts (overlapping failures, not additive):

| Arm | Complex RMSD filter failures | Design RMSD filter failures | Median design RMSD, all candidates |
| --- | ---: | ---: | ---: |
| arm-1 | 69/70 | 38/70 | 2.62031 Å |
| arm-2 | 67/70 | 66/70 | 10.33675 Å |

The aggressive control shows substantial population-level refold stress while retaining two stronger interface candidates. The single PASS from the short control has weaker interface confidence/contact coverage despite reasonable refold consistency. These are observed small-sample tradeoffs, not a universal causal length rule.


The real Specialist’s control recommendation is `PROMOTE_TO_SCALE`; exact proposed allocation: `{"arm-1-scaffold-gontivimab": 5, "arm-2-scaffold-7eow": 5, "arm-2-scaffold-isecarosmab": 5}`. This is a Gate 4 proposal only.

- Both Arms are complete PROMOTION with native PASS; no recovery route applies, so Scale is correct. Rank arm-2 above arm-1 on yield (2 vs 1) and candidate quality. Allocate bounded equal 5-per-scaffold (arm-2 two scaffolds, arm-1 one) given weak evidence and tiny N; larger allocation deferred pending scale yield. arm-1 stays eligible, its weakness shown via rank, risks and low allocation, not a veto.

## First-class recommendation contracts

Candidate Leaderboard contains every native PASS exactly once, current candidate/strategy/Arm identity, original and refold structure references, sequence/design-mask identity, complete available native/runtime metric vectors, missingness, metric directions and within-PASS ranks, concise rationale and risks. Runtime rejects missing/duplicate/foreign candidates and unknown metric references. No universal biological fitness equation is introduced.

Arm Leaderboard includes planned/generated/evaluable counts, native PASS count/rate, scaffold coverage, full-population and PASS distributions, top-k distributions, strengths/weaknesses/uncertainties, actual design hypothesis and per-Arm recovery status. Ranking cannot be replaced by an Arm-level failure diagnosis when native PASS exists.

Promotion contains current selected strategy IDs and exact executor-compatible allocations; multiple scientific Arms can be selected. Gate 4 binds the current execution/dossier/proposal. Source integrity, stale authority and restart/idempotency protections remain. No recommendation silently launches Scale.

For complete zero-pass Arms, deterministic evidence includes denominator, rule failures/co-occurrence, scaffold patterns, distributions, missingness and operational failures. Allowed recommendations are another bounded Pilot, Design revision, Site revision or STOP. Material Site changes return through Gate 2. Incomplete executions cannot use the zero-pass scientific sufficiency exception.

## Recovery, mixed and incomplete acceptance

- Independent deterministic zero-pass fixture: complete/evaluable seven × 40 rows, coherent RMSD failures, not the original positive Arm's 275 failures. Verified failure dossier, Recovery recommendation and Gate 4 semantics.
- An additional real DeepSeek V4 Pro call on `2064f4d90d29831c6941bbb8b99ab80babff42d3` over that explicitly synthetic input returned STOP with no Scale allocation. This validates the model contract; it is not biological evidence or new GPU generation.
- Mixed fixture: complete passing Arm uses promotion while complete zero-pass Arm receives its own Recovery recommendation.
- Incomplete fixture: planned 280 with partial/absent products remains operational/incomplete; partial PASS can be provisionally shown, but it cannot authorize final promotion.
- Runtime integration fixtures exercise Gate 4 publication, replay without additional model calls and source-tampering rejection. Fabricated zero-pass completeness proof is rejected.

## Judge, AFO and bounded fixes

Normal Phase 3 uses Runtime facts → Ranking & Recovery Specialist → Scientist Gate 4. Judge is optional and explicitly labeled; unavailable/unrequested review does not block the card. Existing Phase 4 review contracts remain intact. AFO remains available for optional independent prediction/connectivity/display and is not required for native filtering, ranking or promotion. No AFO sweep over the original 280 was performed.

The actual control Gate 3 review exposed a legacy Judge truncation issue. The first response retains its configured model and limits. After truncation only, compact recovery uses the same evidence, a verdict-only tool surface and a transient non-thinking DeepSeek transport. The live recovery submitted in 6.83 seconds with 551 output tokens after one truncated review. Stage/fact validators, repair/call limits and Scientist authority were retained. DISCOURAGED control risks remained visible and the user's explicit bounded-control authorization was applied to the exact 140-candidate card.

The complete two-Arm packet initially exceeded the unchanged 100k context guard (101,634 characters including schemas). Identical filter rules are now shared while retaining every attempt configuration reference and every candidate vector: shared filter definitions reduced the packet from 88,136 to 81,141 characters. The first model response then exposed insufficient repair headroom after a rationale-length validation error. Distribution statistics and rank vectors now also use shared columns, preserving every value and null while leaving space for the prior submission during bounded repair. Round-trip tests cover 14 attempt profiles, distinct thresholds, empty distributions and missing ranks. The final complete packet is 71,849 characters; actual first-call input including schemas was 85,347. Replaying the saved failed submission now takes 93,366 characters versus the previous rejected 102,658. The actual new review also required one rationale-length repair: its 93,301-character repair input succeeded in 18.98 seconds. Two real calls produced the Gate 4 result, and restart added no model call. The final full regression uses this frozen correction.

Other limited fixes preserve current Design ownership over historical approvals, explicit smaller Pilot scopes, per-attempt filter provenance and source-sensitive thread fingerprints. No Phase 2/4 redesign, autonomous Pilot loop, new family of agents or UI redesign was introduced.

## Validation and retained attempts

Final protected regression on `2c013dc5d69772bb4667785e4cc3688dcb785866`: **1232 passed, 11 skipped**, 1243 collected; exact disjoint coverage across three shards, no failures or collection errors. The skips are opt-in live tests and unavailable PyMOL integration; separate real model/backend acceptances are recorded here.

Whole-source Ruff and Mypy (207 source files) passed. Both affected Skills passed validation. The optional formatter audit identified pre-existing baseline formatting; no unrelated 142-file formatting rewrite was made. A prior completed suite on `ca3bd3bd` passed 1,229 with 11 skipped; the final suite includes model-source fingerprint and lossless multi-Arm filter-profile encoding regressions. An intermediate full run found a stale expected Skill-reference list, which was corrected and retested; its failed receipt remains preserved.

Earlier unsuccessful model/preparation attempts are retained. The first positive model answer ranked candidates but proposed revision, exposing residual diagnosis-first semantics; the corrected contract was then verified by real replay. Early bounded-allocation/owner checks and the three truncated Gate 3 reviews are not hidden or counted as successful acceptance. Interrupted pre-fix regression attempts are not reported as complete runs.

Key receipts under `runtime/tmp/`:

- `product-positive-import-01.json`
- `product-positive-model-exam-02.json`
- `product-positive-final-replay-03.json`
- `product-controls-prepared-03.json`
- `product-controls-gate3-review-04.json`
- `product-controls-dispatch-04.json`
- `product-controls-model-exam-01.json`
- `product-controls-completion-audit-01.json`
- `product-control-repair-headroom-01.json`
- `product-synthetic-recovery-model-01.json`
- `product-full-regression-plan-06.json`, `product-full-regression-shard-06-{1,2,3}.json`, `product-full-regression-summary-06.json`
- `product-final-regression-recheck-01.json`
- `product-closure-summary-01.json`

All 14 actual control tasks succeeded on their first attempt; no backend retries or extra generation were required.

Control run: `pilot-v3-b8d3e15f03772c9c312c6da8`; bounded worker: `job-f55763bdb7734717`. Artifacts reside under this worktree's `workspace/runs/phase34-nk2r-micro-20260915-01/`. All generation attempts and immutable evidence remain available for audit.

## Scientific limits and stopping state

Native PASS and model ranking establish computational triage, not experimental binding, NK2R inhibition, affinity, membrane approach or whole-VHH accessibility. The original five PASS candidates all contact only three of seven approved hotspots. Target-side design-mask area and sequence diversity are not full-VHH affinity or binding-mode diversity. The controls are small, altered-insertion reconnaissance runs; no zero-pass biological outcome was fabricated when they produced passes.

Phase 3 v1 is closed at Scientist Gate 4 with reviewable rankings and proposed next actions. No production Scale authority, production Scale job, further control expansion or autonomous Pilot loop was created. Phase 4 execution remains a separate Scientist decision.
