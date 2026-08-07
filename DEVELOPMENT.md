# EasyDesign 开发指南

[安装主路径](README.md) · [Agent 协议](AGENTS.md) · [数据安全](DATA_SAFETY.md)

## 环境

Core、CLI、UI 和检查工具统一使用仓库 `.venv`；科学后端继续使用 `environments/` 中的
独立 lock。

```bash
uv sync --frozen --extra ui --extra dev
.venv/bin/python -m easydesign --version
```

`.python-version` 固定首选 Python 3.11，契约同时支持 3.12。Makefile 不回退到系统 Python
或旧 Conda core；缺少 `.venv` 时会直接提示运行 `uv sync`。

## 选择任务模式并领取上下文

普通开发默认 `dev-local`；公共科学契约或 managed protocol 使用 `integration`；只有明确
发布才用 `release`，明确运维才用 `ops`。

```bash
.venv/bin/python scripts/dev.py context \
  --mode dev-local \
  --path src/easydesign/ui/app.py
```

首次读取输出中的 `required_reading` 并保存 `policy_bundle_id`。同一逻辑任务后续轮次只复核：

```bash
.venv/bin/python scripts/dev.py context \
  --mode dev-local \
  --path src/easydesign/ui/app.py \
  --known-bundle-id BUNDLE_ID
```

ID 未变化时 `required_reading` 为空。任务进入新子系统时追加 `--path`，只补读新增指南。

## 风险分级验证

```bash
.venv/bin/python scripts/dev.py verify --mode dev-local
.venv/bin/python scripts/dev.py verify --mode integration
.venv/bin/python scripts/dev.py verify --mode release
```

- `dev-local`：diff/结构检查、changed-file Ruff/compile、全包 mypy 和路径映射聚焦测试。
- `integration`：完整 Python 回归；UI 相关变更增加 Chromium 回归。
- `release`：完整 Python/Web/build/wheel 门；只能在用户明确要求发布时运行。

模式低于路径风险时验证器返回 `required_mode`，不会自动升级或执行发布动作。兼容入口仍可用：

```bash
make check
make test
make verify-fast
make verify-integration
```

运行时空间只通过只读报告治理，不自动删除：

```bash
.venv/bin/python scripts/dev.py cleanup-report
```

报告按预算列出最大目录，并将达到年龄阈值的 staging 标为 `retention-review`；该状态不构成
删除授权。`examples/apoe-ui-demo/`、workspace 项目与 run、环境、模型和状态始终列入保护清单。
quarantine、下载 cache 与 wheel 永远要求人工完成引用和活动进程审计。

## UI 与构建边界

开发 UI 使用 18770，带明确 development 标识并禁用 Suzhou2/Managed Worker：

```bash
.venv/bin/python scripts/dev.py ui
```

日常构建只写未跟踪的 `runtime/` staging：

```bash
make build-ui-staging
make build-wheel-staging
make test-web-chromium
make test-web
```

这些目标不更新 `src/easydesign/ui/static/` 或 `dist/`。正式静态资产与 wheel 只有显式门可写：

```bash
make release-build RELEASE=1
```

旧 `make build`/`make build-ui` 会在缺少 `RELEASE=1` 时拒绝。reporting-web 的 node/npm/pnpm
由 workspace environment registry 解析，不要求修改 shell PATH。

## 版本、文档与 Git

`pyproject.toml` 是唯一正式版本来源。普通 main 提交不升版、不更新 lock、不构建正式 wheel；
release 才统一更新版本、lock、正式静态资产和 wheel。README、fixture、检查脚本和前端私有
package 不复制当前开发版本。

普通 bugfix 通过 commit 与测试结果留痕。只有路线图状态、Stage 契约、验证等级或 Blocked
实际变化时才更新 TODO/STATUS/history。提交前核对 scoped diff 和 `git diff --check`，推送前
fetch 并检查 ahead/behind，推送后确认 `HEAD == origin/main`。

CI 在 Ubuntu/Python 3.11 跑完整 Python 回归，macOS 与 Python 3.11/3.12 矩阵保留 focused
smoke。CI 状态可读取时等待终态；不可读取时明确报告 commit 和 pending 状态。

## Immutable 正式 UI release

以下命令只属于用户明确授权的 `release`/`ops`，普通开发禁止调用：

```bash
.venv/bin/python scripts/local_ui_release.py prepare --wheel dist/FILE.whl --confirmed
.venv/bin/python scripts/local_ui_release.py activate --release-id VERSION-SHA256 --confirmed
.venv/bin/python scripts/local_ui_release.py status
.venv/bin/python scripts/local_ui_release.py manager-wheel
```

prepare 在 `runtime/releases/local-ui/` 发布由版本与 wheel SHA-256 命名的全新非 editable
venv。activate 在新 release 真实 health 成功后才追加 revision；失败保持原 activation 并
恢复旧 UI。rollback 使用同一事务追加指向旧 release 的 revision。固定 18769 服务应执行
`local_ui_release.py serve-active`，Manager 只消费 `manager-wheel` 报告的同一 wheel。
