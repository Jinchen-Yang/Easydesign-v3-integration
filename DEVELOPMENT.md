# EasyDesign Local 开发指南

[使用入口](README.md) · [开发 Agent 必读](docs/agent/DEVELOPMENT_AGENT.md) · [数据安全](DATA_SAFETY.md)

## 独立分支

本产品永久位于 `easydesign-local` 和独立 worktree，不整体 merge 回 UI `main`。开发与
运行只作用于当前 clone 所在的本地 Linux GPU 主机；不得调用旧 UI、远程 executor、受管
队列或其他执行主机，也不得发布 UI wheel。

clone 可以位于用户选择的任意数据盘目录。代码、文档和测试通过根
`easydesign-workspace.yaml` 发现工作区，并使用 `runtime/`、`workspace/` 等相对路径；不得
把某台开发机的主机名或 clone 绝对路径写成产品前提。

```bash
./scripts/bootstrap.py --index auto
source .venv/bin/activate
easydesign --version
```

Makefile 只使用仓库 `.venv`，不存在时明确失败，不回退系统 Python 或旧 Conda core。
`uv.lock` 是唯一依赖解析；`config/bootstrap-indexes.json` 只声明下载端点。bootstrap 从 lock
导出 hash-pinned requirements、同步依赖、以 editable 模式安装当前源码，再执行
`uv sync --frozen --extra dev --check`。安装 receipt 位于 `runtime/state/bootstrap/`，不得写入
凭据；自定义源必须显式使用无凭据的 HTTPS URL。

## 最小上下文

```bash
.venv/bin/python scripts/dev.py context \
  --mode dev-local \
  --path src/easydesign/cli.py
```

保存 `policy_bundle_id`。同一逻辑任务后续传 `--known-bundle-id`，只在规则或路径范围改变时
补读指南。路由由 `config/development-policy.json` 定义。

## 风险分级验证

```bash
.venv/bin/python scripts/dev.py verify --mode dev-local
.venv/bin/python scripts/dev.py verify --mode integration
```

- `dev-local`：diff/结构、changed-file Ruff/compile、全包 mypy 和路径聚焦测试。
- `integration`：完整 Python 回归；reporting/Viewer 变更增加 Chromium 回归。
- `release`：仅构建本地产品 staging wheel，不存在 UI 或远程 activation。

兼容入口：

```bash
make check
make test
make test-web
make verify-integration
make build-wheel-staging
```

构建只写 `runtime/builds/`，不写原仓库 `dist/`，不发布正式 UI 静态资产。

## 科学核心同步

`core/`、`stages/`、`filtering/` 和科学 backend 的可共享修复必须单独提交，subject 以
`core:` 开头：

```bash
.venv/bin/python scripts/dev.py core-sync-report --against main
```

报告只读列出共享路径差异。UI 恢复开发时逐个评审/cherry-pick `core:` commit，并在两条
分支各跑 integration；本地产品壳、UI/remote 删除提交永不回 main。

## Runtime 与测试隔离

开发 cache、pytest temp、浏览器和构建产物都写本 worktree `runtime/`。逐组件安装只写
当前 clone，profile/backend 路径不得引用其他 clone。测试应使用合成 registry/asset fixture，
不修改真实 env/model。真实 Stage 1/2 smoke 只写 `runtime/validation/` 与本 worktree
`workspace/`。

`scripts/dev.py cleanup-report` 只盘点，不自动删除。APOE evidence、科学 runs、manifest、
共享 env/model 和唯一资产始终受保护。

提交前运行 `git diff --check`，核对 APOE subtree hash 和结构检查；推送只能指向
`origin/easydesign-local`。
