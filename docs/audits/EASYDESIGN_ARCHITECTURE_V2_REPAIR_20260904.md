# EasyDesign Architecture v2 repair audit — 2026-09-04

## 1. Executive summary

This repair implements the Architecture v2 contracts in the current `easydesign-local`
working tree without creating a branch, worktree, commit, release, or scientific run.

Scientific-correctness changes are: an exact first-pilot protocol, exact-count scale
planning, four-layer Target Identity v2, frozen residue mappings, explicit scientific
claim/evidence types, and correct separation of a completed scientific negative from an
operational or partial failure. Agent/harness changes are: an append-only Research Graph,
typed action intents, immutable execution plans, plan-bound approvals, and a machine-readable
backend capability contract. Engineering-hygiene changes are: responsibility-focused modules,
backward-compatible readers, fail-closed validation, deterministic tests, synchronized product
documentation and Skill guidance, and preservation checks for protected evidence.

The implementation was integrated with the uncommitted GPCR MSA repair already present in the
working tree. Those earlier changes were preserved. Pre-change recovery material is outside the
repository at `/data/easydesign-architecture-v2-prechange-20260904.patch` and
`/data/easydesign-architecture-v2-prechange-untracked-20260904.tar.gz`.

## 2. Exact protocol statement

```text
First pilot = 7 × 40 × X
7 and 40 are fixed first-pilot product invariants.
X is the number of explicitly frozen experimental conditions.
Scale defaults to 50,000 but the user may choose another positive integer.
```

Each first-pilot condition independently contains exactly the seven entries in
`official-vhh7-v1`, with exactly 40 candidates per scaffold. Therefore each condition contains
280 candidates and the frozen first-pilot total is exactly `280 × X`. A diagnostic condition is
not exempt. A condition with a missing/extra scaffold, a duplicate identity, or a count other than
40 fails closed.

Scale stores the exact positive requested count in protocol, allocation, shard/resource plan,
plan digest, approval request, and approval record. The default is 50,000; 10,000, 20,000,
100,000, and other positive integers are valid. Changing the count changes the plan SHA and
invalidates the old approval. Historical `production-50000` artifacts remain readable and are
not rewritten.

## 3. File-level change map

### Core scientific contracts

- `src/easydesign/core/target_identity.py` — Target Identity v2 types, deterministic alignment,
  edit classification, canonical/construct/observed/design-scope mapping, and review policy.
- `src/easydesign/core/claims.py` — typed observation, inference, hypothesis, human-decision, and
  external-fact claims with evidence and prohibited affinity/function promotion rules.
- `src/easydesign/core/decisions.py` — compatible Decision 0.1/0.2 reader and mandatory plan
  binding for 0.2.
- `src/easydesign/core/__init__.py` — public exports for the new contracts.

### Protocol, plans, actions, approvals, and scientific state

- `src/easydesign/orchestration/research_protocols.py` — the sole executable 7 × 40 × X and
  exact-count scale arithmetic contract, including deterministic shard totals.
- `src/easydesign/orchestration/research_plans.py` — immutable, canonical, content-addressed
  freeze/pilot/promotion/scale/selection plans and current-plan verification.
- `src/easydesign/orchestration/research_actions.py` — discriminated typed action intents and a
  deterministic shell renderer retained as compatibility output.
- `src/easydesign/orchestration/research_approvals.py` — DecisionRequest/Record 0.2 creation and
  exact plan-SHA verification.
- `src/easydesign/orchestration/research_graph.py` — typed append-only hypothesis, experiment,
  observation, interpretation, and decision events; hash chain; snapshots; current pointer; and
  compact state reconstruction.
- `src/easydesign/orchestration/research.py` — façade integration for first/follow-up pilot
  classification, plans, approvals, graph events, exact scale counts, and honest pilot evidence.
- `src/easydesign/orchestration/research_models.py` — typed intent on `NextAction` and compact
  Research Graph state on command results.
- `src/easydesign/orchestration/decisions.py` and `src/easydesign/cli.py` — plan identity in
  exported approvals and `--plan-sha` compatibility entry points.

### Target preparation and mapping

- `src/easydesign/orchestration/stage01_sources.py` — canonical-versus-construct resolution,
  deterministic engineered-construct mapping, explicit review/stop states, and PDB source versus
  biological-identity separation.
- `src/easydesign/orchestration/pse_import.py` — Target Identity v2 for PSE imports, with
  engineered/ambiguous canonical claims stopped rather than silently accepted.
- `src/easydesign/backends/target_sources/structure.py` — canonical, construct, auth/label,
  insertion-code, coordinate-presence, edit, and mapping-status fields in JSON/TSV output.
- `src/easydesign/stages/s01_target_preparation/models.py` — TargetBundle 0.5 and ResidueMapping
  evolution while retaining old readers.
