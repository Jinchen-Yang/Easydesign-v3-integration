# Multi-user acceptance evidence

Date: 2026-09-27 · Branch: `codex/v3-multiuser-teams-20260927` (uncommitted
feature work) · QA evidence consolidated by the coordinator.

This document records what has actually been verified through the real
multi-user HTTP/native interfaces, with explicit labels for everything
synthetic. It is engineering acceptance evidence, NOT a real GPU science
acceptance run. No real model inference, no real scientific job, no production
deployment, and no human approvals outside test actors occurred.

## Verification commands

All runs used this clone's interpreter with fresh unique basetemp dirs:

```
.venv/bin/python -B -m pytest <files> --basetemp=runtime/tmp/<unique-name>
.venv/bin/python -B -m ruff check <owned test files>
```

| Scope | Command (files) | Result (latest) |
| --- | --- | --- |
| Final focused Python regression | All `tests/unit/product/`, native Product API, scoped/local worker, bootstrap and developer-workflow tests | **143 passed**, no xfail/XPASS; JUnit: `runtime/tmp/multiuser-focused-python-20260927T114500.xml` |
| Full Python regression | The same **1,594 collected cases**, distributed by file across 8 isolated pytest processes | **1,581 passed, 2 failed, 11 skipped**; both failures independently reproduced on unchanged base source (see below) |
| Full integration entry | `.venv/bin/python -B scripts/dev.py verify --mode integration` | Structure, vendored assets, compile and full Ruff passed; **9 baseline mypy errors in 6 files** still block the entry |
| Frontend type checks and unit tests | Easy / Professional | Both type checks pass; **69 + 54 unit tests pass** |
| Final account browser regression | Easy / Professional account Playwright configs | **9 + 3 passed** against route-stubbed synthetic APIs, with unique evidence directories and fresh CI dev servers |
| Actual account backend browser checks | Current account server and built Easy/Professional interfaces | Registration, review, collaboration, isolation, session eviction and admin observation passed; final creation controls and quota validation also passed live, with 0 page errors. See [browser evidence](MULTIUSER_BROWSER_ACCEPTANCE.md) |

### Full-suite evidence and baseline blockers

The initial serial `make test` run exceeded its 900-second command limit before
finishing. The coordinator then ran **every collected test**, grouped by file
across eight independent pytest processes with separate basetemp/cache/XML/log
paths. No assertion, marker or selection was weakened to obtain this result.

Complete collection, per-shard test lists, exit codes, JUnit XML and logs:
`runtime/tmp/multiuser-python-full-20260927T115837176369/`.
The counts sum to all 1,594 collected cases. Eleven existing optional/live
dependency tests were skipped; the two failures are:

1. `tests/unit/agent/test_control_flow.py::test_real_process_restart_after_applied_gate1`
   — the restarted process returns `incomplete-turn` without a card, leading to
   `KeyError: 'card'`.
2. `tests/unit/agent/test_site_harness.py::test_gate2_restart_does_not_duplicate_approval_or_target[after_site_approval]`
   — `AgentBoundaryError: Scientific state changed; stale card cannot be approved`.

Each failure was reproduced separately using an unchanged source snapshot from
base commit `31d779eb22ce1b941748190530ad2e2f896efefa`, inside a fresh clone-local
test directory. Baseline package selection was checked before running the same
unchanged regression. Evidence respectively:

- `runtime/tmp/multiuser-python-baseline-20260927T115837225943/`
- `runtime/tmp/multiuser-python-baseline-20260927T120747200607/`

The remaining mypy errors are in unchanged `agent/review_availability.py`,
`agent/phase2.py`, `agent/design.py`, `agent/harness.py`, `product/lab_order.py`
and `product/projection.py`. They and the two baseline recovery failures still
prevent an overall green integration gate. This record does not claim release
readiness or repair the parallel developer's scientific workflow by changing
its approvals or recovery semantics.

Final browser regression outputs after configuration/fixture-name cleanup:

- Easy: `runtime/tmp/frontend-easy-e2e-20260927T112750881136/`
- Professional: `runtime/tmp/frontend-workbench-e2e-20260927T112750400930/`

## Coverage matrix (what is actually proven)

### Identity, sessions, administration — REAL HTTP
`test_multiuser_integration.py`, `test_account_http.py`, `test_accounts.py`:
registration → admin approval → login; per-session CSRF; re-login and logout
revocation; password change invalidation; suspension; rate limits; append-only
audit without credential leakage; last-admin protections. Platform admin reads
all scopes (audited `admin.scope.read`) and every write/execute path is denied
(`read_only_scope`); ordinary users cannot reach admin APIs.

### Isolation — REAL HTTP + real subprocess
Personal project/request/event/upload/artifact isolation across users A/B;
two teams; cross-scope request-id and upload reuse rejected; on-disk namespace
(`workspace/projects/scopes/<scope>/…`) verified; a REAL subprocess running
production `WorkspaceContext` code resolves the scoped namespace and its write
policy refuses foreign scope paths (`PathPolicyError`). Landlock sandbox and
tamper cases: `test_scoped_workspace.py` (real subprocesses).

### Quotas, idempotency, concurrency — REAL HTTP
Quota raise via admin API; personal slots (jobs AND GPUs) span all scopes;
blocked second create → 409 `quota_exceeded`; release → next create accepted;
failed create (`input_missing`) rolls its admission back to `failed` and holds
no slot; request ids are namespaced per scope; conflicting payload reuse →
`idempotency_conflict`; six concurrent identical creates return one project
and dispatch once (SYNTHETIC launcher; see labels).

