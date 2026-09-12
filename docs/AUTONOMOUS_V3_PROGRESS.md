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


### Reasoning-safe provider format and adjacent synthesis instruction (live139/140)

The explicit Pro/non-thinking comparison did not solve the long-history loop. Live139
(`phase2-goldens-20260911T211234899432Z`, soluble) ended at27calls (Coordinator4/Site23),
including repeated invalid PMID-to-fulltext requests; live140
(`phase2-goldens-20260911T211234684818Z`, GPCR) ended at27calls (Coordinator3/Site24),
mostly rereading Target fields with no completed Site research. Both preserved failures remain
operational/model findings, not scientific negatives. Neither Site is approved.

The installed ChatOpenAI adapter does not round-trip DeepSeek's reasoning_content. Merely
turning thinking on in that format would therefore be incorrect. Instead the same existing
public init_chat_model factory can use the already-installed Anthropic adapter with DeepSeek's
fixed official /anthropic endpoint. It preserves native thinking/signature blocks in messages
and checkpoints through ordinary tool rounds. No dependency, private patch, provider account,
workflow, approval or scientific kernel changes are required. LLMConfig now has an explicit
reasoning_effort (none default, or low/high/max for DeepSeek); non-DeepSeek reasoning values are
rejected until verified. Default non-thinking behavior is retained. HTTP request observations
remain available only for the old OpenAI-format adapter; reports explicitly list adapter and
http_observation_roles. Native SDK round-trip tests verify the new format without mislabeling
pre-SDK events as HTTP telemetry.

REAL MODEL thinking-probe141 used exactly2calls on explicitly SYNTHETIC input, preserving the
first thinking block into a subsequent tool-result round and returning the final evidence-limited
typed conclusion. Receipt includes only block types/tool arguments/usage, not reasoning text.
No scientific acceptance follows from that probe. Vendor reference (archived HTML139):
https://api-docs.deepseek.com/guides/anthropic_api/ ; thinking/effort reference:
https://api-docs.deepseek.com/guides/thinking_mode/ . The vendor ignores budget_tokens; max_tokens
remains the actual total output cap. The framework intentionally drops forced tool_choice in
thinking mode; typed output remains required by the existing bounded submission checks.

Site finalization additionally appends a short transient runtime control message immediately after
the latest delivered evidence. Earlier beginning-only phase notices were ignored by both models.
The original checkpoint remains untouched, and the added message is included in the unchanged
60000-character budget. It offers no new evidence and cannot resolve unknowns or approve a Gate.
Next retries use explicitly configured Pro/low reasoning with4096output,32shared calls and
60000input. No production compute is authorized or used.


Targeted141:28 PASS (18.89s); targeted141b:26 PASS (7.44s), including actual SDK tool payload
for both formats, exact thinking/signature round-trip and latest runtime phase notice. The one
expected framework warning explains that forced choice is dropped in thinking mode. Ruff141b
PASS; mypy141b:2 changed source files PASS. Protected-check141:all385 files unchanged.
Config before/after snapshots and model-config-change141.json retain SHA b72c733d0535cf41fa944c1e4899d3996f0878ef165d7b7f8a4e5c27f29826d7
→786d02de6d7c4f7e43e2a0d79fdf9017fb3e2e07d0c84476b2ba6b08a968cd40.
Next live141/142 resume the approved soluble/GPCR Target bundles. Phase2 NOT FROZEN.


### Completed-tool working context and exact continuation pages (live141/142)

Live141 (`phase2-goldens-20260911T212007347528Z`, soluble) failed after8calls
(Coordinator3/Site5); live142 (`phase2-goldens-20260911T212007853969Z`, GPCR) after9calls
(Coordinator2/Site7). Both began batched source research but reached the unchanged60000input
boundary while replaying accumulating private reasoning. Soluble's five Site replies alone
contained15116thinking characters; its last sent context was56175chars before another batch.
No input cap is raised. These failures do not invalidate the approved Target or imply biology.

For reasoning mode, the existing model-input projection now represents completed assistant/tool
exchanges as a transient runtime history containing exact action arguments, exact delivered tool
values (including nulls, counterevidence, failure status and full-result refs) and labeled assistant
text. Original human turns retain order. Private reasoning is not a scientific fact and is not
replayed in that working view; original signed blocks remain byte-for-byte in the existing native
checkpoint. Included signed blocks are never cut or forged. Incomplete/orphan exchanges are
not projected. No new artifact/checkpoint/workflow or model-authored scientific summary is added.
The guard counts the actual projected messages, and context metrics identify the projection.

A separate discovered omission affected continue_evidence: it had inherited generic preview
truncation instead of retrieve_evidence's exact-page path. It now retains complete scoped passages,
limitations and available feature types. The original corpus/page size/cursor/ownership checks
are unchanged. Tests compare exact returned values for both initial and continuation pages.

Targeted143:34 PASS (8.40s), including unchanged original messages, complete retained scientific
payloads, pending-call preservation, exact pages and actual SDK/typed boundaries. mypy143:3files
PASS. Ruff143 found one overlong presentation string; formatting corrected. A2-call REAL MODEL
probe143 on SYNTHETIC input accepted the completed-tool working view and submitted an appropriately
limited final tool conclusion; no scientific acceptance is inferred. Small synthetic histories
can become slightly longer due to the explicit provenance envelope; the long-thinking regression
verifies the intended reduction without changing evidence values.
Next live143/144 reuse approved Targets under unchanged Pro/low/4096/32/60000configuration.
Phase2 NOT FROZEN; only Case3 is scientifically accepted.


### Total output exhaustion with reasoning (live143/144)

Live143 (`phase2-goldens-20260911T212629333460Z`, soluble) ended after14calls
(Coordinator3/Site11); live144 (`phase2-goldens-20260911T212629302864Z`, GPCR) after13calls
(Coordinator4/Site9). Both exhausted the two typed-submission corrections; neither returned a
SiteProposal or Gate2. The soluble Case3 evidence remains independently accepted. Inspection of
native SDK response metadata showed stop_reason=max_tokens and output_tokens=4096 for batched
research replies, whose final tool arguments were truncated to an empty object. Private thinking
text was not exported. Completed-tool context projection prevented the previous early input
failures; GPCR's latest sent context was58234chars, still near the unchanged60000 limit.

The next explicitly audited comparison raises only the configured total output cap to8192,
already supported by LLMConfig, to give reasoning and structured tool arguments room to finish.
Config SHA786d02de6d7c4f7e43e2a0d79fdf9017fb3e2e07d0c84476b2ba6b08a968cd40
→e5a5e6e59d516dabda4989cebb336794ef0f24743b34456a662f3d3b6c0a8464.
Before/after snapshots and model-config-change145.json are retained under the existing runtime
evidence directory. Model Pro/low, shared32calls and60000input remain unchanged. No source or
scientific invariant changes accompany this retry; the prior targeted143 tests apply.
Next live145/146 resume the same independently approved Targets. Phase2 NOT FROZEN.


### Canonical lookup, focused instructions and Site output cap (live145/146)

