# Live resources and project deletion — 2026-09-19

This user-requested extension adds real, read-only Suzhou2 GPU telemetry and confirmed deletion of local demo projects. The English white/violet interface, DemoAdapter scientific workflow, lab-request draft and existing EasyDesign backends retain their boundaries.

## Run with Suzhou2 monitoring

From this repository root:

```bash
pnpm install --frozen-lockfile
# First-time setup only; keep an existing .env.local and edit it instead.
cp -n config/compute.env.example .env.local
# Set WORKBENCH_COMPUTE_SSH_HOST=Suzhou2 in .env.local.
ssh -o BatchMode=yes -o ClearAllForwardings=yes -o StrictHostKeyChecking=yes Suzhou2 true
pnpm dev
```

Open `http://127.0.0.1:13180/#compute`. For the built app, run `pnpm build` then `pnpm preview` and open `http://127.0.0.1:13181/#compute`.

SSH must already have a working alias, identity and trusted host key outside the repository. The GPU host needs `python3` and `nvidia-smi`; no daemon or package is installed there. The setting is server-only: do not use a `VITE_` prefix. `.env.local` is ignored by Git and contains only the host alias in this deployment. Restart the server after changing the setting. Set it to an empty value to disable monitoring.

Both Vite dev and preview serve the local, same-origin `GET /api/compute/resources`. Hosting `dist/` as static files alone does not provide that endpoint; the demo remains usable and resources show unavailable. This local prototype is not an authenticated multi-user monitoring service and is not intended to be exposed publicly.

## What the page means

- Every detected GPU is listed; neither device count nor hardware model is hardcoded. The verified Suzhou2 host reports **8 NVIDIA A100-PCIE-40GB cards, 320 GiB total**.
- Summary and per-card readings show utilization, memory, temperature, power/limit, compute-process count and driver version. Counts aggregate processes without disclosing PIDs, command lines, usernames or file paths.
- Visible Compute pages refresh every 10 seconds and offer manual refresh. A shared 10-second cache coalesces requests; refresh within that interval can return the same timestamp. Leaving the page stops browser polling. The server samples only on requests.
- A failed refresh retains the previous reading and marks it **Stale data**. Readings older than 25 seconds are also stale. No successful reading gives an unavailable state. Missing fields show `—`/Unknown, never invented idle utilization or zero processes.
- Sample time is the local monitor's receipt time after a successful remote query. It deliberately does not depend on the GPU host clock; Suzhou2 and this Mac differed by approximately 100 seconds during integration.
- The lower **Demo runs** section remains simulated. Hardware monitoring is whole-node and includes other applications. It cannot identify a real queue, ownership, reservations or job completion. No jobs are submitted, moved or stopped.

The transport runs only fixed read-only queries, with bounded SSH/subprocess timeouts, strict host-key checks and existing credentials. Hosts/commands cannot be supplied by a browser request. The endpoint rejects non-local Host headers, cross-origin requests, non-GET methods and query parameters. It exposes only validated telemetry and generic failure states. No scheduler, scientific job store or backend migration was added.

## Deleting a project

The trash icon sits beside the folder icon at the top left of each card. A named confirmation dialog explains the scope before deletion. Cancel/Escape preserves the project and returns keyboard focus. Confirmation removes that device's selected project, conversation, simulated results and lab draft. It does not affect server files or real GPU processes.

Deleting the active project stops its demo animation and selects a remaining project, or shows the empty project center. Other projects and their drafts remain intact. The empty collection is retained so legacy single-project storage cannot resurrect the last deleted project; new project numbers remain monotonic. Failed persistence keeps the project and reports an error. There is no trash recovery or cross-tab merge guarantee.

## Validation

Validation covers the complete demo journey, resource states, local deletion and production serving. Automated deletion uses disposable projects in isolated browser contexts. The existing project in the user's browser was only used to inspect and cancel the dialog.

- `pnpm test`: **36 passed**; adapter lifecycle/persistence and compute validation/cache/transport regression.
- `pnpm test:e2e`: **39 passed** in the full run. After adding missing-metric coverage, `pnpm exec playwright test e2e/resources-delete.spec.ts` passed **12/12** (including 3 additional cases); full browser suite at 1366×768, 1440×900 and 1728×1117, plus narrow-screen cases. Resource tests mock only telemetry; they cover live/stale/recovery, disconnected monitoring, missing metrics, delete confirmation/cancel, persistence and last-project deletion.
- `pnpm build` and `pnpm test:production`: production 8 → 24 → 6 journey, project isolation, queue demo rows, viewer and lab draft. Production smoke explicitly disables live SSH to remain deterministic, and checks the actual preview API's not-configured response.
- `pnpm test:resources-live`: **passed** with 8 real Suzhou2 GPUs on a separate production-preview port (13182). This opt-in check requires SSH configuration; it does not run as part of the offline suite. Separate read-only checks also verified the dev resource endpoint. Existing user projects and remote workloads are untouched.
- The exact Python collector was exercised with synthetic failed, empty, duplicate and malformed process-list responses: unavailable counts remain null and duplicate PIDs are counted once.

Screenshots `resources-desktop-1440.png`, `resources-narrow-desktop-1440.png` and `project-delete-desktop-1440.png` under `docs/screenshots/` come from deterministic browser tests, not a claim about current utilization. The live page was also inspected in the in-app browser. `resources-live-preview-1728.png` records a real receipt-time sample from the production preview; it is historical evidence, not a current resource reservation. `projects-with-delete-desktop-1440.png` shows the updated card layout.

Remaining boundary: real queue integration, actual scientific job submission, a dedicated production monitoring service and multi-user project storage are not implemented by this change.
