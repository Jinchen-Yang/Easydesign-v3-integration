# EasyDesign Local

[中文](../README.md) · [Development](../DEVELOPMENT.md) · [Data safety](../DATA_SAFETY.md)

EasyDesign Local is the permanent VS Code/terminal product for running the seven-stage binder
design workflow on one local Linux GPU host. It preserves scientific manifests, artifacts, attempts,
decisions, and checksums, but intentionally contains no Workbench, HTTP API, remote execution,
Suzhou2, Manager, or formal UI activation.

## Install

```bash
cd /root/autodl-tmp/Protein_design/easydesign-vscode
uv sync --frozen --extra dev
source .venv/bin/activate
easydesign --version
```

The local `.venv` contains the package and developer tools only. Reuse the existing verified science
environments and models through a read-only link:

```bash
easydesign runtime link /root/autodl-tmp/Protein_design/easydesign-clean/runtime
easydesign runtime status
easydesign doctor --full
```

The link validates registry revisions, environment locks and inventories, and asset identities. A
changed source identity fails closed and requires a new explicit link.

## Run one stage at a time

```bash
easydesign step init workspace/projects/apoe --uniprot P02649
easydesign step validate 1 workspace/projects/apoe
easydesign step run 1 workspace/projects/apoe
```

Each command returns typed status and exact next actions. To inspect the verified structure from a
second VS Code terminal:

```bash
easydesign step view workspace/projects/apoe --run RUN_ID --port 8000
```

Open `http://127.0.0.1:8000/`. The Target Viewer is read-only: it does not edit, upload, approve, or
submit work remotely.

Stage 2 runs SASA and ScanNet independently. The Viewer can switch between them and uses fixed
red/blue/yellow colors for A/B/C. Automatic and manual regions both require an explicit approval:

```bash
easydesign step run 2 workspace/projects/apoe
easydesign step template 2 workspace/projects/apoe --manual
easydesign step approve 2 workspace/projects/apoe \
  --input workspace/projects/apoe/02-approval.sasa.RUN_ID.yaml
```

Stages 4–7 use canonical scientific budgets. Without `--confirm`, the CLI reports the candidate/task
budget, GPU occupancy, disk margin, and required backends without creating a worker, stage, or
attempt. Persistent jobs support `--detach`, `status`, `watch`, safe `drain`, and `resume`; Ctrl-C only
detaches the observer.

All project and run writes stay under this worktree's `workspace/`; logs, receipts, cache, validation,
and quarantine stay under its `runtime/`. The original UI projects and runs are never indexed or
continued. `examples/apoe-ui-demo/` remains a Git-tracked, read-only scientific evidence fixture.

This private Developer Preview supports research decisions; it is not experimental validation,
clinical evidence, biosafety approval, or a supplier order.