- `src/easydesign/stages/s01_target_preparation/bundle.py` — new predicted/imported writers emit
  TargetBundle 0.5, identity report, and frozen mapping TSV.
- `src/easydesign/orchestration/config.py` — explicit biological relationship, isoform, and taxon
  inputs.
- `src/easydesign/orchestration/gpcr_site.py` — legacy mapping normalization during migration
  comparisons.

### Backend capability contract

- `src/easydesign/resources/backend_capabilities/boltzgen-0.3.2.yaml` — pinned 0.3.2 capability,
  commit, source-tree SHA-256, supported constraints, and validation-source manifest.
- `src/easydesign/stages/s03_boltzgen_configuration/capabilities.py` — typed manifest loader and
  exact version/commit/source-tree validation.
- `src/easydesign/stages/s03_boltzgen_configuration/models.py` — explicit approved avoid labels.
- `src/easydesign/stages/s03_boltzgen_configuration/compiler.py` — approved avoid residues compile
  to `not_binding`; overlap, unavailable coordinates, crop errors, and unsupported capabilities
  stop explicitly; all unspecified residues remain neutral.
- `src/easydesign/stages/s03_boltzgen_configuration/__init__.py` and `pyproject.toml` — public
  exports and packaged capability data.

### Deterministic tests and eval contracts

- `tests/unit/orchestration/test_research_protocols.py` — X = 1/2/6 arithmetic, per-condition
  incompleteness, 39-candidate rejection, custom scale counts, and shard sums.
- `tests/unit/core/test_target_identity_v2.py` — exact, truncation, substitution, deletion,
  insertion/fusion, isoform, ortholog, chimera, ambiguity, missing coordinates, and PDB identity.
- `tests/unit/core/test_claims.py` — evidence requirement and claim-class/affinity governance.
- `tests/unit/orchestration/test_research_graph.py` — append-only persistence, checksum drift,
  tamper detection, competing hypotheses, honest empty state, and observation/interpretation split.
- `tests/unit/orchestration/test_research_actions_plans.py` — typed rendering, stable SHA, count and
  mapping drift, and stale approval rejection.
- `tests/unit/test_research.py` — façade state, exact first pilot, completed zero-pass observation,
  operational-failure separation, plans, and decisions.
- `tests/unit/stages/test_s01_target_bundle.py` and
  `tests/unit/stages/test_s03_strategy_compiler.py` — schema compatibility, capability drift,
  `not_binding`, neutral residues, and overlap rejection.
- `tests/unit/test_vhh_skill_evals.py` and `tests/skill_evals/vhh_scenarios.yaml` — deterministic
  Skill guardrails rejecting two-scaffold or 20-per-scaffold first-pilot claims.

### Documentation and Skill surface

- `docs/ARCHITECTURE.md`, `docs/PRODUCT_PHILOSOPHY.md`, `docs/README.en.md`, `docs/ROADMAP.md`,
  `docs/NANOBODY_FILTER_STANDARD_V1.md`, and
  `docs/decisions/ADR-0004-multi-strategy-promotion-and-shared-scale-budget.md` — unified current
  product semantics with explicit historical compatibility.
- `docs/workflow/01-target-preparation.md`, `03-boltzgen-configuration.md`,
  `04-pilot-generation.md`, `06-scale-generation-and-refolding.md`, and their status files —
  executable contract and implementation status.
- `docs/agent/LOCAL_CLI_AND_VIEWER.md` — typed-action/plan approval façade guidance.
- `.agents/skills/easydesign-research/SKILL.md` and the `strategy-yaml.md`,
  `target-and-site.md`, `boltzgen-contract.md`, `scale-and-selection.md`,
  `scientific-claims.md`, and `vhh-geometry-priors.md` references — one consistent research-agent
  policy and explicit stop behavior.

The code-pinned `docs/NANOBODY_FILTER_STANDARD_V1.6.md` was deliberately left byte-identical at
SHA-256 `7fd2d11eba6fe634095bb8cb1e902f39ca59d837cd601c393e978424a4848cfb`. Its 50,000 text is a
historical method identity, not the current façade restriction.

## 4. Schema changes and migration semantics

