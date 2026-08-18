# EasyDesign Local

EasyDesign Local is an agent-native, local protein-binder research workbench. Codex reasons about the
project and invokes deterministic tools; the researcher approves scientific decisions; EasyDesign
preserves manifests, checksums, attempts, and immutable evidence.

The product executes only on the local Linux GPU host that contains the current clone. The repository
root is discovered through `easydesign-workspace.yaml`; documentation and code use clone-relative
paths so each user may choose a different host and data-disk location.

The public workflow is:

```text
prepare → strategize → pilot loop → scale → select
```

The internal seven-stage scientific engine remains intact, but Stage numbers are not part of the
researcher-facing CLI.

## Install

```bash
git clone -b easydesign-local https://github.com/Knitua/Easydesign.git
cd Easydesign
curl --proto '=https' --tlsv1.2 -LsSf \
  https://astral.sh/uv/0.12.3/install.sh \
  | env UV_NO_MODIFY_PATH=1 sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
./scripts/bootstrap.py --index auto
source .venv/bin/activate
easydesign --version
```

If the host already has global `uv 0.12.3`, keep it and skip the uv installer. Bootstrap does not
copy, upgrade, or delete that host tool. When invoking it, bootstrap isolates HOME, configuration,
caches, managed Python, and temporary files under this clone's `runtime/`, then builds a relocatable
environment under `runtime/tmp/`. The verified environment is atomically published as `.venv`;
failed staging is quarantined. Bootstrap then measures the official PyPI, Aliyun, and Tsinghua TUNA
indexes and installs a SHA-256-pinned export of the frozen `uv.lock`. The selected transport therefore
cannot change the resolved package set. Only `--index auto` may try another measured source; an explicit
`--index official|aliyun|tsinghua` or HTTPS `--index-url` fails closed. Every real attempt writes an
immutable receipt under `runtime/state/bootstrap/`; use `--dry-run` for a read-only probe.

On a clean Linux x86-64 host, explicitly install the pinned Miniforge build into this clone. The
command downloads and verifies the installer, then later component installs use it automatically.
Choose either one all-components job or the six individual jobs. While a setup job is running, the
CLI rejects a second launch and returns the existing job's watch command instead of competing for the
same cache.

Install all six components in one sequential detached job:

```bash
easydesign runtime install miniforge
easydesign runtime plan all
easydesign runtime install all --detach
easydesign runtime jobs --job-id SETUP_JOB_ID --watch
```

Alternatively, install and verify one component at a time:

```bash
easydesign runtime plan pymol-pse
easydesign runtime install pymol-pse --detach
easydesign runtime plan boltzgen
easydesign runtime install boltzgen --detach
easydesign runtime plan protenix-v2
easydesign runtime install protenix-v2 --detach
easydesign runtime plan scannet-epitope
easydesign runtime install scannet-epitope --detach
easydesign runtime plan tnp
easydesign runtime install tnp --detach
easydesign runtime list afo
easydesign runtime install afo --detach
easydesign runtime jobs --job-id SETUP_JOB_ID --watch
```

The AFO installer downloads the complete pre-converted release from the public Hugging Face
repository and creates its isolated environment automatically. It does not require the Hugging Face
CLI, a manual weight download, the original PyTorch checkpoint, or a conversion environment. The
current download is about 4.7 GiB; the validated platform is Linux x86-64 with an NVIDIA A100 40 GB
and a CUDA 12-compatible driver.

These commands default to `--source auto`: EasyDesign probes the tracked official and China-local
transport candidates, while the repository lock still fixes the Miniforge SHA, each Conda package
SHA, model SHA, and Git commit. Use `--source official` for strict official transport or
`--source china` for China-local preference with an audited official fallback. Interrupted verified
downloads resume from this clone's `runtime/cache/`; the selected transport is recorded but never
becomes part of the environment identity.

The install command prints the `SETUP_JOB_ID` and an exact watch command. The
watch view shows the current phase and an overall progress bar. File downloads
also show transferred/total bytes, rate, and ETA; Conda and Git phases do not
invent byte percentages when the upstream tool cannot provide them. `Ctrl-C`
only stops watching and leaves the detached installer running.

The `all` command creates one worker and processes
`pymol-pse → boltzgen → protenix-v2 → scannet-epitope → tnp → afo` sequentially. The catalog's AFO
`stable` is installed and activated by that same foreground or detached job; future `candidate`
releases are never installed implicitly. In individual mode, wait
for each job to finish before launching the next. Then run `easydesign runtime status` and
`easydesign doctor --full`. Every cache, log, job, project, run, and locally installed component
remains inside the current clone.

## Start or resume with Codex

Start Codex from the repository or a subdirectory. Repository instructions route protein-design work
to `$easydesign-research`. Project state is restored only through:

```bash
easydesign project status workspace/projects/apoe --json
```

Create and prepare a project:

```bash
easydesign project init workspace/projects/apoe --uniprot P02649
easydesign target prepare workspace/projects/apoe --prediction-backend afo
easydesign site scan workspace/projects/apoe --method both
easydesign site approve workspace/projects/apoe --input PROPOSAL --confirm
```

Draft, validate, freeze, and iterate:

```bash
easydesign strategy draft workspace/projects/apoe
easydesign strategy validate workspace/projects/apoe --config workspace/projects/apoe/strategy-draft.yaml
easydesign strategy freeze workspace/projects/apoe --config workspace/projects/apoe/strategy-draft.yaml --confirm
easydesign pilot run workspace/projects/apoe --strategy strategy-r000001 \
  --prediction-backend afo --confirm --detach
easydesign pilot review workspace/projects/apoe --run PILOT_RUN
```

Scale and select only from a human promotion receipt. Defaults are 50,000 production candidates and
Top 200 delivery; legal results are never duplicated or padded.

Read/validate/color/scan/plan/review/view operations may run directly. Site approval, strategy freeze,
pilot run/promotion, scale, and selection require explicit researcher confirmation. The viewer is
read-only and there is no remote executor, managed queue, Workbench, or UI activation.
Each run freezes the selected backends, AFO release identity, runtime-profile SHA, and config
snapshot. `job resume` accepts no backend override and reuses those frozen identities even if the
active machine profile changes later.

Successful Stage 5 and Stage 7 runs automatically publish an immutable, read-only review dashboard.
Use `easydesign view PROJECT --run RUN --report auto` to open the highest completed report, or select
`target`, `stage05`, or `stage07` explicitly. Legacy runs and reporting failures can be rebuilt with
`easydesign report build`; `easydesign report export ... --output NEW_PATH` creates a portable copy
containing every referenced structure. Browser filters, sorting, scatter selection, and favourites are
display-only and never create a promotion, final selection, or approval receipt.