Live145 (`phase2-goldens-20260911T213641992394Z`, soluble) ended at13calls
(Coordinator2/Site11), still without a valid SiteIntent. Native SDK metadata for the saved
empty SiteIntent call reports stop_reason=max_tokens, output_tokens8191 and25843private-thinking
characters (text not exported). Thus8192 remained insufficient for that reasoning plus final
structured response. Live146 (`phase2-goldens-20260911T213642139020Z`, GPCR) ended at11calls
(Coordinator2/Site9), exhausting four shared argument/prerequisite repairs. It requested
canonical296–307 as design labels, omitted the GPCRdb receptor identifier/selection, then tried
reading the display-only facts_table from its original full_result. Neither reached Gate2;
these are operational failures, not scientific negative results. Exact Case3 PASS remains valid.

A new read_canonical_mapping Site tool only filters existing approved mapping rows by up to six
explicit canonical positions. It preserves all matching rows (including nonunique correspondence),
original qualifiers/nulls/source numbering/model presence and separately lists labels with actual
coordinate-derived SASA rows. No match differs from matched-but-unobserved. No offset, alignment,
biological interpretation, hotspot approval or scientific kernel change is introduced. Existing
ArtifactRef checks and the usual exact-page offload/read path remain authoritative.
REAL APPROVED DATA lookup147 independently verified soluble53→design35,70→52,146/147→unobserved,
and GPCR299–304→427–432 with ambiguous mapping preserved. No events, target state or jobs changed.
Receipt: canonical-lookup147.json. Synthetic tests additionally preserve every row in a multi-match
case and reject duplicate/nonpositive/boolean/oversized requests.

The Site Skill is condensed from145 to101lines, retaining the scientific constraints/research
standards while removing duplicate mechanics. This avoids the observed mandatory second tail read
and reduces repeated prompt overhead. Research references clarify that approved Target identity
is reused; GPCRdb identifier help explicitly distinguishes receptor entry from pdb_id.
The model-response event records SDK stop reason, usage and tool names, without private thinking
or tool arguments, before local submission checks. It is diagnostics in the existing event log,
not a new checkpoint system or a scientific fact. An exception thrown inside the framework before
returning a response may still have no such event; native saved response metadata remains useful.

The provider's current official max_tokens documentation permits values beyond16k:
https://api-docs.deepseek.com/api/create-chat-completion/ (archived deepseek-api-reference147.html).
LLMConfig's explicit maximum is now16384; its2048default is unchanged. Only the Site role is
configured to16384 for the next retry. Other roles remain8192, Pro/low and shared32calls/60000input
are unchanged. Before/after/config-change147 receipts bind
e5a5e6e59d516dabda4989cebb336794ef0f24743b34456a662f3d3b6c0a8464
→ff188ad3e25a994df084375565ac81374004773101ae2d7c65444ea92b479938.

Targeted145:21 PASS/2 opt-in-live skips (421.53s), covering Site/Design steering and restart.
Targeted147:50 PASS/1 FAIL (23.36s); the failure was the actual-SDK test's stale4096assertion
after requesting16384. Correcting that expectation yielded targeted147b:1 PASS (0.77s).
The SDK test confirms16384 reaches the actual request and signed blocks round-trip intact.
Ruff147 PASS; mypy147:8source files PASS. No production/GPU jobs were added.
Next live147/148 resume the independently approved soluble/GPCR Targets. Phase2 NOT FROZEN.


### Preserve pending submission repairs and fit total Site context (live147/148)

Live147 (`phase2-goldens-20260911T215005029436Z`, soluble) ended at23calls
(Coordinator4/Site19; peak sent context50869). It used the new canonical lookup and corrected
precursor/mature numbering, performed discovery and candidate geometry checks. The first complete
SiteIntent response used9546output tokens and passed schema parsing; runtime correctly rejected
an identity research conclusion without that topic's research record. After intervening reads,
a later response used10990tokens with stop_reason=tool_use but an empty SiteIntent input. That
response was NOT a max_tokens truncation. Two correction slots were exhausted; no proposal,
Judge or Gate2 was produced. The final offending runtime diagnostic was lost because the old
code reserved a repair before logging the rejection; this ordering is now corrected.

Live148 (`phase2-goldens-20260911T215004778505Z`, GPCR) ended at9calls
(Coordinator2/Site7; peak sent context59183), at the60000input guard after more scoped reads.
It acquired complete GPCRdb context, invoked the existing receptor analysis and read canonical
correspondences. It had not yet performed discovery search or produced a Site proposal. Thus
it remains FAIL, regardless of the acquired source/context volume. Neither failure is biological.

Two local Harness fixes follow these traces. A rejected parsed opinion and its exact diagnostic
are retained in the existing rejected-submission event and supplied as explicitly unaccepted
model content on subsequent calls, including after corrective tool reads. The view is scoped to
role/thread/execution and cleared by successful submission preflight. It conveys no hard facts,
scientist instruction or approval. This fixes the earlier transient-only correction, which could
vanish when the model chose a tool action. Every attempt still consumes the same persisted budgets.
Rejection logging now precedes reserving a correction, so a terminal exhaustion retains its cause.

When Site's actual total request would exceed60000, older complete registered tool views are
replaced by explicit references to their existing verified artifacts, oldest first. The newest
answer and latest candidate evaluation remain intact, along with original user turns, tool
arguments and all native checkpoint messages. The runtime logs before/after counts and archived
refs. The same hard guard still rejects an oversized pinned/base context. Missing fields remain
unknown and can be reread; no new source/checkpoint/artifact mechanism or model summary is added.
Independent Judge snapshots do not use this reduction and retain their existing full-content guard.

Targeted149:38 PASS (29.58s), including a complete mocked submission-rejection → corrective read
→ persistent diagnostic/opinion → accepted preflight/Gate2 sequence without duplicate proposals,
plus both reasoning/native total-context fits and exact latest answer/evaluation retention.
The existing source integrity, scoped retrieval, Judge counterevidence and actual SDK tests also
pass. Ruff149 found one overlong test string; formatting corrected, Ruff149b PASS. mypy149:2source
files PASS. Model configuration remains Pro/low, Site16384/other8192,32shared calls/60000input.
Next live149/150 resume the same approved Targets. Phase2 remains NOT FROZEN; only Case3 PASS.


### Real Site proposal, lossless Judge view and explicit review recovery (live149/150)

Live149 (`phase2-goldens-20260911T221327117740Z`, soluble) reached a complete real SiteIntent
and the existing Stage02 proposal job. It used19model calls (Coordinator6/Site12/Judge1),
peak sent context57663, four searches and five retained source responses. A false-positive
Agent count check interpreted “canonical 53” and “canonical 70” residue positions as sequence
lengths. The new pending-repair view preserved the complete rejected opinion; the model corrected
its wording and successfully submitted. The actual total-context fit reduced67259→55923chars
without changing source messages. Independent Judge then failed at the32000tool-view limit: the
complete scientific snapshot was33708chars. Case1 remains FAIL pending independent review;
Case3 remains PASS. This is a runtime failure, not evidence against lysozyme inhibition.

Live150 (`phase2-goldens-20260911T221327294006Z`, GPCR) ended at17calls
(Coordinator3/Site14; peak58987), with two searches, nineteen retained source responses, complete
GPCRdb acquisition and actual receptor analysis. The model repeatedly read `facts` from source
passage and canonical-mapping results; four shared field/selection corrections were exhausted.
No GPCR Site proposal or Gate2 was produced. Both owned runner processes are confirmed exited.

