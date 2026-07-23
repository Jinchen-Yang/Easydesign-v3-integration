# Repository layout

[简体中文](REPOSITORY_LAYOUT.zh-CN.md)

The repository separates specification, implementation, configuration, evidence,
and runtime state:

- `workflow/`: normative human-readable stage contracts.
- `src/easydesign/stages/`: Python implementation boundaries mirroring workflow IDs.
- `src/easydesign/backends/`: replaceable scientific and execution adapters.
- `configs/`: portable defaults and versioned profiles, not secrets.
- `tests/`: unit, integration, end-to-end, and small fixtures.
- `docs/`: architecture, ADRs, methods, validation, history, paper, product, legacy.
- `resources/`: small reviewed assets and provenance records.
- `examples/`: minimal redistributable examples.
- `runs/` and `models/`: local ignored state.

Future CLI and UI packages must call orchestration APIs. They must not create a second
pipeline implementation.
