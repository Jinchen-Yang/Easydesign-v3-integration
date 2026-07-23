# 07 contract — Final filtering and selection

        [简体中文](CONTRACT.zh-CN.md)

        **Contract status:** conceptual, version `0.1`; machine schema is intentionally
        deferred until the first implementation has been validated.

        ## Inputs

        - Stage 06 normalized prediction results and original candidate provenance.
- Versioned final filter/ranking profile and requested maximum Top N.
- Clustering, diversity, and human-review policy.

        ## Outputs

        - Candidate-by-rule final decision table.
- Ranked and diversity-aware Top N recommendation.
- Review package containing sequences, structures, metrics, warnings, and audit links.
- Explicit human approval state; no external order side effect.

        ## Invariants

        - Top N is a maximum, never a requirement to include failing candidates.
- Every ranking value and exclusion reason is preserved.
- Recommendation, approval, ordering, and experimental validation are distinct states.

        ## Failure states

        - Final profile is invalid or required evidence is missing.
- No candidate passes; record an empty recommendation as a valid outcome.
- Review package cannot reproduce candidate identity or provenance.

        Failures are written as terminal attempt records with typed error information.
        They are never converted into empty success. Retry creates a new attempt and
        references the failed attempt.

        ## Provenance requirements

        The manifest records upstream manifest and artifact hashes, resolved config,
        code revision, adapter/backend identity and version, model identity when
        applicable, random seeds, executor profile, timestamps, warnings, and all attempt
        states.

        ## Completion gate

        - Every evaluated candidate has a final auditable disposition.
- The recommendation contains no failing candidate and respects diversity policy.
- A human can approve or reject without accessing hidden backend state.
