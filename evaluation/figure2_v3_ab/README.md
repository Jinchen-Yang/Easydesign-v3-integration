# EasyDesign v3 Figure 2A/B successor benchmark

This directory is the prospective, small-sample Figure 2A/B benchmark for the current v3
backend. It does not modify or reinterpret evaluation/figure2, which remains the immutable
historical v2.1 evaluation record.

The first preprint cohort deliberately prioritizes complete metrics over target count:

- Figure 2A measures formation of a valid, pilot-ready project.
- Figure 2B measures candidate quality under matched generation and evaluation budgets.
- Figure 2C external/generalization benchmarks are outside this version.
- Expert performance is never simulated. A human-authored plan is labelled
  expert_curated_reference; a hidden known complex is labelled native_interface_oracle.

No result row may be numerical unless it is measured or deterministically derived from measured
records. Planned, unavailable and proxy values remain explicitly typed as such.

By explicit investigator instruction, Codex operates the benchmark's human-repair slot. The
first-pass result is frozen before repair; at most two correction rounds receive only the released
task, method output and shared deterministic validator diagnostics. Records retain the Codex
operator identity. Any code/Harness modification moves that run to the development ledger and
requires a fresh run from raw input before it can enter Figure 2A.

Before the benchmark freeze, the Gate 2 Harness must pass
configs/harness_acceptance.json. Full and control methods then use the same foundation model,
model settings, source snapshot, atomic scientific tools, target inputs, query budget, generation
backend, candidate budget and independent evaluator. Method-specific retries are forbidden.
