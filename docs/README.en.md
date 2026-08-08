# EasyDesign Local

EasyDesign Local is an agent-native, local protein-binder research workbench. Codex reasons about the
project and invokes deterministic tools; the researcher approves scientific decisions; EasyDesign
preserves manifests, checksums, attempts, and immutable evidence.

The public workflow is:

```text
prepare → strategize → pilot loop → scale → select
```

The internal seven-stage scientific engine remains intact, but Stage numbers are not part of the
researcher-facing CLI.

## Install

```bash
cd /root/autodl-tmp/Protein_design/easydesign-local
uv sync --frozen --extra dev
source .venv/bin/activate
easydesign runtime link /root/autodl-tmp/Protein_design/easydesign-clean/runtime
easydesign doctor --full
```

The linked scientific environments and models are read-only. This worktree owns its caches, logs,
jobs, projects, and runs.

## Start or resume with Codex

Start Codex from the repository or a subdirectory. Repository instructions route protein-design work
to `$easydesign-research`. Project state is restored only through:

```bash
easydesign project status workspace/projects/apoe --json
```

Create and prepare a project:

```bash
easydesign project init workspace/projects/apoe --uniprot P02649
easydesign target prepare workspace/projects/apoe
easydesign site scan workspace/projects/apoe --method both
easydesign site approve workspace/projects/apoe --input PROPOSAL --confirm
```

Draft, validate, freeze, and iterate:

```bash
easydesign strategy draft workspace/projects/apoe
easydesign strategy validate workspace/projects/apoe --config workspace/projects/apoe/strategy-draft.yaml
easydesign strategy freeze workspace/projects/apoe --config workspace/projects/apoe/strategy-draft.yaml --confirm
easydesign pilot run workspace/projects/apoe --strategy strategy-r000001 --confirm --detach
easydesign pilot review workspace/projects/apoe --run PILOT_RUN
```

Scale and select only from a human promotion receipt. Defaults are 50,000 production candidates and
Top 200 delivery; legal results are never duplicated or padded.

Read/validate/color/scan/plan/review/view operations may run directly. Site approval, strategy freeze,
pilot run/promotion, scale, and selection require explicit researcher confirmation. The viewer is
read-only and there is no remote executor, Manager, Suzhou2, Workbench, or port-18769 activation.
