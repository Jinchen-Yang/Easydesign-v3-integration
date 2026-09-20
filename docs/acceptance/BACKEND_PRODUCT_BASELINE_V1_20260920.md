# Backend Product Baseline V1 acceptance — 2026-09-20

## Decision

The backend product baseline closes the natural-language entry path through Gate 1. A user may
start from a goal alone; a PDB/mmCIF file is an optional seed rather than a project-admission
requirement. Runtime still owns identity, structure acquisition, residue mapping, manifests and
human authority.

Authoritative implementation:

- worktree: `/data/easydesign-worktrees/backend-product-baseline-v1`
- branch: `codex/backend-product-baseline-v1-20260920`
- R28 base: `4b6d20bfe23330107e1f2e6cac10b8dbb36f3344`
- goal bootstrap: `be8fe128cc1b168c359078332f5f393cc776ef0c`
- bootstrap client reuse: `26f8b166733c27cd11a315dd44edb166e5e0ab4f`
- repairable Target run binding: `0d0b4dfac2591824971ece2a54520fe88d5cd69f`
- approval-finalization resilience: `b169b4aa`

This acceptance intentionally validates the new entry only through Gate 1. It does not claim a
new Gate 1 to Gate 5 live run. The R28 Site Harness was not changed.

## Product path

```text
Natural-language goal
        |
        v
GoalTargetIntent (discovery input only)
        |
        v
canonical remote Target project
        |
        v
native UniProt + RCSB acquisition
        |
        v
Target Intelligence interpretation
        +---- optional Evidence Judge review
        |
        v
Gate 1 human decision
        |
        v
verified TargetBundle + mapping + provenance
```

`GoalTargetIntent` may supply a bounded query and organism/taxon. It cannot choose a canonical
accession, structure, chain or mapping. Those facts are accepted only after native Stage 1
retrieval and validation. Existing structure-seeded projects continue to use the former path.

## Original goal-only NK2R entry acceptance (R4)

The accepted live run started with exactly:

```text
Design an extracellular inhibitory VHH nanobody against human NK2R (TACR2).
```

No PDB/mmCIF path or prior NK2R answer was supplied to the new project.

- project: `backend-baseline-nk2r-goal-only-20260920-r4`
- thread: `thread-3bd0725c884944c58cb59f7a20962577`
- Stage 1 run: `20260920t061933z`
- Gate 1 card: `982e754f01a197bdc2b950700c576426ab3abf5baf7ee6586f3fd433a0a37c0c`
- human decision: `APPROVE`
- canonical identity: human TACR2, UniProt `P21452`, canonical length 398
- discovered structures: 9W1J-R, 9W2G-R, 9W2H-R, 9W2I-R, 9W2J-R and 7XWO-B
- approved structure: 7XWO chain B, cryo-EM, 2.70 Å
- TargetBundle status: succeeded
- TargetBundle sequence length: 351
- mapping status: ambiguous; two equally optimal alignments were retained
- structure scope: experimental-partial; coordinate coverage 0.7749
- provenance authority: human

The Judge returned `SUPPORTED` for asking the Gate 1 question while explicitly warning that
resolution alone does not establish the deposited state, extracellular-loop suitability,
inhibitory relevance, affinity or function. The completed Runtime artifacts resolve the canonical
accession to P21452 and preserve the construct/mapping limitations.

### Why 7XWO-B differs from the earlier 9W2H case

The prior R28 NK2R case was structure-seeded with 9W2H. This goal-only run had no structure seed
and compared six deposited receptor chains. Target Intelligence favored the highest nominal
resolution candidate, 7XWO-B (2.70 Å). Therefore the two runs do not test the same input condition.

This acceptance proves autonomous discovery and a human-governed choice; it does not prove that
7XWO is scientifically superior to 9W2H for an extracellular inhibitory VHH. Receptor state,
construct engineering and extracellular-loop completeness should receive explicit weight in a
structure-selection policy.

### Post-baseline Stage 1 hardening

The R5 audit showed that the original structure options exposed only experimental method and
nominal resolution. The Target specialist therefore lacked the verified construct/state packet
needed to compare 7XWO with the newer NK2R structures and over-weighted 2.70 Å. The Stage 1 option
packet now also projects exact RCSB deposited title/keywords, entity description, construct length,
UniProt/SIFTS reference coverage, canonical alignment coverage, observed-coordinate coverage,
source-part/fusion indicators, artifact/mutation/conflict counts and primary citation identifiers.
These are Runtime facts; the model still recommends and Gate 1 remains human authority.

An offline replay of the accepted R4 evidence demonstrates the material distinction:

| Candidate | Construct | P21452 reference coverage | Source parts | Deposited context |
|---|---:|---:|---:|---|
| 7XWO-B | 505 aa | 0.8668 | 2 | cytochrome-b562/NK2R fusion; NKA-bound active complex |
| 9W2H-R | 406 aa | 1.0000 | 1 | EB1002-bound active NK2R/miniGs-q70 complex |
| 9W2J-R | 406 aa | 1.0000 | 1 | P383-bound active NK2R/miniGs-q70 complex |

The Target Skill now compares identity/construct burden and coverage before deposited state and
resolution. It must not select a structure solely because it has the smallest nominal resolution.
No candidate ID is hard-coded as the winner.

### Final-code live revalidation (R7)

R7 repeated the same goal-only request on the final R6 code, with no PDB/mmCIF seed and no prior
NK2R answer supplied to the new project:

- project: `backend-baseline-nk2r-goal-only-20260920-r7`
- thread: `thread-dbf6bd98e1934cc0b58b9a068b3febf6`
- Stage 1 run: `20260920t071329z`
- source commit: `0ffcc4a8cbeea67eb377f04b24c50ff26b0f4777`, clean
- Gate 1 card: `647a79beceb5928d8490799ceed11488c2f9c05a79920ed26a8e8352e2929e87`
- recommended and approved option: 9W1J chain R (`pdb-9w1j-entity-5`)
- final canonical identity: human TACR2, UniProt `P21452`, canonical length 398
- selected construct: 406 residues; relationship `engineered_construct`
- TargetBundle status: succeeded; mapping status `review-required`

The enriched packet changed the scientific comparison materially. 7XWO was no longer favored for
its 2.70 Å nominal resolution because Runtime exposed its 505-residue, two-source cytochrome-b562
fusion, lower P21452 coverage and reference conflicts. The specialist instead favored 9W1J because
it is a single-source, zero-mutation, full-canonical-alignment structure in the clean 9W series and
contains the endogenous ligand NKA. 9W2H remains a valid alternative; the older R28 path supplied
9W2H as an input seed and therefore did not perform the same discovery decision.

R7 also exposed one narrow fact-integrity defect during post-run review. The Target and Judge
called 9W1J the best-resolution member of the clean series even though its resolution is 2.97 Å
and 9W2J is 2.82 Å. The option choice can still be supported by the endogenous-ligand rationale,
but that comparative statement is false. The final Stage 1 patch now deterministically rejects a
best/highest-resolution superlative when the recommended option is not the minimum Runtime value;
the model must retain the exact value and explain the biological preference without the false
superlative. The same check runs on Target and Judge submissions.

The run had one `OpenAIConnectionError` immediately after the goal intent was created. The same
project was resumed; no scientific answer or structure choice was injected by Codex. After resume,
the Agent read each required Skill once, made no repeated file-read or job-status loop, produced
the Gate 1 card at model-call 14, accepted human approval, and completed the TargetBundle. Thus R7
is a successful recovery-path acceptance, while uninterrupted provider availability remains an
external condition.

### R8/R9 fact-integrity closure

R8 confirmed that the resolution guard removed the R7 false superlative, then exposed a separate
identity wording error: while pre-approval `hard_facts.canonical_length` was still null, the Target
relabeled the 406-residue construct/entity length as a canonical sequence length. R8 was stopped
before approval. Runtime now rejects any explicit canonical-length claim while that fact is
unresolved; entity and construct lengths cannot be promoted to canonical facts.

R9 exercised the resulting code from the same goal-only input:

- project: `backend-baseline-nk2r-goal-only-20260920-r9`
- thread: `thread-0b3f0e3209ee47eda9e9a081dac004b4`
- Stage 1 run: `20260920t075027z`
- source commit: `eeaa8d7c96c8cdcff84742b118248fddefb98e64`, clean
- Gate 1 card: `658949badff5045fc6e428ba56c7e415856ba4fd424d5a1f981b20b496410227`
- recommended and approved option: 9W2J chain R (`pdb-9w2j-entity-4`)
- approval command explicitly supplied the displayed option ID; it succeeded and persisted
  `selected_option_id=pdb-9w2j-entity-4`
- completed TargetBundle: P21452 canonical 398 aa, engineered construct 406 aa, chain R,
  `mapping_status=review-required`

R9 chose 9W2J rather than R7's 9W1J. Both belong to the clean single-source, full-alignment 9W
series. R7 prioritized the endogenous NKA-bound context; R9 prioritized 9W2J's 2.82 Å value among
the non-fused candidates. This is a scientific preference at a human Gate rather than a changed
Runtime fact. 7XWO remained deprioritized because its globally lower 2.70 Å value comes with the
two-source cytochrome-b562 fusion and lower canonical coverage.