The narrow count guard now requires explicit length language or quantity units, and never joins
separate prose fields into a fictitious statement. It still rejects false canonical/construct/
observed lengths, including slash-separated alternatives and Chinese length claims. Residue
positions/ranges do not become length assertions. This is Agent prose preflight, not a mapping
algorithm or oracle change. Result views now retain their actual stored root-field names and
previous scope when archived. Generic field examples no longer imply every artifact has `facts`;
Site guidance distinguishes matches/cards/facts and encourages broadening empty literature queries.

Judge's Site view displays exactly duplicated research conclusions once at an explicit local
JSON pointer. No unique content is removed. The retained live149 snapshot shrank33708→30895chars
and an exact reconstruction equaled the original scientific projection. All sources, counterevidence,
access failures, nulls and limitations remain visible; originals and bindings are unchanged.
Nonidentical or still-oversized content retains the existing fail-closed guard. Receipt:
`judge-projection151.json`. No input, repair or model-call budget was raised.

Explicit trusted `transfer_unreviewed_site` recovery moves only the current unreviewed pending
proposal into a fresh thread after the source Agent has stopped. It verifies the exact same-project
proposal/Target/facts/research/review and pending original job, refuses existing Judge/Card outcomes
or a used destination, and atomically records source/destination provenance. The original proposal
owner/ID/snapshot/job/checkpoint/fingerprint/budgets remain intact. No new scientific job, verdict
or approval is created. The new thread must obtain independent Judge and the original Gate2
approval. Replays are idempotent; source current-proposal lookup excludes the transferred proposal.
This API is not available to the model. The validation runner accepts an explicit failed-case
resume path and combines actual old Site/new review metrics with per-execution counts preserved.

DETERMINISTIC/MOCK targeted151:51 PASS (90.51s), covering false-count rejection, valid residue
wording, exact Judge reconstruction, nonidentical counterevidence rejection, transfer isolation/
idempotence and actual old-service Gate2 approval without another job. Isolated draft151 count
checks:29 PASS (21.23s). Additional targeted151b:10 PASS (4.75s), including archived field indexes
and canonical lookup. Ruff151 initially found one long runner string; fixed, Ruff151b PASS.
Mypy151:4source files PASS. Protected151:all385 baseline files unchanged.

Next live151 resumes live149's completed unreviewed Site proposal for Judge/Gate2 and then
Binder validation; live152 resumes the independently approved GPCR Target. Configuration stays
Pro/low, Site16384/other8192,32shared calls/60000input. Phase2 NOT FROZEN; Phase3/4 NOT STARTED.


### Coordinator routing and repeated field-directory metadata (live151/152)

Live151 (`phase2-goldens-20260911T223547770192Z`, soluble) successfully transferred the exact
original live149 Site proposal606ec24778f759e845452a4788a560fca234a6520e826e4a9033394c04717376
and original job-bbb38832cfc2405f into live-site-20260911t223547770192z. No scientific job was
created. It then ended incomplete after two Coordinator calls: actual SDK stop_reason=max_tokens,
output8192, with neither text nor tools. The prior19calls remain included in source-thread metrics;
no Gate2 card or independent acceptance was produced. Case3's exact unchanged snapshot PASS was
retained. The unreviewed proposal remains current in live151 and is the next recovery source.

The verified next_specialist previously still said Site when an unreviewed proposal already
existed. It now directs this state to Evidence Judge; existing trusted REVISE outcomes direct
it back to Site. The Coordinator instructions explicitly cover already-completed/resumed Site
proposals. Transfer lineage metrics now follow all same-project receipt ancestors, preserving
actual per-execution calls across repeated engineering recovery rather than losing the first Site
research measurements. No previous budget, fingerprint or native checkpoint is overwritten.

Only Coordinator is configured without thinking for the next retry; it still uses DeepSeek v4 Pro
with8192output tokens. Scientific specialists remain Pro/low (Site16384; other8192). The existing
public OpenAI-format adapter handles this Coordinator role and its actual request metadata observer
will be present again. Shared32calls/60000input remain unchanged. This is an explicit engineering
configuration choice, not a scientific oracle change. Before/after/model-config-change153 receipts:
ff188ad3e25a994df084375565ac81374004773101ae2d7c65444ea92b479938
→5d3b180249f800642bd084e63f2752b4883abcdf5c170d624a4a9450922e61f3.

Live152 (`phase2-goldens-20260911T223548063652Z`, GPCR) completed receptor analysis and correctly
used the newly supplied field directories. At17calls (Coordinator3/Site14), its next input was
77676chars; old whole-result archiving reduced this to60112, still above the60000guard. No oversized
request was sent and no Site proposal/Gate2 was created. This is not a negative biological result.
Repeated identical stored_fields lists now occur once per completed-tool history record; later
instances point to that original tool-call field list. This is navigation-metadata encoding only,
not removal of scientific data or tool arguments. The original messages remain unchanged.
Actual retained native checkpoint:65messages,26metadata references; its unbounded history projection
was112206chars before and108021after. Expanding the references reproduced every original history
record exactly. This is a deterministic projection check, not an actual sent-context measurement;
the next live retry verifies the latter. Receipt:context-projection153.json.

Targeted153:37 PASS (50.47s), with the expected framework forced-tool/thinking warning; includes
complete evidence/argument preservation, field-directory expansion, context fitting, Site transfer,
REVISE routing and actual SDK tool/adapter contracts. Isolated routing draft:7 PASS (45.90s), two
pytest import-rewrite warnings. Ruff153 PASS; mypy153:3source files PASS. No production/GPU jobs.
Next live153 resumes live151's unchanged unreviewed Site; live154 reuses the approved GPCR Target.
Phase2 NOT FROZEN. Only Case3 is accepted; Phase3/4 NOT STARTED.


### Soluble Gate2 independent acceptance (live153; Design/GPCR still running)

Live153 (`phase2-goldens-20260911T225114819732Z`) preserved original Site proposal
606ec24778f759e845452a4788a560fca234a6520e826e4a9033394c04717376 and original Stage02 job,
then obtained the actual independent Judge and Gate2 card
242b9eafc3f7efb59a9129d3f7cc691ec2d9ca8795a441c0f2d75c164b0aa9be.
The complete lossless Judge view was read successfully. Independent six-section scientific
review accepted Case1 at snapshot256c230d607e022a3f0edc19e8a9300991f7c927b8076a765e53c7c4782028d9.
Case3's unchanged identity-trap review remains PASS. This is REAL MODEL / REAL SOURCES /
EXISTING DETERMINISTIC SERVICES acceptance; no binding/inhibition experiment was performed.

All primary design labels35/52/62/63/101 (E/D/W/W/D) are observed and correctly mapped to
canonical53/70/80/81/119, source authL/labelC, normalized designA. Primary literature-derived
cleft insertion and scan-derived rim entry blockade44/46/48/62/101 remain distinct hypotheses.
The card stays DISCOURAGED: buried E35/D52/W63 and spatial components are explicitly retained;
no full-body clearance, dynamics or residue-level epitope proof is claimed. The verified primary
abstract supports a regional protruding-CDR3 precedent, not inhibition. Enzyme titration with
substrate dependence, fold-integrity and interference controls make the hypothesis testable.
The independent review explicitly qualifies two prose overgeneralizations: competitive kinetics
alone do not uniquely prove specificity, and direct catalytic-dyad contact is not universally
required for inhibition. Neither is accepted as a hard fact; orthogonal controls and the card's
uncertainty about sufficiency of cleft occlusion remain necessary.

