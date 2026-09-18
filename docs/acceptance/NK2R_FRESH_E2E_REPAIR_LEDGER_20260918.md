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
- Next accepted run: a new Attempt 002 project and thread, restarted from Gate 1 after commit.

## Issue template

For each issue record: attempt; Gate/stage; trigger; expected and observed behavior; before-state artifact paths and hashes; root cause; generic fix; changed files; fix commit; targeted/full tests; after state; manual project-state changes; attempt invalidation; restart project/thread.
