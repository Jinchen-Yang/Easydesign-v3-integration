# Figure 2A BenchBB-derived project-formation benchmark

Status: development preflight. No row in `results/` is a formal Figure 2 result until
`configs/protocol.json` records `status=frozen` and an exact frozen commit.

This benchmark measures formation of a mechanically valid, pilot-ready VHH project from the
same target-specific natural-language task and the same catalog structure. It is a BenchBB-derived
computational evaluation, not the official BenchBB experimental hit endpoint.

## Methods

- `base_llm_tools`: same model and frozen atomic evidence packet; one structured submission per
  Site and Binder stage; no autonomous loop, domain Skill, Judge, or automatic recovery.
- `generic_agent`: same model and tools in a generic autonomous loop; no EasyDesign domain Skill,
  dossier, specialist decomposition, scientific Judge, or EasyDesign recovery.
- `easydesign_v3_full`: the production domain workflow.
- `expert_curated_reference`: real named human work only; never simulated by an LLM.

Codex is the declared operator for minimal post-failure repair. Development-time code changes
exclude the affected run and require a fresh run from the raw input.

## Endpoint

`pilot-ready` requires verified target/chain/mapping, a ranked and approved selectable site, an
approved Design strategy, real YAML, and compiler/backend-input validation. Figure 2A does not
require candidate generation.

## Preflight then freeze

1. BHRF1 and PD-L1 fresh EasyDesign Gate 1 to Gate 3 preflight.
2. Repair only shared infrastructure/Harness defects and retain the failure ledger.
3. Freeze commit, model config hash, source snapshot, task prompts, budgets, validators, and metrics.
4. Run every method on all seven targets in randomized order with three fresh replicates.
5. Preserve first-pass output before any operator action and append every event to the run ledger.
