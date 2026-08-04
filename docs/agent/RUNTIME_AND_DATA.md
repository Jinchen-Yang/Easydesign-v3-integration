# Agent 指南：运行时与数据

修改 workspace、setup、registry、环境、模型、资产、run、迁移、归档或任何潜在破坏性
操作前，必须完整阅读根 `DATA_SAFETY.md`。

## 写入边界

- 正常写入只允许当前 workspace 的 `runtime/`、`projects/`、`runs/`、`archives/` 和明确
  Git 操作；外部输入与 SSH key 只读。
- 禁止删除、覆盖、删除式同步、系统清理、环境移除和修改 shell/profile/系统代理/证书。
- 新环境、模型、release、registry revision 和 artifact 先写不存在的 staging，校验后
  原子发布；失败 staging 进入 quarantine，旧内容保留。
- mutable registry/index 使用 append-only revision；损坏的新 revision 不遮蔽旧合法值。
- 环境 available 必须同时满足 lock、inventory、版本探针和所有必需资产许可/SHA。
- UI upload、项目、run、归档和恢复遵守 manifest/ArtifactRef 闭包，不创建空成功壳。

## Git 与历史数据

- `runs/`、环境、模型、cache、quarantine、密钥和历史证据不得提交或自动清理。
- 已锁定、detached 且提交进入 main 的历史 worktree 可保留只读；未知 worktree/branch
  先审计，不以“单一 main”为删除授权。
- ops 只完成用户要求的部署/恢复/观察，不顺带修改代码或清理资源。
