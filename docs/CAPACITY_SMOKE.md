# Isolated capacity evidence

`scripts/capacity_smoke.py` starts its own loopback-only server and uses fresh synthetic
accounts, databases, inputs and queues below this clone's `runtime/tmp/capacity-smoke-*`.
It does not accept a target URL, use a real model credential, or offer any GPU slots.
The subprocess model provider is a local deterministic fixture; a second guard refuses
scientific process creation even if an admission bug tries to start one.

This measures local engineering behavior, not Cloudflare/network quality, browser
rendering, supplier throughput, scientific correctness or production-server capacity.
The local host and capacity configuration are included in every report. Real password
verification uses the unchanged 600,000-iteration PBKDF2 setting; account preparation is
outside the timed workload. GPU acceptance is reported as **queued**, never completed.
Each synthetic account uses its own independent personal scope. A 300-account pass
does not mean 300 submissions into one shared team scope: team quotas are shared and
require a separately specified team workload and capacity policy.

The default input is a 64-KiB parseable synthetic PDB with harmless REMARK padding,
not a biologically meaningful target. `--upload-bytes` records a different explicit
size. `--boundary-uploads` adds exactly one 32-MiB upload and a 32-MiB+1 declared
length rejection; the latter intentionally sends no oversized body and is not a
throughput measurement. It does not create 300 maximum-size files.
Uploads compare the API receipt's SHA-256 and byte count with the known in-memory
synthetic input. The verified input ID is passed into project creation; `input_bound`
counts accepted submissions carrying that verified input. A hash/length mismatch
fails the flow rather than creating an unrelated empty-input project.

## Profiles and outcomes

- `conservative` keeps production capacity defaults, including AI 2 active / 20 per
  minute / 120 seconds maximum waiting. A 300-slot queue does not imply 300 requests
  can finish before their deadlines. Request-count limits are not a monetary budget.
- `stub-throughput` changes only the isolated fixture's AI settings to 16 active /
  60,000 per minute / 600 per user per minute. This exposes application bottlenecks
  without pretending that a supplier permits those rates. Both baseline and selected
  settings are recorded. HTTP, login and scientific queue defaults remain unchanged.

The normal workload finishes all GPU submissions before submitting AI requests, so a
full scientific queue must not exclude web chat. Reads use the actual request and
project-workbench snapshot APIs, including their queue projection costs. Static files
are explicitly synthetic and do not represent the full production frontend bundle.

Reports keep successful and all-response p95/p99 separate; fast rejections cannot
make successful requests look faster. Known overload codes are listed separately
from unexpected failures but still fail the all-flows-success target. GPU queue
refusal and AI refusal remain separate operations. No blanket 429/503 exception
turns rejected work into a successful flow.

The proposed local targets are login successful p95 <= 3 seconds, light-API p95 <= 1
second, and GPU submission-to-persisted-request-ID p95 <= 1 second. `goal_pass` is
stricter than an error-budget allowance:
every normal flow and request must succeed. AI completion time is recorded, not
promised. The actual span of login request start times is recorded separately from
the requested 5-second arrival window. HTTP requests are not browser page-load scores.

## Running after the freeze

Use the existing clone virtual environment; no dependency installation is needed.
The following commands are intended for an otherwise idle local test host:

```bash
.venv/bin/python scripts/capacity_smoke.py --users 2 --profile stub-throughput \
  --login-window-seconds 0.1 --fault-checks --boundary-uploads

.venv/bin/python scripts/capacity_smoke.py --stages 30,100,300 --profile stub-throughput \
  --login-window-seconds 5 --soak-seconds 1800 --poll-seconds 5 \
  --fault-checks --boundary-uploads

.venv/bin/python scripts/capacity_smoke.py --users 300 --profile conservative \
  --login-window-seconds 5 --hold-seconds 15
```

The increasing stages use independent databases and stop escalation if the current
stage fails. Soak/fault/boundary checks apply only to the last stage. The soak repeats
real authenticated snapshots and request status, and submits independent AI requests
every 60 seconds. Outstanding AI is explicitly cancelled at final drain; those
cancellations remain failed model attempts in the normal summary.

The separate slow-AI scenario holds one stream per user while fresh browser sessions
log in and the original sessions continue reads/uploads. It reports how many streams
really registered, queued, completed or cancelled, and every mixed-load refusal.
The requested hold is a minimum: synchronous mixed work/drain can take longer, so
actual duration is recorded. Cleanup cancellation has bounded fan-out; normal mixed
requests are not retried. Cancelled streams are never counted as completed full flows.
This scenario exposes interaction with the 384-connection HTTP cap; it does not assume
that 84 nominal remaining connections guarantee acceptable login/read behavior.
Its mixed-workload latency targets must also pass; successful-but-slow responses do
not produce a passing exit code. Any attempted scientific-process spawn fails final
acceptance in every scenario, even if the safety guard prevented execution.

Fault checks kill only a new session/process group created by this tool, including its
local model stub. PID/PGID ownership is retained in evidence. The same port/database
is restarted, checking session and GPU queue persistence, cancellation/resume, old AI
request-ID rejection and new AI quota recovery. That fixture's first user has one chat
slot, making a single leaked admission observable. Injected-fault and boundary results
are separate from normal throughput; they are not silently excluded from raw evidence.
Exit code 2 means a target/check failed and must be investigated, not relabeled success.

## Evidence and safety

Each run retains `report.json`, `spec.json`, request timing JSONL, server queue/provider
samples, process RSS/thread/CPU/child-count samples and child logs. Request bodies,
passwords, cookies, authorization headers and provider credentials are not logged.
Synthetic credentials exist only in load-generator memory; hashes remain in the
new private fixture database. Evidence is not automatically deleted.
Resource peaks are **observed peaks sampled every 0.5 seconds**, not absolute maxima.
Child counts include children created by all server threads, deduplicated across the
thread group; short-lived processes between samples can still be missed.

Source edits are verified via the official integration verifier. Only tiny local
debugging runs are appropriate while development/regression is running. Formal
30/100/300 and 30-minute soak results must wait for the complete regression and
browser processes to finish, avoiding contention with the load generator. A tiny
debugging pass is not 300-user acceptance.
