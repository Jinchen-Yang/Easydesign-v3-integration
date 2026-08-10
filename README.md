# EasyDesign Local

[产品理念](docs/PRODUCT_PHILOSOPHY.md) · [完整新机安装](docs/INSTALLATION.md) ·
[开发指南](DEVELOPMENT.md) · [数据安全](DATA_SAFETY.md)

EasyDesign Local 是一个由 Codex 辅助、研究者批准、在本机 GPU 上执行的蛋白设计工作台。
公开流程是：

```text
prepare → strategize → pilot loop → scale → select
```

EasyDesign 负责确定性工具、任务执行、manifest、checksum 和不可变科学证据；Codex 负责结合
项目状态与研究经验提出方案；位点、策略、放大和最终交付由研究者批准。

## 从全新机器开始

```bash
git clone -b easydesign-local git@github.com:Knitua/Easydesign.git
cd Easydesign

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

./scripts/bootstrap.py --index auto
source .venv/bin/activate
easydesign --version
```

`bootstrap.py` 会从官方源、阿里云和清华源中实测选择可用来源；`uv.lock` 保证各来源安装的
依赖版本和校验身份一致。该步骤安装 EasyDesign 主环境，不包含大型科学模型与独立环境。

运行真实设计前，按[完整新机安装](docs/INSTALLATION.md)安装 PyMOL、BoltzGen、Protenix、
ScanNet 和 TNP，然后检查：

```bash
easydesign runtime status
easydesign doctor --full
```

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

OpenFold3/AFO 仍处于与 Protenix 并行的灰度验证阶段，不会自动成为默认后端。详见
[OpenFold3 后端](docs/OPENFOLD3_BACKEND.md)。

本分支为私有 Developer Preview；结果用于研究决策支持，不等于实验或临床验证。