Site/review lineage records actual19+2+6model calls (Coordinator12/Site12/Judge3), peak supplied
context57663 under60000, four searches, five acquired source responses, three retained corpus
documents and five focused cards. Empty narrow function/epitope searches mean no evidence was
retrieved in this run, not literature-wide absence. The six-section review is retained at
`soluble/gate2-independent-review.json` in the live153 evidence directory.

The existing trusted human-input path then applied the validation actor's explicit warning
OVERRIDE and verified the old Site approval. No new Site job was created. Standard Binder
Strategy is now running with the real isolated BoltzGen0.3.2 validator, to be followed by a
separate native expert YAML case. Live154 GPCR continues actual receptor/source/mapping work.
Cases2/4/5 and full regression remain outstanding. Phase2 NOT FROZEN; Phase3/4 NOT STARTED.


### Complete owner views and approved-Site Design continuation (live153/154)

After Case1/3 acceptance and the actual Gate2 warning override, live153's standard Binder
ended before any proposal at16shared calls (Coordinator2/Binder14), peak sent context58203.
Repeated reads of one approved design snapshot accumulated beyond60000. The full original
snapshot was20978chars and its complete scientific projection17878chars, so splitting it
into many small views was unnecessary. Native Case5 was not run; accepted Target/Site and
reviews remain intact. No candidate generation or prediction occurred.

Live154 GPCR (`phase2-goldens-20260911T225114966519Z`) ended at20calls
(Coordinator3/Site17), peak59646. It acquired19source responses and completed the real receptor
analysis, but repeatedly requested entire topology/candidates objects and reread mapped pages.
No keyword discovery search, Site proposal or Gate2 was completed. This is a context/navigation
failure, not evidence against the receptor or a scientific negative result. Both runner PIDs
were confirmed exited before Agent files changed.

Binder now receives the complete scientific `read_design_evidence` projection when it fits
32000chars, including every approved hotspot, all seven official scaffold constraints,
Site rationale, warnings and controls. The existing60000input/32call limits remain unchanged;
oversized owner data is explicitly partial with its full immutable source retained.

The Site receptor tool now supplies a declared candidate overview with identity/state/membrane/
topology summary, every candidate's non-residue scientific metadata and every member in explicit
source-residue columns. Uniform columns are represented as exact tables; missing keys remain
distinct from present nulls. This is a scoped projection of existing output, not new ranking,
mapping, topology or accessibility science. Other columns, full topology, chain graph and
provenance remain available through the same verified artifact reader. The view is explicitly
partial relative to the complete analysis and complete only for its declared fields. Source
coordinates are expressly not approved design coordinates; canonical lookup and qualifications
remain necessary. Display aliases resolve back to this deterministic source projection.

Retained live154 analysis635111chars → declared overview24972chars. All7candidate entries,
all44members, all non-residue scientific fields and every displayed source-numbering value were
compared to the original artifact. Receipt `receptor-overview155.json` is a DETERMINISTIC
PROJECTION CHECK, not new live-model acceptance. Full-VHH approach and efficacy remain unresolved.

The validation runner extracts the same standard/native Gate3 test into a shared function and
adds an explicit approved-Site continuation entry. It verifies source Case1/3 acceptance, exact
review hash, stored card/Judge, delivered validation actor response, current applied Site approval,
unchanged scientific content and original Target mapping. Pending and approved Stage02 manifest
bindings remain distinct. It starts fresh Design threads without touching prior checkpoints,
proposal ownership, verdicts or scientific jobs; existing expert inputs are reused unchanged.
Each Design attempt exports metrics even on failure. No new scheduler/approval system is added.
The real saved Site passed read-only resume verification at
`phase2-goldens-20260911T231956503269Z`; no model calls or new jobs were made. An initial driver
check used the Site thread for a Target-only canonical event lookup; the correct original Target
thread fixed that ordinary validation defect, with the failed diagnostic retained.

DETERMINISTIC/MOCK targeted155:36 PASS (554.36s), including actual old-service Site approval,
pre-approval rejection, changed/failed review rejection, complete owner view, strict native
constraints and design runtime/harness. Earlier isolated draft owner-view test:9 PASS (2.26s).
Mypy155/155b passed; final table/alias and lint checks are recorded below when complete.
Protected155:all385 baseline files unchanged. Cases2/4/5 and full regression remain pending;
Phase2 NOT FROZEN and Phase3/4 NOT STARTED.

Final targeted155b:11 PASS (11.04s), covering exact candidate tables/aliases and the approved-Site
review recovery guard. Both preserved live processes and the test processes have exited.
Ruff155c PASS; mypy155b PASS. Next live155 continues only standard/native Design from the actual
live153 Site approval; live156 reuses the approved GPCR Target with the new candidate overview.
No model/output/call/input or GPU budgets changed.


### Reuse the already installed validation backend (live155)

Live155 (`phase2-goldens-20260911T232126002200Z`) verified the actual approved Site and its
independent review, then stopped before any model call because the validation helper tried to
recreate the already existing isolated BoltzGen directory from live153. No scientific state or
prior backend data was overwritten. The helper now reuses only the exact current fixture
profile/paths, verifies console bytes plus real version/source commit/molecule-data identities,
and preserves the existing profile bytes. A mismatched runtime is rejected instead of replaced.

Targeted157:1 PASS (1.85s), MOCK backend probe only, proves repeated setup preserves profile/
executable and rejects replacement console bytes. Ruff157 PASS. The installation-reuse check
uses the actual backend (no YAML check or generation) and records before/after profile SHA in
`backend-reuse157.json`. Live157 will retry only the pending Design cases from live153's actual
Site approval. Live156 GPCR remains running on the unchanged Agent fingerprint. Phase2 NOT FROZEN.


### Independent Gate3 review rejects factor/absence overclaims; GPCR context repair

Live157 (`phase2-goldens-20260911T232342960993Z`) used the verified existing isolated backend
and reached a standard Gate3 card after 10 real model calls (Coordinator5/Binder3/Judge2).
The actual existing compiler and BoltzGen0.3.2 check passed all7 strategies, planned280,
no generation. Exact approved Target/Site, full target, current hotspot and default scaffold
constraints were retained. Nevertheless the independent six-section content review is FAIL:
card353523a3ff253a1af3dd567f366802baa5a7b39b0d0f75ef7b3d7d0a954ffa5b and
Judge judge-d92e1257ab9549f6891026be5b73e89c accepted a CDR3-only factor narrative, whereas
actual emitted YAML designs all three CDRs and samples their insertion ranges across seven
scaffolds. Default constant bounds do not freeze sequences/lengths or isolate CDR3 causality.
The opinion also inflated limited unproductive function searches to global absence of binding/
function evidence, despite the structural binding precedent. An unsuccessful small sample must
not establish failure of a scaffold set. The exact failed review is preserved; Case5 was not run,
Gate3 was not approved and no compute job was launched. Case1/3 acceptance remains valid.

Binder and independent Judge instructions now explicitly challenge those three consequential
reasoning errors. The verified design-constraint view explains design.res_index and the three
insertion ranges without changing scaffold assets, compiler semantics or the frozen first-pilot
plan. No new keyword-based scientific oracle is added; the actual model must reason from the
same executable constraints and independent content review must still pass.

