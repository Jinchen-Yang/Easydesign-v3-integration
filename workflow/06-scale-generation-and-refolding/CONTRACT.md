# 06 contract — Scale generation and refolding

        [简体中文](CONTRACT.zh-CN.md)

        **Contract status:** conceptual, version `0.1`; machine schema is intentionally
        deferred until the first implementation has been validated.

        ## Inputs

        - Selected strategies, frozen Stage 05 evidence, and explicit scale budget.
- Generation backend, executor profile, and structure-prediction backend capability.
- Deduplication and expensive-evaluation allocation policy.

        ## Outputs

        - Scaled candidate index with complete generation provenance.
- Deduplicated prediction request manifest.
- Raw and normalized structure-prediction results with model provenance.
- Coverage report for generated, selected, submitted, completed, and failed candidates.

        ## Invariants

        - Scale budget is configuration, not a hidden constant; 50,000 belongs to a future SMART production profile.
- Backend-specific fields stay inside adapters and map to a generic result contract.
- Prediction coverage and failure bias are visible.

        ## Failure states

        - Budget, backend capability, or executor profile is incompatible.
- Candidate identity is lost during deduplication or request preparation.
- Prediction output is incomplete, corrupt, or cannot be normalized.

        Failures are written as terminal attempt records with typed error information.
        They are never converted into empty success. Retry creates a new attempt and
        references the failed attempt.

        ## Provenance requirements

        The manifest records upstream manifest and artifact hashes, resolved config,
        code revision, adapter/backend identity and version, model identity when
        applicable, random seeds, executor profile, timestamps, warnings, and all attempt
        states.

        ## Completion gate

        - All planned tasks are terminal and coverage is reported.
- Every normalized prediction maps to one candidate and model execution.
- Stage 07 can evaluate results without backend-specific directory scanning.
