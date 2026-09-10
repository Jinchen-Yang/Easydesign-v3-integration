# Figure 2 prospective evaluation

Scope: freeze EasyDesign v2.1 and evaluate it without changing core architecture.
`configs/` contains the pre-outcome protocol, target selection and evaluator definition.
All scientific outputs remain clone-local. The evaluation workspace is explicitly requested
by the researcher; production project/run artifacts stay in `workspace/`.

Tier 0 contract tests are instrumented real executions of the frozen repository's tests.
They characterize deterministic enforcement, not autonomous agent performance, and cannot
be labelled as the full agent versus Plain Codex comparison. Repeated tests are technical
replays, not independent scientific replicates. Tier 1 setup receipts retain all failures
and required scientific approval states. A valid target bundle or parsed strategy alone is
not an executable project.

No main-figure comparative rows are admitted without full method identity, isolation,
backend, target/site, budget and provenance checks. Missing measurements remain empty.
Use `reports/FIGURE2_FINAL_AUDIT.md` for the actual status of each tier and panel.

Entry point on the current clone: `.venv/bin/python evaluation/figure2/runners/run_cpu.py --help`.
The GPU queue is inert and must pass `runners/gpu_gate.py` before any launch.