Live156 GPCR (`phase2-goldens-20260911T232126182415Z`) delivered the full candidate overview,
then failed the unchanged60000-character context guard after8calls (Coordinator3/Site5), before
SiteIntent. Its original26-message native checkpoint was read-only replayed: old projection
70472→67112chars; the repaired optional-reference projection gives59747chars. The newest
identity answer and complete24972-character scientific candidate overview remain exact. All
original messages and the checkpoint SHA remain unchanged. Receipt `context-replay158.json`
is a DETERMINISTIC PROJECTION REPLAY of real trace data, not live acceptance.

When older scientific-view archival is insufficient, Site may now replace previously read
optional research/membrane/shielding Skill pages with explicit re-read references. Main role
instructions, newest requested answer, latest candidate evaluation, user inputs and unknown
file paths are preserved. Reference instructions remain applicable and fingerprint-bound;
this changes model input only, not source artifacts/checkpoints or scientific evidence. If the
remaining context is still too large the original hard guard rejects it. Live156/157 processes
were confirmed exited before editing Agent/Skills. Targeted tests/lint are running; no model,
output, call/input or GPU budget changed. Phase2 NOT FROZEN; Phase3/4 NOT STARTED.


Targeted158:35 PASS (472.71s), including original-message preservation, exact newest candidate
answer, main/foreign-file protection, native/reasoning reference archival, owner evidence views,
old design compilation/freeze and multi-turn harness paths. Ruff158/158b PASS. Initial mypy158
required a local variable type annotation; annotation-only correction then mypy158b PASS for
both changed modules. Protected158:all385 baseline files unchanged. Next live158 retries only
standard/native Design from live153's approved Site; live159 retries only GPCR Site from live104's
approved Target. Model config and frozen spec/oracle remain unchanged.


### Standard Gate3 second independent review (live158)

Live158 (`phase2-goldens-20260911T234323971865Z`) reached standard Gate3 after9 real calls
(Coordinator4/Binder3/Judge2), peak48715 system/message characters. Actual default three-CDR
and scaffold sampling is now described correctly; zero/low yield remains INCONCLUSIVE. Real
backend validation again passed7strategies/280planned/no generation. The independent review
nevertheless remains FAIL, snapshot35ad6c1ff1ebc9cd423c8e26afdf87f124481d6a0c6f7f1993382a1892b24dd4:

- Card820ba978a02b18ed04abcac27b36afa4eff3bfbeed2e599dbeb51c052df7667d treats CDR insertion
  counts as final loop lengths and argues that “12–14-residue CDR3” ranges permit the tip. The
  unchanged legacy boltzgen-contract explicitly distinguishes design.res_index, insertion
  counts and final loop length. This existing semantic warning was missing from v3 guidance.
- Proposal/Judge/card say “No residue-level epitope exists”; the evidence establishes only that
  a residue-resolved interface was not established in the retrieved evidence, not nonexistence.
- Judge judge-e918967153984f5e9c6e7bb4cf6e056d says upstream Site override lineage is outside
  verified scope, although the supplied upstream_decision explicitly verifies that old approval.
  The pending Gate3 and the verified prior Site override must remain separate.

The failed six-section review and complete emitted design remain preserved; native Case5 was
not run, no Gate3 approval or generation occurred. Cases1/3 stay accepted. The next local draft
adds the existing insertion-count semantic distinction, scopes every unknown including epitopes,
and distinguishes verified upstream Site authority from pending Design authority. It will be
synced only after active GPCRlive159 exits, preserving that execution's Agent/Skill fingerprint.
No kernel/oracle or scientific Gate change is required. Phase2 NOT FROZEN.


### Preserve every newly returned parallel answer (live159)

Live159 (`phase2-goldens-20260911T234324135660Z`) progressed through research, receptor
analysis, primary/database passages, glycan/topology inspection and approved canonical lookup,
then failed the60000-character guard after19calls (Coordinator3/Site16), before SiteIntent.
Its final projection was85629→64823chars. The early optional-reference fix worked, but repeated
reads accumulated because another delivery bug hid answers before their first model consumption.

`batch-delivery159.json` compares the exact native checkpoint with the actual first projection:
a3103-character canonical mapping answer from a4-tool batch became a295-character archived
reference while the other3answers remained. Prior examples also hid candidate patches/mapping
in batch positions preceding the last result. Source/checkpoint bytes remain intact, but this is
not usable delivery. The old policy pinned only the latest single answer. Both working-set and
total-budget projections now pin every matching result of the latest AI tool-call batch using
its actual tool_call_ids, including current Skill reads; latest candidate evaluation is retained.
Old read-only views can still be archived, and irreducible oversize input still fails the guard.

`batch-replay160.json` is DETERMINISTIC REPLAY, not live acceptance. At historical tool batches
9–14, previously hidden answers are now all present, at58514/58629/58712/58177/58297/58979chars.
The already bloated histories at batches15/16 remain over budget (67633/76182); they are honestly
rejected rather than silently losing requested answers. The fix must prevent repeated unseen
reads in a fresh Site execution; no claim is made that the old terminal context now fits.
A first diagnostic replay encountered an empty initial checkpoint and was corrected to skip it;
no checkpoint/state was changed. Live158/159 were confirmed exited before source synchronization.

Targeted160:24 PASS (48.28s), including actual RoleBoundary middleware for native/reasoning
parallel batches, all prior context/projection tests, existing compiler/freeze and submission
correction after a tool round. Ruff160 PASS; mypy160 PASS for3changed modules. Protected160:
all385 baseline files unchanged. The CDR insertion-vs-loop, evidence scope and upstream-approval
wording repair is included. Next live160 retries standard/native Design from acceptedSite153;
live161 retries GPCR Site from acceptedTarget104. Same model configuration,32calls,60000input,
formal7x40 Design intent and micro-only future compute constraint. Phase2 NOT FROZEN.


### Exercise the existing Scientist REVISE path after exact Design content review

Live160 (`phase2-goldens-20260912T000018423827Z`) reached a third standard Gate3 with real
backend validation passed. Insertion counts versus final loop lengths and three-CDR sampling
are now explicit, and Judge scopes absent epitope evidence correctly. Its independent review
is still FAIL (snapshotdc3a9238420cbb3acef1757106396bf5116bd4cd92fd1f7b7a62dbe8285cfb6d):
the owner calls the empty cdr_template_validation list a performed override-range validation,
negative-result wording overstates causal discrimination, Judge calls inferred cleftTrp63 a
catalytic residue, and verified upstream Site authority is conflated with pending Design authority.
The actual default asset checks/compiler pass, hotspot/counts and no-generation boundary remain
valid. The review preserves explicit corrective instructions without changing scientific inputs.

The validation runner now optionally uses that exact failed, unanswered Gate3 card for the
existing trusted REVISE action by the explicitly labeled scripted validation actor. It checks
review/snapshot SHA, all six sections, stored card/Judge, current design and approved Site,
source project/config/spec/oracle and absence of an earlier response. This read-only verification
creates no decision; actual steering goes through run_session's existing human-input interface.
A revised result must have the original parent_card_id and a fresh independent content review.
Old cards/checkpoints/inputs are retained, and no new approval/decision/recovery system is added.
It is an explicit validation Scientist turn, with its own existing execution accounting, not an
invisible budget reset or a claim that the original failed model answer passed.

