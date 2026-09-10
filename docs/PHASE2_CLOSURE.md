# EasyDesign v3 Phase 2 closure

Status: complete through Gate 3; Phase 2 frozen candidate ready for collaborator review.
Candidate tag: `easydesign-v3-phase2-frozen-candidate-20260911`. No Phase 3 work is included.
Baseline: `easydesign-v3-phase1-frozen-20260910`, peeled commit
`83229bd9ee5b0b077ac2b147a34113c383e31a55`. Engineering branch:
`codex/easydesign-v3-phase2`, in `/data/easydesign-worktrees/v3-phase1-20260910`.
The directory name is historical; the active branch is Phase 2. Production `/data/Easydesign`
remains on the v2 compatibility checkout. Phase 1's annotated tag is preserved.

## 1. Preflight

`TargetBridge.terminal_result()` reports `incomplete-turn` when required target preparation
has no scientific run/job. A real graph that invokes no preparation tool, including restart,
cannot report `finished`. README, AGENTS, ARCHITECTURE and PRODUCT_PHILOSOPHY now mark the
in-product v3 Agent as the primary intelligence and retain external Codex/v2 as compatibility
and development paths. Preflight commit: `22727e2189218c9f3f73908ee39f4e477f6eb9d1`.

## 2. Package changes

```text
src/easydesign/agent/
  harness.py, models.py, cli.py           shared assembly and typed role boundaries
  contracts.py, session_store.py         existing common decisions and replay bridge
  phase2.py, phase2_tools.py             Site bridge and bounded scientific tools
  site_contracts.py, site_evidence.py    mapped Site intent and original-kernel evidence
  design.py                             approved Site to original validation/freeze services
  design_contracts.py, design_evidence.py typed Binder intent and compiler translation
  skills/site-mechanism/SKILL.md
  skills/site-mechanism/references/{membrane,shielding}.md
  skills/binder-strategy/SKILL.md
  skills/evidence-judge/SKILL.md
```

Tests live in the existing `tests/unit/agent` and opt-in integration test surfaces. All four
specialist SKILL.md files carry valid name/description frontmatter; the installed framework's
metadata parser is exercised directly to verify discovery. Site/Binder science SOP text was
already used in the live smokes through explicit reads; final packaging adds the missing
discovery metadata without changing that scientific text. The exact
changed-file inventory and patch accompany the complete repository. No Stage02Agent or
Stage03Agent, new scheduler, ORM, DAG, workflow engine or database table is introduced.

## 3. Site & Mechanism responsibilities and tools

This specialist interprets WHERE and WHY: surface eligibility, spatial coherence, biological
state, mechanism, topology, shielding and alternative sites. Its typed tools read approved
Site evidence and evaluate candidate mapped residues. It can read its own skill and the two
progressive references, plus bounded offloaded results. It cannot run shell, edit files,
change target identity or approve a gate.

The runtime calls the original coordinate/mapping loader, SASA surface-diversity calculation,
manual-region normalization, radius of gyration, GPCR frame analysis and sequence motif
warnings. Metrics are facts within their calculation scope. Scientist-supplied biology is
explicitly labelled by source and authority; active state, conservation, occupancy, docking
clearance and functional usefulness are not inferred from SASA. Missing evidence stays unknown.

## 4. Binder Strategy responsibilities and tools

Binder decides HOW against the already approved Target/Hotspot. `read_design_evidence` returns
approved context, inherited warnings/override rationale and the actual SHA-verified official
VHH template and backend capabilities. `evaluate_design_constraints` is a pure typed preflight;
it does not claim to have compiled YAML. Binder can read only its own skill/bounded results.
It cannot select a new hotspot, create arbitrary YAML, approve or launch pilot generation.

## 5. Site contract

`SiteIntent` contains a selected region in approved label numbering, positive evidence,
mechanistic/accessibility/approach rationale, real alternatives when relevant, risks,
uncertainty and scientific recommendation. The runtime binds target identity, mapping,
full calculation evidence and proposal identity in the delegated callback. The model never
copies canonical SHA bindings. Source author numbering and insertion codes remain attached
to verified mapping; unknown canonical identity is not fabricated.

