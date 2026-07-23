# 03 contract — BoltzGen configuration

        [简体中文](CONTRACT.zh-CN.md)

        **Contract status:** conceptual, version `0.1`; machine schema is intentionally
        deferred until the first implementation has been validated.

        ## Inputs

        - Target Bundle manifest and selected hotspot sets.
- Reviewed VHH scaffold registry with provenance.
- Design priors, BoltzGen backend capability, and pilot strategy policy.

        ## Outputs

        - Validated BoltzGen YAML files with stable strategy identifiers.
- Strategy matrix manifest linking target, hotspot, scaffold, and parameters.
- Resolved asset bundle and validation report.

        ## Invariants

        - A strategy is reproducible from its manifest and immutable asset checksums.
- Generated YAML never claims unsupported backend capabilities.
- Scaffold provenance is accepted before use.

        ## Failure states

        - Missing or unreviewed scaffold asset.
- Unsupported BoltzGen field or incompatible backend version.
- Hotspot expression cannot be represented without ambiguity.

        Failures are written as terminal attempt records with typed error information.
        They are never converted into empty success. Retry creates a new attempt and
        references the failed attempt.

        ## Provenance requirements

        The manifest records upstream manifest and artifact hashes, resolved config,
        code revision, adapter/backend identity and version, model identity when
        applicable, random seeds, executor profile, timestamps, warnings, and all attempt
        states.

        ## Completion gate

        - Every planned strategy validates against the declared backend.
- All referenced assets exist and match checksums.
- Stage 04 can execute without modifying scientific configuration.
