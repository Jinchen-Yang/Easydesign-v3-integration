# NK2R fresh end-to-end acceptance and repair ledger

## Acceptance objective

Run a new human-NK2R extracellular inhibitory VHH case from Gate 1 through Gate 5 using a fresh EasyDesign project and model thread. Previous NK2R project state, dossiers, ranked sites, residues, YAML, candidates and decisions are excluded from the scientific Agent context. Product-native retries are allowed and recorded. Any developer code, contract or state repair invalidates that attempt; the final accepted attempt must restart from Gate 1 on the repaired frozen commit.

## Fixed interpretation

- Expected Scientist Gate approvals and choices are part of the product contract and are not developer intervention.
- No prior NK2R project artifacts may be imported or read by the scientific Agent.
- Fixes must be generic; no P21452, 9W2H, prior site residue or prior ranking special cases may be added.
- A fresh RCSB 9W2H mmCIF is supplied as the local structure input because the current public Agent entry point requires `--target`. Target identity, chain, state, sites and strategies remain for the new Agent to determine.
- Pilot uses native BoltzGen design, inverse folding, Boltz2 refold and native analysis. AFO is optional and is not requested for the acceptance path.
- Gate 4 production intent and any bounded validation execution projection remain distinct.
- Standing Scientist preference after an independently generated Gate 2 portfolio: choose a
  hard-valid deeper `outer-pore` candidate for downstream design when one is offered. Do not
  reveal Attempt 001 residue membership or rank labels to a later scientific Agent, and do not
  reinterpret a verified intracellular/inner-pore candidate as this preferred option.

## Run identity

- Host: `suzhou2` (`ailuoyun-GPUBMS`)
- Repository: `/data/easydesign-worktrees/Final-backends`
- Baseline branch: `codex/easydesign-final-backends`
- Acceptance branch: `codex/nk2r-fresh-e2e-20260918`
- Baseline commit: `0298f53bba3e620c28d50cf48cccaca9ba2d63d9`
- Model provider/profile: `deepseek / deepseek-v4-pro`; secret values are excluded
- Fresh target retrieval: `https://files.rcsb.org/download/9W2H.cif`
- Target SHA-256: `33ff56e619b30fbb1edeba2d58726aaf78006ad1b2480416b97bb4892e488e51`
- Fresh project prefix: `nk2r-fresh-e2e-20260918-aNN`

## Blind-isolation controls

- New project and thread IDs for every attempt.
- Empty Final-backends workspace before Attempt 001.
- No import from `nk2r-inhibition-20260914-01`, `phase34-nk2r-micro-20260915-01`, `phase34-nk2r-ranking-20260917-01`, or exported NK2R cases.
- No prior candidate residues, rank order, SiteDecision, DesignIntent or candidate pool in prompts.
- New clone-local scientific HTTP cache; authoritative remote sources may be fetched again.
- Codex may operate infrastructure and repair generic code, but may not supply remembered scientific answers to the EasyDesign Agent.

## Setup findings

### SETUP-001 — pure-backend copy lacked an executable scientific runtime profile

- Detected before Attempt 001: yes
- Expected: `Final-backends` can load its clone-local runtime profile and validate BoltzGen configuration before starting a scientific case.
- Before state: `/data/easydesign-worktrees/Final-backends/runtime/profile.yaml` was absent; loading the runtime profile raised `ConfigurationError`.
- Root cause: the earlier pure-backend separation copied the frozen source and Agent Python environment but intentionally did not copy the large scientific backend runtime registration.
- Repair: created a clone-local runtime snapshot containing the installed BoltzGen and OpenFold environment/model files plus OpenFold component receipt. Paths and `runs_root` were rebound to `Final-backends`; no old project, run or scientific evidence was copied.
- Storage method: hard-linked immutable environment/model bytes on the same filesystem; new clone-local profile and state paths satisfy the runtime escape guard.
- Runtime profile SHA-256: `058570518e4febcb7e682399c9292838ac5ee3d7c28793a3b0d38737e116c4a2`
- After state: profile loads as `final-backends-nk2r-e2e`; available backends are `boltzgen`, `boltzgen_validation`, and `openfold3_af3_jax`; runs root is clone-local.
- Attempt invalidated: no, because no scientific attempt had started.

## Attempts

### Attempt 001