Actual pendingDesign160 passed verification-only (`design-revision-verify162.json`): no model
calls, no decision applied, no new job. Targeted162:3 PASS (114.58s), including exact failed-review
binding, rejecting changed current evidence/existing responses, and the existing Gate3 revision/
process-restart test that preserves Target/Site/goal. Ruff162 PASS. Only validation scripts/tests
and this report changed while GPCRlive161 runs; Agent/Skill/model fingerprint is unchanged.
Next live162 will apply the captured review instruction through REVISE, then recheck standard
Gate3 and native Case5 if standard passes. No approval or generation. Phase2 NOT FROZEN.


### Standard Design accepted after trusted Gate3 REVISE (live162)

Live162 (`phase2-goldens-20260912T001103284678Z`) resumes the exact standard160 thread and
applies the explicit validation-actor REVISE. Its new card
a6c8d40581289c1a4aac2b3e939d37ff0b526b5f3ea4ee6029f9bdc88cbb9bfa has the original
45979beebd41b78bd18d2cf2ecff4e91c6aec5a07c48a5b04e2b2eebb0b423f4 as parent. The fresh
Judge judge-afffb9b53b9c49ffb4d8120f7d5d5197 and independent six-section review pass the revised
Design. Review snapshot5a58cb7e0f51813795b5dffb1a69cc40223724ad0305e7c7d3935c0904845a57;
receipt SHA3e2bc214f9ea8e832d9e2819fab82f19e047397248b068f93a6f8eaf1692ab97.

The exact approved Target/Site, one arm/all7scaffolds/40each/full target and unchanged hotspot
are retained. The owner accurately distinguishes insertion counts from loop lengths, all3CDR
sampling from a CDR3-only experiment, empty custom-override validation from official-asset
checks, catalytic Glu35/Asp52 from inferred Trp63 lining, and verified prior Site override from
pending Design approval. Negative micro yield is INCONCLUSIVE with competing explanations.
Actual compiler/BoltzGen0.3.2 check passes7strategies/280planned; strategy SHA
da64195d47ece5d539493234b60b7cd620208a8631a7d2ed0e9789a95ec5b2b0. No generation.

Root review preserves the accepted Site qualification: competitive kinetics alone is not unique
proof of specificity; orthogonal integrity/interference controls remain necessary. Direct dyad
contact is one proposed route, not a universal condition of inhibition. This is a testable,
DISCOURAGED exploratory Design, not evidence of successful binding, inhibition or permission to
launch compute. The actual card stays awaiting-human-approval. Case4 is PASS after explicit
Scientist steering, not unassisted first-attempt acceptance. Across the original and revision
executions: Coordinator8/Binder6/Judge4; initial10calls + revision8calls, peak51420chars.
Case1/3 acceptance is retained. Separate native Case5 is now running; Phase2 is NOT FROZEN.

Live161 GPCR (`phase2-goldens-20260912T000018691957Z`) independently failed the unchanged
context guard after Coordinator3/Site17calls, with real research/receptor analysis and two
candidate evaluations retained but no SiteIntent/Gate2. The parallel-answer fix prevented
first-delivery loss; repeated raw topology reads still accumulated. Existing complete candidate/
topology projection aliases were not listed in stored_fields or archived navigation. A local
navigation-only repair is staged pending completion of live162, so no active Agent/Skill
fingerprint is changed. No mapping, receptor algorithm, oracle or Gate change is required.


### Native Case5 interpretation correction; retain accepted Case4

Live162 reached native Gate3 card20af29724c0b0e5576e85af61cfabb7ce2ecb842c7a407b37e8e1fdfec611ea4
in separate threadlive-design-expert-native-20260912t001103284678z. Exact native YAML byte
checks and all7 real backend validations passed, but content review FAIL: Judge's warning says
"No inhibition or kinetic evidence exists", exceeding the actual bounded retrieval. The native
specification otherwise retains the seven official variants/one condition,40each/280planned,
full approved Target/Site, insertion-count semantics and DISCOURAGED access warnings.
The failed review (snapshot3b3dc192acce740b1791016af67cb49ec424aef078d34f8c0182830e50e2a9c0,
receipt64d2788423e32c5d186dce7a3ecc2edadedca95e5cba05565908f2685d6830da) preserves exact
corrective instructions: scoped evidence absence, between-variant scaffold factor versus
within-variant CDR sampling, INCONCLUSIVE micro, alternative explanations and controls. No
Gate3 approval/generation. Standard Case4 remains accepted and gets no rerun.

The existing validation-only REVISE runner now accepts either standard or expert-native Design.
It independently verifies an accepted pending standard card/review before inheriting Case4,
then binds the exact failed native review to its original thread. Native REVISE does not reimport
or rewrite the scientist input. Current Target/Site/card/Judge/snapshot and hashes must still
match. Read-only actual-state verification passed for both standard PASS and native FAIL
(`design-revision-verify163.json`); neither card had a response and no state was changed.
Targeted163:4 PASS in94.09s (both standard/native exact review binding, Site approval recovery,
and native byte-preserving import/Judge/Gate/shared approval). Ruff163 PASS. This is a
validation script extension, not a new Agent/Gate/checkpoint engine. Agent/Skills stay unchanged
while native163 applies the trusted correction; local GPCR navigation repair remains unsynced.


### Native Design accepted after exact REVISE (live163)

Live163 (`phase2-goldens-20260912T002508961160Z`) retained Cases1/3/4 and independently
passed native Case5. New card58b3f3cc7087ebb2da5cca803c2022b417f1603e0305ae6160f004003bfafbee
has failed card20af29724c0b0e5576e85af61cfabb7ce2ecb842c7a407b37e8e1fdfec611ea4 as parent;
fresh Judge judge-08e080a22b1f43b1b9a2e63919be91c8. Review snapshot
367d2ccdcb2a256b200eb15b7756eea8edc091ac1995137b101046f19c5630d0; receipt SHA
3d64c4a73b044685781e9efc790498297d777e1e6f439c6ae744c098a8f553a0.

Source-bound absence statements, between-variant scaffold versus within-variant CDR sampling,
insertion-count semantics, micro INCONCLUSIVE and competing explanations are now explicit.
Competitive kinetics is expressly a hypothesis test, not unique specificity proof. Original
hotspots/full context/all7native variants/40each/280planned and scientific warnings are retained.
Judge's broad final cannot-certify-approval caveat is recorded as an authority limitation, not
as invalidation of the verified Site approval; its own reason3 and the owner correctly retain
upstream Site OVERRIDE and pending Gate3, independently checked by the runtime and root review.
No Gate3 approval, generation, prediction or biological efficacy is claimed.

`native-revision-byte-audit.json` verifies all7 original YAML SHA values and expert comments,
identical native input refs before/after revision, and only1 native-strategy-input event.
The runner also matches all7 compiled design.yaml bytes to the original imports. Real backend
0.3.2 check passes7variants/7strategies/280planned; native strategy SHA
747535765efe59e1410fb271fa04eca33823222fba13ca5254976f990d964388. Thread totals:
Coordinator9/Binder6/Judge4; original9calls + revision10calls; peak56142chars. One overlong
Coordinator delegation was rejected and corrected through the existing bounded path. This is
real explicit Scientist steering, not unassisted first-attempt acceptance. Protected163 confirms
all385 baseline files unchanged. Case2 GPCR and full regression remain; Phase2 NOT FROZEN.

