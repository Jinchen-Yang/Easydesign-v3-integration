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


### Real Site submission binding and GPCR content review (live080/081)

Live080 (`phase2-goldens-20260911T184511700924Z`) reached a typed SiteIntent at modelcall24
with actual candidate evaluations, but used search/acquisition card IDs and paraphrased receipt
text as excerpts. Existing citation validation rejected it before proposal registration. No
Gate2 PASS. Known-owned-source citation mismatches now enter the existing two typed-submission
corrections before the registration callback; foreign card IDs and integrity failures remain
fatal. The exact existing source and citation checks run again at registration. Field descriptions
explicitly require a focused passage card ID and verbatim excerpt; unavailable/unread sources
belong in limitations, never invented quotes. No scientific threshold or budget relaxed.
Targeted082 had two fixture/message-compatibility defects; corrected targeted084:31 PASS
(9.97s), mypy08320 PASS. Live085 is the next soluble retry.

Live081 (`phase2-goldens-20260911T184511658340Z`) actually reached GPCR Gate1, but failed the
required before/after canonical-binding focused-read assertion: Target omitted the after-read.
The independently inspected card also FAILS scientific review: Judge treats construct501 vs
observed284 as a contradiction (these are different quantities), and overinterprets an arbitrary
optimal alignment of chainB to the receptor reference. No response/approval was delivered.
`gpcr/gate1-content-review-after-failure.json` preserves the rejection. Verified frozen mmCIF
entity annotations explicitly describe entity1/A as Beta-2 adrenergic receptor, Lysozyme and
entity2/B as Camelid Antibody Fragment; these should be surfaced as depositor annotations,
not replaced by chain-size guesses or global-alignment claims. The frozen oracle is unchanged
and is not suspected; the errors are Agent evidence presentation/interpretation.


### Current-source prerequisites and durable scientific working set (live085 recovery)

Live085 (`phase2-goldens-20260911T185111542914Z`) exhausted32 model calls after losing earlier
passages from its four-view working set, repeatedly reading old Site fields and mistaking a
12-item stored facts page for a whole-target array (offsets25/33). It did retrieve the primary
8784355 abstract and official sources, but no proposal/acceptance followed. No PASS inferred.
Site now keeps the latest passages from up to three distinct source identities alongside the
current geometric view, within the same four-view/32k-detail and60k-context limits. Selection is
by recency/source identity, never whether evidence is favorable. Original checkpoints unchanged.
Out-of-range scoped list reads explicitly return list length and distinguish list indices from
residue labels; search-query field help now states that question is not the executable query.

Pending Target evidence includes entity descriptions/auth-label associations read from the
checksum-verified original mmCIF. These are labeled depositor annotations, not alignment-derived
biological identities. Approved Target snapshots are unaffected. After canonical configuration
changes, prepare_target is not offered until focused TARGET_IDENTITY cards from that exact
source have been read in the current binding; no repeat acquisition or new gate is required.
Target/Judge guidance separates construct length, coordinate coverage, alignment diagnostics
and physical entity annotations. No kernel, oracle or Gate semantics changed.

Targeted086:14 PASS (23.53s) for source projection, current-view prerequisites, identity/binding.
Targeted088:37 PASS (48.24s) for working memory, pagination, source arguments and Site runtime.
Mypy087/089 found one return annotation; fixed without behavior change, mypy09020 PASS.
Real frozen-source projection090 verifies exact GPCR entity annotations with input SHA unchanged.
Next live retries091/092 will cover soluble Site and GPCR respectively; still Phase2 NOT FROZEN.


The pre-commit Ruff check found three non-behavioral issues (one101-character diagnostic line,
two zip calls needing explicit strict=False). Live091/092 were already launched by the wrapper
with that tested source. Preserve their exact fingerprint while they run; commit this engineering
state with the lint debt explicitly recorded, then apply those equivalent style fixes once the
sessions are complete. This is not a Phase freeze and no Ruff PASS is claimed for this checkpoint.


### Conditional mappings and inapplicable delegation (live091/092)

