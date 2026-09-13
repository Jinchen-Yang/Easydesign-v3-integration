# Typed navigation for saved evidence results

The frozen `0885942b` GPCR attempt completed nine native summaries without the prior
context guard or duplicated-cutoff failure. It stopped before Handoff after the
four-round shared tool-repair allowance was exhausted. This remains a failed exam.

Saved calls show two interface confusions: `matching_chunks` is a scalar count,
not a pageable collection; and retrieved passage pages have `cards`, not the
`facts` key used by residue evidence. After summarization, opaque result handles
remained selectable while the model had to guess the object shape. Error text
for scalar paging also gave irrelevant residue-table advice on a literature page.

`read_evidence_result(ref)` now provides a bounded typed index without reading
scientific source content. Scoped reads retain their exact selector semantics.
Tool views expose the same index, including array lengths. Retrieval-page metadata
separates the saved `cards` list from the total match count and copies the exact
existing continuation cursor; it never synthesizes a query or a new cursor.

Unknown keys, conflicting selectors and offsets on scalar/object values still
reject. Current execution, role, Judge binding and artifact checksum checks precede
inspection exactly as they precede data reads. No repair or model-call budget was
increased. No source record, mapping service, scientific criterion or Gate authority
changed. Tests cover the actual scalar/list and wrong-result-schema patterns,
inspect-then-read through the assembled agent, and authority failures in inspection.
