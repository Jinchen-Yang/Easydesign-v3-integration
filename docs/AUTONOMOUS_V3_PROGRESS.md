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


## Gate 1 content and authoritative identity reached; continuation repair

Live040 (phase2-goldens-20260911T175824Z, HEAD87f5d2a) reached Gate 1 with actual
TargetInterpretation and independent JudgeVerdict. Review snapshot
fdb46db15844fb1654d930e9503b4c0cb2166b704111490fc6b01896f5c2aeed passed all six
content-review sections. The trusted scripted validation actor approved card6c1d1c688fd2efd3b0e5cc3fb909c22e0fc71234861acb4a382fec3b26082623.
Old Stage01 attempt0002 succeeded. The unchanged approved_identity oracle verified the actual
bundle and row mappings after the runner failure; exact report retained as
soluble/approved-identity-oracle-after-failure.json. No goldens have been declared fully accepted.

The resumed Coordinator polled the completed job then repeated its earlier pending-chain text;
runtime truth was site-not-proposed / next_specialist=site-mechanism. The failed run report is
preserved. Coordinator now receives only the three verified progress fields at each model call,
with old messages retained and no new workflow state or scheduler. Independent science stays in
owning specialists. The progress summary cannot authorize a card, job, or gate transition.

Miniforge005 succeeded, official installer SHA
848194851a98903134187fbb4ab50efe87b003e0c0f808f97644b7524a62bf2c.
BoltzGen installer035 uses this worktree's locked environment and asset receipts; installation
continues with existing mirror fallback. AFO039 downloads the frozen3.1.4 archive through an
existing configured equivalent mirror after official transport failure; fixed size/hash unchanged.
These are CPU installation/download operations; no GPU scientific job has launched.