Live091 (`phase2-goldens-20260911T185808993592Z`) incorrectly redelegated approved Target work;
the Target then attempted another role's Skill, correctly rejected by the file boundary. The
Coordinator now receives NOT_APPLICABLE if it delegates upstream Target/premature Judge while
trusted state is site-not-proposed; only the pending scientific owner can work there. This is
existing state/role enforcement, not automatic scientific selection or a second scheduler.

Live092 (`phase2-goldens-20260911T185808864699Z`) reached Gate1 and passed the canonical
before/after source round trip with one acquisition. Entity and construct/coordinate distinctions
were improved. Independent content review nevertheless FAILS its assertion that null constant
offset means no residue-level correspondence exists. No human/scripted approval was delivered.
The current read-only projection exposes the old engine's actual counts: chainA design493 rows,
365 with canonical positions and128 unmapped, still ambiguous/no proven global offset; chainB126
mapped rows in its arbitrary alignment, not biological receptor identity. Depositor source segments
are retained with original mmCIF field names, source organism and source position annotations.
They are not canonical/design renumbering. Verification retained in gpcr-mapping-projection093.json.

Target/Judge explicitly separate absence of a global offset, existing conditional per-row mapping
and unproven uniqueness. Source segments do not prove native function/state. Judge Skill fits in
one bounded118-line read. Protected science/oracle unchanged. Targeted093:27 PASS (22.77s),
mypy09420 PASS. Previous Ruff debt and one additional long line corrected; Ruff095 PASS.
Next real attempts096/097 continue soluble and GPCR acceptance independently.


### Source-view prerequisites and lossless Target display (live096/097)

Live096 (`phase2-goldens-20260911T190530636316Z`) failed before Site science: its first
specialist call constructed a /result-<evidence_id>.json reference that had never been supplied
to that role. The authority check correctly rejected it. Scoped-result navigation is now offered
only after the current role/execution has received a registered tool view. Foreign/stale/tampered
references remain fatal; no cross-role permission or guessed file alias was introduced.

Live097 (`phase2-goldens-20260911T190530404046Z`) reached GPCR Gate1 but omitted the focused
UniProt read before canonical proposal. A verified known-source proposal now returns a read-only
REQUIRES_ACTION diagnostic until actual TARGET_IDENTITY passages for that source/current binding
exist; no config revision or download occurs on rejection. After-read enforcement remains.
The independently inspected Gate1 card also FAILS: it labels T4 lysozyme BRIL-type without source
support, infers terminal fusion order inconsistent with deposited segments, and mistakes a two-item
preview for complete coordinate missingness. Rejection retained in gate1-content-review-after-failure.json;
no approval delivered. Null offset/ambiguous correspondence is still not absence of all per-row mapping.

Pending Target display now retains complete depositor segments; large missing-position lists use
exact inclusive ranges and explicit counts, preserving original full lists offloaded. For the real
GPCR chainA that is217 missing-coordinate residues, separately from48 canonical alignment deletions.
This is lossless presentation, not mapping/kernel change. Whole source, original order and frozen
oracle remain unchanged. Source-segment guidance prohibits inferred fusion order from names.
Targeted098 had32 PASS and one old tool-availability assertion; after updating its prerequisite,
targeted100:33 PASS (25.24s), mypy101:20 source files PASS. Supplementary display checks102:22 PASS (5.19s), Ruff102 PASS, mypy102:20 files PASS. The complete real pending GPCR scientific facts fit5775 characters after lossless position-range encoding.
Phase2 remains NOT FROZEN; case3 only has PASS. No new GPU jobs.


### Reviewed GPCR Target and scoped evidence-reader recovery (live103/104)

Live103 (`phase2-goldens-20260911T191615175406Z`) reached Site science but exhausted the shared
four argument repairs: display-only facts_table vs original facts, redundant identical field/path,
requesting12 list items against max8, then a numeric JSON path index. No Gate2 proposal/PASS.
The model now sees one path selector; legacy field/fields remain compatible in the actual API.
Identical redundant selectors normalize to their sole meaning; conflicting selectors still fail.
Numeric path indices normalize without guessing. Requests up to64 items return at most8/4400chars,
with exact next_offset. Display facts_table and coordinate-position ranges resolve by lossless
projection of the same already-authorized/checksum-verified source. Foreign/stale/tampered and
cross-role/Judge-snapshot errors remain fatal; scientific constraints and32/60000 budgets unchanged.

