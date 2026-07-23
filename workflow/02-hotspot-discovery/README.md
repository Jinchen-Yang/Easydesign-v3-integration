# 02 — Hotspot discovery

        [简体中文](README.zh-CN.md) · [Contract](CONTRACT.md)

        ## Purpose

        Produce comparable hotspot candidates and avoid regions with explicit evidence.

        ## Supported use cases

        - Manual residues or imported hotspot definitions.
- A mature SASA/surface-geometry baseline with transparently labeled custom ranking.
- Known-complex interface transfer with residue mapping.
- UniProt functional annotations and user-supplied biological priors.

        ## Boundary

        This stage owns its declared transformation and output validation. External tools
        are accessed through backend adapters. Orchestration, UI behavior, and downstream
        scientific decisions are outside this stage.

        ## Non-goals

        - Pretending a geometric patch score is energetic hotspot prediction.
- Choosing a final binder sequence.
- Discarding candidate methods because they disagree.

        ## Implementation status

        `planned`. This directory specifies intended behavior; no scientific
        implementation is implied by the presence of these documents.
