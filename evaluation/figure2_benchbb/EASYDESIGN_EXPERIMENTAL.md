# EasyDesign-only Figure 2A measurement layer

This external observer is limited to the EasyDesign experimental group. It does not modify
the Agent Harness, prompts, Skills, validators, recovery, or project artifacts.

Protected Agent baseline: c8545570b30d279fa05b1fbb56a64e86e7c59291.

Run the baseline guard before and after each formal task, then derive the source-data bundle:

    python evaluation/figure2_benchbb/runners/guard_agent_baseline.py
    python evaluation/figure2_benchbb/runners/derive_figure2a.py

Development preflights are fixtures only. Missing observations are emitted as
not_available and are never silently converted to zero.
