# ADR 0001: Clean contract-first repository foundation

[简体中文](0001-repository-foundation.zh-CN.md)

- Status: Accepted
- Date: 2026-07-23

## Context

The legacy repository mixes duplicated packages, UI concerns, execution assumptions,
and scientific workflow logic. Incremental cleanup risks preserving unclear ownership
and misleading status.

## Decision

Start a new private repository from zero. Use seven stable numbered workflow
directories, mirrored legal Python package names, immutable manifest handoffs,
replaceable backends, bilingual normative documentation, and a Python-API-first
product path. The legacy repository remains read-only reference material.

## Consequences

Useful legacy ideas must be intentionally reimplemented or migrated only after review.
Initial progress appears slower, but boundaries, provenance, validation, and future
CLI/UI reuse become enforceable. No public license or Git remote is configured yet.
