# Phase 4 global scientific comparison — 2026-09-17

Starting authority: `ea8e5b2bd099c096d1767eaec7047382569507a9`.
Status: **PASS — global ranking and capacity acceptance complete.**
Runtime/test acceptance commit: `c36da40b592fff553ad9a6833faa24e48f602df8`.

The native review entry previously selected up to 30 observations by engineering RMSD order,
with exact-sequence deduplication and Arm coverage. Final Selection could compare multiple
metrics only within that restricted population. A candidate beyond the cutoff was invisible.

The new entry retains all eligible observations, including different poses of equal sequences.
Pilot and Scale load one shared scientific ranking reference. Decision views use lossless
value tables and metric vectors; full facts remain in Runtime. Calls are sized with prompt,
schema, repair reserve, output estimates and provider context limits. Populations that fit
are compared together. Oversized populations use recorded scientific comparisons over globally
mixed groups and subsequent cross-group rounds, never an RMSD filter or per-batch Top-N.

FinalSelectionOpinion remains the only final panel proposal. Capacity rounds use the same
Final Selection role and the existing model-call ledger, not a new Agent. Runtime validates
complete ID coverage and advancement; successful opinions can be reused after restart only
with identical evidence, configuration, prompt, implementation and science reference. Gate 5
shows comparison coverage and explicitly discloses the approximation of hierarchical selection.
Exact-sequence deduplication is applied to final panel membership, retaining all observations.

Native profiles/decisions, AFO/Judge optionality, Gate 4 production intent, execution projections,
batch completeness, stale-card guards and validation-only handoff semantics are unchanged.
Legacy saved contract hashes are preserved when the additive ranking audit is absent.

Targeted scenarios include 60 PASS across three synthetic Arms, initial malformed submission,
200 PASS with an intentionally smaller context budget, a good interface candidate outside the
old RMSD Top30, lossless metric/missing-value projection, restart reuse, changed-evidence
invalidation, no hidden truncation, and all 61 native PASS published despite review_count=30.
Synthetic opinions establish software reachability and coverage, not biological ranking validity.

Remaining limits: hierarchical comparison can lose a candidate in an earlier scientific round;
it is not equivalent to an exhaustive all-pairs ranking. Exact sequence grouping does not
establish pose diversity. Production-scale GPU throughput and wet-lab performance are outside
this validation. A campaign too large for the per-execution call budget requires an explicit
resume; completed comparison receipts remain reusable.

## Frozen acceptance

All three real-model checks used configured `deepseek-v4-pro`, with the existing 8,192-token
output cap and 100,000-character hard input guard. Each completed after one bounded schema
repair; there were no max-token failures. Group comparison opinions in the hierarchical
check submitted successfully on their first attempts. These receipts count actual model-call
and model-response events, not the OpenAI-only request observer (empty for this transport).

| Case | Evidence | Comparison | Calls | Peak input incl. schema | Peak provider output tokens |
| --- | --- | --- | ---: | ---: | ---: |
| Current NK2R Gate 4 → Gate 5 | 15 saved native results; 3 PASS | direct | 2 | 29,121 | 3,229 |
| 60 candidates / 3 Arms | synthetic metric fixture; real model | direct | 2 | 24,332 | 1,543 |
| 100 candidates, 22k soft budget | synthetic metric fixture; real model | 6 group comparisons → 26 finalists | 8 | 17,367 | 4,349 |

The 60/100-row real-model fixtures exercise a compact six-metric scientific contrast, not
new protein generation. In both, a stronger-interface candidate beyond the former RMSD
Top30 was selected into the panel. This demonstrates visibility and model use of the
tradeoff, not biological superiority or a guarantee about every future selection.

A separate 60-row density fixture starts from the current NK2R decision view, preserves all
41 native/context metric columns and shared profiles/Arm context, and deliberately perturbs
floating-point values to prevent artificial deduplication of identical metric vectors. These
perturbed rows are synthetic capacity evidence only. Lossless round-trip checks pass for
every call. A single packed call would require 77,976 characters (83,976 with repair reserve),
so the configured 60k working budget correctly triggers two comparisons plus a final call;
peak actual harness input is 51,532 characters. The latter check uses scripted opinions.
Thus candidate count alone never decides whether a call fits.

NK2R uses a new isolated project copy, with the original Pilot dossier, selected strategies,
production intent and all native measurements unchanged. Nine precomputed batches retain
15 observations, including 12 FAIL rows. Controlled missing-batch recovery and idempotent
receipt replay pass. Gate 5 proposes one primary and two backups, with Judge not requested.
A separate process resumes the same card with zero additional model calls; repeated approval
retains the same handoff. Every selected candidate is traced through its original native
profile, sequence/structure refs, batch/strategy, Gate 4 allocation and upstream Design/Site/Target.
The handoff remains `validation-only-not-authorized-for-experiment` and `not-ordered`.
No new GPU generation, AFO sweep or wet-lab action was performed.

Full regression: **1,274 passed, 11 skipped, zero failed/errors; 1,285 collected**. Three
disjoint JUnit populations match all collected node IDs exactly. Shards report 407/442/425
passed and 5/3/3 skipped. Skips are the existing three opt-in live API/backend tests and
eight unavailable PyMOL integration cases. Real Final Selection calls are separately
covered above. `make check` passes: repository structure, viewer asset checksums, compilation,
Ruff and mypy across 233 source files. All eight new targeted tests pass.

The normal `dev.py verify --mode integration` entry was invoked on the changed tree. Its
serial suite was deliberately interrupted after 38 PASS/11 SKIP to run complete disjoint
shards faster; that interrupted attempt is preserved, not counted as full acceptance. The
complete replacement suite and exact coverage receipt provide regression acceptance.
Initial development failures concerned output reservation/default budget and test execution
identity; both were fixed before the code freeze. The development context reports existing
historical worktrees under a legacy single-branch policy; the user's current Phase 4 worktree
authority governs, and no other worktree or source history was changed.

## Review receipts

All files below remain under `runtime/tmp/` in the development workspace:

- `phase4-ranking-full-regression-summary-01.json` and `phase4-ranking-full-01-shard-{0,1,2}.*`
- `phase4-ranking-live-select-01.json` and `phase4-ranking-live-approve-01.json`
- `phase4-ranking-capacity-live-01.json` and `phase4-ranking-hierarchy-live-01.json`
- `phase4-ranking-native-density-01.json` and `phase4-ranking-native-density-02.json`
- `phase4-ranking-targeted-04.log`, `phase4-ranking-make-check-01.log`
- `phase4-ranking-package-data-01.json` and `phase4-ranking-source-copy-01.json`

The final post-freeze delta is report/README prose and one package-data inclusion for the
new shared Markdown reference. Runtime and test source remain byte-identical to the acceptance
commit. Actual setuptools data-file discovery verifies that the reference is included; no
release version bump or wheel build was performed.