- Project: `nk2r-fresh-e2e-20260918-a01`
- Thread: `thread-1329d1a617f5413aa80540cc4f5ec630`
- Start commit: `f37ffef2aad04305849811e0e2316edfa1196a32`
- Status: invalidated at Gate 2; retained as read-only defect evidence
- Gate 1: independently resolved human NK2R UniProt `P21452`, receptor author chain `R`
  (label chain `B`) and an engineered 406-residue construct versus 398-residue canonical
  sequence. The Scientist approved chain `R`.
- Gate 2 research: completed new remote UniProt, RCSB, GPCRdb and literature acquisition. The
  GPCRdb lookup repaired its own first identifier choice from `TACR2_HUMAN` to `NK2R_HUMAN`
  through the bounded product prerequisite path. No prior NK2R dossier was supplied.
- Gate 2 dossier SHA-256: `bed97b7596743794b0a769e7e20a5417b2d7136a6eb0b95bc5248232eb387e7a`
- Gate 2 card snapshot SHA-256: `6908b04df9b9427a517aca886f8baed5cc0387b88d66f6f68428976b7a47c46d`
- Site portfolio before repair: A outer-vestibule ECL2/ECL3, B deeper outer-pore TM2/TM6/TM7,
  and C inner-pore/intracellular TM2/TM3/TM7. The model's own C explanation called it
  inaccessible to an extracellular VHH, but Runtime incorrectly left it selectable.
- Scientist steering after observing the independent portfolio: prefer the hard-valid deeper
  outer-pore strategy for subsequent Gate 3 work. This is a human Gate choice, not an input to a
  fresh Agent's site discovery or ranking.
- Developer repairs after start: `NK2R-E2E-001` and `NK2R-E2E-002` below.
- Final autonomy eligibility: no. Any code repair after the attempt starts invalidates it.

### Attempt 002

- Project: `nk2r-fresh-e2e-20260918-a02`
- Thread: `thread-030272aab5fe4e138435489b6386eecd`
- Start commit: `0e8d603bdd26a120623efe31e8584ed1c15de505`
- Status: invalidated at Gate 2; retained as read-only defect evidence
- Gate 1: independently resolved human NK2R UniProt `P21452`, receptor author chain `R`
  (label chain `B`) after 23 target model calls. One product-native typed-contract repair was
  used. The independent Judge returned `SUPPORTED` on its first review.
- Gate 1 card: `b392026e7da080014d2a280dd0fc2f0fa82f4e90cf68a6f1ac5fbc4d6000e23d`;
  the Scientist approved chain `R`.
- Operator event: the first approval command mistakenly supplied `--candidate chain-r`.
  Runtime rejected it atomically with `Candidate selection requires a ranked Site card and
  APPROVE`; no state changed. The same displayed card was then approved without `--candidate`.
  This was an operator CLI error, not a scientific-Agent repair.
- Target preparation: job `job-572f212e78ae496d`, run `20260918t053203z`, succeeded.
- Gate 2 research: executed about 45 Site model calls and independently acquired and read remote
  UniProt, RCSB, GPCRdb and literature evidence. No prior dossier, site proposal, rank or residue
  answer was supplied.
- Terminal defect: four widely separated native tool correction rounds at event sequences 214,
  277, 438/442/444 and 457 consumed the execution-global limit. Resume then failed before Site
  dossier submission with `INVALID_FIELD_PROJECTION: tool argument repair budget exhausted
  (4 shared correction rounds per execution)`.
- Evidence separation: the four rounds involved two different tool operations and were separated
  by many successful calls; parallel errors at 438/442/444 correctly shared one native batch.
- Start log SHA-256:
  `b6be2ff6166eb5b6f4a34d35ab5b4bbd968903461f64300ef08c08b732c17f9a`.
- Gate 2 log SHA-256:
  `bd70791d0c669c3a8f1988ebb7b390dfe39f0a8003e8e6f61eee3ecc7a40641c`.
- Resume log SHA-256:
  `6236d86cbb5e769d5f8cad541f8dd2240f76829a74f2c3b206855f587938302b`.
- Developer repair after start: `NK2R-E2E-003` below.
- Final autonomy eligibility: no. The generic recovery-budget code repair requires a new
  Gate-1-to-Gate-5 attempt.

### Attempt 003

