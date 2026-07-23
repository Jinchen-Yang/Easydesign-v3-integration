# 03 — BoltzGen configuration

        [简体中文](README.zh-CN.md) · [Contract](CONTRACT.md)

        ## Purpose

        Resolve target, hotspot, VHH scaffold, and priors into validated BoltzGen strategies.

        ## Supported use cases

        - Generate a strategy matrix across selected hotspot sets and reviewed VHH scaffolds.
- Resolve all asset references into a self-contained execution bundle.
- Validate generated YAML against the declared BoltzGen capability/version.

        ## Boundary

        This stage owns its declared transformation and output validation. External tools
        are accessed through backend adapters. Orchestration, UI behavior, and downstream
        scientific decisions are outside this stage.

        ## Non-goals

        - Executing BoltzGen.
- Supporting non-VHH binder families in EasyDesign 1.0.
- Embedding cluster paths or credentials into generated scientific configuration.

        ## Implementation status

        `planned`. This directory specifies intended behavior; no scientific
        implementation is implied by the presence of these documents.
