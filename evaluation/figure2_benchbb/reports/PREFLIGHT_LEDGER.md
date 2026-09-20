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
