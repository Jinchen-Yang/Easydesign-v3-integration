# 07 — Final filtering and selection

        [简体中文](README.zh-CN.md) · [Contract](CONTRACT.md)

        ## Purpose

        Apply final evidence rules, preserve diversity, and package an auditable Top N for human approval.

        ## Supported use cases

        - Apply final structural, interface, confidence, clash, and system-specific gates.
- Rank and cluster passing candidates under a declared diversity policy.
- Package sequences, structures, metrics, warnings, and provenance for review.

        ## Boundary

        This stage owns its declared transformation and output validation. External tools
        are accessed through backend adapters. Orchestration, UI behavior, and downstream
        scientific decisions are outside this stage.

        ## Non-goals

        - Automatically placing synthesis orders in EasyDesign 1.0.
- Suppressing negative or uncertain evidence to fill Top N.
- Claiming selected candidates are experimentally validated.

        ## Implementation status

        `planned`. This directory specifies intended behavior; no scientific
        implementation is implied by the presence of these documents.
