# User-authorized Phase 2 consolidation assignment

The user explicitly adopted this handoff on 2026-09-13. It supersedes earlier retry/phase
continuation instructions. In particular: one fresh GPCR run after offline/replay stability;
freeze source during that run; stop on failure; never enter Phase 3.

You are taking over EasyDesign v3 from a clean context.

The attached review package is the authoritative handoff:
EasyDesign-v3-review-20260913-7b4d43ae.zip

Start from the packaged repository state and Git history. Read START_HERE_合作者说明.md first, then inspect the current authoritative Phase 2 architecture/contracts and the latest GPCR independent review.

This is NOT another “fix the latest GPCR bug and retry” task.

Your assignment is:

EASYDESIGN V3 — PHASE 2 CONTRACT CONSOLIDATION, LEGACY SWEEP, AND FINAL FREEZE

Current state:
- Phase 1 is frozen.
- Phase 2 Cases 1, 3, 4, 5 have accepted historical PASS results and must be preserved.
- GPCR Case 2 has reached Gate 2 in the latest run, but independent scientific review failed.
- Phase 2 is therefore NOT frozen.
- Phase 3/4 must not begin.

The recent development loop repeatedly used fresh GPCR E2E runs to discover one legacy contract/interface problem at a time. Stop that pattern.

For the first stage of this assignment:

DO NOT launch a fresh GPCR run.
DO NOT make live model calls unless explicitly allowed later by this task.
DO NOT enter Phase 3.
DO NOT change Golden truth, accepted snapshots, protected deterministic scientific kernel, or model configuration merely to make tests pass.

First perform a systematic audit of the complete active Phase 2 execution path:

Approved Target
→ Evidence Research
→ Research Handoff
→ Site Evidence Dossier
→ SiteDecision
→ runtime hydration / authoritative SiteIntent
→ Evidence Judge
→ Gate 2

The goal is to identify and remove legacy architectural assumptions that still participate in this active path.

In particular, audit every scientific/control concept for:
1. who produces it,
2. who is the authoritative owner,
3. who validates it,
4. whether an older duplicate representation still affects routing, validation, completion, or scientific interpretation.

Pay special attention to:
- decision_questions vs old taxonomy/topics
- material_questions
- research_conclusions
- query IDs vs page/view IDs
- pagination/cursor semantics
- candidate IDs/names
- canonical / construct / raw-structure / design numbering
- topology / membrane side / region labels
- residue accessibility vs whole-VHH accessibility
- evidence IDs / citations / provenance
- SiteDecision vs hydrated SiteIntent
- Judge verdict / Gate option IDs
- local context-size limits or historical guards that duplicate the current shared model-input policy
- compatibility/fallback/deprecated logic that still participates in the main Phase 2 path

Do not delete history merely because it is old.
Durable evidence, failed-run records, Git history, and audit artifacts should remain traceable.

But old tentative Research opinions, obsolete validators, old taxonomy assumptions, stale local limits, or compatibility fields must not continue to act as current scientific authority merely for historical compatibility.

The target invariant is:

ONE scientific concept → ONE authoritative representation.

Examples:
- target identity / approved mapping → runtime / approved Gate 1
- canonical↔design mapping → runtime
- chain / coordinate membership → runtime
- topology / membrane-side facts → deterministic kernel/runtime
- computed geometry/SASA → deterministic kernel
- whole-VHH accessibility → only authoritative if the corresponding calculation was actually performed; otherwise UNRESOLVED
- literature evidence → durable evidence store
- open scientific interpretation and candidate preference → SiteDecision
- independent critique of interpretation → Evidence Judge
- final consequential decision → Scientist Gate

Models must not be asked to regenerate or reinterpret trusted hard facts simply so that runtime can later check whether they copied them correctly.

Create a concise Phase 2 authority/contract audit artifact documenting the final ownership model and all legacy assumptions found in the active path.

Then consolidate/refactor the implementation accordingly.
Prefer deletion/simplification of obsolete active-path logic over adding another compatibility layer.
Do not rewrite the deterministic scientific kernel.

Before any new live model run, convert the latest live187 scientific failures into deterministic or fixture-based regression tests wherever possible. At minimum cover:

- compatible UniProt disulfide annotations must not be treated as mutually contradictory hard facts;
- if whole-VHH approach/collision validation was not performed, the system must not promote “the VHH cannot approach this site” to an authoritative conclusion;
- authoritative intracellular topology must not be relabeled as extracellular/ECL candidate geometry;
- a declared avoid-residue constraint must deterministically conflict with a selected hotspot containing those residues.

Where a failure is an open scientific interpretation rather than a deterministic contradiction, test that the Judge receives the correct authoritative facts and is required to challenge unsupported absolute claims.

After the legacy sweep and deterministic/fixture regressions pass:

1. Use the SAVED live187 evidence to replay the relevant Phase 2 path.
   Do not redo literature research merely to test contracts.

2. Verify:
   Research/Handoff compatibility
   → Dossier construction
   → SiteDecision
   → runtime hydration
   → independent Judge
   → restart/resume behavior

3. Revalidate accepted Cases 1/3/4/5 only as necessary to ensure the shared contract cleanup did not regress them.
   Do not redo their scientific research or overwrite accepted snapshots.

Only after all of the above is stable may you perform ONE fresh GPCR Case 2 E2E validation.

Before that final fresh run:
- commit the code,
- ensure the working tree is clean,
- record the exact commit,
- freeze source changes for the duration of the run.

During that final fresh GPCR run:
- EasyDesign may use its own bounded retry/recovery/checkpoint mechanisms;
- you must NOT patch source code in the middle of the run;
- you must NOT change the Golden oracle or lower scientific acceptance standards.

The run either PASSes or FAILs as a frozen product candidate.

If the frozen fresh GPCR run FAILS:
- preserve all evidence and diagnostics,
- stop,
- report the exact remaining blocker,
- do NOT automatically launch another fresh GPCR run.

If it PASSes:
- revalidate Cases 1/3/4/5,
- run the full regression suite,
- verify capability parity and protected kernel integrity,
- update Phase 2 closure documentation,
- create the formal Phase 2 frozen milestone/tag,
- then STOP for human review.

Do not enter Phase 3.

The objective is not to make one GPCR run pass by accumulating patches.

The objective is to make the Phase 2 architecture internally consistent enough that, once source code is frozen, EasyDesign can run without a developer modifying Python code during execution.

Use autonomous engineering judgment for implementation details, but keep the architecture simpler after this task than before it.