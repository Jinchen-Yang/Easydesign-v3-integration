# EasyDesign 开发指南

[安装主路径](README.md) · [架构](docs/ARCHITECTURE.md) · [数据安全](DATA_SAFETY.md)

## 开发环境

EasyDesign core、CLI、UI 和检查工具由 uv 管理；科学后端仍使用 `environments/` 中的
独立 Conda lock。

```bash
uv sync --frozen --extra ui --extra dev
source .venv/bin/activate
easydesign --version
```

`.python-version` 固定首选 Python 3.11，项目契约同时支持 3.12。不要把 PyMOL、
BoltzGen、Protenix、ScanNet 或 TNP 的重型依赖加入 core `.venv`。

## 更新依赖锁

只有 `pyproject.toml` 的依赖契约经过评审后才更新 lock：

```bash
uv lock
uv lock --check
uv sync --frozen --extra ui --extra dev
```

提交 `pyproject.toml` 与 `uv.lock`。`uv.lock` 是跨平台解析结果；`.venv`、Conda 环境、
模型、缓存和安装状态都不能进入 Git。普通依赖验证禁止联网漂移，CI 必须使用 `--frozen`。

## 本地质量门

正式门禁使用锁定的 Python 3.11：

```bash
make check PYTHON=/path/to/python3.11
make test PYTHON=/path/to/python3.11
make test-web PYTHON=/path/to/python3.11
make build PYTHON=/path/to/python3.11
git diff --check
```

- `make check`：状态汇总、仓库结构、静态资源、ruff、mypy 和编译检查。
- `make test`：Python 单元与契约测试。
- `make test-web`：目标查看器、Workbench Playwright 和 UI 构建。
- `make build`：先发布前端静态资源，再构建 wheel，并在隔离环境验证 console script、
  Python 模块入口、UI 资产和许可证文件。

UI 源码修改必须同时提交 `web/workbench/src/`、浏览器测试和构建后发布到
`src/easydesign/ui/static/` 的资产。不得手工编辑哈希静态文件。

## 干净克隆 smoke

在新的临时目录验证 README core 路径：

```bash
git clone /path/to/easydesign clean-smoke
cd clean-smoke
uv sync --frozen --extra ui --extra dev
uv run easydesign --version
uv run easydesign --help
uv run easydesign setup --help
uv run easydesign ui serve --help
```

轻量 CI 只验证 core/UI，不创建 Conda 科学环境、不下载模型、不连接 Suzhou2，也不要求
GPU。真实后端测试必须使用已授权资产、精确 lock 和独立运行记录。

## 文档与状态

功能、测试和状态必须同批更新：

1. 修改对应 Stage `README.md` 或 `STATUS.md`。
2. 更新 `TODO_NOW.md` 与必要的历史记录。
3. 运行 `python scripts/sync_status_rollup.py`，不要手工修改自动生成摘要。
4. 运行完整质量门并记录真实证据；不得把 planned/implemented 写成 validated。

## 版本和 Suzhou2 Manager

任何会改变 wheel SHA-256 的提交都必须遵守
[跨仓版本契约](docs/ARCHITECTURE.md)：先在 ProteinDigger 构建并验证 wheel，再只读确认
Suzhou2 队列和 running job 为空，创建新的不可变 Manager release/activation revision，
最后验证 probe 报告完全相同的 EasyDesign 版本和 wheel SHA。

Manager 源码版本、科学环境和模型资产不会因为 core wheel 更新而重装。存在运行任务时
只能等待自然结束，禁止终止、抢占或覆盖当前 activation。

## Git 边界

- 当前工程只在唯一 `main` 工作树开发；不得额外创建分支或 worktree。
- 提交前确认工作树只包含本任务文件，使用小型 Conventional Commit。
- 推送后核对本地 `HEAD`、`origin/main` 和 ahead/behind。
- 不删除或覆盖 `runtime/`、`runs/`、模型、环境、缓存、密钥或历史 manifest。
