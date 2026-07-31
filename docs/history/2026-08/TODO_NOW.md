# 2026-08 项目历史

本文件归档跨阶段工作；各 Stage 的详细证据仍以对应
`workflow/*/history/2026-08.md` 为准。

## 2026-08-01 — ENG-030 / ENG-031 / UX-008 / UI-022：双执行与 Suzhou2 统一队列

- 状态：`implemented`。
- 完成时间：2026-08-01T03:39:51+08:00
- 问题：Stage 04/06 既要在当前 GPU 机器自动分配，又要使已获授权的无本地算力用户通过 Suzhou2 运行；旧 SSH 路径缺少统一队列、一卡一租约和大数据原地交接。
- 方案：引入非科学 `ExecutionTarget`、本机 GPU 发现/租约、Suzhou2 `RemoteJobBundle`/Managed Worker、独立 SSH key 与 host fingerprint 配对、逻辑解绑、结构化观察及 metadata/review/complete 同步。
- 安全边界：新 worker 只能写 `/data/easydesign/managed-worker`；旧 `/data/easydesign`、APOE 50k、旧环境和 `/root/Easydesign/Easycontrol` 均保持原样。本任务没有执行删除、移动、覆盖、进程终止或系统代理修改。
- 验证：386 passed/8 skipped；Ruff 通过；149 个源文件 mypy 通过；Workbench 非视觉 60/60；Target Viewer 3 passed/2 skipped；dev32 wheel SHA-256 `50a9a1369ddce8106fbbec3cda7e51b4407493403b83e518a6d89f207480855b` 且资产/console script smoke 通过。
- 遗留边界：本轮达到工程 `implemented`，不伪装 Suzhou2 已部署。`VAL-008` 继续负责 systemd unit 人工审阅、专用 key 配对、本机极小 Stage 04、Suzhou2 极小 Stage 04、Stage 06 单 shard 和 Stage 07 adapter probe。
- 实现提交：`bede8e13f161987d5ce77658c73121ba0aeac5b5`。