- Project: `nk2r-fresh-e2e-20260918-a03`
- Thread: `thread-7d8fb0ed52a04e57948844ccda17eca8`
- Start commit: `08d4883561bc7af095206145770d0a96d448d07e`
- Status: invalidated at Gate 1; retained as read-only routing-defect evidence
- Target owner: independently verified UniProt `P21452` and the deposited receptor entity, but
  conflated label chain B with auth chain B. It recommended `chain-b` even though option IDs use
  the auth namespace and the receptor is auth chain R / label chain B.
- Independent Judge: correctly rejected the owner interpretation, identified auth chain B as
  Gβ1, and recommended the existing eligible `chain-r` option for auth chain R. This is a
  successful scientific safety catch, not the defect.
- Deadlocked state: the negative assessment created no decision card (`cards = 0`) and no
  owner-revision action. Runtime nevertheless reported `awaiting-human-approval`. A normal
  `--message` containing the Scientist's already authorized chain-R correction was persisted but
  merely returned the same terminal state, so neither APPROVE nor REVISE was possible.
- Read-only post-fix replay on the frozen Attempt 003 database resolves the next action to
  `target-judge-revision` for `target-intelligence` and carries the bound review finding and
  runtime-eligible `chain-r` alternative.
- Start log SHA-256:
  `aa9d8ae685ebfc82332051209e8e889ff0d0b5bf927ec5f6f6367a054836332d`.
- Technical status SHA-256:
  `30eb832b32cbb308db139aa98cd11c70530a7837c600b91e4f82517c3a724567`.
- Follow-up log SHA-256:
  `a619fec5025afcccb8f40ff280195dd5bdfd366262bc6ba85bbd180835d18079`.
- Developer repair after start: `NK2R-E2E-004` below.
- Final autonomy eligibility: no. The routing repair requires a new Gate-1-to-Gate-5 attempt.


### Attempt 004

- Project: `nk2r-fresh-e2e-20260918-a04`
- Thread: `thread-ca24e4c59e6847fa8ef5186789539dfa`
- Start commit: `32f404155652ae15e8d45af00e465ee58b1a76ae`
- Status: invalidated at Gate 2; retained as read-only acquisition-boundary evidence
- Gate 1: independently resolved the correct receptor author chain `R`; the first independent
  Judge review returned `SUPPORTED`. Scientist approval created card
  `48b33c68466bb924ce2fd0f040c3af838d341f836a5ed8bc258262cf151dca4c`.
- Target preparation: run `20260918t074803z`, job `job-4340138b82814cec`, succeeded.
- Gate 2 research: progressed through approximately 34 Site model calls and all 12 allowed remote
  research reservations, including independent source selection and focused source reads. No old
  NK2R dossier, candidate membership or rank was supplied. The Site had not yet submitted its
  typed research handoff.
- Terminal defect: the model's final native batch first completed a valid `retrieve_evidence`
  read and then requested a thirteenth `research_evidence` acquisition. Runtime rejected the
  acquisition with `This execution used its 12 bounded research queries` and terminated the
  entire execution, discarding the opportunity to synthesize the evidence already collected.
- Operational interruptions: two external interactive SSH frontends disconnected, and one
  provider call stalled before the abandoned frontend process was cleanly terminated. Durable
  checkpoint recovery preserved the same execution and did not mutate scientific state. These
  events exposed neither the defect nor its repair; the deterministic query-ceiling exception did.
- Start log SHA-256:
  `a9253f22b4b5c9a655cac096c3837aea6319322f8f2136f5198d5a20fa36d28f`.
- Gate 1 approval log SHA-256:
  `da7d13df479e6fd97ec4bae9d9b721fa68aab3cf4b8b1d330234888ae9b30d11`.
- Gate 2 initial/resume log SHA-256 values:
  `5a3d581e47b1a2ee8340fe9e2bec9ad0f7ca783dbcc1c0ed609d3b0794131825`,
  `516086f53049918821d73f891ac69d406722615a30030c5dd8f5fad0189af3cf`,
  `35ddb36bc8b8441138696e012a359c4e0144b5946fbaa1c230bb6fd195447f67`,
  `fba51fe543a02b65f3603bb66e7d146acda8cb62727ddede4787aaf00217cf2e`,
  and `338acd1f0c6a83c9361e3510a50fcac84ecee19227b2abb4ccf942f7ac148311`.