## 6. Design contract

`BinderIntent` describes VHH, scientific objective, approach/context/scaffold/CDR rationale,
1–3 meaningful hypothesis arms, risks and uncertainty. Each arm supports approved-hotspot
conditioning, mapped exclusions, existing crop and CDR-override types and pilot scope.
The existing protocol remains seven official VHH scaffolds × 40 candidates per condition.
CDR design ranges cannot escape the named loop into the official framework. The runtime
reports exact loop-bounds verification across all seven official assets. Only the four supported
intent controls are exposed; the unrelated backend `template=false` capability is not passed
through as an ambiguous statement about VHH scaffold availability/numbering. Verified template
indices do not imply cross-scaffold geometric equivalence. Runtime assigns
compiler-safe arm IDs; a scientific label is not a backend identifier.

The unchanged `ResearchStrategy` schema and compiler translate the intent to executable YAML.
The original validator checks the real BoltzGen input; the original StrategyFreezePlan binds
that validation. One compilation receipt references the YAML and necessary assets. We do not
introduce per-residue artifacts or another YAML language.

## 7. Gate 2 and Gate 3

Site, Binder and Phase 2 Judge use the public framework structured-output interface. The Judge
still returns only a scientific opinion; source role and bindings are runtime-owned. Malformed
JSON or a prose-only final opinion receives at most two bounded protocol corrections, all
counted against the same execution budget. The Phase 1 compatibility path remains unchanged.

Both gates reuse Phase 1 DecisionCard/DecisionOutcome, SessionStore intent persistence and
LangGraph interrupt/resume. Runtime attaches canonical evidence identity and source role to
independent Judge opinions. The Coordinator receives a trusted assessment reference and can
request the exact common card; it cannot forge an assessment, approval or execution.
Ordinary final output summarizes the actual frozen scientific settings. It does not inherit the
Phase 1 instruction to always print a selected chain and Viewer link; no Design Viewer exists.
Gate 2 calls the original Site proposal/hotspot approval services. Gate 3 calls the original
plan approval and strategy freeze services, verifies the original DecisionRecord and stops.

## 8. Four steering actions

APPROVE accepts a SUPPORTED current proposal. REVISE persists a real human instruction,
returns to the owning specialist and requires a new proposal, independent Judge and card.
REJECT rejects the proposal while retaining the scientific project. OVERRIDE requires a
DISCOURAGED, executable proposal and explicit acknowledgement plus rationale. Those warnings,
human rationale and parent-card lineage remain in the scientific evidence and downstream card.
All decisions remain distinct from Agent model opinions.

## 9. Scientific status

SUPPORTED means support within the evidence scope. DISCOURAGED covers executable but risky
choices: weak exposure/coherence, membrane or glycan concerns, context loss, altered untested
CDR geometry, weak experimental contrasts or independent Judge concerns. BLOCKED requires
runtime constraints: absent mapping/coordinates, forbidden regions, unapproved conditioning,
conflicting inclusion/exclusion, incompatible crop, invalid template range, fixed protocol
violation or compiler rejection. The LLM cannot promote low confidence into a hard block,
and ordinary override cannot bypass a deterministic block.

## 10. Dependency and execution semantics

Explicit domain bindings implement Target → Site → Design. A changed Target invalidates both
downstream layers; a changed Hotspot invalidates Design while preserving Target; local HOW
revision preserves both upstream approvals. A trusted Gate 3 REVISE that changes WHERE can
explicitly reopen Site, require new Gate 2 approval and invalidate Design. Different imported
biology also invalidates old Site/Design evidence. Historical events remain for review, but
are no longer current authority. There is no universal dependency graph.

The immutable research goal, current message, trusted revision and conversation history remain
separate. A discovered Gate 1 worker-update window is handled by checking the original active
job first, not by changing old compute recovery. Empty resume and duplicate responses reuse
the persisted execution. Phase 2 human acceptance begins the next 32-call execution exactly
once; crash/restart does not renew it twice. This was necessary because a healthy three-gate
path otherwise exhausted 32 calls. Phase 1 compatibility behavior remains unchanged.

