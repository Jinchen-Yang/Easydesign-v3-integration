# EasyDesign Local

[English](docs/README.en.md) · [产品理念](docs/PRODUCT_PHILOSOPHY.md) ·
[开发指南](DEVELOPMENT.md) · [数据安全](DATA_SAFETY.md)

EasyDesign Local 是一个 Agent 原生的本地蛋白设计研究工作台：Codex 理解问题、讨论策略
并调用工具，研究者批准关键科学选择，EasyDesign 负责确定性执行、manifest、checksum
和不可变证据。公开流程只有：

```text
prepare → strategize → pilot loop → scale → select
```

内部仍保留经过验证的七阶段科学实现，但研究者不再直接操作 Stage 编号。本产品没有完整
Workbench、远程提交、Suzhou2、Manager 或 18769 activation。

## 安装

在任意 Linux 数据盘目录 clone 后进入仓库；下面所有相对路径都以当前 clone 为根，不依赖
开发机上的固定目录。全新主机先安装 uv：

```bash
git clone -b easydesign-local git@github.com:Knitua/Easydesign.git
cd Easydesign
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
./scripts/bootstrap.py --index auto
source .venv/bin/activate
easydesign --version
```

bootstrap 会分别探测 PyPI 官方源、阿里云和清华 TUNA，显示可用性、延迟及代表性 wheel
吞吐量，只在 `auto` 模式按实测结果依次尝试。它从冻结的 `uv.lock` 导出带 SHA-256 的依赖
清单，因此镜像只改变“从哪里下载”，不会改变“安装什么”。系统 Python 可以是 3.10，uv
会准备所需的 Python 3.11；`.venv` 只包含 EasyDesign Local 和轻量开发依赖，不会混装
PyMOL、BoltzGen、Protenix、ScanNet 或 TNP。

需要固定来源时可以显式选择；显式来源失败会立即停止，不会静默换源：

```bash
./scripts/bootstrap.py --index official
./scripts/bootstrap.py --index aliyun
./scripts/bootstrap.py --index tsinghua
./scripts/bootstrap.py --index-url https://your-mirror.example/simple
```

每次真实安装都会把 source、探测结果、Git/lock 身份、校验结果和失败原因写入
`runtime/state/bootstrap/` 的不可变 receipt；`--dry-run` 只探测和展示计划，不创建环境或
receipt。中断后直接重跑同一命令即可，bootstrap 不会覆盖 lock 或删除已有 `.venv`。

### 全新机器安装科学 runtime

科学环境使用仓库中经过校验的 Conda explicit locks。没有 Conda 的 Linux x86-64 主机可把
固定版本 Miniforge 安装到当前 clone 的 `runtime/tools/`，不修改系统 Python、base Conda
或 shell profile：

```bash
test -f easydesign-workspace.yaml
mkdir -p runtime/tmp runtime/tools
curl -fL \
  https://github.com/conda-forge/miniforge/releases/download/26.3.2-2/Miniforge3-26.3.2-2-Linux-x86_64.sh \
  -o runtime/tmp/Miniforge3-26.3.2-2-Linux-x86_64.sh
printf '%s  %s\n' \
  42260ffe3830fb953d5eee1bbb32229ff06aa7c3833c1ed7a9a0420a95685d94 \
  runtime/tmp/Miniforge3-26.3.2-2-Linux-x86_64.sh \
  | sha256sum -c -
bash runtime/tmp/Miniforge3-26.3.2-2-Linux-x86_64.sh \
  -b -p "$PWD/runtime/tools/miniforge3"
runtime/tools/miniforge3/bin/conda --version
```

逐组件先看只读计划，再启动持久安装。一次只安装一个，完成后再进入下一个；有许可要求的
资产会在启动前逐项询问。推荐顺序为 `pymol-pse → boltzgen → protenix-v2 →
scannet-epitope → tnp`：

```bash
easydesign runtime plan pymol-pse
easydesign runtime install pymol-pse \
  --conda "$PWD/runtime/tools/miniforge3/bin/conda" --detach
easydesign runtime jobs --job-id SETUP_JOB_ID --watch
easydesign runtime status
```

安装命令会返回 `SETUP_JOB_ID` 和可直接复制的观察命令。`--watch` 持续显示当前阶段、总体
进度条；文件资产还显示已下载/总大小、速度和 ETA。Conda/Git 等无法可靠获得总字节数的
步骤显示阶段进度，不伪造下载百分比；`Ctrl-C` 只停止观察，后台安装继续运行。把上述组件
名依次替换为后续四项。每个环境、模型、cache、日志、registry 和失败 quarantine 都只写
当前 clone 的 `runtime/`；安装目标已存在时校验并复用，不覆盖不可变内容。全部完成后运行：

```bash
easydesign runtime status
easydesign doctor --full
```

### 已有 runtime 的同机快速路径

只有当前机器已经存在另一套经过验证的 EasyDesign runtime 时，才可以选择只读 link；这
不是全新安装的前置条件：

```bash
easydesign runtime link /absolute/path/to/existing/runtime
easydesign runtime status
easydesign doctor --full
```

