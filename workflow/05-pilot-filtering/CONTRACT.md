# 05 contract — Pilot filtering

        [简体中文](CONTRACT.zh-CN.md)

        **Contract status:** conceptual, version `0.1`; machine schema is intentionally
        deferred until the first implementation has been validated.

        ## Inputs

        - Stage 04 candidate index and referenced raw artifacts.
- Versioned per-system filter profile and metric backend capabilities.
- Deduplication, diversity, gate, and ranking policies.

        ## Outputs

        - Candidate-by-rule pass/fail table with values, thresholds, and reasons.
- Deduplication and clustering assignments.
- Ranked pilot shortlist and selected scaling strategies.
- Filter configuration snapshot and method provenance.

        ## Invariants

        - Every decision is reconstructible from preserved metrics and configuration.
- Missing metrics follow an explicit fail, skip, or review policy.
- Raw candidate artifacts remain immutable.

        ## Failure states

        - Required metric cannot be produced or mapped to a candidate.
- Filter profile is invalid, incompatible, or lacks a version.
- No strategy passes; this is recorded as a valid negative scientific result.

        Failures are written as terminal attempt records with typed error information.
        They are never converted into empty success. Retry creates a new attempt and
        references the failed attempt.

        ## Provenance requirements

        The manifest records upstream manifest and artifact hashes, resolved config,
        code revision, adapter/backend identity and version, model identity when
        applicable, random seeds, executor profile, timestamps, warnings, and all attempt
        states.

        ## Completion gate

        - Every candidate has an auditable disposition.
- The selected strategy set is non-empty or an explicit no-scale decision exists.
- Stage 06 receives a frozen filter snapshot and selected strategy manifest.