### Team drafts — REAL HTTP
Member/team-admin save/edit with revision conflicts (409 `stale_draft`),
concurrent same-revision saves resolve to exactly one winner, member cannot
start (`team_admin_required`), admin start → project, idempotent restart,
`draft_frozen` after start; conflicting-start adoption regression (findings
#1, fixed) and recovery; administration-only mode: `compute_available=false`
advertised, starts fail 503 `compute_unavailable` BEFORE any admission, drafts
remain usable.

### Native Gate flow through the account transport — REAL worker + synthetic providers
`test_multiuser_native_gate.py`:
- Stage-01 evidence is produced by the REAL detached local worker subprocess
  (Landlock-sandboxed, scoped write roots) inside the TEAM namespace
  (findings #3 fixed and verified here).
- The pending Site decision card is SYNTHETIC fixture evidence
  (`setup_portfolio`/`review_card`, scripted models `NoInference` — labeled
  test doubles; the agent advance uses scripted provider doubles only).
- Human approval is performed by TEST ACTORS over the real scoped HTTP API:
  ordinary member `bob` → 403 `team_admin_required`; team admin `alice` →
  202, idempotent replay, native response applied via the same in-process
  path a scoped worker runs, native `approved_site` hotspots match the chosen
  option, decision clears, `selected_rank` visible in scientific context.
- A mocked launcher records compute dispatch (`admission`, `scope`) — clearly
  labeled; no real GPU job is started from these tests.
- Real detached-worker control-plane lifecycle (spawn/assignment/revocation/
  crash/recovery with honest scientific failure) is covered by the backend
  worker's reserved `test_worker_execution.py` — not duplicated here.

### Link rewriting — unit
Scoped responses rewrite every declared link field (`url`, `details_url`);
non-link strings untouched (findings #2 regression).

## Fixed multi-user findings

1. Draft-start conflict froze drafts via unrelated journal row — FIXED
   upstream, regressions pass with markers removed.
2. `decision.details_url` fell back to unscoped endpoints — FIXED upstream
   (`SCOPED_LINK_KEYS`), regression added.
3. No native stage execution inside an ExecutionScope (local-worker write-root
   mismatch) — FIXED by the boundary worker with EXACT trusted-root
   validation (`local_worker` compares against `WorkspaceContext.write_roots()`
   with tuple equality retained; arbitrary supersets are NOT accepted — 4
    real-subprocess regressions in `tests/unit/test_scoped_local_worker.py`). Verified by the
   real-worker Gate test above.
4. Concurrent identical creates can 500 on `PRAGMA journal_mode=WAL`
   (`SessionStore.__init__` race) — FIXED in `ProductService` via bounded
   WAL-bootstrap retry (`_open_session_store`) and idempotent thread seeding
   (`_seed_thread`). QA removed both non-strict xfail markers and re-ran the
   two parametrizations unmarked: 2 passed with assertions unchanged
    (backend independently measured 10/10 repeated passes).
5. Partial/error chat streams were released as successful — FIXED: only a
   flushed `done` event marks success; failures remain recorded and retryable,
   with no second HTTP response after NDJSON headers.
6. Renaming an identical upload overcharged storage — FIXED: quota identity now
   matches the canonical format/content identity; rejection before storage
   incurs no charge. Bytes actually stored but invalid remain retained and charged.
7. Admin management reads and suspended-team access — FIXED: management reads
   are audited; ordinary members cannot read or mutate suspended teams, while
   platform-admin inspection and unsuspend remain available.
8. Professional creation controls, quota validation and legacy token entry —
   FIXED and browser-tested; forbidden creation controls are disabled with a
   reason, invalid quotas cannot be submitted, and account mode never authenticates
   a shared workspace token.

## Browser acceptance (cross-reference)

Real backend-connected browser observations by the coordinator are documented
in [`MULTIUSER_BROWSER_ACCEPTANCE.md`](MULTIUSER_BROWSER_ACCEPTANCE.md): a
real `MultiUserServer`/`AccountStore` behind current-tree Vite builds,
exercising registration/approval, team invitation and draft collaboration,
member execution boundaries (403 `team_admin_required`), personal-scope
isolation (404), cross-tab logout, and audited read-only platform-admin
observation — asserted via DOM accessibility state and HTTP status codes.
That is LIVE account HTTP/browser coverage. It is distinct from (a) the
frontend worker's route-stubbed UI tests (no live backend), and (b) real
science: no real scientific jobs, model providers, or Gate approvals were run
there (administration-only fixture, no compute launcher). Account browser
coverage does not establish candidate-result rendering, a complete five-Gate
scientific run, or real provider/GPU execution. The narrower engineering
unit/subprocess coverage above remains explicitly labeled.

## Remaining gaps / honest limits

- The final integration entry remains blocked by 9 existing typing errors;
  the completed full Python regression contains the two independently verified
  baseline recovery failures listed above.
- The Gate approval in `test_multiuser_native_gate.py` applies native
  responses in-process (worker simulation). A Gate round-trip through the
  DETACHED scoped worker with synthetic providers is NOT COVERED by the
  current tests (`scoped_worker` builds real provider clients; no scripted
  seam exists). No new seam is requested this turn.
- Browser acceptance and the final Professional/quota follow-up are complete
  within the documented synthetic-account scope (see cross-reference).
- Real multi-user GPU science acceptance: NOT performed (out of scope and
  unauthorized for QA).
