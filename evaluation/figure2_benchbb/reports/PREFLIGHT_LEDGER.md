# BenchBB Figure 2A preflight ledger

## F2BB-INFRA-001 — published Stage 1 environment omitted the Agent extra

- Case: BHRF1 / 2WH6.
- Run: `preflight-bhrf1-easydesign-r1-20260920`.
- Boundary: process import before project creation and before any model call.
- Before: the Backend Product Baseline Stage 1 `.venv` did not contain `deepagents`.
- Cause: Stage 1 closure used a deliberately lean environment; `--through design` imports the
  Agent extra locked in `pyproject.toml` / `uv.lock`.
- Repair: built a new clone-local Python 3.11 environment at
  `runtime/tmp/figure2-benchbb-env-py311` with `uv sync --frozen --extra agent --extra dev`. No
  other worktree environment is referenced and the existing `.venv` was not modified.
- Validation: critical imports pass; 42 focused Phase 2/Design tests pass.
- Disposition: infrastructure preflight only; zero model calls, no project, excluded from formal
  effectiveness and efficiency estimates. R2 starts from the original input.

The separately created Python 3.12 staging environment is not adopted because the product baseline
uses Python 3.11.15. It remains untouched as an auditable unused staging directory.

## F2BB-HARNESS-001 — Binder rewrote a full-result reference as an unissued handle

- Case: BHRF1 / 2WH6.
- Run: `preflight-bhrf1-easydesign-r4-20260920`.
- Boundary: Gate 3 Binder Strategy, after design evidence and deterministic constraint evaluation.
- Before: Runtime supplied `/result-e007…json`; the model submitted
  `result:e007…`. The latter resembles a short handle but contains a content hash instead of a
  Runtime-issued event sequence. Runtime correctly refused it, while the Binder lacked the bounded
  unknown-reference repair already available to Target and Site, so the run terminated with
  `AgentBoundaryError`.
- Cause: result-reference syntax was under-specified for the Binder and its recoverable-role list
  omitted `binder`. No scientific evidence, approved site, constraint result, or artifact checksum
  was wrong.
- Repair: instructions now require the supplied `full_result` verbatim and forbid constructing
  `result:<hash>`. A Binder that still submits an unknown hash-like handle receives only recent
  references owned by that same role, thread, and execution, expressed as Runtime-issued
  `result:N` handles. Foreign, stale, cross-role, cross-thread, and tampered references remain fatal.
- Validation: 11 result-reference recovery tests pass, including a Binder hash-as-handle regression
  and the existing Judge/unregistered-file denial; the broader tool-argument and Gate 3 suite had
  36 existing tests pass. Ruff and mypy pass for the changed modules.
- Disposition: development preflight only. R4 is excluded from formal effectiveness and efficiency
  estimates. The next attempt is a fresh R5 from the frozen raw target input, never a resume of R4.
