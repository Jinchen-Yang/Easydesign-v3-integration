# Autonomous v3 migration — resumed 2026-09-12

Status: Phase 2 repair in progress; no new phase freeze. Baseline efc9bbc8aaf4e12eee719ac42743e7069e09d8f2.
Authority: AUTONOMOUS_V3_ASSIGNMENT_20260912.md. Historical stop-after-first-failure is superseded.
Milestones remain sequential: Phase 2 full regression + five reviewed real goldens, then Phase 3
pilot loop + real backend micro + meaningful synthetic decisions, then Phase 4 tiny real scale +
synthetic 50k stress + Gate 5 handoff. Stop after Phase 4; no storage/Workbench/benchmark expansion.

## Resume context

The authorized branch is codex/easydesign-v3-phase2-4 in the existing worktree. The v2 baseline
and unrelated worktrees remain untouched. Developer context bundle:
533c6120621dd585d0711517f5541a74ab9bc6629871965705faf54658c6d775.
The context command's extra-worktree blockers are historical topology, explicitly retained by
this assignment. Run its verification checks within this branch; do not delete worktrees.

Read architecture/product, Phase 1 freeze, Phase 2.2d closure, five-gate, parity, Golden spec,
contract ownership, state ownership, development Skill/guides and DATA_SAFETY. The pre-existing
compute-bounded master contract was also read; current assignment restates its invariants.
The fixed Golden spec SHA is 96ead11b3f071dce05780dd1f6fba6ee353d2346aa5a53438ac4ef0e8a850a49;
oracle SHA is 2e367355d197d541df7f77b87f6b505659a81997dc79db7a97a0b0e0ff3258c9. Neither may be weakened.

## First repairs

Reproduced the failed focused-card regression before edits (baseline-test001). Added page sizing
after binding metadata, with cursor advancement only over delivered, untruncated cards. An
absent scientific job is excluded from model observation choices until a real receipt exists;
status observation itself remains read-only. Target Skill clarifies prerequisites. No budget,
provider, scientific algorithm, approval authority or compute recovery change.
Validation: targeted002 14 PASS; related004 42 PASS/1 FAIL exposed a new coordinator
observation lookup during Gate 3 Site revision. Restricting the absent-job model-surface check
to its Target owner fixes that regression (targeted006 includes the passing exact test).
Two local development failures in targeted006 (frozen DTO alias normalization and the old
fixed two-card page assumption) were corrected; targeted007 is 19 PASS. Agent mypy20 PASS;
Ruff PASS. Full regression is reserved for phase freeze.

Live003 (phase2-goldens-20260911T170453Z) exited with a recoverable query/cursor mismatch:
Coordinator2 + Target16 calls, 2 full sources and 7 delivered focused cards; the original
no-job loop is absent. The Target changed its question while reusing the exact prior cursor.
Only a verified current-thread, current-source, current-binding cursor with a reworded question
now receives a bounded argument correction. Foreign/unknown/tampered cursors remain fatal. Known owned stale cursors are rejected
without delivering data and receive a bounded instruction to open a current selected view.
The existing two source/projection corrections per execution are reused. PDB identifier/pdb_id
aliases are normalized before frozen DTO creation; conflicting explicit identifiers are rejected.
Tool descriptions clarify evidence need/topic mapping. No successful Golden boundary claimed.

Current-worktree Miniforge install started (miniforge005); installation is separate from Agent
validation and consumes no GPU. Existing scientific installations outside this clone remain unused.

Evidence root: runtime/tmp/autonomous-v3-20260912. Every attempt uses a fresh named log/XML/project;
old source inputs, jobs and failed runs remain intact. Pending actual content-review requests
are inspected by the developer against fixed truth before any scripted fixture Gate response.

## Runtime setup to resolve before backend checks

The historical external validation configuration names another clone's BoltzGen interpreter.
Do not use it for this resumed assignment. Establish and verify a current-worktree installation
for backend checks and later micro execution, using the existing installer/runtime contracts.
No backend has been invoked in this resumed task; source and environment ownership need validation.

