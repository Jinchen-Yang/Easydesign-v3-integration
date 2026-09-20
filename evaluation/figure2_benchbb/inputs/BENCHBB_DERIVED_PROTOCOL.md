# BenchBB-derived computational protocol

## Frozen inputs

For each target and comparison group, freeze the same coordinate file, natural-language objective, permitted public tools, wall-time policy, LLM/provider settings where applicable, candidate-generation budget, refold method, and validation profile.

## Two evaluation layers

**Project formation** ends when the system has a valid target identity, chain and residue mapping, ranked/selectable site portfolio, scientist-approved site, and backend-valid design YAML.

**Candidate evaluation** starts from the approved YAML and uses identical generation, refold, native analysis, filtering, and selection budgets for all groups.

## Failure and repair accounting

Record every failure with timestamp, stage, observed error, root cause, state before repair, code or data change, state after repair, rerun scope, human active time, and whether the final measured run was fresh. Repairs made while developing a system are development work; the final benchmark must use a frozen commit on an unseen fresh run.

## Statistical unit

The target/task is the primary unit for cross-target claims. Multiple generated candidates from one target are not independent target-level replicates. Show candidate distributions for descriptive evidence, and keep target-level uncertainty explicit when the initial study contains only one or two targets.

## Experimental extension

For the official BenchBB endpoint, express selected designs and test binding by BLI or SPR. Count a hit only when a measurable interaction has `KD <= 10 µM`. Report assay completion separately so missing measurements are not silently treated as biological failures or successes.
