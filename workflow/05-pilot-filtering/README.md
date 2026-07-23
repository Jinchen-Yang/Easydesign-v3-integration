# 05 — Pilot filtering

        [简体中文](README.zh-CN.md) · [Contract](CONTRACT.md)

        ## Purpose

        Apply versioned, system-specific evidence rules and select strategies for scaling.

        ## Supported use cases

        - Compute or import structure, interface, hotspot-contact, clash, and sequence metrics.
- Deduplicate candidates and preserve diversity.
- Apply hard gates and an explicit ranking policy.

        ## Boundary

        This stage owns its declared transformation and output validation. External tools
        are accessed through backend adapters. Orchestration, UI behavior, and downstream
        scientific decisions are outside this stage.

        ## Non-goals

        - Using one universal threshold profile for every target.
- Dropping failed candidates without a reason record.
- Treating a composite score as experimental validation.

        ## Implementation status

        `planned`. This directory specifies intended behavior; no scientific
        implementation is implied by the presence of these documents.