Live104 (`phase2-goldens-20260911T191615664583Z`) passed independent Gate1 review, snapshot SHA
1830a040bb2f18ebb830a404c18a2c05f7d72a9be3969fcad83204efb88f8dcd, card
3ad387fe6a240816013a6605179b8f581db3fc5dc37ff8787c2a16fded3eed6a, run20260911t191632z.
The scripted validation actor's actual approve response was delivered through existing services;
resulting canonical/construct/coordinate identity and all493 design rows pass the frozen oracle.
Chain A has365 conditional canonical rows/128 unmapped; ambiguity is preserved. Gate1 review
records a non-adopted incidental Judge inference about a missing interval; it is not treated as a
verified fusion-junction or disorder fact. No biological approval or whole-case PASS is implied.

Its subsequent Site execution exhausted32 calls while paging930 UniProt corpus chunks for
specific topology features, after acquiring real RCSB/primary paper/GPCRdb context. No Gate2 PASS.
An explicit optional feature_types filter now selects original UniProt feature indices from the
verified full record, retaining the exact old chunks and passage IDs without reindexing or
redownloading. Cursor identity includes the filter; another scope cannot continue the old cursor.
Acquisition receipts expose source_id (distinct from card_id); verified GPCRdb context points to
the existing complete receptor-analysis tool instead of generic manual pagination. Existing full
sources, source-selection scope, source limits and old analysis kernel remain unchanged.

The validation continuation can now reuse either reviewed approved soluble or GPCR Target.
It rechecks exact card/review hash, delivered actor response, original canonical before/after
round trip, current authoritative Target oracle and site-not-proposed ownership; it creates a
compatible new Site thread and never rewrites the old checkpoint, budget, approved input or run.
Targeted105:37 PASS/4 old RecoveryModel availability assertions failed; those fixture assertions
were updated for the already-tested reader prerequisite. Mypy105:20 files PASS; Ruff106 PASS.
Targeted106:47 PASS (15.24s), covering corrected integration fixtures and current reader/source boundaries. Next live107/108 reuse the reviewed soluble/GPCR Targets respectively.


### Existing large analysis artifacts and retained mapping context (live107/108)

Live107 (`phase2-goldens-20260911T192506679890Z`) retrieved the primary abstract, original
UniProt catalytic features and RCSB entity passages and attempted SiteIntent. It failed a material
NOT_SEARCHED conclusion after one schema correction. Its rejected draft also contained unsupported
numbering and access claims; no proposal was registered and no scientific PASS is inferred.
The latest exact read_site_evidence is now pinned alongside up to three distinct source views
within the same four-view/32k detail budget. Previously a later fourth source page could evict
geometry even when three source identities were already pinned. Reordering regression covers it.
Known evidence-state mismatches (unresearched material topics, false no-evidence/support/conflict
states) now use the existing two typed-submission corrections. Every missing topic is named;
relabeling NOT_SEARCHED as UNRESOLVED is still rejected. Unknown source IDs remain fatal before
status correction, and citation/primary-strength/hard-fact checks still apply.

Live108 (`phase2-goldens-20260911T192505924083Z`) successfully used explicit topology feature
filtering and reached the actual old receptor analysis at modelcall12. The analysis persisted,
but its returned chain graph exceeded the generic256KB summary offload ceiling. The tool now
registers the already-persisted/checksum-verified analysis artifact as a scoped tool view, returning
only a bounded field index and complete small identity/state/warning fields. It neither copies
huge science into the summary store nor raises the store/model limits. The unchanged existing
reader handles on-demand paths, with the same role/execution/integrity constraints; tests verify
large-artifact scope, cross-role rejection and tamper rejection. No new artifact system or kernel.

Targeted109:45 PASS (14.20s); Ruff109 PASS; mypy109:20 files PASS. Next live110/111 reuse reviewed
approved soluble/GPCR Targets. Phase2 still NOT FROZEN; cases1/2/4/5 incomplete, case3 PASS only.


### Latest scoped answers remain visible; invalid read-only labels are repairable (live110/111)