The local GPCR navigation draft was replayed read-only against actual source161 before sync:
`receptor-navigation163.json` and `receptor-projection-replay164.json`. Raw state+membrane+
topology request is425805chars; existing state+membrane+topology_summary is1485chars. Each of
7complete candidate projections is2732–3302chars, with all44 members and every candidate
non-residue field exactly retained, including limitations/counterevidence. These aliases already
existed but were not discoverable after archival. Staged scoped sibling/path navigation passes
exact source/member comparisons; original635111-byte analysis SHA unchanged. This replay is
DETERMINISTIC diagnostic evidence, not GPCR live acceptance. Next synchronize the narrow repair,
run targeted context tests and retry GPCR from its accepted Target104.


### Receptor projection navigation repair validated (164)

Expose existing candidate_overview/topology_summary as separately declared projection_aliases,
not fabricated stored source keys. Preserve this small navigation list in both working-view
archival passes and scoped tool responses. Sibling fields now resolve the same exact aliases
as nested paths. Oversized receptor requests explain the usable topology summary and individual
candidate path. Raw topology/residue arrays remain at their original verified paths; there is
no new ranking, mapping, geometry or scientific summary. Alias descriptions are added only to
receptor responses, avoiding unrelated-tool context inflation. Site Skill directs focused
recovery of an archived overview rather than rebuilding it by paging from residue zero.

Targeted164:23 PASS (6.94s), including exact oversized-read recovery, all candidate counterevidence,
unaltered source data, alias navigation retained after both archival passes, complete parallel
answers and prior context/source tests. Related164b:15 PASS (4.48s), including real harness
argument recovery, legacy selector semantics, lossless pagination, process/resume accounting
and foreign/tampered evidence rejection. Ruff164 PASS; mypy164 PASS2source modules. All385
protected baseline files remain unchanged. No live process was running during source sync.
Next live164 starts a new GPCR Site execution from accepted Target104, preserving all previous
failed evidence and avoiding Target preparation. Existing32calls/60000chars are unchanged.
Cases1/3/4/5 stay accepted; GPCR scientific acceptance and Phase2 full regression remain due.


### Parallel prerequisite errors need one model correction opportunity (live164)

Live164 (`phase2-goldens-20260912T003308980376Z`) failed after Coordinator3/Site5calls,
before the repaired navigation could be used in reasoning. In one native tool batch the Site
requested four not-yet-selected sources; all4 diagnostics exhausted the old four-error allowance.
It then explicitly selected/acquired all4 correctly, but later requested UniProt for two newly
unselected evidence needs. The fifth diagnostic aborted the batch before a new correction
opportunity. No Gate2/SiteIntent or GPCR acceptance. Complete sources/receptor analysis and all
failed checkpoints remain; prior Cases1/3/4/5 are unchanged.

The Agent ledger now budgets four **model correction rounds**, shared across roles/categories.
Each current native AI message/tool-call batch has an ID derived from its runtime message and
call IDs (not a model tool argument). All recoverable errors in that batch reuse its attempt,
while each diagnostic still has its existing append-only event. Explicit source/need selection
is still required, and no rejected tool executes implicitly. A new model message consumes a
new round; replay of the exact batch preserves its round across process restart. Legacy events
without a batch ID each count once. Stale execution, role/source/artifact authority and the
32model-call/60000context guards are unchanged. No table/schema or scheduler is introduced.

`repair-round-replay165.json` applies the proposed identity calculation read-only to actual164
native messages: its first four-source batch uses one correction round; the later new-need
batch is a second. This is metadata replay, not live scientific acceptance. Public ToolCallRequest
regression verifies five distinct missing-source diagnostics are delivered in one round with
zero HTTP requests and zero implicit selections, plus a real new message spending another.
Ledger tests cover shared categories, roles, old events, restart, replay, exhaustion and follow-up.

Targeted165 initially24PASS/1FAIL exposed an old domain-boundary test whose malformed research
arguments were intercepted before its intended HTTP guard. The test now supplies valid research
arguments so it actually reaches and verifies the disallowed-domain rejection; production
permissions were not relaxed. A mypy local-variable union was also corrected. Targeted165b:
25 PASS in11.90s, including actual harness recovery and foreign/tampered reference rejection.
Ruff165b PASS; mypy165b PASS2source modules. Next fresh live165 reuses approved GPCRTarget104
with these bounded recovery semantics; previous scientific calculations/evidence stay intact.


### Oversized first-delivery batch admission (live165 / repair166)

Live165 (`phase2-goldens-20260912T005949431856Z`) failed after Coordinator3/Site3 calls,
before SiteIntent or Gate2. Four explicitly selected sources were acquired. Its next batch
combined complete receptor analysis26231chars, three successful passage pages4901/5223/3921,
a1579-character Skill reference and a643-character missing-selection diagnostic. These42498
new characters plus the required working context exceeded60000 before another model call.
All new answers were correctly pinned; dropping them before first delivery would be data loss.
The new correction-round semantics worked (the missing source/need used attempt1), but did not
address aggregate output size. No scientific acceptance; all original checkpoints are retained.
An incidental Nb35 premise in a retrieval question was not accepted as a source fact; future
GPCR review must verify the actual nanobody identity/interface against primary evidence.

Site middleware now admits native tool batches before any scientific handler: complete receptor
analysis reserves32000 output characters, Skill reads12000 and bounded result pages6000 each.
A multi-call batch above32000 gets explicit TOOL_BATCH_TOO_LARGE diagnostics requesting split
reads, with receptor analysis alone. The whole batch is rejected; no evidence is selected for
the model, no queued work or automatic tool retry is created, and no answer is silently dropped.
All diagnostics share the existing four-round repair ledger. The final60000input and32call
guards remain unchanged. Role/file/scoped-reference checks still reject authority violations.
This is interface admission, not a scientific calculation, mapping, ranking or scheduling change.

Targeted166:14 PASS in8.90s, covering public native ToolCallRequest parallel rejection with zero
handler calls, exact response delivery after splitting, one correction round, role/file/foreign
reference refusal, prior complete-batch archival behavior and source-selection recovery.
Ruff166 PASS; mypy166 PASS2source modules. Case1/3/4/5 acceptance remains valid. GPCR and final
full regression remain required before Phase2 freeze. Fresh live166 reuses approved Target104.

Launch165 source/Skills were committed atc8dbe8f4; its new test_repair_rounds.py was initially
untracked and omitted by git diff --name-only, then immediately committed65d14d82 without source
changes. `launch-code-provenance165.json` records the exact supplement; the original launch
receipt is preserved. Future launcher receipts explicitly record untracked files as well.


### Exact receptor display references and short-page admission (166/167)

Live166 (`phase2-goldens-20260912T010829793245Z`) corrected batch and source-selection
diagnostics and acquired all four required sources, but failed after Coordinator2/Site8 calls.
Its receptor analysis was correctly executed alone. The working view still reached62694chars
(after68453 before final archival), so its first model delivery was refused. No SiteIntent/Gate2.
The short membrane reference plus four acquisition requests had been conservatively rejected
as36000chars; actual known Skill size can safely avoid that unnecessary correction/extra history.
All source/checkpoint evidence is retained; no scientific or oracle acceptance is inferred.
Related scripted Site harness166:10 PASS in127.09s; one separate opt-in live API test SKIPPED.
The actual GPCR golden is separately FAILED, not replaced by that skipped test.

