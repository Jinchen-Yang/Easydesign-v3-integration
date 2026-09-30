# Suzhou full-flow migration

## Scope and comparison

User-authorized comparison, migration and production release of the Suzhou 2
development line `/data/Easydesign-final`, branch
`codex/product-fullflow-20260927`, through
`edea84be2c1f815d76f8edc72af91a2a3beef399`.

The comparison baseline is our `44221f915b28666fd58490777da2b68500f5cd74`;
the shared ancestor is `592e1e5646dd6e8d512fe0706230f0d2d4144fb3`.
There were 56 upstream-only commits, including one merge. Equivalent fixes
already present in our multi-user line were retained rather than reimplemented.

| Upstream changes | Result in the integrated release |
| --- | --- |
| Typed target identity, project-local run lookup, bounded phase continuation, Site citation recovery | Preserve our equivalent implementations, scope confinement and role-specific budgets; retain upstream regressions |
| Sequence-backed Target gate and mandatory GPCR pocket ranking | Guard coordinate-only operations by loaded input type; deterministically rank the already verified, eligible required pocket, without inventing evidence or removing hard blocks |
| `eb3471d`, `c548557`, `57b95e4` candidate loading | Explicit Pilot/Scale/final lists, compact summaries, separate selected details, deduplicated reads; additional race guard prevents late Pilot results replacing Scale |
| `ddc165a`, `569f65f`, `57a9e00`, `6a973cf`, `7349a1d` | Invalidate approval caches after durable receipt; show pending transition, lightweight live job refresh and truthful active Scale progress |
| `9f1cedc`, `60fafcf`, `0b64561`, `015e6fa` | Every scaffold's frozen YAML, Gate 3 plan size, clearer Gate 4/5 choices, scoped artifact reads |
| `01dfa64`, `c721eb3`, `3ea2654`, `de24d14` | Synchronized Site choice/structure preview, validated per-browser opening history, recoverable project hiding |
| Chinese scientific details and partial translation repair | Scoped translation cache; preserve identifiers and numbers; retry unresolved passages; use existing shared chat capacity ledger; retain original scientific text |
| `8ad2f25` through `edea84be2` frontend presentation | Transparent stage-aware companion, concise approvals, remove engine branding from Easy; port into the actual unified `/app/` frontend, preserving English mode and shared Pro viewer |

Preserved local features: account/team authorization, registration password
confirmation and browser autocomplete, session/draft recovery, queue cancellation
status, CSRF, model-call/resource capacity controls, WAL migration concurrency,
and the repaired live chat status contract. Email verification remains deferred.

The backend merge is `6604d2d`; the complete code release is
`ad5e4a8095162e28521097bd1718d559614bd301`. Frontend changes are committed
separately from the backend/scientific migration (`2e855a6`). Follow-up
`42a1b6e` makes the live projection optimization effective across scoped HTTP
requests: a bounded cache is keyed by actor and scope, while command services and
admission state remain request-local. Each reuse validates native events and
request versions, refreshes queue receipts, and checks project tombstones. Stable
approval and candidate caches are not shared across requests. `ad5e4a8` keeps
queued project creation on the bootstrap path until a native project exists;
this was found by the mixed-traffic capacity suite and all 14 capacity tests
passed after the fix. Unrelated capacity documents
and other agents' worktrees were preserved.

## Data and running-task compatibility

Project removal is a `deleted_at` tombstone, not filesystem deletion or archival.
The UI says that records/evidence remain and can be restored by an administrator.
Running projects cannot be hidden. Scoped DELETE requires edit rights, Origin
and CSRF; it emits a `project.hide` audit record. Existing typed-input identities
are backfilled from the original request during additive journal migration.

Scientific session fingerprints include source files. A release administration
step appends an exact `harness-upgrade-approved` receipt only for threads whose
stored fingerprint matches the preflight baseline. It binds the original hash,
previous hash, new hash and full release SHA. The thread's original fingerprint,
goal and scientific decisions are not overwritten. Unknown configurations remain
rejected. This operation is not exposed to a scientific tool or HTTP endpoint.

A has running scientific workers. Consequently the original source tree stays
at `e43731a`; the new service imports a pinned Git worktree under the **same
clone's** `runtime/tmp/fullflow-code-ad5e4a8`. It uses that clone's original
environment, assets and workspace. `EASYDESIGN_CODE_ROOT` is propagated through
worker descendants, and both parent/child import paths are checked before
activation. Existing workers retain their original code. No GPU reset, worker
termination or new scientific approval is part of this release.

## Verification evidence

Evidence directory: `runtime/tmp/upstream-migration/` (local ignored artifacts).

- Unified app: TypeScript check, 170 unit tests, 9 Chromium workflows and Vite
  production build pass. The new browser flow covers Site radio/3D consistency,
  stage-specific candidates, frozen YAMLs, localization and project hiding.
- Legacy Easy: TypeScript check and 168 unit tests pass.
- Repository structure, APOE asset verification, Ruff and mypy (268 files) pass.
  APOE tree remains `c72691229f3fad47d7ceda9b204a8874a1e4e164`.