## 11. Existing scientific code reused

Direct reuse includes Stage 01 target preparation/mapping/decision services; Stage 02 structure,
SASA, manual regions, GPCR geometry, motifs and published hotspot approval; Stage 03 official
VHH assets, capability manifest and compiler; original strategy validation, plan approval,
freeze and BoltzGen check adapter. The command ledger only reconnects Agent replay to original
jobs or reconciles one approved freeze. Scientific job identity/recovery remains authoritative.
Protected-source verification is supplied separately.

## 12. v2 compatibility

`easydesign` and its existing scientific commands, research/orchestration, stage implementations,
backend adapters, runtime profile, viewer, project layout and recovery remain available.
`easydesign-agent --through target` retains the Phase 1 slice, `--through site` stops at approved
hotspots, and the default `--through design` stops at frozen Design Specification.
No production checkout migration or storage relocation is performed.

## 13. Regression and live validation

The final integration verifier (`phase2-verify-integration-006.log`) passed. Repository and
vendored-asset checks, compileall, Ruff and mypy all passed (179 source files checked by mypy).
The complete offline suite passed: **701 passed, 11 skipped, 0 failed**, 712 collected,
931.56 s pytest wall time; the integration verifier took 941.767 s in total.

The same JUnit report contains **97 passed, 3 opt-in live skips** across Agent unit/integration
tests. The multi-turn, scientist-steering, HITL-resume and Site/Binder harness file group contains
**27 passed**; these are subsets of the complete suite, not extra tests added to the total.
The 11 skips comprise three explicitly opt-in model smoke tests and eight existing PyMOL
integration cases requiring `EASYDESIGN_PYMOL_PYTHON`. Phase 2 live tests were separately run below.
The final targeted role/configuration and actual SDK skill-discovery checks also passed
(19 tests, 7.37 s). The delivery includes the JUnit file, exact grouping statistics and logs.

Gate 2 prerequisite live passed before Phase 2B implementation (`34350f881e`, 24 model calls).
The final source Gate 2 live (`9daae69df1`) passed in 83.85 s: human REVISE → mapped labels
4/5/6 → new Judge/card → approval/restart, with Target unchanged and no unresolved-gate finish.
The final Gate 3 live (`0b7b0cbc17`) passed in 278.42 s: full-target single VHH arm → real
compiler/BoltzGen validation → independent Judge → human CDR3 revision → new validation/Judge →
explicit warning acknowledgement/override → restart and one original scientific strategy freeze.
Target and Hotspot remain unchanged; no job beyond step 2 and no pilot generation starts.
The final reports were manually reviewed for the earlier template-numbering and fabricated-viewer
errors. Runtime structured facts, including relative SASA, remain the exact quantitative source.

Three real graph checks for Site revision/restart, bounded prose-Judge recovery and Gate 3
revision/restart passed (84.69 s). The direct scaffold-evidence regressions passed (2 tests,
47.46 s), verifying all seven actual compiled CDR3 settings and the Judge's identical runtime
loop-bound facts. Wheel construction/assets checks, SDK discovery of all four specialist
skills, inclusion of both progressive references and both v2/v3 CLI entry points passed.

Offline tests use actual original scientific services and compiler, with the backend subprocess
explicitly mocked in the Binder fixture. Live Gate 3 uses the actual installed BoltzGen 0.3.2
validator at pinned commit a3149cf18eeb58648d1abbb27539bd73f746cdda. Its source/cache/profile and
check outputs are isolated; no generation, model download or scientific kernel rewrite occurs.

### Live failure review and corrections

Live attempts were not silently discarded. Early Gate 2 attempts exposed overly long
Coordinator delegation and malformed structured JSON; the bounded tool surface now rejects
oversized requests without dispatch and uses the public structured-output path with limited
protocol repair. A later malformed output still stopped safely after the bounded policy.

