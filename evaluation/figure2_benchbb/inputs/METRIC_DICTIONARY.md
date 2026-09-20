# Figure 2 metric dictionary

This document separates official BenchBB outcomes from EasyDesign computational and workflow metrics.

| Metric | Layer | Definition / denominator | Direction | Official BenchBB endpoint? |
|---|---|---|---|---|
| Experimental hit | Wet lab | Clearly measurable BLI/SPR interaction and `KD <= 10 µM` | Higher is better | Yes |
| Experimental hit rate | Wet lab | Hits / designs with completed valid binding assays | Higher is better | Derived from official hit definition |
| `kon`, `koff`, `KD` | Wet lab | Kinetic/affinity parameters from declared BLI/SPR model | Context dependent | Yes |
| Valid project formation | Workflow | Reaches approved site plus compiler/backend-valid design YAML | Higher is better | No; EasyDesign metric |
| Time to valid project | Workflow | Wall time from natural-language request to valid pilot-ready project | Lower is better | No |
| First-pass validity | Workflow | Fresh trials passing without human repair / all fresh trials | Higher is better | No |
| Active human time | Workflow | Hands-on diagnosis, editing, approval, and repair minutes | Lower is better | No |
| Silent-failure rate | Workflow | Invalid outputs accepted without explicit warning / evaluated outputs | Lower is better | No |
| Qualified-candidate yield | Computational | Native-filter PASS candidates / attempted candidates with complete native evidence | Higher is better | No |
| Success@N | Computational | Trials with at least one qualified candidate among the first N generated | Higher is better | No |
| Interface PAE | Computational | Declared inter-chain predicted aligned error summary | Lower is better | No |
| ipTM | Computational | Predicted interface TM score | Higher is better | No |
| Target-aligned RMSD | Computational | Target structural drift after alignment under the declared atom/residue set | Lower is better | No |
| Hotspot satisfaction | Computational | Declared approved hotspot contacts satisfied under fixed distance rule | Higher is better | No |
| Interface area / ΔSASA | Computational | Buried solvent-accessible surface area under declared implementation | Higher is often preferred, but context dependent | No |
| Clashes | Computational | Steric overlaps under declared cutoff and atom selection | Lower is better | No |
| H-bonds / salt bridges | Computational | Interface contacts under declared geometric definitions | Descriptive, not monotonically causal | No |
| Diversity | Computational | Sequence/structure clustering under declared thresholds | Higher panel coverage is preferred | No |

## Denominator rules

- Do not count candidates with missing native evidence as biological or computational FAIL; report them as operationally incomplete.
- Report native PASS/FAIL using the filter profile that actually governed the run, including profile version, threshold, observed value, and decision.
- AFO or other independent prediction is an optional evidence dimension unless the prospective protocol explicitly requires it for every system.
- When comparing systems, fix generation count, selection budget, refold method, and evidence profile within each target.
- Report per-target results before averaging across targets. Use a macro-average for cross-target summaries so a large batch cannot dominate.

## LLM review

An LLM reviewer can score clarity, scientific reasoning, and risk disclosure under a frozen rubric. Objective facts such as target identity, chain, residue mapping, YAML validity, metric values, and filter decisions should be checked deterministically. The LLM reviewer must not replace these checks or create an experimental-affinity claim from computational evidence.
