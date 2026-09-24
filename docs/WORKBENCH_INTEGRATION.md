# EasyDesign Workbench integration

## Status and authority

This Workbench is a browser projection of the existing v3 Runtime. It is not a
second scientific workflow. The integration was started from the accepted
Gate-3 backend commit `e0e9a73e2a8cf4fa5fbdbd9c923a45743d843e26`; the native
Target, Site, Design and Phase 3/4 contracts remain authoritative.

The browser can submit only versioned product commands. `NativeGateway` opens the
current native Agent session, `DomainSession` derives the exact current action and
Gate card, and `run_session` performs every transition. The Product layer never
constructs an approval, changes an A/B/C rank, edits a Design YAML, or grants
Pilot/Scale authority itself.

```text
browser (same origin)
  -> versioned Product API + idempotent request journal
  -> background worker + project writer lock
  -> NativeGateway / current Agent session
  -> existing v3 Runtime, evidence ledger and Scientist Gates
  -> bounded projection of cards, artifacts, tasks and progress
```

## User-visible behavior

- The existing white/violet layout is retained. Live mode is the default;
  `?mode=demo` explicitly opens the original deterministic prototype.
- A project begins from a natural-language goal. A PDB/mmCIF upload is an optional
  source seed, not scientific identity or Gate authority.
- Runtime work runs in a detached background worker. The browser polls serially,
  so a slow model call cannot create overlapping requests or make the UI appear
  frozen.
- The middle conversation shows bounded progress such as the active specialist,
  evidence/contract validation, Site portfolio readiness, Design YAML readiness,
  independent review and the current Scientist Gate.
- Raw provider requests/responses, chain-of-thought, tool payloads, secrets and
  server paths are never returned to the browser.
- Gate responses carry the current native revision and card identity. Stale
  responses fail closed and require refresh. Uncertain transport retries reuse
  the same request identity.
- A read-only question at a Gate cannot approve, resume or mutate scientific
  state. Its answer and retry state persist independently in the Product journal.
- Worker interruption is recoverable. The native append-only ledger remains the
  source of truth; the Product journal records transport lifecycle only.

## Gate semantics

- Gate 1 approves the native Target/structure decision.
- Gate 2 exposes every selectable ranked Site candidate. Selecting B or C is an
  ordinary approval, not an override.
- Gate 3 approves only the current compiled Design specification. Runtime hard
  invalidity/`BLOCKED` removes approval; advisory `DISCOURAGED` does not create an
  override-only route.
- Gate 4 and Gate 5 are shown only when the native downstream Runtime produces the
  corresponding bounded cards. Validation fixtures never imply production
  compute, scientific Scale, wet-lab execution or an order.

## Build and launch

The Python environment must include the repository's `agent` optional dependency,
and `config/llm.yaml` must reference configured provider credentials. Build the
checked-in frontend once:

```bash
cd web/workbench
pnpm install --frozen-lockfile
pnpm build
cd ../..
```

Then launch from the workspace root:

```bash
easydesign-workbench \
  --models config/llm.yaml \
  --web web/workbench/dist \
  --env-file .env.local
```

The service binds only to `127.0.0.1` and prints a one-time local access link. The
token is stored with mode `0600` under `runtime/state/product/`; it is exchanged
for an HttpOnly, SameSite=Strict cookie. The server rejects foreign Host/Origin
values and serves only declared same-origin assets and checksum-verified artifacts.

## Verification

Backend product boundary:

```bash
python -m pytest tests/unit/agent/test_product_api.py -q
ruff check src/easydesign/product tests/unit/agent/test_product_api.py tests/product_replay.py
mypy src/easydesign/product
```

Frontend:

```bash
cd web/workbench
pnpm test
pnpm typecheck
pnpm build
pnpm format:check
```

Release acceptance must also include one bounded real-provider smoke from a fresh
natural-language Goal through the first native Gate. Synthetic providers validate
contracts and deterministic state, but they cannot prove the lifecycle behavior of
loop-affine SDK clients, live connection pools, credentials or provider transports.
The smoke stops at the Gate and must not manufacture a Scientist approval. A live
browser check then verifies the durable card, candidate evidence, truthful activity
states and the expected structure placeholder or checksum-verified coordinates.

`tests/product_replay.py` is an explicitly isolated browser acceptance driver. It
uses the real Product API, background workers, v3 Runtime, Gate responses,
artifact integrity checks and UI. Its providers and downstream compute are typed
synthetic fixtures, and it refuses to run outside an initialized
`runtime/tmp/...` workspace. It must never be interpreted as scientific evidence
or production compute authority.

The frozen verification results and local browser-evidence locations are recorded
in [the 2026-09-24 acceptance report](WORKBENCH_INTEGRATION_ACCEPTANCE_20260924.md).