- Developer repair after start: `NK2R-E2E-005` below.
- Final autonomy eligibility: no. The acquisition-boundary control-flow repair requires a new
  Gate-1-to-Gate-5 attempt.


## Repairs

### NK2R-E2E-001 — Site Judge recovery repeated the full evidence packet

- Attempt / stage: Attempt 001, Gate 2 independent review.
- Trigger: the first two Judge calls exhausted the 8192-token output allowance without a typed
  verdict; the third call submitted typed arguments but failed the 300-character field contract.
- Expected: after truncation or a schema-invalid typed submission, retry with a compact decision
  view and, when present, repair the previous typed opinion.
- Before state: first model context was approximately 75,554 characters and both recovery calls
  were approximately 76,014 characters. The recovery schema was smaller, but the evidence input
  was not. Two calls ended at `max_tokens`; the final invalid submission exhausted the repair
  budget. The safe `independent review unavailable` fallback worked, but did not repair Judge.
- Root cause: dossier-backed Site review uses `site_judge.py`; its recovery branch changed only
  `RecoverySiteJudgeVerdict` and prompt wording, then called the same `review_input(packet)` as the
  first attempt. The separate legacy Harness compactor was not on this path.
- Generic fix: recovery now receives every candidate, exact memberships, verified locations,
  compact residue summaries, complete ranked interpretation, hard authority and downstream
  scope. Repeated passages, receptor metadata and full mapping namespaces are removed. A prior
  typed opinion and every fact it cited are carried into schema repair. Final validation still
  uses the immutable full packet, so compaction cannot hide a fact conflict.
- Real Attempt 001 read-only replay: full review input 69,143 characters; first recovery 29,290
  characters (57.6% reduction); schema repair with the saved prior submission 32,999 characters
  (52.3% reduction). All three candidate IDs remain present.
- Changed files: `src/easydesign/agent/site_judge.py`,
  `tests/unit/agent/test_site_judge.py`.
- Fix commit: `29a475924ce3ee19a005505ba444f7adb03a2c40`.
- Manual project-state changes: none.
- Attempt invalidated: yes.

### NK2R-E2E-002 — verified intracellular candidate remained selectable

- Attempt / stage: Attempt 001, Gate 2 ranked portfolio hydration.
- Trigger: candidate `site-f910847701957db7`, labels
  `[68,72,127,128,130,131,134,307]`, was rendered selectable even though the persisted dossier
  contained cytoplasmic canonical annotations and all signed kernel points were negative-axis
  `inner_pore` positions.
- Expected: the ranking-first contract keeps weak, buried and risky hard-valid candidates in
  A/B/C, while an explicit extracellular binder objective plus decisive verified intracellular
  location is a hard compartment conflict.
- Before state: early deterministic evaluation only consulted optional user-supplied
  `BiologyContext`, which was absent. Later remote UniProt/GPCRdb topology and signed membrane
  geometry were available in the Runtime-built dossier but were not connected to eligibility.
- Root cause: `compile_ranked_decision()` used only the early geometric evaluation and explicit
  avoid labels. It ignored the later Runtime-owned candidate `location` object.
- Generic fix: extract a compartment requirement only from explicit wording in the immutable
  user objective; combine that with verified canonical topology, GPCRdb segments and signed
  membrane geometry. A hard block requires concordant sidedness. TM membership, low exposure,
  point burial and uncertain whole-VHH access remain ranking penalties. Ambiguous evidence stays
  selectable.
- Real Attempt 001 read-only replay after repair: A remains selectable; B deeper `outer_pore`
  remains selectable; C is retained in the audit portfolio with no rank and
  `hard_block=verified-compartment-conflict`.
- Changed files: `src/easydesign/agent/site_dossier.py`,
  `src/easydesign/agent/site_decision.py`, `src/easydesign/agent/judge_packet.py`,
  `tests/unit/agent/test_site_portfolio.py`.
- Fix commit: `29a475924ce3ee19a005505ba444f7adb03a2c40`.
- Manual project-state changes: none.
- Attempt invalidated: yes.

### NK2R-E2E-003 — unrelated Site tool corrections exhausted one global budget

- Attempt / stage: Attempt 002, long-running Gate 2 Site research.
- Trigger: after four correctable model-tool batches over roughly 45 Site model calls, a later
  source-selection prerequisite could no longer return its deterministic correction payload.