来源 registry、inventory 或资产身份变化后会 fail closed，必须重新 link；共享来源永远
只读，cache、日志、job 和科学结果仍只写当前 clone。

OpenFold3/AFO 正在灰度接入，Protenix 仍是默认结构预测后端。只有持有经过校验的离线
bundle 时才安装；安装会创建本地不可变 Python 3.12/JAX 环境并执行真实 GPU smoke：

```bash
easydesign runtime install openfold3 --bundle /absolute/path/to/bundle
easydesign runtime status
easydesign doctor --full
```

安装成功也不会自动切换默认后端。固定科学面板、人工批准和单独的默认切换 commit 全部
完成前，AFO 只能显式选择，Protenix 继续作为默认及显式 fallback。资产身份、硬件边界和
灰度验收说明见 [OpenFold3 后端](docs/OPENFOLD3_BACKEND.md)。

## 用 Codex 开始研究

从本仓库或其子目录启动 Codex。根 `AGENTS.md` 会把蛋白设计任务路由到仓库级
`$easydesign-research` Skill；研究任务不会加载开发协议。可以直接说：

```text
为 P02649 新建一个 EasyDesign 项目，先准备靶点；遇到歧义停下来和我讨论。
```

```text
恢复 workspace/projects/apoe，查看目前证据，和我讨论下一轮 pilot 策略，不要自动批准。
```

```text
检查这个已染色 PSE 的 A/B/C 位点，启动只读 Viewer；我确认前不要 freeze strategy。
```

Codex 每次恢复项目只需读取：

```bash
easydesign project status workspace/projects/apoe --json
```

该结果包含当前 target/site foundation、strategy revisions、pilot/production runs、待批准项
和结构化下一步；不要扫描目录猜状态。

## 语义化命令

创建项目支持 PSE、本地结构、本地序列、PDB ID、UniProt accession/query 和经过验证的
target bundle：

```bash
easydesign project init workspace/projects/apoe --uniprot P02649
easydesign target prepare workspace/projects/apoe
```

位点入口按证据选择，最终都汇合为不可变 `target-and-site-ready` foundation：

```bash
easydesign site propose workspace/projects/apoe --from-pse-colors
easydesign site propose workspace/projects/apoe --input workspace/projects/apoe/SITE.yaml
easydesign site scan workspace/projects/apoe --method both
easydesign view workspace/projects/apoe --run RUN_ID --port 8000
easydesign site approve workspace/projects/apoe --input PROPOSAL --confirm
```

SASA 与 ScanNet 独立保存，不融合分数；A/B/C 在只读 Viewer 中固定为红/蓝/黄。

策略由研究者和 Codex 讨论后起草，校验不发布，显式批准才 freeze：

```bash
easydesign strategy draft workspace/projects/apoe
easydesign strategy validate workspace/projects/apoe --config workspace/projects/apoe/strategy-draft.yaml
easydesign strategy freeze workspace/projects/apoe --config workspace/projects/apoe/strategy-draft.yaml --confirm
```

策略支持 target crop、approved binding subset、七 scaffold 或子集、CDR range/插入长度、
显式多 variant，以及带 SHA-256 和真实 backend check 的专家 BoltzGen YAML。

每轮 pilot 是独立不可变 run；科学负结果仍是有效证据：

```bash
easydesign pilot plan workspace/projects/apoe --strategy strategy-r000001
easydesign pilot run workspace/projects/apoe --strategy strategy-r000001 --confirm --detach
easydesign pilot review workspace/projects/apoe --run PILOT_RUN
easydesign pilot promote workspace/projects/apoe --run PILOT_RUN --strategy ID1,ID2 --confirm
```

规模化和选择默认 50,000 / Top 200；不足 200 时不重复、不补齐：

```bash
easydesign scale plan workspace/projects/apoe --selection SELECTION
easydesign scale run workspace/projects/apoe --selection SELECTION --count 50000 --confirm --detach
easydesign select plan workspace/projects/apoe --run PRODUCTION_RUN --top 200
easydesign select run workspace/projects/apoe --run PRODUCTION_RUN --top 200 --confirm --detach
```

任务控制统一为 `easydesign job status|watch|resume|drain`。`Ctrl-C` 只脱离观察，`drain`
只在安全检查点停止新调度。所有命令支持 `--json`，文本和 JSON 来自同一 `CommandResult`。

## 数据位置与批准边界

- `workspace/projects/`：输入、可变 draft、不可变 site/strategy/promotion receipt；
- `workspace/runs/`：不可变科学 run、manifest、attempt 和 artifact；
- `runtime/`：本产品 receipt、profile、cache、日志、job、validation 和 quarantine；
- `examples/apoe-ui-demo/`：Git 跟踪、checksum 不变的只读科学证据。

读取、校验、染色、扫描、规划、review 和 Viewer 可直接执行。`site approve`、
`strategy freeze`、`pilot run/promote`、`scale run` 和 `select run` 必须由研究者显式确认。
旧七 YAML 项目只读识别，不原地迁移。

结果用于研究决策支持，不等于实验验证、临床结论、生物安全批准或供应商订单。本分支为
私有 Developer Preview，不发布 PyPI。