The first resolution guard treated every superlative as global and caused three unnecessary R9
repairs: two Target submissions correctly said 9W2J was best among non-fused entries, and one Judge
submission correctly said 7XWO had the best global nominal resolution. The final comparator now
binds the claim to the PDB ID named before the superlative and recognizes a Runtime-verifiable
non-fused/single-source subset. Exact saved-submission replay passes both R9 claims while still
rejecting the false R7 claim that 9W1J was best within the clean 9W series. This refinement reduces
repair overhead without relaxing the original fact guard.

## Timing

R4 remains the original goal-bootstrap acceptance:

- run creation to approval: 114.71 seconds
- run creation to completed TargetBundle: 130.13 seconds
- approval worker completion: 15.42 seconds

R7 separates native Runtime work from model reasoning:

- native run manifest created: `2026-09-20T07:13:29.252960Z`
- native Stage 1 reached its structure-selection boundary: `2026-09-20T07:13:56.569112Z`
- native run creation to decision boundary: 27.32 seconds
- human decision intent persisted: `2026-09-20T07:16:12.052051Z`
- completed TargetBundle: `2026-09-20T07:16:30.478979Z`
- approval intent to TargetBundle completion: 18.43 seconds
- native run creation to TargetBundle completion: 181.23 seconds, including the model/Judge and
  human-approval interval
- successful provider response latency through the Gate 1 card: 75.66 seconds across 13 responses;
  one additional provider call failed and was resumed
- post-approval successful provider response latency: 38.21 seconds across seven responses,
  including the final Judge repair and report

R9 timing on clean commit `eeaa8d7c`:

- native run creation to structure-selection boundary: 21.01 seconds
- run creation to persisted approval intent: 130.66 seconds
- approval intent to completed TargetBundle: 20.63 seconds
- run creation to completed TargetBundle: 151.30 seconds
- successful provider latency through the Gate 1 card: 106.85 seconds across 16 responses; about
  29.44 seconds and three calls were the now-removed over-strict resolution repairs
- post-approval successful provider latency: 38.14 seconds across six responses

The SQLite event stream does not persist a wall-clock timestamp for card creation, so this record
does not invent an exact end-to-end Gate 1 wall time. It reports manifest timestamps and provider
latencies separately. The 27.32-second native boundary time demonstrates that R5/R6 slowness came
from Agent loops rather than UniProt/RCSB acquisition itself.

## Failure-to-fix ledger

