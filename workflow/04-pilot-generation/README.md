# 04 — Pilot generation

        [简体中文](README.zh-CN.md) · [Contract](CONTRACT.md)

        ## Purpose

        Execute a real, small BoltzGen pilot with complete task and environment provenance.

        ## Supported use cases

        - Plan a bounded pilot budget across validated strategies.
- Submit through an executor adapter and collect task-level status.
- Normalize successful candidate outputs without altering raw backend artifacts.

        ## Boundary

        This stage owns its declared transformation and output validation. External tools
        are accessed through backend adapters. Orchestration, UI behavior, and downstream
        scientific decisions are outside this stage.

        ## Non-goals

        - Production-scale generation.
- Filtering or declaring scientific winners.
- Hiding partial failures by reporting only successful tasks.

        ## Implementation status

        `planned`. This directory specifies intended behavior; no scientific
        implementation is implied by the presence of these documents.