Validation of the progress refresh: targeted041 completed with15 PASS and one new fixture failure
(the test omitted Coordinator's required read_file tool). Correcting that fixture gives
 targeted0421 PASS; existing Gate1/2/3 restart, rejection and upstream revision integration cases
all passed in041. Mypy04320 files PASS; Ruff PASS; all385 protected hashes unchanged.
Live044 started with the exact pending patch (four dirty paths recorded in its launch receipt),
then reached a second independently reviewed Gate1 (snapshot6153e13ce99751f554683a47a692d8e75d564561dcd8553e1dd71feee50d512d).
The actual content receipt scopes ambiguous A/B suggestions as unverified; sample-processing,
activity and assembly limits remain visible. Scripted response delivered; Site continuation running.


## Identity checkpoint and exact Site pages

Live044's post-approval Coordinator reached Site. It acquired real UniProt/RCSB/PMID8784355
sources and evaluated three mapped candidate patches, but spent its32-call turn traversing
residue pages and repeated reads. Generic preview was showing only a few rows of each12-row
page while advancing by12. The full source stayed intact, but this was not usable evidence.
Site display now encodes all mapping and metric columns in exact tables. Size-aware pages
advance only by the number of delivered rows. Original dictionaries and source references remain
available at full_result.facts; no numeric rounding, residue translation or scientific metric change.
Actual retained page now delivers8 exact rows in5432 characters and next_offset20 from offset12.
The Site Skill directs focused candidate-label review and active discovery, retaining the
primary-source, counterevidence and independent-Judge requirements.

Targeted04517 PASS (page + Site runtime); targeted04610 PASS including exact reconstruction,
null preservation and no skipped rows. Mypy047 exposed annotations in the display helper;
annotation-only fixes give mypy05020 PASS. Ruff passes. No protected kernel change.

The real acceptance runner can resume from an exact approved Target in the original project.
It validates the old card and delivered scripted response, prior review snapshot, current
bundle/oracle and stable source identity before starting a new compatible conversation. Old
failed checkpoints/fingerprints/budgets are never overwritten. Reports identify original project,
source thread and continuation thread, with inherited Target metrics kept separately. This is
validation recovery using existing project-global science, not a second workflow/checkpoint engine.

Live048 (phase2-goldens-20260911T181457Z) accepted case-3-identity-trap after reviewing the
actual succeeded bundle, all129 rows, exact frozen truth, and independently reading the actual
old DecisionRecord. Review snapshot:
d3cb16be5ab48bd8dde7dfcc25d42a381571cc86d3bae7e03e9c54763f99e1fe.
Canonical147 / construct129 / observed127; missing128–129; canonical=construct+18;
no substitution/insertion. This is scoped validation acceptance, not efficacy evidence.

That continuation's Coordinator then reread old Target details instead of delegating Site,
misreading mapping.entries (a count) as an array until four corrections exhausted. In the exact
site-not-proposed state, the Coordinator now sees its observation/delegation tools without
Target/detail-reading tools. Full detailed science remains available to Site; pending proposal
review restores result reading. Current progress explains preserved mapping review-required and
not-in-snapshot provenance scope separately from whether a gate is pending. No action is scheduled
or approved by this model surface change. Targeted0521 PASS after fixing a test assertion that
mistook the static explanatory text for stale dynamic progress; mypy05520 PASS. Site integration
051 continues; its known fixture-only failure is fixed by052. Live054 resumes the same exact
approved Target with its previously reviewed identity snapshot; Site acceptance remains pending.

## Current-worktree runtime recovery

BoltzGen035 was interrupted during a very slow sequential download fallback. Environment,
source and molecule asset are now verified in this clone; real CLI --help probe053 succeeds.
The Phase2 validator config is runtime/tmp/autonomous-v3-20260912/boltzgen-runtime.json.
No other clone environment or model was used. Miniforge receipt and BoltzGen environment lock
016440a47ff80466ead66417de866dc463018ca5ac599095c7cf50b22afb2fac are retained.

AFO039 transport failed after partial progress. CPU download recovery049 reuses exact retained
HTTPS ranges independently across bounded retries, through the existing strict Content-Range
reader and final size/SHA publisher. Catalog identities and transport TLS checks are unchanged;
failed segments no longer cancel successful sibling progress in this development wrapper.
An existing zero-byte failed diverse-checkpoint segment caused exclusive-create retries; it was
renamed and retained as .empty-retained049 before retry. No scientific artifact was changed.
The detached recovery also prepares remaining BoltzGen weights and materializes the fixed AFO
bundle after checksum validation; it does not install AFO or launch GPU jobs.

Targeted051 completed18 PASS plus the known stale-string test assertion;052 corrected that
assertion and passed. Live054 reached Site in two Coordinator calls, confirming the owner
boundary repair. Site then passed a UniProt accession as a source-card ID; the exact source-card
precondition rejected it before calculation. This ordinary argument mismatch is the next repair.
Identity-trap remains PASS and no Site/Phase2 acceptance is claimed.


### Scoped result navigation and verified runtime preparation (live060, targeted066)

Live060 (`phase2-goldens-20260911T183054Z`) reused the exact approved Gate1 and
identity-trap snapshot, then performed real Site discovery/acquisition and focused residue
inspection. It failed when Site used `read_file` for a supplied scientific result reference.
No Gate2 proposal was accepted. Phase2 is still NOT FROZEN; only golden case3 is PASS.

The Agent now accepts that path as a read-only field-index alias after exactly the same
role/execution/Judge-snapshot/artifact-integrity verification as `read_evidence_result`.
It never invokes the filesystem reader or supplies unbounded field values. Foreign, stale
execution and modified artifacts remain fatal. A UniProt accession used as source-card ID
has a narrow diagnostic under the existing shared four-repair budget; unknown foreign cards
remain fatal. Selector help now uses actual field names instead of Target-only examples that
misled Site. No model/context/recovery budget was increased.

Targeted059: 13 PASS. Targeted061 had a test-launch PYTHONPATH error. Targeted063/065 each
had one new test-fixture/assertion defect (a synthetic non-table passed under a table tool
name, then an English regex against a Chinese integrity error). Corrected targeted066:
33 PASS (9.47s), including scoped-result negative boundaries. Mypy062: 20 files PASS;
Ruff062 PASS. These are DETERMINISTIC/SYNTHETIC TESTS, not live golden acceptance.

Download recovery049 completed the exact catalog size/SHA verification for all BoltzGen
assets and the AFO 3.1.4 bundle. No assets or environments were borrowed from another clone.
BoltzGen final registration068 is in progress. AFO installation064 has a separately saved
single-GPU/single-sample/one-recycle/no-MSA/no-template 3600-second maximum compute plan;
it failed before any GPU work because the clone lacks fixed uv 0.12.3. Dependency preparation
continues; this is installation readiness, not Phase3 pilot acceptance. All old download
partials, failed setup logs and quarantined staging are retained.


### Explicit atomic source selection (live069 failure, targeted072, live075)

Live069 (`phase2-goldens-20260911T183805Z`) passed the identical inherited Target/identity
checks and reached substantive Site research. It used all four source/argument repairs, then
changed a cursor's question, correctly hitting the existing limit. No Gate2 PASS is claimed.
`research_evidence` now accepts optional explicit `selection_reason`: the existing corpus
records SELECTED for the exact source and topic-derived need before the existing acquisition.
This is an adapter over the same selection/acquisition services, not inferred selection from
a query or scientific approval. Without that explicit reason, prior selection is still required.
Cross-role access remains rejected; source replay does not refetch. Help distinguishes PMID
records from PMCID full text and explains that a new question starts without an old cursor.

Targeted072: 30 PASS (12.38s), including exact selection, no network before selection,
replay, source boundaries and existing recovery. Mypy073 found two literal-type annotations;
using the validated DTO entry point corrected them (mypy074: 20 files PASS). Live075 is the
next real retry, with exact inherited snapshot review; its outcome remains pending.

BoltzGen final installation068 returned `ok=true`: own locked environment, all weights,
molecules and exact source registered, import probe successful. Still no generation performed.
Own pinned uv0.12.3 installed at `runtime/tools/uv-0.12.3` using the existing clone-local
Miniforge pip; PyPI download identity is retained in uv070-pip-report.json. AFO071 retries the
unchanged one-sample installation plan; Python3.12.13 preparation progressed to offline
wheelhouse installation. AFO064 consumed zero GPU jobs; no production compute authorized.


### Focused Site reads, shared budget visibility and real AFO installation smoke

Live075 (`phase2-goldens-20260911T184021Z`) consumed its 32-call execution budget mostly
reading all residue pages and then revisiting earlier offsets; no scientific Site proposal.
After the first overview, the Site model's read schema now requires explicit labels for the
patch/hypothesis being investigated. The original overview, all candidate patches and complete
scoped results remain available; no runtime candidate choice or ranking changed. Each model
invocation receives the current shared call count and remaining capacity, without increasing
any limit or allowing weak/invented evidence. Typed correction diagnostics persist across this
budget message.

Targeted076: 24 PASS, one restart integration failed because this developer edited the harness
while that test's two sessions were running (fingerprint correctly rejected incompatibility).
No stored fingerprint was altered. With stable source, targeted079 is 1 PASS (20.37s).
Targeted078: 7 PASS for typed correction and durable output-error exhaustion; mypy07720 PASS.

Runner supports explicit single-family diagnostic scopes, still checking the unchanged oracle,
real review receipts and all required criteria for each selected case. A partial run can only
report PARTIAL_CASE_SCIENTIFIC_ACCEPTANCE_PASS, never five-case acceptance. Unique microsecond
output paths allow soluble and GPCR validation to progress independently in isolated projects.
Live080 continues approved soluble Target toward Site/standard/native; live081 starts GPCR.
Both are pending, and Phase2 remains NOT FROZEN.

AFO071 completed the exact installed component, offline dependency inventory and real GPU smoke:
29-residue single chain, seed101, one sample, one recycle, no MSA/templates/data pipeline,
physical GPU UUID recorded; returncode0 and 72.20-second model inference. Actual CIF chain A has
29 residues; confidence and input JSONs exist. One installation GPU job total (064 failed before
GPU; 071 succeeded). Receipt SHA ebe57dc14ef1fd8b5c00956e0698093b94e5425c95f725e66d501ac50d811ef3.
This is backend installation readiness, not Phase3 target-binder generation/filtering acceptance.
See AUTONOMOUS_V3_BACKEND_READINESS.md. All protected kernel hashes remain mandatory.
