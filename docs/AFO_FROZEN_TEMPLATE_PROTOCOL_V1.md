# AFO frozen template protocol v1

Protocol ID: `afo-native-target-boltzgen-vhh-v1`

This document is the authority for the standard AFO template inputs used after
BoltzGen generation.  It changes template provenance only.  Target/binder MSA
policy, chain order, model release, model parameters, seeds, sample counts and
candidate ordering remain independently frozen by the run configuration.

## Target chain

The exact construct sequence and already-frozen target unpaired A3M are passed
to the unmodified AFO 3.1.4 native DataPipeline.  The configured target paired
A3M is preserved byte-for-byte.  The input starts with `templates: null` and the
runner is invoked with:

- `run_data_pipeline=true`
- `run_inference=false`
- `use_msa_server=false`
- receipt-pinned `hmmbuild`, `hmmsearch` and `hmmalign`
- receipt-pinned PDB seqres and local mmCIF snapshots
- one frozen `max_template_date`

The processed JSON must retain the exact target sequence and both MSA fields.
Templates must contain inline mmCIF plus non-empty, in-range `queryIndices` and
`templateIndices`.  A genuine zero-hit is recorded as an explicit terminal
protocol failure; the standard condition does not fall back to no template or
to a manually selected experimental structure.

Stage 05 does not automatically relabel this standard input as a second
`target-conditioned` prediction.  Doing so would create identical AFO inputs
with different scientific labels.  A state-specific source-structure condition
must instead be configured and audited as a separate experimental arm.

## Binder chain

Each candidate uses only its own BoltzGen stage-1 VHH structure.  The binder
chain is located by exact sequence identity, extracted into a VHH-only mmCIF,
renamed to chain `B`, and mapped over every binder residue.  A non-unique chain,
missing residue, sequence mismatch or mapping mismatch is terminal.  Target,
ligand, water, ion and unrelated chains are not copied.

Binder unpaired and paired MSA policies are not changed by this protocol.  In
the current frozen configuration both remain query-only.  In particular,
**binder paired MSA is not changed to an empty string**.

## Final inference and audit

The final target/binder input is produced deterministically and inference uses
`run_data_pipeline=false`, `run_inference=true`, and
`use_msa_server=false`.  Each target search, binder extraction and final input
has an immutable receipt.  The chain audit records chain ID, sequence length,
sequence hash, unpaired/paired MSA depth, template count, template source and
mapped residue count.  The final input hash, runner/model release, seed and
parameters remain part of the normal AFO evidence.

## Scope and fail-closed boundary

The active v1 complex contract is target + binder.  No current eight-target
validation task contains a Gα chain.  A future target/Gα/binder task must add a
three-chain prediction contract and its own independently processed Gα receipt
before it can enable this protocol; it must fail closed rather than silently
dropping Gα or pairing chains.

Production activation requires a clone-local component receipt for the HMMER,
seqres and mmCIF assets.  A test fixture or database from another clone is not a
valid production component.