Admission now computes each allowlisted Site Skill's full text size plus line-number/wrapper
margin; foreign paths are never opened for estimation. Receptor analysis still reserves32000,
other tools6000 each, final model input60000 and shared32calls unchanged. A short reference plus
four receipts is admitted; analysis plus another read is still rejected before scientific work.

The receptor display now replaces only exactly repeated values with explicit local JSON pointers
(value_same_as) to full values in the SAME complete tool view. All unique source values remain
present. This affects the full displayed overview only: raw analysis, scoped candidate aliases,
all non-residue fields, seven candidates/44members, numbering and kernel outputs are unchanged.
A reserved-field collision keeps the ordinary unencoded representation. There is no new summary,
scientific priority, candidate filter or cross-artifact pointer. Existing source refs/ownership and
archival remain authoritative. The source view can be expanded mechanically and compared exactly.

`receptor-display-replay167.json` replays the actual failed166 checkpoint read-only: its original
62694-character terminal working view becomes59501 with the unchanged60000limit and complete
newest analysis retained. Every value expands exactly; all7candidates/44members match; original
635111-byte analysis SHAa8a94c7d44d5f5e8b77e88db7b86c0e91c5247b63c00fef1a119133d5f942975 is
unchanged. Display24972→20364chars. This is DETERMINISTIC REPLAY, not live acceptance. Historical
Skill wording is retained in that checkpoint; the fresh Skill adds a small explanatory delta.

Targeted167 initially31PASS/1FAIL exposed a new test calling result_tool with a nonexistent third
argument, corrected to its actual two-argument API. Mypy initially found the native ToolCall vs
plain-dict annotation; fixed using the public ToolCall type. Targeted167b32PASS in7.76s includes
whole latest-batch delivery, exact display expansion, unchanged source/scoped reads, reserved-field
collision, source/projection recovery and admission boundaries. A final wording clarification
uses in-the-same-view (JSON serialization can reorder keys); targeted167c7PASS in2.01s.
Ruff167b PASS; mypy167b PASS2source modules. Protected167:all385baseline files unchanged.
Next fresh live167 from approved GPCRTarget104. Cases1/3/4/5 stay accepted; Phase2 not frozen.


### Late completed-history value references (live167 /168)

Live167 (`phase2-goldens-20260912T012118550748Z`) delivered the complete receptor analysis into
real subsequent model calls (58664chars), and actually used the new state/membrane/topology
aliases. It later repeated scalar matching_chunks reads, incorrectly indexed that count once,
and reread residue-region/topology views. The fourth shared repair round handled that scalar
argument error. It finally requested real individual inhibit/activate candidate_overview entries,
but their first delivery failed at60158chars after ordinary archival (71289before); Coordinator3/
Site16calls. No SiteIntent/Gate2. This is a later context failure, not a scientific rejection.
The successful first-analysis and alias behaviors do not constitute GPCR case acceptance.

Only if Site's reasoning working history remains oversized after existing whole-view archival,
the same exact-value reference encoder now shares repeated historical values inside that one
history message. history_value_same_as points to the exact value at a local JSON pointer;
history_encoding explicitly states the scope and complete-value semantics. All unique action
arguments, answers, errors, limits, source qualifications and nulls stay in the same message.
Original user turns and checkpoints are unchanged. Existing receptor display encodings remain
untouched within their own tool view; reserved-field collisions retain unencoded data. There
is no model-generated summary, new artifact/checkpoint/store, auto-retry, scientific selection
or scheduling. Native/non-reasoning input behavior remains unchanged. Telemetry records when
this last-resort exact history encoding is used; the60000hard guard still applies afterward.

`history-reference-replay168.json` replays the actual60-message failed167 checkpoint with the
original and repaired fitters:60158→56080chars at the same3602system chars. Every working-history
value expands exactly; all3latest answers match their originals after the already-existing field
index interning is expanded. Human turns, scientific archival choices and original checkpoint
messages are unchanged. This is DETERMINISTIC REPLAY, not real model acceptance.

Targeted168:28 PASS in7.15s, including large repeated diagnostics with full scientific payload
round-trip, original user/checkpoint preservation, incomplete native transactions, existing
receptor encoding isolation, whole latest-batch delivery, scoped aliases and source boundaries.
Ruff168 PASS; mypy168 PASS2source modules. Fresh live168 again reuses approved GPCRTarget104.
Cases1/3/4/5 stay accepted; Case2 and final full regression remain due. Phase2 NOT FROZEN.


### Related Site harness verification (168)

The related scripted Site harness completed:10 PASS in123.05s (`site-harness168.log`).
This is deterministic/scripted harness coverage, not GPCR scientific acceptance. Live168
remains in progress from the unchanged Agent sourcea103ed00. It has acquired the primary
abstract and official records; the attempted PMC3058308 full text returned404 and remains an
explicit access limitation. Repeated scoped reads and the initially rejected GPCRdb acquisition
are still under observation. No SiteIntent/Gate2 acceptance is inferred from partial progress.

A stale developer-side SSH multiplex connection delayed inspection; a separate direct SSH
connection succeeded, and the local read-only helper now uses direct SSH. No server Agent,
scientific job, data, checkpoint or remote runtime was restarted or changed for this transport
repair. Source/Skill fingerprints remain unchanged during live168.


### Repeated scalar reads and explicit Site reasoning experiment (168/169)

Live168 (`phase2-goldens-20260912T014139653529Z`) FAILED after Coordinator3/Site19calls.
Its last three scoped answers were retained, but92601chars only reduced to67477 after ordinary
archival and exact history references. The unchanged60000guard correctly refused the next
model request. No SiteIntent/Gate2 and no GPCR scientific acceptance. The native model repeatedly
requested matching_chunks (integer values1/8/27) with different limits and repeatedly reread
candidate_patches/mapping snapshots. GPCRdb was initially in a rejected batch; a later retry
without selection_reason received SOURCE_NOT_SELECTED, but the model did not complete that
prerequisite or receptor analysis. A false Gs-heterotrimer premise in source questions is not
accepted as a verified3P0G fact. All failed sources, tool outputs and checkpoints remain.

The Site Skill now explicitly distinguishes the matching_chunks count from cards/next_cursor
and tells the owner not to reread an unchanged stored value. The next experiment uses the same
DeepSeekV4Pro native thinking adapter with Site effort **high**, replacing **low**; Coordinator
and other roles are unchanged. This is an explicit recorded engineering choice, not a hidden
provider/model fallback. Model output16384, input60000 and shared32calls remain unchanged.
`model-config169.json` preserves exact old/new configurations and hashes; new configuration SHA
cbcb92de6e402e9ecb7b184570eeee0bc39924aa5452b723e65cf5d083e04294. Existing per-case accepted
reports retain their own exact model configuration. They are not relabeled as high-effort runs.

Targeted169:35 PASS in6.74s. The actual SDK-payload regression now covers both low/high effort,
including the SiteIntent-only finalization tool set and explicit output_config effort, without
network calls. Existing history/source/argument contracts remain covered. Two expected native
thinking/forced-tool warnings are retained; runtime uses the supported auto-tool request.
Ruff169 PASS. Protected169:all385baseline files unchanged. Fresh live169 reuses approved
GPCRTarget104; no Target preparation or scientific kernel work is repeated. Phase2 NOT FROZEN.
