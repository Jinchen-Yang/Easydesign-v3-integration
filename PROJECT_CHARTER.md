# EasyDesign Project Charter

[简体中文](PROJECT_CHARTER.zh-CN.md)

## Mission

EasyDesign will turn binder-design research workflows into a traceable,
reproducible, and product-ready system. The project advances three coordinated
outcomes: publishable scientific work, a credible software release, and a
protectable commercial product. Speed comes from clear contracts and evidence,
not from hiding uncertainty or coupling every tool into one script.

## Definition of EasyDesign 1.0

Version 1.0 implements the complete seven-stage VHH path. It may use modest
budgets and baseline models, and it does not promise binder accuracy. It must:

1. execute all seven stages with real tools rather than mocked scientific outputs;
2. pass one experimental-structure end-to-end benchmark;
3. pass one sequence/UniProt benchmark without a suitable supplied structure;
4. integration-test all six Stage 01 input routes;
5. resume safely, preserve provenance, and never overwrite completed artifacts;
6. report software success separately from scientific screening results.

Other binder families may expose adapter interfaces but are outside the 1.0
implementation commitment.

## Product and research tracks

- **Research:** preserve methods, benchmark definitions, negative results, and
  claim-to-evidence links suitable for a primary paper.
- **Release:** provide a stable Python API first, then a thin CLI, then a UI
  calling the same API.
- **Company:** protect intellectual property, record asset rights, and avoid
  architectural choices that prevent private or commercial deployment.

## Non-negotiable engineering laws

1. One concept has one implementation and one source of truth.
2. Every stage consumes declared manifests and emits an immutable manifest.
3. Silent fallback, fabricated success, misleading backend names, and swallowed
   failures are prohibited.
4. Every run records inputs and hashes, resolved configuration, code revision,
   random seeds, backend versions, model identifiers, and execution environment.
5. CLI, UI, notebooks, and shell scripts contain no scientific business logic.
6. Filters, scaffolds, predictors, and executors are replaceable adapters with
   explicit capabilities.
7. Scientific heuristics are labeled as heuristics. They must not be described as
   energetic or experimentally validated methods without evidence.
8. Runs are append-only. Resume creates a new attempt and preserves failed and
   completed attempts.
9. Secrets, model weights, caches, large run data, and unreviewed assets are not
   committed.
10. Third-party code, models, data, and scaffolds require provenance and rights
    review before incorporation or release.
11. Code changes update tests, contracts, TODO state, and both documentation
    languages in the same change.
12. Contract, architecture, evidence, or compatibility decisions require an ADR.

## Evidence and status vocabulary

The only project status labels are:

- `planned`: specified but not implemented;
- `implemented`: code exists and passes engineering checks;
- `smoke-validated`: a real small-scale run completed;
- `scientifically-validated`: predefined scientific benchmarks passed;
- `production-ready`: operational, support, security, and release gates passed.

A higher label may be used only when evidence for every lower gate is linked.

## Governance

Development is trunk-based. `main` stays verifiable; work uses short-lived
branches and Conventional Commits. Review must reject duplicated logic, hidden
state, untraceable assets, unverifiable scientific claims, or documents that
disagree across languages. Public licensing, hosting, and publication metadata
require explicit IP and release decisions; absence of a `LICENSE` file is
intentional during private development.
