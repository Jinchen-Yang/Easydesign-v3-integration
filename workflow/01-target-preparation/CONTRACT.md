# 01 contract — Target preparation

        [简体中文](CONTRACT.zh-CN.md)

        **Contract status:** conceptual, version `0.1`; machine schema is intentionally
        deferred until the first implementation has been validated.

        ## Inputs

        - TargetRequest: exactly one source kind plus source-specific parameters.
- Structure-selection policy and explicit prediction fallback policy.
- Optional chain/domain choice and biological constraints.

        ## Outputs

        - Canonical `target.cif`; optional derived `target.pdb` for a declared backend need.
- `sequence.fasta` and an explicit residue-number mapping table.
- Target metadata, source records, structure-quality report, and artifact checksums.
- Stage manifest identifying whether the structure is experimental, imported, or predicted.

        ## Invariants

        - Canonical residue identity and mapping are unambiguous.
- Every search, ranking, download, conversion, and fallback is recorded.
- The original input remains referenced by checksum and is never overwritten.

        ## Failure states

        - Invalid or ambiguous source request.
- No acceptable structure under the declared policy.
- Sequence/structure mismatch, unsupported chemistry, or unresolved chain selection.
- Conversion or mapping fails validation.

        Failures are written as terminal attempt records with typed error information.
        They are never converted into empty success. Retry creates a new attempt and
        references the failed attempt.

        ## Provenance requirements

        The manifest records upstream manifest and artifact hashes, resolved config,
        code revision, adapter/backend identity and version, model identity when
        applicable, random seeds, executor profile, timestamps, warnings, and all attempt
        states.

        ## Completion gate

        - All required Target Bundle artifacts validate and are checksummed.
- Source and fallback decisions are explicit.
- The Stage 02 consumer can resolve every residue through the mapping.
