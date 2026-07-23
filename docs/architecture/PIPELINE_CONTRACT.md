# Pipeline contract

[简体中文](PIPELINE_CONTRACT.zh-CN.md)

## Identity

A run has stable `project_id` and `run_id`. Each stage has a stable numbered
`stage_id`. Every execution creates an `attempt_id`. Artifacts are addressed by
logical role plus checksum, never only by an incidental filesystem path.

## State

Run and stage states distinguish planning, execution, engineering validation,
scientific result, cancellation, and failure. A completed execution may validly have
zero candidates passing scientific filters.

## Immutability and resume

Accepted manifests and attempt artifacts are immutable. Resume verifies upstream
hashes and configuration compatibility, then creates a new attempt. It does not edit
the failed or completed attempt.

## Adapter isolation

Backend-specific request and result fields stay inside adapters. Core contracts expose
capabilities and normalized evidence, allowing BoltzGen, prediction models, and
schedulers to change without rewriting stage boundaries.
