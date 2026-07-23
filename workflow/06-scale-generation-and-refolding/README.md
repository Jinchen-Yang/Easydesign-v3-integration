# 06 — Scale generation and refolding

        [简体中文](README.zh-CN.md) · [Contract](CONTRACT.md)

        ## Purpose

        Scale selected strategies and evaluate candidates through a generic structure-prediction backend.

        ## Supported use cases

        - Generate at an explicit scale budget using the same traced execution contract.
- Normalize and deduplicate candidates before expensive prediction.
- Prepare, execute, and collect generic complex-structure prediction requests.

        ## Boundary

        This stage owns its declared transformation and output validation. External tools
        are accessed through backend adapters. Orchestration, UI behavior, and downstream
        scientific decisions are outside this stage.

        ## Non-goals

        - Hardcoding 50,000 designs into the stage contract.
- Binding the contract to Phoenix, AFO, AF3, or any single model brand.
- Treating a model ranking score as final ordering approval.

        ## Implementation status

        `planned`. This directory specifies intended behavior; no scientific
        implementation is implied by the presence of these documents.
