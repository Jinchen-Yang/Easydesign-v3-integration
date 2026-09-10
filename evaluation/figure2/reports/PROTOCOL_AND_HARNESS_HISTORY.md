# Protocol and instrumentation history

This is prospective benchmark version 0.1.0 against the dirty EasyDesign v2.1
working tree, not a new EasyDesign software release. No core scientific source
or initial frozen evaluator threshold was changed during these measurements.

1. `provenance/freeze.json` records the commit, dirty state, 397 source hashes,
   initial protocol/target/evaluator/fault configurations and original CPU runner.
2. Tier 0 ran the original CPU harness, whose exact bytes are retained in
   `provenance/harness-at-freeze/run_cpu.py`. Its hash matches the initial freeze.
3. Before Tier 1, the CPU harness gained conditional SASA scan/strategy-draft
   attempts after successful target preparation, and per-episode runner hashing.
   This change did not alter Tier 0 cases, assertions, or scientific core code.
   All Tier 1 receipts record their actual runner hash. They are setup diagnostics,
   not a preregistered main three-method comparison.
4. A separate 12-case model decision-policy probe was added before model responses.
   Its input/case hashes and actual CLI command are in every episode. The first
   attempt in both arms failed before inference because the CLI rejected an
   override of the reserved OpenAI provider. The unsupported flag was removed;
   three successful sessions per arm (r2–r4) followed. Initial failures remain
   raw and unscorable. WebSocket retry and HTTP fallback time is not method speed.
5. Post-run work adds portable artifact copies, failure classification, report/plot
   generation, conservative evaluator input-validation tests, and a checksum-aware
   GPU queue validator. These changes do not retroactively alter raw receipts.
   The HQ cutoff profile remains byte-identical to the original freeze.

`runners/` contains the final analysis and instrumentation code. Historical
commands are retained even when a historical runner's full bytes are unavailable.
Package-level checksums seal the complete delivered record after execution;
they are not represented as externally timestamped preregistration.

During final QA, BBF-14's recorded target-preparation success was distinguished
from the later site-scan approval request. Original episode fields are untouched.
The v2 classification sidecars consume the actual later CLI response; final tables
therefore count these three episodes as awaiting site approval, not successful
executable-project completion or an unexplained draft failure. The v1 sidecars
are retained for an explicit correction trail.

## Target correction required for a successor manifest

The initially selected BHRF1 accession P03182 does not match RCSB 2WH6 entity 1.
The archived RCSB entity reports P0C6Z1, author chain A, Epstein–Barr virus AG876.
This is a verified accession/strain mismatch, not failed model performance.
Use P0C6Z1 only in an explicit successor target manifest if the intended target
is the deposited AG876 construct; otherwise select an appropriate structure for
the intended strain. Preserve all three original blocked-input attempts.
The current frozen target selection is deliberately unchanged, and no silent
nearest-sequence fallback or replacement outcome is introduced.

## Scientific design review before the main comparison

Read `CONTROLLED_ESTIMAND_REVIEW.md`. A fixed first-wave generator-input comparison
does not by itself test interpretation-driven improvements in design quality.
A two-wave, equally budgeted adaptation comparison needs a separate prospective
protocol and cost approval, not a post hoc expansion of the present denominator.
