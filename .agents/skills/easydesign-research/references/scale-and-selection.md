# Scale and selection

Scale consumes only a human promotion receipt. Default to 50,000 total candidates and show allocation,
backend, GPU occupancy, disk margin and immutable inputs before confirmation. Preserve checkpoint-safe
worker semantics; draining stops new scheduling and does not kill active scientific work.

Selection consumes one production lineage. Default to Top 200, apply the frozen filter/ranking contract,
and never duplicate or pad candidates. If fewer than 200 legal candidates exist, deliver the true count.
Keep empty result, scientific stop and operational failure distinct.

Review final manifests, checksums, representative structures and selection receipts. The read-only
viewer may display evidence but must not edit, approve, upload or submit anything.