- Expected: repeated consecutive failure of one tool operation remains bounded, while an earlier
  repaired and subsequently successful operation cannot consume the allowance of a later,
  independent research action.
- Before state: prerequisite repair, field-projection repair and parallel projection errors for
  different tools all shared `TOOL_REPAIR_LIMIT = 4` across the entire execution. Successful tool
  invocations did not close a repair streak. A long but progressing research turn therefore
  became less recoverable over time.
- Root cause: `_reserve_repair()` keyed native batches for parallel deduplication but counted every
  distinct batch in one execution-wide dictionary. The implementation had no role/tool scope and
  no durable success boundary.
- Generic fix: native Harness repairs are now isolated by role and tool operation. At most four
  consecutive model batches may fail for the same operation; all errors in one native batch share
  one attempt; a successful invocation durably closes that operation's streak; restart preserves
  both failures and success boundaries. Legacy unscoped API callers retain execution-wide
  accounting for compatibility. The independent model-call ceiling remains unchanged.
- Safety behavior: five consecutive failed batches for the same operation are still rejected;
  replaying an already delivered batch does not obtain another attempt; using a different tool
  cannot reset a failing tool's streak.
- Regression coverage: seven independent tool scopes can each receive their first correction;
  same-batch parallel errors share an attempt; the streak survives store reopen; success resets
  only its own scope; four post-reset failures are accepted and the fifth is rejected; an
  end-to-end `RoleBoundary` tool call verifies automatic success reset.
- Changed files: `src/easydesign/agent/session_store.py`,
  `src/easydesign/agent/harness.py`, `tests/unit/agent/test_repair_rounds.py`,
  `tests/unit/agent/test_tool_argument_recovery.py`.
- Targeted affected-module suite: 75 passed. Focused new/store/harness suite: 25 passed. Ruff and
  `git diff --check`: passed. A broader `tests/unit/agent` run progressed beyond 10% with no
  failure before it was stopped because unrelated slow Agent scenarios made it unsuitable as a
  pre-restart blocker.
- Fix commit: `38cbd14b8997491807544cff883807355b27191a`.
- Manual project-state changes: none.
- Attempt invalidated: yes.

### NK2R-E2E-004 — actionable Target Judge rejection had no owner-revision route

- Attempt / stage: Attempt 003, Gate 1 Target review.
- Trigger: Judge rejected the owner's wrong chain namespace and supplied a different,
  runtime-eligible option with `status=SUPPORTED`.
- Expected: the wrong owner proposal cannot reach a Scientist approval card; the actionable
  review must return to the Target owner for a fresh evidence-based interpretation, followed by a
  fresh independent review.
- Before state: `next_action()` only allowed Target `reject` assessments through when the Judge
  marked the same option `DISCOURAGED`. A supported alternative fell into
  `scientific-review-blocked`. The surrounding terminal API still described the scientific state
  as `awaiting-human-approval` even though no card existed, creating an unrecoverable interface
  state.
- Root cause: control flow tracked the current evidence binding and human revisions, but did not
  model an actionable owner revision arising from a bound independent review. It also searched
  Judge assessments only after the human-revision boundary, so a new owner submission could have
  reused an older review.
- Generic fix: for Target Gate only, a `reject` assessment with a `SUPPORTED` recommendation for
  an existing runtime-eligible option routes back to `target-intelligence`. The owner must reread
  evidence and submit a fresh `TargetInterpretation`. Judge selection is now bounded after the
  latest owner-assessment sequence, forcing fresh review. At most two Judge-directed owner
  revisions are allowed for one evidence request; a third conflict stops without a tool action.
- Authority boundaries: Judge does not directly select or approve the alternative; Runtime checks
  eligibility, Target remains proposal owner, a new Judge reviews the new proposal, and the
  Scientist still owns Gate 1 approval.
- Regression coverage: actionable supported alternative dispatches Target; old Judge opinion is
  not reused after a new owner result; three repeated conflicts end in
  `scientific-review-blocked`; existing control-flow suite 23 passed; adjacent Target, Judge,
  Scientist steering, terminal consistency and state ownership suite 30 passed; Ruff and
  `git diff --check` passed.
- Real-state read-only replay: Attempt 003 now selects `target-judge-revision` and names
  `chain-r` from the current bound assessment.
- Changed files: `src/easydesign/agent/control_flow.py`,
  `tests/unit/agent/test_control_flow.py`.