Live110 (`phase2-goldens-20260911T193119565077Z`) used real primary/database passages and
both candidate evaluations, then exhausted 32 calls while repeatedly inspecting an evaluated
patch. The checkpoint exposed a working-set defect: four pinned geometry/source pages filled
all slots, so even the newest successful scoped answer was immediately replaced by an archived
reference before the next model call. Site now always retains its newest detailed answer,
latest mapping/evaluation/receptor context, and up to three distinct source pages within the
unchanged32k detailed/60k input ceilings (at most six preferential Site views). Ordinary recent
views still fill only four slots. Source selection uses identity/recency, never favorable content;
complete history and exact artifacts remain unchanged. A fitting candidate evaluation is delivered
in full instead of an unnecessary list-prefix preview. The regression reproduces a newer scoped
answer after three source pages plus geometry and checks that adverse evaluation evidence survives.

Live111 (`phase2-goldens-20260911T193119012673Z`) supplied invented design labels10011–10050
to read_site_evidence and failed before proposing. This read-only mismatch now shares the existing
four argument/source corrections and returns exact observed-label ranges with explicit numbering
warnings. No rows or valid hotspot are manufactured; actual proposal evaluation, approved mapping,
foreign-reference and integrity boundaries remain unchanged. Exhaustion still fails closed.
Both failed executions remain preserved. No new Site PASS or Phase2 freeze is inferred.

Targeted112 named one nonexistent test path and collected zero tests; retained as an invocation
failure. Corrected targeted112b is the actual regression run. Ruff112 PASS; mypy112:20 files PASS.
Protected-baseline recheck: all385 files unchanged. Validation outcome recorded below before retry.
Targeted112b:40 PASS (49.35s). Next live113/114 reuse the independently approved soluble044 and
GPCR104 Targets; all source/gate/identity/science oracles remain unchanged.


### Skill file surface and object-offset semantics (live113/114)

Live113 (`phase2-goldens-20260911T193948187038Z`) reached real literature/database research and
then exhausted32calls paging the same facts_table object with offsets12…238. Latest answers were
now visible; the next defect was a nonzero object offset silently returning the same complete
object. The scoped reader now rejects nonzero offsets on objects/scalars through the existing
argument repair budget, names the object's actual keys, and distinguishes rows-list indices from
another residue-region query. Lists/text retain their original paging semantics; unknown/foreign
references remain fatal. Regression checks that an object/scalar cannot replay as a successful page
and that explicit rows-list pagination still returns the correct second row.

Live114 (`phase2-goldens-20260911T193948722244Z`) invented a file path by prefixing a project
evidence URI during its initial Site call. The existing authority guard correctly rejected it.
The model-visible read_file schema now lists only each specialist's authorized Skill paths,
including the three Site references. Coordinator has no authorized Skill file and no longer sees
this file tool. Scientific reads use existing scoped evidence tools; old authorized result-index
compatibility and the strict runtime path guard are preserved. No filesystem authority expanded.
These are separate recoverable engineering defects, not scientific failures or acceptance PASS.

Targeted115:38 PASS/12 old Coordinator tool-surface assertions failed; those fixture assertions
now explicitly require Coordinator read_file to be absent, preserving strict checks for every
specialist. Ruff115 found one overlong description line (wrapped without semantic change).
Mypy115:20 files PASS; Ruff115b PASS; targeted115b:56 PASS (536.48s), including actual Site/Design
revision, original Gate1 saver recovery and full input-to-frozen-design integration. All385
protected files remain unchanged. Next live116/117 reuse the reviewed Targets; no new source,
science-oracle, compute-budget or Gate-policy changes.


### Retrieval syntax diagnostics and literal annotation types (live116/117)

Live116 (`phase2-goldens-20260911T195349549131Z`) successfully compared actual mapped candidate
evaluations, then supplied an unissued cursor while changing the question. Its cursor encoded
offset4; this exact source view had returned offsets1,3,5 only. The foreign/altered cursor boundary
correctly failed closed and remains unchanged. No proposal/Gate2 PASS is inferred. UniProt's full
record contains thousands of reference chunks; targeted annotations should use the existing literal
feature filter. Acquisition receipts now list available types from the verified original record,
not from a hard-coded answer. A filter miss names the unmatched types and explicitly does not mean
biological absence. Exact old chunks, passage IDs, complete sources and cursor identity persist.
Site Skill describes this existing selector and forbids constructing opaque cursors.

