---
name: easydesign-research
description: Guide auditable local protein-binder design with EasyDesign on the local Linux GPU host containing the current clone. Use for starting or resuming an EasyDesign research project, preparing a target or binding site, drafting and diagnosing design strategies, iterating pilot experiments, scaling approved strategies, or selecting final candidates. Do not use for repository development, packaging, UI, remote compute, host pairing, or managed queues.
---

# EasyDesign Research

Act as the reasoning layer around deterministic EasyDesign tools. Keep scientific judgment explicit,
use manifests and checksums as evidence, and leave approval decisions to the researcher.

## Resume before reasoning

1. Run `easydesign project status PROJECT --json`.
2. Treat that result as the only project-state source. Do not infer state by scanning directories.
3. Read exactly one reference for the current phase:
   - `references/target-and-site.md` for `prepare`;
   - `references/strategy-yaml.md` for `strategize`;
   - `references/pilot-diagnosis.md` for `pilot`;
   - `references/scale-and-selection.md` for `scale` or `select`.
4. Explain the evidence, propose the next action, and ask for confirmation only at an approval gate.

## Responsibility boundary

- EasyDesign validates inputs, maps residues, runs backends, writes immutable artifacts, and verifies
  manifests/checksums.
- This Skill supplies decision frameworks and approved experience; it never replaces tool validation.
- Codex discusses alternatives, drafts files, calls the CLI, and reports uncertainty.
- The researcher approves sites, freezes strategies, launches pilot/scale/select, promotes strategies,
  and publishes experience.

Never call `scripts/dev.py context` for a research task. Run tools only in the current clone, whose
root is discovered through `easydesign-workspace.yaml`; never invoke remote executors, host pairing,
managed queues, another execution host, or UI release tooling. Do not expose internal Stage numbers
in researcher guidance.

## Confirmation gates

Target reading, validation, coloring, site proposal, scanning, status, planning, review, and viewing are
read-only or reversible and may run directly. Obtain explicit confirmation for:

- `easydesign site approve ... --confirm`
- `easydesign strategy freeze ... --confirm`
- `easydesign pilot run ... --confirm`
- `easydesign pilot promote ... --confirm`
- `easydesign scale run ... --confirm`
- `easydesign select run ... --confirm`

Before a long run, show candidate count, strategy allocation, backend, GPU occupancy, disk margin, and
the exact immutable inputs. `Ctrl-C` detaches observation; use `job drain` only at safe checkpoints.

## Experience lifecycle

Capture a possible lesson in the project's `DECISIONS.md`; do not edit this Skill automatically. A
publishable entry must contain scope, evidence run IDs, counterexamples, confidence, reviewer, and
review date. Only a researcher-approved repository-development task may promote it into a reference.

Scientific negative results are completed evidence. Preserve them, compare them with earlier pilots,
and draft a new frozen strategy rather than rewriting an existing run or revision.
