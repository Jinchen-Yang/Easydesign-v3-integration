# EasyDesign

[English](README.md)

EasyDesign 是一个契约优先、可追溯的七阶段 VHH binder 设计流程。本仓库是
clean-room 基础版本：先定义边界、产物、溯源和工程规则，再实现科学计算后端。

**当前版本：** `0.1.0-dev`（`0.1.0.dev0`）

**当前状态：** 仓库基础架构为 `implemented`，七个科学阶段仍为 `planned`。
当前仓库没有产出任何可被视为实验验证或科学验证的设计。

## 七个阶段

| 阶段 | 职责 |
| --- | --- |
| `01-target-preparation` | 将六类 target 输入统一为标准 Target Bundle。 |
| `02-hotspot-discovery` | 生成带证据来源的 hotspot 候选和 avoid 区域。 |
| `03-boltzgen-configuration` | 构建并校验 VHH 主线的 BoltzGen 策略 YAML。 |
| `04-pilot-generation` | 执行可完整追溯的小批量 BoltzGen pilot。 |
| `05-pilot-filtering` | 用每个体系独立、版本化的规则筛选 pilot 候选。 |
| `06-scale-generation-and-refolding` | 放大入选策略，并通过可替换的结构预测后端评估。 |
| `07-final-filtering-and-selection` | 排序、去冗余、打包并审计最终 Top N，交由人工批准。 |

面向人的阶段规范位于 [`workflow/`](workflow/README.zh-CN.md)，Python 实现将
一一镜像到 `src/easydesign/stages/`。

## 仓库原则

- 每个科学或软件概念只有一个事实来源。
- 阶段间只通过显式 manifest 交接，禁止猜路径和静默回退。
- 科学逻辑只能存在于 Python API，不能放进 CLI、UI 或 shell 包装层。
- 软件完成与科学成功必须分开报告。
- 运行结果、模型权重、密钥和未经审查的第三方资产不得提交。

开发前先阅读[项目宪章](PROJECT_CHARTER.zh-CN.md)和
[贡献指南](CONTRIBUTING.zh-CN.md)。宏观路线见 [TODO](TODO.zh-CN.md)，
当前工作和历史见 [TODO_NOW](TODO_NOW.zh-CN.md)。

## 开发

核心包以 Python 3.11 为基线。重型科学工具必须通过 adapter 接入，可以使用
各自独立的运行环境。

```bash
make check PYTHON=/path/to/python3.11
make test PYTHON=/path/to/python3.11
make build PYTHON=/path/to/python3.11
```

当前是私有开发仓库，刻意不提供公开许可证、正式 CLI、UI 或 Git 远程地址。