| Attempt | Before | Cause | Correction / after |
|---|---|---|---|
| R1 | Goal intent persisted, then the process failed before Stage 1 with a missing credential. | Bootstrap created model clients; the scientific boundary removed secret environment variables; the same process attempted to create clients a second time. | Reuse the already-created bootstrap clients for the same run. No credential is copied into scientific workers or artifacts. |
| R2 | Resume reached Target preparation but the local worker failed before producing scientific output. | The new worktree lacked its own runtime profile. A provider connection also failed transiently. | Add a worktree-local, Target-only runtime profile. No backend release is required for Stage 1. |
| R3 | Six candidates were discovered, but the coordinator passed the project ID as `run_id`; the read raised a fatal boundary error. | Model-formatted operational identifier error. | Return a bounded repairable response for an invalid ID while retaining the project binding. |
| R4 | Goal-only discovery, Gate 1 card, human approval and TargetBundle succeeded. The approval CLI then read the manifest before the detached worker completed. | The worker required about 15 seconds; the status tool waited only 10 seconds. Historical model calls also repeated the project-ID/run-ID mistake during a later resume. | This run is the live scientific acceptance. Follow-up patch makes active reads retryable, waits up to 30 seconds and deterministically maps the current project ID to the sole current run ID without weakening evidence binding. |
| R5 | Final-code revalidation exhausted the 64-call turn safeguard before Target submitted an interpretation. | The Target made 56 `read_file` calls. Successful Skill reads were persisted only for `Phase2Bridge`; Stage 1 uses `TargetBridge`, so the immutable Target Skill remained advertised after every read. | Persist successful Skill-read state for every bridge/execution and remove `read_file` after the one required read. Add a Stage 1 regression proving the tool is not reoffered. The failure is a Harness state bug, not provider latency. |
| R5 structure audit | The six structure options contained only method and resolution; 7XWO was recommended mainly for 2.70 Å. | Runtime had acquired richer RCSB evidence but did not project it into the Gate 1 comparison packet. | Add the compact deposited construct/state/coverage packet described above. Resolution remains one quality signal rather than the sole comparison input. |
| R6 | The Skill read fell from 56 calls to one, and native Stage 1 reached `awaiting-human-approval` in about 17 seconds, but the Target then made 55 `get_job_status` calls and exhausted the 64-call safeguard. | The enriched six-candidate packet exceeded the generic 8 KB offload threshold and became a `/result-*.json` reference. Stage 1 has no scoped result navigator. The terminal job also continued to advertise both preparation and status tools, so the model repeatedly polled instead of receiving the decision packet. | Keep the bounded Stage 1 Gate 1 packet inline up to 60 KB. Make its operational tool surface finite-state: before dispatch expose prepare; while active expose observation; after any terminal boundary expose evidence only. Phase 2 tool routing and its scoped result navigator are unchanged. |
| R7 | The final R6 code completed a fresh goal-only Stage 1 without either loop and selected 9W1J, but post-run review found the prose incorrectly called 2.97 Å the best resolution in the clean series; 9W2J is 2.82 Å. | Runtime projected the exact per-option values, but the narrow Target/Judge fact validator checked lengths and not comparative resolution superlatives. | Reject a best/highest-resolution claim unless the selected option has the minimum Runtime value. Apply the same deterministic check to Target and Judge; keep biologically justified preferences legal when written with the exact value and without a false metric superlative. |
| R7 CLI | Passing the exact displayed Gate 1 option with `--candidate` was rejected even though CLI help permits an exact scientific option ID. | `SessionStore.respond()` accepted explicit options only for ranked Site and downstream cards. | Gate 1 `APPROVE` now accepts only the exact option already reviewed on that card. A different option is still rejected and requires a new reviewed card, so approval cannot silently switch structures. |
| R8 | Target called the 406-residue construct/entity sequence the canonical sequence while Runtime canonical length was unresolved. | The count checker rejected mismatches only when a canonical length was already known; it did not reject invention of an unresolved value. | Treat an explicit canonical length as a contradiction when Runtime says unresolved. Preserve construct/entity/canonical semantics. R8 was not approved. |
| R9 | The fresh run produced a correct 9W2J card and completed an explicitly selected Gate 1 approval, but the first resolution comparator spent three repairs rejecting correct qualified statements. | The guard attributed every superlative to the recommended option and compared only with the global pool, even when prose explicitly named 7XWO or a non-fused subset. | Bind a claim to its explicit PDB mention and recognize the Runtime-verifiable non-fused/single-source subset. Exact R9 replay passes; exact R7 false-claim replay still rejects. |

## Verification

- focused implementation suite before the final operational patch: `34 passed, 1 skipped` in
  `310.57s`; the skip is the explicitly opt-in live-model integration test.
- final Target tool regression: `10 passed` in `16.03s`.
- post-baseline R6 Stage 1 hardening regression: `78 passed` in `29.53s`.
- final Stage 1 focused regression, including Target/Judge fact integrity and explicit Gate 1 option
  approval and scoped resolution comparison: `134 passed`.
- Ruff: PASS.
- strict mypy: PASS for the changed source modules.
- at tag `BACKEND_PRODUCT_BASELINE_V1`, `src/easydesign/agent/harness.py` was byte-identical to R28.
  The subsequent Stage 1 hardening intentionally changes only Skill-read persistence in that
  shared file; Site routing, research budgets and Phase 2–4 control flow are unchanged.

The 1.5-hour full repository suite was not rerun for this Gate-1-only acceptance. R28 remains the
last full-regression authority (`1330 passed, 11 skipped`). The changed entry, Target, project and
Phase 3/4 compatibility boundaries were exercised by the focused suite.

## Evidence and limitations

The R4 manifest records commit `0d0b4dfa` and `dirty: true` because the live model configuration
was an untracked local file during execution. No tracked source diff was present. R7 records clean
source commit `0ffcc4a8` and the ignored runtime profile, then completed Stage 1 after one external
provider connection failure and same-project resume. R9 records clean source commit `eeaa8d7c`,
accepted the exact displayed option ID and completed the corrected 398-aa canonical / 406-aa
construct bundle. The final scoped-comparator refinement is validated against the exact saved R7
and R9 submissions as well as the focused regression suite.

This closure establishes the product entry and canonical architecture documentation. It does not
experimentally validate any NK2R structure as the uniquely best epitope-design input, guarantee
provider availability, or revalidate Gates 2 to 5. Those statements remain separate from the
accepted engineering result.
