# 02 contract — Hotspot discovery

        [简体中文](CONTRACT.zh-CN.md)

        **Contract status:** conceptual, version `0.1`; machine schema is intentionally
        deferred until the first implementation has been validated.

        ## Inputs

        - Validated Target Bundle and canonical residue mapping.
- One or more enabled hotspot-source adapters.
- Optional preferred, forbidden, functional, competitor, or accessibility priors.

        ## Outputs

        - Hotspot sets expressed only in canonical residue identifiers.
- Avoid regions and conflicts with target annotations.
- Per-candidate source, evidence, method version, score, confidence, and warnings.
- A comparison report retaining disagreement among methods.

        ## Invariants

        - Every reported residue resolves through the Stage 01 mapping.
- Scores from different methods retain method-specific meaning and are not falsely equated.
- Heuristics, transferred evidence, and direct user input remain distinguishable.

        ## Failure states

        - Residues cannot be mapped or lie outside the canonical target.
- No enabled method can produce a valid candidate.
- Required annotations or reference complexes are inconsistent.

        Failures are written as terminal attempt records with typed error information.
        They are never converted into empty success. Retry creates a new attempt and
        references the failed attempt.

        ## Provenance requirements

        The manifest records upstream manifest and artifact hashes, resolved config,
        code revision, adapter/backend identity and version, model identity when
        applicable, random seeds, executor profile, timestamps, warnings, and all attempt
        states.

        ## Completion gate

        - At least one valid hotspot set exists or an explicit no-candidate result is recorded.
- Evidence and avoid regions are preserved.
- Selected candidates are suitable for Stage 03 without renumbering.
