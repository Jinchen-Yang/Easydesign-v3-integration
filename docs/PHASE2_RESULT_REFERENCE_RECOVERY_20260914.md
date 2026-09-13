# Repairing an unissued result reference

Fresh case `phase2-goldens-20260913T194242288354Z` at `8c9abad` stopped during
Research: its summary transposed `cf9f` to `fc9f` in an opaque result ID. The
original result and issuance event were correct, but the next read treated the
never-issued ID as an unrecoverable authority violation. No Site Judge ran.

For Target and Site readers only, distinguish an unissued well-formed ID from a
known foreign reference. An unissued ID returns no content and lists at most 20
recent IDs already issued to the same role, thread and execution. The model must
explicitly choose an exact reference; there is no fuzzy lookup or auto-correction.
Each catalog entry also offers a short `result:N` handle to its immutable issuance
event. Reading that handle resolves the original reference and applies the same
role/thread/execution and artifact checks. Evidence bytes and UUID paths stay intact.
The first real catalog-only replay still copied the UUID incorrectly; the short
handle avoids requiring the model to distinguish transposed characters in long IDs.
This uses the existing shared four-round tool-argument repair budget. Repeated
errors still exhaust that budget.

Known cross-role, cross-thread and old-execution references remain fatal. Invalid
paths, unregistered existing artifacts, checksum failures and Judge snapshot
boundaries remain fatal. The repair catalog grants no access; the subsequent read
again performs the full original authorization and integrity checks.

Preserve the failed case and replay its exact mistyped read against an isolated
ledger. Validate the real model's recovery and denial cases before a clean commit
and another frozen fresh GPCR. No scientific input, oracle or budget is changed.