- Target Viewer browser checks: 5 pass, 2 skip. Wheel staging and embedded
  resources/entrypoint verification pass.
- Additional account/harness tests: 11 pass; legacy journal/backfill tests:
  7 pass; pinned code/scoped workspace tests: 12 pass; chat bridge/harness tests:
  7 pass. Cross-request cache, authorization and projection tests: 19 pass.
  These supplement the full release suite, including checks after late changes.
- The complete backend run finished with **1975 passed, 11 skipped, 26 failed**.
  Twenty-two failures came from inherited shell proxy settings (SOCKS without the
  optional client package; the first partial cleanup also exposed malformed
  IPv6 NO_PROXY). Four exposed the queued-bootstrap cache boundary fixed in
  `ad5e4a8`. The exact 26 failing test IDs then **all passed** on the final source
  with proxy variables removed. The original failed verifier log is retained;
  this is aggregate regression evidence, not a claim that its first invocation
  returned success. `FULL-VERIFICATION.json` records both results.
- Fresh post-cache coverage additionally completed **308 account/scheduling tests**,
  **14 capacity smoke tests**, and the native live-refresh test. The earlier
  overlapping product rerun was interrupted after its failure report was
  captured (106 passed, 3 capacity failures); those failures and the remaining
  files were all covered by the successful follow-up runs. Final static checks
  and wheel verification were repeated after the bootstrap fix.
- `core-sync-report --against main` could not run because this checkout has no
  `main` ref. The report against the actual prior integration HEAD shows no
  changes under the shared core/stages/filtering/backends paths.

## Deployment and rollback

Deployments use an archive with per-file SHA-256, a verified Git bundle and
`99-zzz-fullflow-ad5e4a8.conf` service override. The original ExecStart flags,
capacity configuration, model configuration and GPU choices are preserved.
Static files are under `runtime/releases/fullflow-ad5e4a8`; old hashed assets
remain available for already-open browser tabs.

Before activation, `runtime/backups/pre-fullflow-ad5e4a8` stores the old unit,
source archive, account/chat ledgers, registered project journals and session
databases. SQLite backups use the backup API and quick_check. Worker PID start
ticks and account hashes are compared. Rollback disables only this release's
service override and restarts the controller using its previous configuration;
the old source and prior assets remain available. Additive columns and explicit
compatibility events do not require destructive database rollback.

The full-service rollback is for acceptance failure before new-version sessions
are created. A later UI rollback should restore only the previous static paths,
keeping the pinned backend: the old backend does not understand sessions first
created with the new fingerprint. After such sessions exist, prefer a forward
fix or a separately reviewed compatibility release, never rewriting their
fingerprints or restoring stale databases over live scientific records.

B test deployment is active at `https://test.easydesign.pro/app/`. Public browser
checks passed with 11 screenshots, no page errors, ordinary-account rights,
connected compute/chat and preserved registration confirmation. A real streamed
chat reached `done`; scientific translation retained GPCR and the input number.
Four baseline-compatible project snapshots read successfully with no new
admissions. Six preexisting unmatched historical sessions were left unchanged.
The QA account was returned to suspended status after every probe.

A production is deployed at `https://easydesign.pro/app/` on `ad5e4a8`.
The release administration unit exited successfully. All 9 existing scientific
sessions received exact compatibility receipts and their snapshots remained
readable. Accounts, teams and membership counts and the user-record hash were
unchanged by cutover. The previously active admissions had completed before
cutover; no active admission was present when the controller restarted.

Public acceptance verified all 24 JS/CSS hashes and the entrypoint references
(the server injects account metadata and Cloudflare adds its beacon). Account
UI, registration confirmation, scoped API access and desktop/mobile settings
passed with 11 production screenshots and no page errors. Real A chat returned
49 characters and `done`, without error; scientific translation retained GPCR
and the numeric token. QA accounts were returned to suspended status.

**Known A hardware/telemetry limitation:** the public GPU panel reported
`unavailable`. Same-environment probes showed the 5-second monitor timeout being
exceeded (compute-apps timed out; a GPU query took 4.85 seconds). The actual
scientific executor probe, with its normal 15-second query allowance, succeeded
in 13.94 seconds and enumerated 7 GPUs, indexes 0–6. The configured allowed set
remains 4,5,6,7; only 4,5,6 are currently enumerated. No driver/GPU reset, device
reassignment or scientific job was performed. This release therefore verifies
application delivery and executor discovery, **not full GPU health or a new
end-to-end research campaign**.

Production receipts: `a-deploy-result.json`, `a-public-assets.json`,
`a-projects-accepted-retry.log`, `a-chat-accepted-retry.log`,
`a-public-browser/LIVE-CHECKS.json`, `a-executor-probe.json` in the evidence
folder. B final receipts are `b-deploy-accepted.log`, `b-projects-accepted.log`
and `b-public-accepted.log`. The screenshot archive contains both sites and a
caption index, without credentials.