## Compute plan

Phase 2: no generation/prediction. Phase 3/4: validation_micro only; minimal backend-legal count,
minimal representative prediction subset, explicit total candidate/batch/GPU-job ceilings before
launch. Preserve requested production plan separately (e.g. 50,000) from tiny execution scale.
Zero passes and tiny between-arm differences are INCONCLUSIVE, never scientific failure or
promotion evidence. Larger scientific decision branches use labeled synthetic/precomputed data.
No production compute, legacy deletion, unapproved real science or wet-lab ordering.

## Evidence navigation refinement

Live009 made Coordinator2/Target7 calls and acquired UniProt + RCSB, then reused an RCSB cursor
after canonical configuration invalidated its binding. Runtime still refuses that old view;
a known owned cursor now produces STALE_EVIDENCE_CURSOR and explicit restart/reselection guidance.
Foreign or unknown cursors and checksum failures cannot use this correction path. The existing
shared two argument/prerequisite corrections and 32 model calls remain unchanged.
Targeted011 24 PASS; Ruff and mypy20 PASS.

Live013 made Coordinator2/Target8 calls. It corrected its question/cursor mismatch successfully,
then tried to read identity_evidence from a source passage page before Target preparation and
exhausted the shared argument-correction limit. This motivated a source-reading improvement:
UniProt corpus now includes a deterministic contiguous identity section with actual accession,
organism, source sequence length, and Signal/Propeptide/Chain annotations in source numbering.
All original fields, response bytes and evidence references are retained; no structure mapping
or biological inference is created. Actual retained P00698 summary is 1,150 characters and
contains canonical 147, Signal1–18, Chain19–147. Targeted014 19 PASS, including exact frozen
source-feature checks and negative conflicting-source aliases. No scientific oracle changed.

Next: rerun the real Phase 2 cases from this source; independently inspect every Gate snapshot.
Do not claim Phase 2 frozen until five cases and full regression pass. Miniforge005 continues
its verified current-worktree download; no GPU jobs have been launched.

## Bounded recovery update after live016

Live016 (phase2-goldens-20260911T173516Z) delivered the coherent UniProt source summary.
Two concurrent acquisitions without prior selection consumed both shared corrections in one
model turn; a later reworded RCSB cursor then exhausted the allowance (Coordinator2/Target8).
The shared source/argument allowance is now four, persisted across roles/restarts within the
same execution. Output-contract allowance remains two; model calls32 and context60000 remain.
This is measured bounded Harness tuning authorized by the current assignment, not a scientific
contract change. Foreign references, integrity failures and unknown cursors remain fatal.
RCSB corpus sections now expose individual source entity chain inventories and individual
polymer fields; complete response bytes and all original view fields remain retained. This
avoids mixing distinct entities into one arbitrary JSON fragment. No canonical mapping is inferred.
Historical reports describing two corrections remain historical. Current parity rows are updated.

Targeted018 32 PASS (14.55s), mypy01920files PASS. Live020
(phase2-goldens-20260911T174016Z) reached actual typed Target submission and independent Judge
but exhausted the four shared corrections at modelcall21: after reading sibling fields,
read_evidence_result was itself re-offloaded and its full_result pointed to a wrapper instead
of the original snapshot. The Judge repeatedly requested source fields from that wrapper.
Scoped reads now retain their verified original navigation root. Invalid selectors report
actual available keys after authorization/integrity checks. No limit increase follows this failure.

Targeted021 21 PASS (4.51s), mypy02220files PASS, including sequential reads through the
returned original reference, actual key diagnostics and unchanged cross-role/thread/Judge-scope
rejection tests. Live023 started with these changes. No Phase acceptance claimed yet.

