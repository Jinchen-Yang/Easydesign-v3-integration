# Strategy YAML

Draft strategy from the current approved target/site foundation. Discuss target crop, binding-residue
subset, scaffold choice, CDR design ranges/insertion lengths, per-variant candidate count, rationale and
expected result. Default to all seven registered scaffolds and 40 candidates per explicit variant, but
do not force a region-by-scaffold Cartesian product when the experiment asks a narrower question.

Use `strategy validate` for staging compilation and real BoltzGen validation. It publishes nothing.
Use `strategy freeze --confirm` only after the researcher approves the exact file; the frozen revision
is immutable.

An expert native BoltzGen YAML is allowed only after it is copied into project inputs, checksummed,
validated by the registered BoltzGen 0.3.2 backend, and referenced by the scientific manifest. Reject
out-of-range crop/residues, binding residues outside the approved site, unknown scaffolds, invalid CDR
overrides, or backend check failure.
