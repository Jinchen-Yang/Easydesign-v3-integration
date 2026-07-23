# EasyDesign

EasyDesign 是一个契约优先、可追溯的七阶段 VHH binder 设计流程。本仓库先把
阶段边界、产物、溯源和工程规则定义清楚，再逐步实现科学计算后端。

- 当前版本：`0.1.0-dev`（包版本 `0.1.0.dev0`）
- 仓库基础架构：`implemented`
- 七个科学阶段：`planned`
- 当前范围：VHH 主线；不承诺设计准确率

## 七个阶段

| 阶段 | 目标 |
| --- | --- |
| [`01-target-preparation`](workflow/01-target-preparation/README.md) | 将六类输入统一为标准 Target Bundle。 |
| [`02-hotspot-discovery`](workflow/02-hotspot-discovery/README.md) | 生成带证据的 hotspot 候选和 avoid 区域。 |
| [`03-boltzgen-configuration`](workflow/03-boltzgen-configuration/README.md) | 生成并校验 VHH BoltzGen YAML 策略矩阵。 |
| [`04-pilot-generation`](workflow/04-pilot-generation/README.md) | 运行可完整追溯的小批量 BoltzGen pilot。 |
| [`05-pilot-filtering`](workflow/05-pilot-filtering/README.md) | 使用体系专属、版本化规则筛选 pilot。 |
| [`06-scale-generation-and-refolding`](workflow/06-scale-generation-and-refolding/README.md) | 放大策略并调用可替换结构预测后端。 |
| [`07-final-filtering-and-selection`](workflow/07-final-filtering-and-selection/README.md) | 终筛、去冗余并生成供人工批准的 Top N。 |

## 从哪里开始

- 项目目标和开发铁律：[`PROJECT_CHARTER.md`](PROJECT_CHARTER.md)
- 宏观路线图：[`TODO.md`](TODO.md)
- 当前任务和历史：[`TODO_NOW.md`](TODO_NOW.md)
- 阶段交接规则：[`workflow/README.md`](workflow/README.md)
- 仓库和运行架构：[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- 旧仓审计基线：[`docs/legacy/BASELINE.md`](docs/legacy/BASELINE.md)

## 开发环境与检查

全部环境先使用 Conda 管理。EasyDesign 主环境是 Python 3.11 的 `easydesign-core`；
BoltzGen、Boltz2、AF3/AFO/Phoenix 等重型工具保持各自独立环境，通过 adapter 调用。

在普通 Conda 安装中：

```bash
conda env create -f environment.yml
conda activate easydesign-core
make check
make test
make build
```

Proteindigger1 使用 `/root/miniconda3/bin/conda`，环境实际存放在
`/root/autodl-tmp/conda_envs/`；该站点路径只用于部署，不进入核心代码。

当前仓库保持私有，没有公开许可证、正式 CLI、UI 或 Git remote。