Live023 failed earlier: Target called prepare_target concurrently with its initial Skill read,
then tried to configure the requested canonical source after a structural-only run had started.
The existing immutable-input boundary correctly rejected retargeting; failed run retained.
Target preparation is now omitted from the initial model surface until the own-Skill read has
returned. The preparation tool and Target system prompt state the canonical-before-prepare
prerequisite directly, before progressive Skill loading. No existing scientific run is retargeted.

Targeted024 was a command-path error (nonexistent test_harness.py; no tests ran).
Corrected targeted026 is 22 PASS (6.77s), mypy02520files PASS, Ruff PASS.
Protected385file hashes match the starting baseline. Additional Site/Design/Target integration
and a fresh live attempt follow this checkpoint; full phase freeze remains pending.

Live027 reached Target submission and Judge, but exhausted32modelcalls through repeated Judge
reads of options/identity/interpretation/hard_facts. The one-detailed-view Judge window discarded
all but the last field of every batch, forcing repeated rereading. The working set now keeps up
to four distinct scopes (duplicate reads archived), with32000total detailed characters and the
unchanged60000input ceiling. It changes model context only; checkpoints/artifacts are intact.
Also, the actual6126character Target result has a5350character scientific projection, so the
complete four-chain fact table can be supplied within6000. Use that complete projection rather
than the generic recursive list preview which had hidden chainM behind the first few rows.
The live Target incorrectly called L the only exact_subsequence option; this attempt is NOT a
scientific pass. The full oracle, Judge and subsequent independent review remain required.

Relevant028 20 PASS/3 opt-in LIVE SKIP (52.62s); independent live031 is running.
Targeted029 25 PASS (6.47s), mypy03020files PASS, Ruff PASS. New regressions verify that
Judge can compare four distinct source fields in the same actual model request, repeated
reads do not evict distinct fields, checkpoint messages remain unchanged, and all four small
Target chain facts/options survive the output adapter. No Phase2acceptance claimed.

Live031 again exhausted32calls: Judge enumerated all source fields, including request hashes,
then cycled among fields after the original complete snapshot was archived. Four recent scopes
alone did not resolve comparison memory. Judge now pins its latest complete delegated snapshot
alongside at most three additional scopes within the detail budget. The output marks a fully
supplied scientific projection as complete, instead of always partial merely because technical
refs are stored separately. System guidance distinguishes actual Target versus Site/Design keys
and asks for an independent verdict once the supplied facts suffice. No scientific opinion or
verdict is manufactured; source-bound criticism and all gates remain mandatory.

Targeted03214PASS, mypy03320filesPASS, RuffPASS. Live034 reached real Gate1 at23modelcalls.
Independent review receipt gate1-independent-review.json is FAIL, bound to snapshot
0b38321304ab073b84d7de775a1cb15bd6556bfe33a1b2f451d091a5cbc20291; no fixture approval followed.
Known147/129/127facts pass, but card wrongly prepended old structural-only unknown-reference
limitations, and Target/Judge conflated18canonical alignment gaps with2missing coordinates.
Card now uses the current verified snapshot's limitations. Pending canonical comparison adds
a compact constant offset only when all existing kernel rows prove one and alignment is not
ambiguous, plus explicit difference-type semantics. This is an Agent display projection; no
mapping algorithm, oracle or scientific approval semantics changed.

Miniforge005 installed and verified (official26.3.2-3, SHA848194851a98 prefix). Current-clone
BoltzGen install035 is running through the existing detached installer; job
setup-20260911T175319Z-a08e96e89b. AFO bundle036 materialization downloads/verifies the fixed
5,032,471,381byte stable archive only; no AFO install/inference or GPU job has been launched.

Targeted03717PASS (35.44s): actual cached-source Stage01/decision/bundle tests, gate resume,
working-set tests, and frozen soluble/GPCR mapping projections. mypy03820filesPASS; RuffPASS.
AFO bundle036 failed on official-network reachability; bundle039 retries the same exact
size/SHA through the already configured hf-mirror transport using the existing verified downloader.
No source catalog, release identity or model bytes changed; download is progressing.