Live117 (`phase2-goldens-20260911T195349601679Z`) recovered one real owned stale cursor, then
passed unsupported offset=0 to retrieve_evidence. Framework validation returned plain error text,
which passage-count telemetry incorrectly parsed as JSON. Retrieval DTO validation now happens
before dispatch, with schema-only errors consuming the existing four argument/source repairs;
no source view is consumed. Error-status tool messages are not parsed as successful passage pages.
Regression covers both the live syntax defect and plain framework error handling, four-repair
exhaustion, no source/job creation, literal feature-type miss and exact-source receipt reuse.
Source/identity/integrity/unknown-cursor failures still escape; there is no blanket exception retry.

The model-visible cursor field now offers empty/start-new plus at most four exact recent cursor
strings actually supplied to this role. This is a copying aid; the unchanged runtime independently
checks query, thread, current binding and source selection. It does not accept unissued cursors,
alter offsets or rewrite checkpoints. Targeted118:53 PASS (17.28s); after this model-surface addition,
targeted118b:46 PASS (8.70s). Ruff118 overlong metadata line and mypy118b message-content union were
corrected without changing scientific behavior; Ruff118c PASS, mypy118c:20 files PASS.
Next live119/120 reuse approved soluble044/GPCR104. Phase2 remains NOT FROZEN; only case3 PASS.


### Copyable owned result handles and bounded synthesis guidance (live119/120)

Live119 (`phase2-goldens-20260911T200009943741Z`) used literal UniProt feature filters and real
research, then exhausted32calls re-reading source/search pages without a SiteIntent. The Site
prompt now explicitly targets a concise reviewable hypothesis, with meaningful alternatives and
all material unresolved conclusions. At10remaining shared calls it reminds the owner to reserve
about6for independent Judge/Coordinator and synthesize from delivered evidence, researching only
facts that affect executability. This is reasoning guidance, not a new scheduler, forced verdict,
waiver of scientific checks or increase to any budget. Model tools remain available.

Live120 (`phase2-goldens-20260911T200009567228Z`) reached mapped GPCR residue reads at21totalcalls,
then invented /result-c1f9e3a2f7144553a7e27ea8917e8fdf.json; it was absent from all16registered
views in that thread. The concurrent second ref was valid. The first reference correctly failed
its ownership check; no foreign data was read. The model now sees up to32exact recent result refs
from its own role/execution in the existing registry, instead of only a hexadecimal pattern.
Actual reads retain independent role/execution/Judge-binding/checksum checks. Earlier sources,
threads and checkpoints are untouched; metadata choices are no new artifact/authority system.

Targeted121:55 PASS (12.41s), including argument recovery and hard tool boundaries; Ruff121 PASS;
mypy121:20 files PASS. Next live122/123 reuse independently approved soluble044/GPCR104.
Phase2 NOT FROZEN; cases1/2/4/5 remain incomplete, case3 remains independently accepted only.


### Exact missing-topic diagnostics and rejected owned-cursor transcription (live122/123)

Live122 (`phase2-goldens-20260911T200516649739Z`) now reached repeated real SiteIntent submissions
at29totalcalls. The DTO rejected missing epitope/state conclusions, but its generic error did not
name them; the correction added unrelated NOT_SEARCHED topics while still omitting epitope. The
unchanged requirement now names every missing topic and exact research_conclusions fields. It does
not manufacture research, remove material questions or increase the two-repair budget. A regression
verifies that syntactically completed unknown conclusions still fail the real NOT_SEARCHED check.
The rejected opinion also overstated mapping ignorance and confused archived with never-retrieved
pages; Site instructions explicitly preserve supplied non-null conditional mapping rows and their
ambiguity qualification. No scientific PASS is inferred from this invalid draft.

Live123 (`phase2-goldens-20260911T200516579799Z`) manually reset an owned view's encoded cursor to
offset0 when changing its question, despite exact choices in the model schema. Cursor handling now
explicitly requires an issued token even when its decoded view otherwise matches (previously that
same-view case could accept a fabricated offset). An unissued token whose view is proven by a
checksum-verified evidence-view artifact in this thread returns a bounded read-only syntax repair,
with no page, no advancement and no evidence-view event. Unknown/foreign views and corrupt evidence
remain fatal. This deliberately distinguishes a malformed owned read request from source/artifact
integrity or authority failure; it never accepts an altered token. Original cursors, paging identity,
source bytes and stores remain unchanged. Tests cover zero state/data advancement, foreign-view
rejection, valid continuation after rejection, and unchanged source-fetch count.