| Contract | Old reader | New reader | New writer | Migration semantics |
| --- | --- | --- | --- | --- |
| TargetBundle | 0.1–0.4 | 0.1–0.5 | explicit 0.5 in new Stage 01 writers | No in-place rewrite. 0.1–0.3 report insufficient identity detail; 0.4 reports legacy evidence extension; 0.5 requires identity report and mapping TSV. |
| ResidueMapping | 0.1–0.3 | 0.1–0.4 | 0.4 when Target Identity mapping exists | Optional canonical/construct/status/edit fields allow old entries to normalize without inventing identity. |
| Target Identity | none | 0.2 | 0.2 | New evidence artifact linked from TargetBundle 0.5; no second target-bundle system. |
| ResearchStrategy | 1.0/1.1 | 1.0/1.1/1.2 | 1.2 | 1.2 requires `protocol_kind`; follow-up requires prior event references; an old strategy used for a new first pilot still passes the current protocol validator. |
| PromotionReceipt | 1.0 | 1.0/1.1 | 1.1 | 1.1 binds plan and approval; 1.0 remains read-only compatible. |
| DecisionRequest/Record | 0.1 | 0.1/0.2 | 0.2 for major research actions | 0.2 requires exact plan kind and SHA. Existing 0.1 records remain readable but do not silently authorize a changed 0.2 plan. |
| Execution plans | none | 1.0 | 1.0 | Immutable content-addressed artifacts; changed count, strategy, backend, foundation, source manifest, or mapping produces a different SHA. |
| Research Graph | none | 1.0 | 1.0 | Old projects return `not-initialized`/empty state. New events append by revision and predecessor SHA; observations verify evidence bytes. |
| ClaimReceipt | none | 1.0 | 1.0 | Claims have explicit knowledge class, evidence, limitations, and status; proxy metrics cannot become affinity/function observations. |
| Backend capability | none | 1.0 | 1.0 | Loader rejects backend/version/commit/source-tree drift; unsupported constraints are errors, not dropped fields. |
| Scale artifacts | `production-50000` | legacy plus exact user-defined plans | exact positive user-defined plan | Historical receipts are read, never rewritten. New exact count participates in plan and approval identity. |

## 5. Test evidence

| Test/check | Command | Result | Status | Notes |
| --- | --- | --- | --- | --- |
| Touched-path context routing | `.venv/bin/python scripts/dev.py context --mode integration --path <59 paths>` | 59 paths routed; policy bundle `9302ba572120a170519cafc997ab0ffee1d938b1f2a52898cf9cd742ac758707`; command exit 3 | not-runnable as a clean-topology gate | Required reading resolved. The nonzero result is solely the two pre-existing non-ancestor worktrees listed in section 9; no worktree was created, removed, or modified in this repair. |
| Targeted Architecture v2 contracts | `PYTHONPATH=.:src .venv/bin/pytest -q <11 focused test modules>` | 86 passed | passed | Covers protocol, identity, graph, claim, action/plan, capability, bundle, façade, GPCR compatibility, and Skill contracts. |
| Unit suite | `PYTHONPATH=.:src .venv/bin/pytest -q tests/unit` | 598 passed | passed | Executed in the authoritative Git working tree. |
| Repository/static integration | `make check` (invoked by `scripts/dev.py verify --mode integration`) | repository structure, Mol* 5.11 assets, compileall, Ruff, and mypy all passed | passed | Mypy: 158 source files. |
| Full deterministic suite | `make test` (invoked by `scripts/dev.py verify --mode integration`) | 601 passed, 8 skipped | passed plus skipped | 609 collected. Skipped tests are not counted as passed. |
| PyMOL PSE integration | full-suite collection of `tests/test_pymol_pse_integration.py` | 8 skipped | skipped | `EASYDESIGN_PYMOL_PYTHON` is not configured. No runtime was installed. |
| Integration verification driver | `.venv/bin/python scripts/dev.py verify --mode integration` | exit 0, `status: passed` | passed | It executed both `make check` and `make test`. |
| Scoped diff hygiene | `git diff --check` | exit 0 | passed | No whitespace-error output. |
| Protected example evidence | `git diff --quiet -- examples` | exit 0 | passed | No protected example file changed. |
| Pinned scientific-method identity | `sha256sum docs/NANOBODY_FILTER_STANDARD_V1.6.md` | `7fd2d11e…4848cfb` | passed | Confirms byte-identical pinned source. |
| Real GPU scientific workflows | prohibited by task contract | not executed | not-runnable | Synthetic artifacts, fixtures, and mocks were used; no high-cost pilot, scale, prediction, or benchmark was launched. |

The clean-topology context gate is reported separately and is not presented as passed. All
deterministic code, contract, schema migration, Skill contract, and repository integration gates
for Architecture v2 passed.

## 6. Scientific scenarios

- **Exact native:** identical canonical and construct sequences take the deterministic fast path,
  yield exact mapping, and require no identity review. A unique terminal canonical subsequence is
  also mapped automatically and records the canonical offset.
- **Engineered construct:** substitutions, loop deletions, terminal fusions, and insertions are
  aligned deterministically and represented residue-by-residue. They are no longer rejected only
  because they are not exact substrings. Engineered edits remain human-review gated; insertions
  near/in scope and missing coordinates are explicit risk signals.
- **Ortholog/chimera/isoform:** a declared relationship is preserved as biological identity, never
  normalized to exact native, and requires review before a design mapping can authorize execution.
