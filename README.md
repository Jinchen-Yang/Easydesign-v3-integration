# EasyDesign Local

[产品理念](docs/PRODUCT_PHILOSOPHY.md) · [开发指南](DEVELOPMENT.md) ·
[数据安全](DATA_SAFETY.md)

EasyDesign Local 是一个由 Codex 辅助、研究者批准、在本机 GPU 上执行的蛋白设计工作台。
公开流程是：

```text
prepare → strategize → pilot loop → scale → select
```

EasyDesign 负责确定性工具、任务执行、manifest、checksum 和不可变科学证据；Codex 负责结合
项目状态与研究经验提出方案；位点、策略、放大和最终交付由研究者批准。

## 从全新机器开始

### 1. Clone 并安装主环境

```bash
git clone -b easydesign-local git@github.com:Knitua/Easydesign.git
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

已经全局安装 `uv 0.12.3` 的机器可以跳过 uv 安装命令；uv 本身由宿主机管理，bootstrap
不会复制、升级或删除它。调用全局 uv 时，bootstrap 会把 HOME、配置、cache、Python 下载
和临时文件全部隔离到当前 clone 的 `runtime/`。随后它从官方源、阿里云和清华源中实测
选择可用来源；`uv.lock` 保证各来源安装的依赖版本和校验身份一致。`.venv` 先在
`runtime/tmp/` 中完成安装与验证，再原子发布；失败内容只进入 `runtime/quarantine/`。
该步骤不包含大型科学模型与独立环境。

### 2. 安装本仓库的 Miniforge

EasyDesign 主程序由 `uv` 安装在 `.venv/`；PyMOL、BoltzGen、Protenix、ScanNet 和 TNP
还包含 CUDA、编译库等独立依赖，需要 Conda 按仓库中的 explicit lock 分别创建重型环境。
因此新机器还需要一套只属于当前 clone 的 Miniforge。用户明确运行下面的命令后，它会下载
固定版本、校验 SHA-256 并安装到 `runtime/tools/`，不会修改系统 Python、系统 Conda 或
shell profile：

```bash
easydesign runtime install miniforge
```

### 3. 依次安装科学环境

安装顺序是：

```text
pymol-pse → boltzgen → protenix-v2 → scannet-epitope → tnp
```

每次先查看计划，再安装一个组件：

```bash
easydesign runtime plan pymol-pse
easydesign runtime install pymol-pse --detach
```

安装命令会打印 `SETUP_JOB_ID` 和对应的观察命令。复制它给出的命令，或运行：

```bash
easydesign runtime jobs --job-id SETUP_JOB_ID --watch
```

当前组件完成后，把上述命令中的 `pymol-pse` 依次替换为 `boltzgen`、`protenix-v2`、
`scannet-epitope` 和 `tnp`。遇到许可确认时，阅读终端提示并显式提供要求的
`--accept-license`；`Ctrl-C` 只退出观察，后台安装继续。

### 4. 验收

五个科学组件全部完成后运行：

```bash
easydesign runtime status
easydesign doctor --full
```

只有 `doctor --full` 通过后，才把这台机器视为完整可用的 EasyDesign Local 主机。

OpenFold3/AFO 当前是可选灰度后端，不属于默认新机安装。只有持有经过校验的离线 bundle
时才执行：

```bash
easydesign runtime install openfold3 --bundle runtime/imports/openfold3-bundle
easydesign doctor --full
```

安装 AFO 不会自动替换默认 Protenix；详细边界见
[OpenFold3 后端](docs/OPENFOLD3_BACKEND.md)。

## 用 Codex 开始

从仓库目录启动 Codex，直接描述研究目标，例如：

```text
为 P02649 新建一个 EasyDesign 项目，先准备靶点；遇到歧义停下来和我讨论。
```

Codex 会读取仓库级 `$easydesign-research` Skill，并通过语义化命令推进项目。也可以直接从
终端开始：

```bash
easydesign project init workspace/projects/apoe --uniprot P02649
easydesign target prepare workspace/projects/apoe
easydesign project status workspace/projects/apoe --json
```

查看全部命令：

```bash
easydesign --help
easydesign project --help
easydesign runtime --help
```

## 数据位置与批准边界

- `workspace/projects/`：输入、draft、位点和策略 revision；
- `workspace/runs/`：不可变科学 run、manifest、attempt 和 artifact；
- `runtime/`：本机环境、模型、cache、日志、任务状态和安装 receipt；
- `examples/apoe-ui-demo/`：只读 APOE 科学证据示例，不得改写。

读取、校验、染色、扫描、规划和 review 可以直接执行。`site approve`、`strategy freeze`、
`pilot run/promote`、`scale run` 和 `select run` 必须由研究者显式确认。

本分支为私有 Developer Preview；结果用于研究决策支持，不等于实验或临床验证。
