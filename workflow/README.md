# Workflow specifications

[简体中文](README.zh-CN.md)

`workflow/` is the human-readable source of truth for stage responsibilities.
Numbered directory names are stable workflow identifiers. Python modules use legal
names prefixed with `s01_` through `s07_`, and runtime output mirrors the numbered
names.

Each stage has a narrative README, a normative CONTRACT, and an examples placeholder.
Contracts describe artifacts conceptually but do not yet freeze a JSON Schema.

## Handoff rule

A stage may read only artifacts declared in accepted upstream manifests. Every stage
writes a new immutable manifest containing stage identity, contract version, status,
inputs, outputs, provenance, attempts, warnings, failures, timestamps, and checksums.
Directory scanning is not an interface.

Runtime layout:

```text
runs/<project_id>/<run_id>/
├── run-manifest.json
├── config-snapshot/
├── 01-target-preparation/
├── 02-hotspot-discovery/
├── 03-boltzgen-configuration/
├── 04-pilot-generation/
├── 05-pilot-filtering/
├── 06-scale-generation-and-refolding/
└── 07-final-filtering-and-selection/
```

A resumed stage creates a new attempt; it never rewrites an earlier attempt.
