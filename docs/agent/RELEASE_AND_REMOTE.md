# Agent 指南：发布与远程

仅在版本、依赖、package data、正式 wheel、18769、SSH executor、Manager 或 systemd
任务中读取。普通开发不得自动进入本指南的发布动作。

## 开发与发布分离

- 普通 main 提交保持 `pyproject.toml` 当前版本，不生成正式 wheel，不更新 18769 或 Manager。
- `pyproject.toml` 是唯一正式版本来源；检查、fixture、README、Makefile 不硬编码当前版本。
- 只有用户明确要求 `release` 才统一升版、更新 lock、发布 UI 静态资产并构建 wheel。
- 发布前先完成全部源码/UI 用户视角验收，再冻结 diff 和升版，避免一次任务连续发布版本。

## 正式 artifact 与 activation

- 正式 wheel 必须来自 clean main，保存 SHA-256，且同一版本不得发布不同 identity。
- ProteinDigger 正式 UI 只使用 append-only local release activation；旧 release 保留。
- Manager 只安装与本机正式 release 完全相同 SHA-256 的 wheel；不重装科学环境或模型。
- 激活前确认相关队列/任务无冲突；失败 release 进入 quarantine，不改变当前 activation。
- 激活后验证版本、wheel SHA、systemd 稳定、后端、磁盘、阶段链和逐卡 probe。
- SSH 断线只代表观察中断；不得杀死远端任务、重建候选或把它改写为失败。

## Git

- release 通过全部门后形成清楚的 Conventional Commit 并只推送 `main`。
- push 后再次核对远端 SHA；网络/权限失败时报告未推送 commit，不新建 remote 或分支。