Targeted124:52 PASS (19.34s); Ruff124 PASS; mypy124:20 files PASS. Next live125/126 reuse the
approved Targets. Phase2 remains NOT FROZEN; cases1/2/4/5 incomplete, case3 PASS only.


### Research prerequisites, result selectors and effective model output budget (live125/126)

Live125 (`phase2-goldens-20260911T201229113546Z`) compared mapped candidate sites but exhausted
the four shared corrections with sibling keys supplied as a nested path. Model result reads now
expose two explicit mutually exclusive selectors: fields for root siblings, path for traversal.
Legacy field remains API-compatible only. An invalid path that names actual root siblings gives
the exact fields correction; successful nested traversal is never silently reinterpreted.

Live126 (`phase2-goldens-20260911T201228727348Z`) sent gpcrdb-context with query instead of required
identifier, received a framework error, then attempted analysis without any acquired context.
Research DTO errors now return a bounded correction before selection/fetch/state mutation, using
the existing shared four-repair budget. Receptor analysis is offered only after a complete GPCRdb
context card exists, with its actual card IDs in the model schema; handler identity/context checks
remain authoritative. No model-generated source ID or fabricated complete context is accepted.

The actual installed ChatOpenAI SDK rewrites max_tokens to max_completion_tokens, which does not
match DeepSeek's documented request field. Live122 recorded 3078/3140 completion tokens despite
the configured2048. DeepSeek now receives max_tokens in its vendor extra_body; no model or budget
is increased. No-network tests inspect the actual HTTP request through the real SDK and verify
DeepSeek/OpenAI/Anthropic use their respective supported fields. Primary vendor documentation:
https://api-docs.deepseek.com/api/create-chat-completion/ and
https://api-docs.deepseek.com/quick_start/agent_integrations/oh_my_pi/ .

Targeted127's first command referenced a nonexistent test filename and collected zero tests.
Corrected targeted127b:61 PASS/1 FAIL; the new prerequisite test caught non-JSON ValueError context
in Pydantic diagnostics. Diagnostic serialization now excludes raw exception context while
retaining exact locations and messages. Targeted127c:62 PASS (16.79s); Ruff127c PASS; mypy127c:20 files PASS.
Next live128/129 reuse the independently approved Target bundles.
Phase2 remains NOT FROZEN; cases1/2/4/5 incomplete, case3 independently PASS only.


### Complete focused rows and a bounded Site synthesis reserve (live128/129)

Live128 (`phase2-goldens-20260911T202101612210Z`) exhausted32calls (Coordinator3/Site29).
It repeatedly read already-delivered evaluation fields and applied residue-like offsets to small
explicit label sets. Full Target/research/scan backgrounds were also repeated in focused reads,
crowding actual requested residue rows out of the6000-character model view. Focused reads now
display their exact mapping/metric rows, cursor/counts and all limitations; the complete original
including approved Target/background remains in the same checksum-verified full_result. A complete
requested set is explicitly identified. The model's focused query accepts up to12exact labels and
no offset, so a different region is a new exact label set. The legacy SiteQuery API still supports
its original40labels and pagination. No mapping, SASA or candidate ranking algorithm changes.

Repeated prompt-only synthesis reminders did not stop this no-progress loop. The existing shared
32-call guard now reserves the last8calls for SiteIntent finalization and independent review: Site
sees only its original typed output tool; late read attempts execute nothing and receive the
existing bounded output-contract correction. This supersedes earlier guidance-only behavior.
It adds no scheduler, scientific decision or approval. Every material research status, exact
citation, hard-fact check, independent Judge and Gate requirement remains unchanged; incomplete
evidence can still fail instead of manufacturing a PASS. No call/context/output budget increases.

