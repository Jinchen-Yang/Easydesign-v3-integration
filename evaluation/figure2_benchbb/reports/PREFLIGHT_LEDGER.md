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

## F2BB-INFRA-002 — clone-local profile lacked the BoltzGen validation backend

- Case: BHRF1 / 2WH6.
- Run: `preflight-bhrf1-easydesign-r5-20260920`.
- Boundary: final Gate 3 callback, after a valid `BinderIntent`, deterministic constraint
  evaluation, compilation of two Arms across all seven VHH scaffolds, and successful result-
  reference reads.
- Before: `runtime/profile.yaml` was the Target-only baseline and resolved neither
  `boltzgen_validation` nor the full generation backend. The callback therefore stopped with
  `AgentBoundaryError: runtime profile 未配置 boltzgen-validation backend` before it could certify
  the compiled YAML.
- Cause: this isolated backend-product clone had never installed its own locked BoltzGen runtime.
  This was an operational dependency gap, not a scientific, Agent, compiler, or Harness failure.
- Repair: installed the repository-locked BoltzGen 0.3.2 environment under the current clone's
  `runtime/`, plus only the two assets required for validation: source commit
  `a3149cf18eeb58648d1abbb27539bd73f746cdda` and the inference molecule dataset with SHA256
  `3d4f56ac4262e745bb3d09cfaa19099b1d01be208122d501667b952e45521e53`. The five generation
  checkpoints were deliberately not installed because Figure 2A stops at a validated pilot-ready
  project.
- Validation: the immutable environment probe passed at lock
  `016440a47ff80466ead66417de866dc463018ca5ac599095c7cf50b22afb2fac`; the formal adapter probe
  reported capability `yaml-validation`; all 14 R5 compiled YAML files (2 Arms × 7 scaffolds)
  passed real `boltzgen check` with return code 0. The profile resolves `boltzgen_validation` while
  leaving the full generation backend unset.
- Disposition: infrastructure preflight only. R5 is excluded from formal effectiveness and
  efficiency estimates. It proves that `F2BB-HARNESS-001` is fixed and that the proposed design is
  backend-valid, but R6 still starts fresh from the original input and does not resume R5.

## F2BB-EVIDENCE-001 — selected RCSB complexes lacked target-partner residue contacts

- Case: PD-L1 / 4Z18.
- Run: `preflight-pdl1-easydesign-r1-20260920`.
- Boundary: Gate 2 Site ranking, before Scientist approval and before Binder Strategy.
- Before: Site research correctly selected the human PD-1/PD-L1 co-crystal `4ZQK` for
  `PPI_INTERFACE`, but the RCSB source card exposed only deposition and polymer-entity metadata.
  The Site handoff therefore stated that the PD-1 interface remained unresolved and ranked a
  generic exposed patch `site-c69ad380b277991f` first. The Judge preserved that limitation.
- Cause: `structure-record` verified entry/entity identity but did not publish coordinate-derived
  target-partner contact residues. The Agent had found the right source but its tool could not
  deliver the residue facts needed for a competition-site decision.
- Repair: commit `97c2ef1dedc09a31b5959e25f187cd07cf117b05` adds a generic, source-bound
  complex-interface projection. For a selected RCSB `structure-complex`, Runtime downloads that
  record's mmCIF, identifies target entities by the already approved UniProt accession, and reports
  5 Angstrom heavy-atom contacts between target and non-target protein chains. It retains author
  and label numbering, partner identity, exact coordinate provenance, and an explicit scope that
  geometric contacts do not prove physiological assembly, binding energy, competition or efficacy.
  No PD-L1 residue or target-specific answer is hard-coded.
- Validation: a synthetic target/partner coordinate test passes; a real deterministic `4ZQK`
  probe resolves target chain A as `Q9NZQ7`, partner chain B as PD-1/`Q15116`, 56 residue pairs
  and 22 target-side contact residues. Ruff and mypy pass. The evidence plus Site/Harness regression
  set passes 119 tests in 289.11 seconds.
- Disposition: development preflight only. R1 is excluded from formal effectiveness and efficiency
  estimates and remains pending at its unapproved Gate 2 card. R2 must start fresh from the frozen
  raw `4Z18.cif` input and may not resume or read R1.
