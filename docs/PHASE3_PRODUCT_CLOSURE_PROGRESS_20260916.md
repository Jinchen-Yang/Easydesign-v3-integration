# Phase 3 Product Closure — active implementation

Authoritative base: `a5d5dead9b572dfa1e65aa6b1c8c4fe824bcd35c` (clean integration HEAD).
Branch: `codex/easydesign-v3-phase3-product-v1`.
Worktree: `/data/easydesign-worktrees/v3-phase3-product-20260916` on Suzhou2.
The previous integration worktree and all original NK2R outputs remain intact.

## Authorized scope

The user approved the complete Phase 3 Product Closure assignment on 2026-09-16,
including bounded actual controls, and clarified that the supplied metric manual is
only a calculation reference. No lulu-specific thresholds, policies or outcomes enter
the product. Preserve Phase 2, Gate 3 authority, Phase 4 promotion and all scientific
provenance. Stop at Gate 4; no production Scale or autonomous Pilot loop.

Initial control budget: short CDR3 and aggressive CDR3, each seven scaffolds by ten
candidates (140 new candidates). If aggressive reconnaissance naturally has coherent
near-zero native passes due to refold failure, its total may be expanded to 280;
maximum new unique candidates then 350. No repeated mutation to manufacture zero-pass.
Retries retain their bounded attempt budget and are reported separately.

## Implementation checkpoint

- Added native filter profiles/decisions with exact saved task configuration and pinned
  BoltzGen 0.3.2 source identity. Native pass is reconciled against per-rule values.
- Added scientific Arm grouping, completion/evaluability routing, PASS candidate and
  Arm boards, zero-pass failure histograms, per-Arm recovery and metric-rank evidence.
- Native Pilot measurement no longer requires independent prediction. Existing AFO
  measurement kernel and Phase 4 behavior remain available.
- Phase 3 cards can explicitly record optional Judge as not requested; Gate 1–3/5
  rules are unchanged. Historical absent-field serialization is preserved.
- Specialist Skill now distinguishes ranking, recovery and operational incompleteness;
  calculation reference is loaded into the actual model prompt.

## Evidence and work remaining

The real positive case is the existing 5/280 NK2R Arm 1 Pilot: Suzhou2 contributes 7eow,
Xiamen the remaining six scaffolds. Its source aggregate job remains incomplete on
Suzhou2 and is not rewritten. Import must verify task/structure/config identities and
form a derived evidence view, not falsely mark that source run successful.

Verified import now covers all 280 candidates and five native PASS candidates, with
declared immutable sources, current Gate 3 authority and exact YAML identities. The
complete columnar Specialist packet is 60,900 characters; original metric names/values
are retained. The import receipt is `runtime/tmp/product-positive-import-01.json`.
Source-byte integrity is rechecked on interpretation and Gate 4 approval reads.

Foundation checks passed (24 tests before the additional integrity/allocation checks;
19 focused native/contract checks afterward). Five existing Gate 4 runtime tests
passed, covering STOP, another Pilot, Design/Site revision and idempotency. Changed
source passes Ruff and Mypy. The clone-local BoltzGen environment is installed.

Still required: complete runtime regressions; bounded controls and actual Specialist calls; exact
Gate 4 artifact/restart acceptance; final full regression, report and clean commits.
This document is a progress record, not a Phase 3 completion claim.

## Real positive and bounded-control preparation

Commits `42570757`, `c8dd902d` and `84aa03bb` implement native ranking, the mandatory
ranked promotion proposal for complete passing Arms, and explicitly approved smaller
Pilot allocations while preserving the default Phase 2 Design budget.

The first real model attempt ranked all five positives but recommended Design revision;
it therefore did not satisfy promotion acceptance. This exposed residual diagnosis-first
semantics. The runtime/Skill contract now requires the ranked Scale proposal, retaining
all scientific concerns and the Scientist's STOP/revision choices.

`runtime/tmp/product-positive-model-exam-02.json` records successful DeepSeek V4 Pro
acceptance on `84aa03bb7354d3568d2c5ada411a745fbe251d04`: five candidates ranked,
one complete PROMOTION Arm, an explicit four-scaffold allocation, and the same Gate 4
card after restart without another model call. Two calls were used (one compact repair
after output truncation). No Scale authority or generation was created.

The two controls use insertion ranges `1..3` and `45..55`, not universal final CDR3
lengths. All 14 actual compiled YAMLs passed backend validation; CDR1/2, insertion anchors,
remaining design/exclude regions, target, seven hotspots and 87 avoid residues are
unchanged. The source Design keeps its default 40/scaffold budget; the explicit Pilot
approval will authorize only 10/scaffold for each Arm (140 total). No control GPU run
has started at this checkpoint.

Further readiness checks cover pending new Design versus historical approval, completed
zero-pass recovery evidence, provisional incomplete rankings, candidate-attempt filter
profiles, optional review access and source integrity on direct approval. These are
being validated before control dispatch. Original runs and earlier acceptance attempts
remain preserved, including failed preparation/test attempts.

## Gate 3 truncation discovered during real control review

On `b7bd8bc9dbd45cf6002de1ef377a115679f0b291`, the prepared controls passed all
14 backend checks. The actual Gate 3 Judge then exhausted 8,192 output tokens on
three consecutive review responses (after an initial scoped evidence read), without
a typed verdict. Its existing two-repair limit correctly stopped execution. No control
GPU generation or approval occurred. Receipt/log: `product-controls-prepared-02.json`
and `product-controls-gate3-review-02.log` under `runtime/tmp`.

The correction is restricted to a truncated legacy Judge response: use the same
delivered evidence and model with only the typed verdict tool, and a transient
non-thinking DeepSeek adapter for compact recovery. Preserve the configured first call,
8,192 output limit, shared call budget, two-repair budget, fact/stage validators and
Scientist authority. The configured model/client remains unchanged. DeepSeek explicitly
documents that Anthropic `thinking.budget_tokens` is ignored; merely setting it to 1,024
does not reserve space for a final verdict. See the
[official compatibility reference](https://api-docs.deepseek.com/guides/anthropic_api/).

Actual-SDK mocked transport tests verify the disabled-thinking recovery, unchanged
output allowance, verdict-only tool surface, rejection of wrong-stage verdicts and
continued refusal to publish without delegated evidence authority. The first full
regression attempt collected 1,238 tests, then was deliberately interrupted for this
live-discovered fix; it is not a completed regression claim. Failed/interrupted logs
are retained, and the final frozen implementation requires a new full regression.