Live129 (`phase2-goldens-20260911T202101672174Z`) successfully acquired complete GPCRdb context
and ran the real existing receptor analysis, then failed at17calls on an out-of-role tool name.
The original diagnostic omitted the name and the failed model response was not checkpointed;
its exact cause cannot be claimed diagnosed. Rejections now persist tool names, role/execution and
executed=false before raising, without arguments/source content. This retains the hard permission
boundary and makes the next real rejection diagnosable.

Both traces and their valid upstream approvals are preserved. Case3 independently PASS; Phase2
NOT FROZEN. Phase2/3/4 status documents now distinguish this active user-authorized continuation
from the superseded historical STOP and installation-only AFO smoke. Targeted130:63 PASS/1 FAIL (52.56s); the old model-schema assertion still supplied
offset and was updated for the explicit focused query. Final targeted130b:56 PASS (11.90s),
including late-read rejection, no approval creation, full row reconstruction, immutable full-result
retention and permission rejection telemetry. Ruff130b PASS; mypy130b:20 files PASS.
Next live131/132 reuse the approved soluble/GPCR Target bundles.


### Cursor-only source continuation and actual transport finalization (live131/132)

Live131 (`phase2-goldens-20260911T202831612959Z`) received complete focused row tables, but its
Site owner kept attempting reads after the finalization reserve. Those reads executed nothing;
the two existing corrections were exhausted at27totalcalls (Coordinator2/Site25). Wire133 uses
the real LangChain agent/ToolStrategy and installed SDK with HTTP MockTransport, without network:
the actual request correctly contained only SiteIntent, tool_choice=required, max_tokens2048 and
thinking disabled. Thus the model's late tool choice, rather than missing client-side schema
filtering, remains the observed problem. Finalization now sets DeepSeek's documented named
SiteIntent choice through extra_body while preserving provider settings and output budget. The
updated wire test proves the exact outgoing named choice and no jobs/proposals. Unknown fields,
citations, hard facts and independent approval rules remain enforced after response generation.
Primary transport reference: https://api-docs.deepseek.com/api/create-chat-completion/ .

Live132 (`phase2-goldens-20260911T202832636041Z`) repeatedly used a UniProt cursor on an RCSB
question, then exhausted the shared four argument repairs. Model retrieval now separates initial
queries from continue_evidence(cursor): the latter restores need/question/source/filter/page size
from the existing verified evidence-view artifact and invokes the same corpus reader. No new
store, pagination algorithm or stale-view reset exists. Legacy RetrieveEvidence remains compatible.
The model's continuation schema offers exact recently issued cursors only. Foreign/unissued tokens,
source corruption, changed selection and stale current binding remain rejected; no page/offset
advances on rejection. Tests verify exact equality with the old valid continuation, no skipped
passages/new source fetches, extra-field rejection, foreign ownership and changed-selection checks.
Continuation passages receive the same working-set retention and delivery metrics as initial reads.

Targeted133:67 PASS (14.36s), including the actual SDK wire path. Ruff133 found one description
line; mypy133 found an overly broad role type in the Site-only provider branch. Both corrected.
Model-context now records actual offered action names/output schema and counts only the tools
offered in synthesis mode. Final targeted133b:44 PASS (7.24s); Ruff133b PASS; mypy133b:20 files PASS.
Next live134/135 reuse the independently approved Target bundles. No Phase2 freeze is claimed.


### Effective wire diagnostics, retrieval prerequisites and bounded output configuration (live134/135)

Live134 (`phase2-goldens-20260911T205449967205Z`) exercised cursor-only continuation successfully
but still requested an old read during finalization, then produced a truncated SiteIntent. Its
unregistered draft also treated a KNOWN_EPITOPE view with no selected source as absent evidence
and understated already-approved mapping. No scientific acceptance is claimed. Live135
(`phase2-goldens-20260911T205450943074Z`) also used successful continuations but exhausted two
output repairs on further read requests at27calls. Named-choice behavior must be checked at the
actual transport, not inferred only from the successful no-network wire test.

The validation runner now requests a narrowly whitelisted HTTP metadata observer from the model
factory: role/model, actual tool names/choice, thinking/output fields, stream flag and message
count only. It writes model-wire-metadata.jsonl in that attempt's existing evidence directory.
No messages, headers, credentials, raw sources or tool arguments are logged. The default factory
behavior remains unchanged without an observer; no authority or artifact/checkpoint system is added.

