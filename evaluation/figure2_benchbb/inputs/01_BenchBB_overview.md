# BenchBB overview

## Definition

BenchBB is a curated set of seven protein targets proposed as a rigorous, consistent, and practical benchmark for computational binder-design methods. The target selection balances four considerations stated by the official authors:

1. **Novel interfaces**: limit over-representation in common model-training data.
2. **Challenging conformations**: cover targets whose conformational behavior permits different binding mechanisms.
3. **Therapeutic relevance**: include targets with translational value.
4. **Experimental accessibility**: favor recombinant production and broad laboratory validation, often including expression in *E. coli*.

## What is official

- The seven-target catalog.
- Label-free binding measurement with BLI or SPR.
- Reporting of `kon`, `koff`, and `KD` when available.
- Sharing assay conditions and raw kinetic data where feasible.
- A binder/hit definition of measurable binding with `KD <= 10 µM`.

## What is not an official BenchBB score

The following may be useful in an EasyDesign computational screen but are not substitutes for the official hit definition:

- Boltz2 or AlphaFold confidence values;
- interface PAE or ipTM alone;
- target-aligned or binder RMSD alone;
- hotspot satisfaction, interface area, hydrogen bonds, salt bridges, or clash counts;
- any unpublished weighted composite score;
- an LLM judge opinion.

The official article also cautions that computational quantities such as ipAE, iPTM, and ESM2 pseudo-log-likelihood showed only weak correlation with experimentally measured affinity in the cited EGFR dataset. Computational metrics should therefore be reported as model-quality and triage evidence, not as affinity measurements.

## EasyDesign interpretation

For the first preprint version, EasyDesign can use BenchBB targets to compare project formation, design completion, candidate quality, recovery, and robustness. That work should be labelled **BenchBB-derived computational evaluation**. A later wet-lab phase can add official BenchBB binding outcomes.

Sources and retrieval records are listed in `sources/SOURCE_INDEX.md`.