Gate 3 attempt `f73bbc9e6b` exposed an arm-label/backend-ID mismatch; runtime now assigns compiler
IDs. Attempt `6a473b8779` exposed ambiguity between completed Target assessment and a pending
Design decision; the Judge instruction now scopes these verdicts explicitly. Attempt
`12297f63eb` passed automated execution checks, but manual scientific review rejected its final
report: it misinterpreted backend `template=false` as lack of verified VHH scaffold numbering
and invented a Design Viewer. The final evidence now provides explicit loop-bound verification,
only relevant capability controls and the actual frozen settings; normal Phase 2 output no
longer inherits the Phase 1 mandatory chain/viewer wording. Attempt `25441444e8` exposed a
prose-only Judge response; Phase 2 Judge now uses the same structured-output interface.
These failures never bypassed deterministic constraints or launched generation. Transient
provider-invalid JSON can still exhaust the bounded protocol corrections and stop an attempt;
this is an explicit fail-closed limitation, not an excuse to accept partially parsed scientific
intent. The successful final smokes validate the full paths, not a statistical reliability rate.

Earlier full-suite attempts were interrupted when source corrections became necessary;
they are not reported as passing complete regressions. Attempt 004 completed with 696 passed,
11 skipped and one stale test that still treated the newly supported Binder model role as
unknown. That assertion was corrected to use an actually unregistered role, with an explicit
Binder override assertion; its test file and the final full suite passed. The final verifier
006 log is authoritative.

## 14. Model-call distribution

| Scenario | Coordinator | Target | Site | Binder | Judge | Total | Calls per execution |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Gate 2 prerequisite live, before Binder implementation | 10 | 0 | 8 | 0 | 6 | 24 | 12, 12 |
| Final Gate 2 live (`9daae69df1`) | 10 | 0 | 10 | 0 | 8 | 28 | 16, 10, 2 |
| Final Gate 3 live (`0b7b0cbc17`) | 12 | 0 | 0 | 16 | 6 | 34 | 15, 17, 2 |
| Full Input → Gate 1 → Gate 2 → Gate 3 scripted regression | 19 | 10 | 4 | 4 | 9 | 46 | 13, 19, 12, 2 |

The scripted full-path row is the isolated budget regression, not provider telemetry. Both live
segments use DeepSeek `deepseek-flash`, the configured 2,048-token output cap and 32-call execution
cap; no provider key or private model file is delivered. The final healthy live executions remain
well below 32, so a soft-32/hard-64 or dynamic budget was not needed. Diagnostic callback logs
record only role, finish reason and token counts, never prompts or raw tool arguments.

The 32-call hard bound stays active per execution. Oversized delegation is refused without
invoking a specialist and returns a short correction prompt. Retried model calls count against
the same bound. Structured-output protocol repair is limited to two retries. Lifetime usage
is telemetry, not a persistent-thread hard stop. No dynamic-budget subsystem was added.

## 15. Limitations

These are migration/scientific-contract fixtures, not biological validation or Figure 2.
The six-residue soluble fixture has unresolved biological identity; the synthetic seven-helix
fixture validates GPCR tool semantics, not native topology or binding. Supplied topology/state
and glycan annotations do not establish independent biological truth or glycan occupancy.
No docking, membrane/VHH collision simulation, dynamics, generated candidate, affinity or
functional assay is implied. The original first-pilot seven-by-40 restriction remains.

A changed target configuration may need a new explicit preparation context; this phase fails
closed rather than inventing target edits. A partially written compiler directory requires
inspection rather than blind recompilation. Validation/freeze retain their original immutable
scientific outputs and temporary-staging behavior. Dependencies, runtime installations, model
weights, caches and private credentials are not embedded in the source review package.

## 16. Phase 3 candidates — not implemented

Potential later cleanup: audit duplicated bridge-facing adapters after more scientific use;
review control-plane concepts against the frozen architecture; refine large evidence summaries
from measured model traces. Do not delete legacy orchestration, migrate storage, build Workbench,
expand broad specialists or launch a benchmark as part of this delivery. Phase 2 stops at Gate 3.