An acquired specific source without selection for the requested need now raises the existing
SOURCE_NOT_SELECTED prerequisite before any passage/view is produced. The Site/Target guard
allows its existing bounded correction for retrieval as well as acquisition, with an explicit
not-absence message and no refetch requirement. Existing exact/stale cursor behavior is retained.

Inspection of the standing contracts confirms2048 was a historical configuration default, not a
frozen scientific invariant. Following observed real JSON truncation, this authorized worktree's
ignored config/llm.yaml now uses max_output_tokens4096. Library defaults and all provider choices
remain unchanged. DeepSeekFlash/no role overrides,32shared calls,60000input chars, frozen oracles
and validation_micro compute are preserved. This supersedes the earlier self-imposed decision
not to adjust the output limit. Before/after configuration and a change receipt are preserved as
model-config-before136.yaml, model-config-after136.yaml and model-config-change136.json under
runtime/tmp/autonomous-v3-20260912. Config SHA changed763c907c7b9ed9ff8933d138a0f938dd6da5ac9a26c758ac5ba3445aa884d87c
to1e0f04e2f422ac93bd862d2d19f0a57ef46c8749a67b4b8852d26a88b921ef1a.
The runner now records the actual non-secret model configuration in every pre-live/report artifact.

Targeted136:21 PASS (7.20s); Ruff136 and mypy136:20files PASS. Retrieval-focused136b:51 PASS/2 FAIL (19.96s); the old isolation tests expected empty
pages for unselected sources. These now assert explicit prerequisite rejection. Follow-up136c
found one further old empty-page assertion (7PASS/1FAIL); corrected along with the equivalent
context test. Final136d:13 PASS (8.47s). Ruff136d PASS; mypy136b:20files PASS.
Next live137/138 use the recorded4096output configuration and whitelisted wire observer.
Phase2 NOT FROZEN; cases1/2/4/5 incomplete, case3 independently PASS only.


### Explicit model comparison after verified named-tool rejection (live137/138)

Live137 (`phase2-goldens-20260911T210449158524Z`, soluble) and live138
(`phase2-goldens-20260911T210449491657Z`, GPCR) failed at27shared calls. The actual HTTP
metadata proves each of the three finalization requests offered only SiteIntent and named it
in tool_choice, with thinking disabled and max_tokens4096. Responses still requested old
reading/evaluation tools. No such late action executed; two bounded corrections were exhausted.
The GPCR trace also failed to use the supplied receptor-analysis workflow and over-read topology.
These are operational/model behavior failures, not scientific negative results or Phase2 PASS.

A read-only provider capability check139 returned deepseek-flash and deepseek-v4-pro. A bounded
2-call REAL MODEL test on explicitly SYNTHETIC evidence confirmed both can honor a named final
submission after an old tool call in a short conversation; this does not certify long-context
robustness or scientific acceptance. Receipts: model-capability139.json and model-probe139.json.
Official model/tool references: https://api-docs.deepseek.com/updates/ and
https://api-docs.deepseek.com/guides/tool_calls/ .

The next real retries explicitly select deepseek-v4-pro, non-thinking,4096output, with no role
overrides. This is an engineering configuration change authorized by the autonomous assignment,
not a silent fallback or a change to the scientific input/oracle. The runner's old Flash-only
assertion was a historical setup restriction rather than a frozen requirement; it now accepts
the already strict explicit ModelConfig and records all actual settings. Shared32calls and
60000input remain fixed. Before/after config snapshots and model-config-change139.json are saved
in the existing evidence directory. Config SHA1e0f04e2f422ac93bd862d2d19f0a57ef46c8749a67b4b8852d26a88b921ef1a
becomes b72c733d0535cf41fa944c1e4899d3996f0878ef165d7b7f8a4e5c27f29826d7.
Independent Judge, hard-fact/source checks, five Gates and micro compute limits are unchanged.
Phase2 remains NOT FROZEN. Valid Target approvals and exact Case3 acceptance remain reusable.

Targeted139:18 PASS (3.47s), covering provider configuration/actual SDK payload and frozen golden
spec assertions. Ruff139 PASS. Next live139/140 resume the approved soluble/GPCR Target bundles.