- Fix commit: `c746ba3545593845012eeb279c315fc23ec632ea`.
- Manual project-state changes: none.
- Attempt invalidated: yes.


### NK2R-E2E-005 — research acquisition ceiling terminated a completed evidence-gathering phase

- Attempt / stage: Attempt 004, Gate 2 Site research.
- Trigger: after 12 durable acquisitions and substantial focused reading, a thirteenth acquisition
  in the same native batch raised the generic execution boundary error.
- Expected: 12 remains a hard acquisition ceiling, but reaching it is a convergence boundary.
  Existing evidence and explicit unknowns must remain usable for the typed
  `SiteResearchHandoff`; no thirteenth remote request may run.
- Before state: `EvidenceResearch.acquire()` raised a generic `AgentBoundaryError`. Harness had
  no semantic distinction between a forbidden query and normal completion of the bounded
  acquisition phase, so the error escaped and killed the whole Gate 2 execution before dossier
  construction.
- Root cause: acquisition accounting and scientific finalization were disconnected. The worker
  correctly enforced a durable limit, but the model-call boundary continued advertising
  `research_evidence`, and the tool boundary could not convert an in-flight parallel overflow
  into a typed convergence diagnostic.
- Generic fix: the limit is now one shared constant. At the model boundary, a Site execution with
  12 reservations removes every action tool and enters submission-only
  `site-research-finalization`, explicitly requiring `SiteResearchHandoff` from delivered
  evidence with unknowns retained. A thirteenth request that crosses the limit inside an already
  emitted native batch performs no network access and returns
  `RESEARCH_QUERY_BUDGET_COMPLETE` with `submit_site_research_handoff`; it does not consume the
  tool-argument repair budget. Target research also loses the acquisition tool at the same
  ceiling while retaining its deterministic Target tools.
- Safety behavior: the limit was not increased; budget exhaustion is not negative scientific
  evidence; existing dossier, hard-fact, source-citation, Judge and Gate validation remain
  unchanged.
- Regression coverage: a thirteenth query cannot instantiate a network client and returns the
  finalization diagnostic; the next Site model call sees zero action tools and must submit a
  typed handoff; adjacent research, Site Harness, shared model-budget, native batch and contract
  suites passed `110` tests. Ruff and `git diff --check` passed.
- Changed files: `src/easydesign/agent/evidence_research.py`,
  `src/easydesign/agent/harness.py`,
  `tests/unit/agent/test_progress_and_pages.py`.
- Fix commit: `c2c4fc5e937a90d601f2943c796cb08335e76ba0`.
- Manual project-state changes: none.
- Attempt invalidated: yes.


## Validation after repairs

- Focused Site Judge, ranked portfolio, dossier and fact-integrity suite: 92 passed before the
  two backward-compatibility fixture corrections; all six identified failures plus all new
  tests were rerun, 9 passed. The six failures were limited to direct synthetic dossiers without
  a Harness thread goal and a scripted model expecting the original field names.
- Compatibility behavior: a historical/synthetic direct dossier without a thread goal gets no
  inferred compartment constraint; product runs continue to use their immutable goal. Compact
  recovery retains the established `candidate_facts` and `final_site_decision` field names.
- Ruff on all changed Python and test files: passed.
- `git diff --check`: passed.
- Final post-adjustment focused rerun: 3 passed; Ruff passed.
- Fix commit: `29a475924ce3ee19a005505ba444f7adb03a2c40`.
- Attempt 002 restarted from Gate 1 after the first repair commit and was invalidated at Gate 2
  by `NK2R-E2E-003`.
- Attempt 003 restarted from Gate 1 after the repair-budget commit and was invalidated at Gate 1
  by `NK2R-E2E-004`.
- Attempt 004 restarted from Gate 1 after the Target-review routing repair and was invalidated
  at Gate 2 by `NK2R-E2E-005`.
- The next accepted run is a new Attempt 005 project and thread, restarted from Gate 1 after
  commit `c2c4fc5e937a90d601f2943c796cb08335e76ba0`.

## Issue template

For each issue record: attempt; Gate/stage; trigger; expected and observed behavior; before-state artifact paths and hashes; root cause; generic fix; changed files; fix commit; targeted/full tests; after state; manual project-state changes; attempt invalidation; restart project/thread.
