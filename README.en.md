# EasyDesign

[中文](README.md) · [English](README.en.md)

EasyDesign is a contract-first, evidence-preserving, recoverable workbench for a seven-stage
protein-binder design workflow.

Current version: `0.1.0.dev47`. This repository remains a Developer Preview: it is not published
to PyPI, does not add a new open-source license, and retains the `Private :: Do Not Upload`
classifier. Review intellectual-property, license, and data permissions before using it outside
the authorized repository context.

## Seven-stage workflow

```text
01 Target → 02 Regions → 03 Plans → 04 Pilot generation
                                      ↓
07 Final candidates ← 06 Scale ← 05 Pilot filtering
```

- Stages 01–03 freeze the target, user-confirmed design input, and executable plans.
- Stages 04→05 run as one continuous pilot-generation and filtering task.
- Stages 06→07 run as one continuous user-sized scale and final-filtering task.
- Users explicitly choose the current machine or authorized Suzhou2 public compute; neither is
  an automatic fallback for the other.
- Scientific stops, operational failures, and human approvals remain distinct, and historical
  manifests and artifacts are never rewritten.

## Install core, CLI, and UI in five minutes

Prerequisites: Git, [uv](https://docs.astral.sh/uv/), and Python 3.11 or 3.12. Python 3.11 is
recommended.

```bash
git clone https://github.com/Knitua/Easydesign.git
cd Easydesign

uv sync --frozen --extra ui
source .venv/bin/activate

easydesign --version
```

`uv sync` creates `.venv` and installs this checkout in editable mode. `uv.lock` fixes exact
versions, sources, and platform markers; `--frozen` prevents resolution or lock changes during
installation. After activation, every product command starts with `easydesign`.

For each new terminal:

```bash
cd Easydesign
source .venv/bin/activate
```

Developer installation:

```bash
uv sync --frozen --extra ui --extra dev
source .venv/bin/activate
easydesign --version
```

`uv run easydesign ...` remains available when activation is inconvenient and is the preferred
form for CI or automation. The ordinary user path uses `easydesign ...`.

<details>
<summary>pip compatibility path when uv is unavailable</summary>

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[ui,dev]"
```

This path does not strictly consume `uv.lock` and therefore cannot offer the same reproducibility
as `uv sync --frozen`.

</details>

At this point only core, CLI, and UI are installed. The UI can open and inspect existing evidence,
but the five scientific backends, models, and local GPU execution are not yet ready.

## Install the five isolated scientific environments

Complete local seven-stage compute requires Linux, NVIDIA GPUs, and Conda on `PATH`:

```bash
conda --version
nvidia-smi
```

PyMOL, BoltzGen, Protenix-v2, ScanNet, and TNP do not enter `.venv`. EasyDesign publishes each
exact Conda lock under `runtime/envs/`; models and caches go to `runtime/models/` and
`runtime/cache/`. It does not change base Conda, shell profiles, system proxies, or global pip
configuration.

Install components sequentially. Inspect the plan and pending licenses, start one detached job,
and wait for its terminal state before starting the next component.

### 1. PyMOL/PSE

```bash
easydesign setup --component pymol-pse --plan
easydesign setup --component pymol-pse --detach
easydesign setup --status
```

### 2. BoltzGen

```bash
easydesign setup --component boltzgen --plan
easydesign setup --component boltzgen --detach
easydesign setup --status
```

### 3. Protenix-v2

```bash
easydesign setup --component protenix-v2 --plan
easydesign setup --component protenix-v2 --detach
easydesign setup --status
```

### 4. ScanNet

```bash
easydesign setup --component scannet-epitope --plan
easydesign setup --component scannet-epitope --detach
easydesign setup --status
```

### 5. TNP

```bash
easydesign setup --component tnp --plan
easydesign setup --component tnp --detach
easydesign setup --status
```

Do not run these large installers concurrently. Do not use an unscoped full setup: uv already
owns core/UI, so a second core Conda environment is unnecessary.

### Accept exact asset licenses

Use the current plan output instead of copying historical asset IDs:

```bash
easydesign assets status
easydesign setup --component COMPONENT --plan

easydesign setup --component COMPONENT \
  --accept-license ASSET_ID_1 \
  --accept-license ASSET_ID_2 \
  --detach
```

`--accept-license` is repeatable. There is no “accept every license” command. Unapproved assets
remain `awaiting-approval` and cannot make a backend ready.

### Wait for terminal state and validate

```bash
easydesign setup --status
easydesign setup --status --job-id JOB_ID
easydesign env status
easydesign assets status
```

A component is complete only when its `result.json` is `succeeded`. `incomplete`, `failed`, and
`interrupted` are not success and do not trigger automatic cleanup. After all five components:

```bash
easydesign env status
easydesign assets status
easydesign doctor --full
```

Only a successful `doctor --full` means the complete local scientific workbench is ready. See the
[environment manual](environments/README.md) for disk peaks, mirrors, caches, and safe recovery.

Platform boundaries:

- Linux + NVIDIA: complete local seven-stage scientific execution.
- macOS: core, UI, evidence inspection, and remote client capabilities.
- Windows: native execution is not promised in this iteration; use WSL2.
- No local GPU: connect to an authorized Suzhou2 deployment with an existing Manager.

## Optional: repository-specific Suzhou2 SSH key

This section is only for users who have Suzhou2 access. Read the fingerprint and verify it through
an administrator or another trusted channel; do not trust the first network connection alone.

```bash
easydesign remote pair-scan \
  --host SUZHOU2_HOST \
  --port 22
```

Create or reuse the repository-specific Ed25519 key:

```bash
easydesign remote pair-begin suzhou2 \
  --controller-id MY_CONTROLLER \
  --host SUZHOU2_HOST \
  --port 22 \
  --user root \
  --confirm-fingerprint SHA256:VERIFIED_FINGERPRINT
```

Keys live under `runtime/secrets/ssh/suzhou2/`. A complete pair is reused. If only one half exists,
the command stops instead of replacing it. The private key stays mode `0600`; keys and known-host
data never enter Git or scientific configuration.

Install the public key idempotently and enter the remote password once through OpenSSH:

```bash
ssh-copy-id \
  -i runtime/secrets/ssh/suzhou2/id_ed25519.pub \
  -o UserKnownHostsFile=runtime/secrets/ssh/suzhou2/known_hosts \
  -o StrictHostKeyChecking=yes \
  -o IdentitiesOnly=yes \
  -p 22 root@SUZHOU2_HOST
```

The password is read only by OpenSSH and never enters EasyDesign arguments, environment variables,
the browser, logs, or disk. Then validate Manager, protocol, exact EasyDesign version, continuous
stage chains, and resources:

```bash
easydesign remote pair-confirm suzhou2
```

Logical unpairing:

```bash
easydesign remote unpair suzhou2 --confirmed
```

Unpairing only appends a registry revision. It does not delete local keys, known-host data, the
remote public key, or historical evidence.

## Start the UI

```bash
easydesign ui serve \
  --host 127.0.0.1 \
  --port 18769
```

Open `http://127.0.0.1:18769`:

- Successful `doctor --full`: complete scientific execution is available on the current machine.
- Successful `pair-confirm`: Suzhou2 can be selected explicitly.
- uv core only: evidence inspection and frontend development only.

The UI does not use a startup gate to pretend an environment is ready. Real jobs still run
structured GPU, disk, environment, model, and license preflight before submission.

## Evidence and boundaries

- The Stage 01–07 engineering chain, APOE PSE region import, and real pilot/remote smoke runs have
  immutable evidence.
- UI and installation changes do not rewrite current filtering thresholds or historical APOE
  conclusions.
- Results support research decisions; they are not experimental validation, clinical conclusions,
  biosafety approval, or supplier orders.
- External models, databases, weights, and services retain their own licenses, terms, and data
  policies.
- A public license, PyPI release, and formal multi-user security boundary remain separate decisions.

See [TODO_NOW.md](TODO_NOW.md) for current work, [TODO.md](TODO.md) for the complete task registry,
and the [Case Registry](docs/validation/CASE_REGISTRY.md) for scientific evidence.

## Documentation

- [Environment installation and recovery](environments/README.md)
- [Development, testing, and uv lock](DEVELOPMENT.md)
- [Architecture and cross-repository synchronization](docs/ARCHITECTURE.md)
- [Seven-stage contracts](workflow/README.md)
- [UI workbench](docs/product/UI_WORKBENCH.md)
- [Data safety](DATA_SAFETY.md)
- [Project charter](PROJECT_CHARTER.md)
