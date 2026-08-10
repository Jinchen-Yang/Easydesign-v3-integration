---
name: easydesign-development
description: Use for EasyDesign repository engineering tasks, including code, tests, documentation, developer policy, repository skills, runtime configuration, the local worker, and the Viewer. Do not use for protein-binder research execution.
---

# EasyDesign Repository Development

Use this skill only for repository engineering. Do not create scientific runs, jobs, or attempts.

1. Identify every repository path in scope.
2. Choose the least sufficient mode:
   - `inspect` for read-only analysis.
   - `dev-local` for isolated implementation.
   - `integration` for science contracts, orchestration, CLI/worker, Agent or Skill policy,
     runtime boundaries, or Viewer integration.
   - `release` only when the user explicitly requests a release.
   - `ops` only for current-clone runtime installation, diagnosis, or recovery.
3. Run `.venv/bin/python scripts/dev.py context --mode MODE --path PATH`. Repeat
   `--path` for each scoped path.
4. Read every file listed in `required_reading` completely. Preserve the
   `policy_bundle_id` for the same logical task and pass it through
   `--known-bundle-id` after context compaction.
5. Make the smallest scoped change while preserving user data and unrelated edits.
6. Run `.venv/bin/python scripts/dev.py verify --mode MODE`. If verification reports
   that the mode is too low, rerun it at the required mode.
7. Review the scoped diff and report validation results and any unresolved risk.

The development context owns engineering policy. Treat the root `AGENTS.md` as the
research-facing protocol; never use it to infer repository engineering workflow.
