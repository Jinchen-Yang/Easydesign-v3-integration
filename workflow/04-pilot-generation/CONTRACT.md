# 04 contract — Pilot generation

        [简体中文](CONTRACT.zh-CN.md)

        **Contract status:** conceptual, version `0.1`; machine schema is intentionally
        deferred until the first implementation has been validated.

        ## Inputs

        - Validated strategy bundle and pilot budget.
- BoltzGen backend plus local/Slurm/SMART-capable executor profile.
- Resource limits, retry policy, and deterministic seed policy.

        ## Outputs

        - Immutable raw backend outputs and logs per attempt.
- Task table containing submitted, running, succeeded, failed, and cancelled states.
- Normalized candidate index with strategy and source-artifact links.
- Resolved environment and backend provenance.

        ## Invariants

        - Raw outputs are never rewritten during collection.
- Each candidate maps to one strategy, task, seed, and attempt.
- Executor state and scientific result state remain separate.

        ## Failure states

        - Backend capability or executable does not match the validated plan.
- Resource, scheduler, or task failure.
- Output is incomplete, corrupt, or cannot be linked to its strategy.

        Failures are written as terminal attempt records with typed error information.
        They are never converted into empty success. Retry creates a new attempt and
        references the failed attempt.

        ## Provenance requirements

        The manifest records upstream manifest and artifact hashes, resolved config,
        code revision, adapter/backend identity and version, model identity when
        applicable, random seeds, executor profile, timestamps, warnings, and all attempt
        states.

        ## Completion gate

        - All tasks reach a terminal state and are represented in the manifest.
- Successful outputs pass structural collection validation.
- Partial completion is explicit and acceptable only under the configured gate.
