# Explicit source selection and focused retrieval in one call

The frozen GPCR attempt at 8ea5ee1 ended during Research, before Handoff or Judge.
It used 34 Site calls including 8 summaries, with maximum input 74,014 characters.
The shared four correction rounds were exhausted: one initial acquisition batch,
three invalid projection calls in one later batch, and two source/need mismatches.
A further RCSB read changed PPI_INTERFACE to STRUCTURE_STATE without selecting that
source for the new need. No hard fact, budget or model configuration was changed.

`retrieve_evidence` now accepts optional `selection_reason` for an exact acquired
`source_id` and a new query. Like the existing acquisition option, this is the
Agent's explicit selection with a reason, recorded through `EvidenceCorpus.select`
for the current thread, binding and need before the focused read. It makes no
network acquisition. Original source and corpus checksums are verified first.

Missing reasons retain existing selection requirements and bounded repair. Unknown
sources are not inferred, selected, searched or acquired. Cursor continuation
cannot change selection; it retains existing issued-query and authority checks.
Other threads, needs and revisions do not inherit the new selection. Selection
is neither entailment nor Scientist approval. The existing separate selection API
and SELECTED/DEFERRED/EXCLUDED decisions remain available.

The Site instructions use the atomic option whenever selection is uncertain and
avoid putting a separate selection beside its dependent read in a parallel batch.
This is an interface correction, not an increase in repair budget or taxonomy
coverage. Tests cover real harness execution, exact source preservation, new-need
and thread/binding separation, unknown references, malformed requests and tamper
rejection. Saved-case and real-model replay results are retained under runtime/tmp.