- **Ambiguous mapping:** tied/repetitive alignments, absent canonical evidence, or missing
  design-scope coordinates fail closed with review required. An explicit PDB ID resolves the
  structure source only; it does not claim that canonical biological identity is resolved.
- **Frozen downstream numbering:** TargetBundle 0.5 freezes canonical, construct, observed
  auth/label/insertion-code, coordinate-presence, and design-scope mapping. Execution plans bind
  its SHA, so downstream stages cannot silently re-guess residue numbering.

## 7. Agent and harness scenarios

- Freezing Strategy 1.2 appends separate hypothesis and experiment events with strategy and
  evidence references. Successful, scientifically complete pilot review appends an observation
  whose source artifacts are checksum verified. Agent interpretation is a different event type;
  promotion is a separate human decision.
- A partial, failed, unfinished, empty, or unreadable pilot is operational evidence only and does
  not become a scientific negative. A completed, readable zero-pass pilot is a scoped
  computational negative observation with limitations and evidence provenance.
- `NextAction` carries a discriminated ActionIntent. Human-readable command strings are rendered
  deterministically from the typed source and remain compatibility output rather than the primary
  harness protocol.
- Freeze, pilot, promote, scale, and select publish immutable plans before execution. Decision 0.2
  binds the exact plan SHA and approver. Count, strategy, backend, mapping, foundation, or source
  artifact drift produces a new identity, so a stale approval cannot execute the changed plan.
- BoltzGen constraints resolve through the pinned capability manifest. Explicitly approved avoid
  residues become `not_binding`; unspecified residues remain neutral. Binding/avoid overlap,
  source-version mismatch, missing coordinates, bad crop, and unsupported features raise explicit
  errors and are never silently removed.
- Observation claims require real evidence refs. Inference, hypothesis, human decision, and
  external fact are separately typed. Affinity or function observations require experimental
  evidence; structure proxies cannot auto-promote to those facts.

## 8. Remaining risks and evidence maturity

- **Implemented:** protocol arithmetic, Target Identity v2, Research Graph, typed actions,
  immutable plans, plan-bound approvals, claim governance, and capability validation are connected
  to the research façade and new artifact writers.
- **Contract-tested:** all items above have deterministic unit/contract coverage; schema readers,
  checksum/plan drift, operational versus scientific outcomes, and Skill rules are included.
- **Backend-smoke:** the checked-in BoltzGen manifest was compared with the installed pinned source
  receipt and schema (`0.3.2`, commit `a3149cf…`, source SHA `1f9e0b2…`). No real BoltzGen job was
  run, so runtime behavior beyond contract validation is not newly demonstrated here.
- **End-to-end-smoke:** façade state transitions use synthetic projects and artifacts. The complete
  repository integration suite passed, but no live GPU target-to-selection workflow was started.
- **Benchmarked:** not benchmarked in this repair; throughput, disk estimates, and large-scale
  sharding were not measured on a live 10k–100k run.
- **Experimentally calibrated:** not established by this software repair. Computational metrics and
  zero-pass observations are not binding, affinity, function, or wet-lab truth.
- **Environment:** the independent PyMOL interpreter is not configured, causing eight explicit
  skips. Installing it was outside authorization.
- **Repository topology:** two pre-existing non-ancestor worktrees make `dev.py context` return 3.
  This repair did not create, remove, hand off, or modify them. They remain a coordination risk for
  future integration, not an Architecture v2 code/test failure.
- **Working-tree ownership:** the repository remains deliberately dirty and contains the earlier
  uncommitted GPCR MSA repair as well as this repair. No commit isolates either change set.

## 9. Git and worktree status

- Branch: `easydesign-local`.
- HEAD: `22206ede700f02bc63a5a88075ddb2f567a96cc3` (unchanged; local branch was already nine commits
  ahead of `origin/easydesign-local`).
- Architecture v2 touched 58 implementation/test/documentation/Skill files plus this audit. The
  complete working tree currently reports 74 dirty path entries before adding this audit because
  it also contains 19 modified and 8 untracked entries from the earlier GPCR MSA repair; several
  paths were safely shared and integrated.
- Existing worktrees: `/data/Easydesign`; locked historical
  `/data/easydesign-worktrees/bootstrap-index`; active
  `/data/easydesign-worktrees/chain-feature-inputs`; and active
  `/data/easydesign-worktrees/openfold3-314`.
- No branch or worktree was created. No stash, reset, clean, protected-data mutation, release,
  version bump, commit, or push was performed.

## 10. Final verdict

`PASS — Architecture v2 repair round complete`

The verdict covers the Architecture v2 implementation and its deterministic acceptance gates.
The pre-existing worktree topology condition, PyMOL skip, and deliberately prohibited live GPU
validation remain explicitly scoped risks above and are not represented as passed evidence.
