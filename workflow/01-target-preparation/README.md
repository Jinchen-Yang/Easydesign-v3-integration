# 01 — Target preparation

        [简体中文](README.zh-CN.md) · [Contract](CONTRACT.md)

        ## Purpose

        Resolve heterogeneous target inputs into one canonical, traceable Target Bundle.

        ## Supported use cases

        - Local PDB or mmCIF structure.
- RCSB PDB identifier.
- FASTA file or raw amino-acid sequence.
- UniProt accession, gene, or protein-name query with organism context.
- PyMOL PSE session.
- An already prepared Target Bundle.

        ## Boundary

        This stage owns its declared transformation and output validation. External tools
        are accessed through backend adapters. Orchestration, UI behavior, and downstream
        scientific decisions are outside this stage.

        ## Non-goals

        - Selecting hotspots or generating binder designs.
- Claiming that a predicted target is equivalent to an experimental structure.
- Silently replacing a requested source with a different source.

        ## Implementation status

        `planned`. This directory specifies intended behavior; no scientific
        implementation is implied by the presence of these documents.
