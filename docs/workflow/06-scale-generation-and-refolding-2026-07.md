# Stage 06 2026-07 历史

## S06-001：分片式规模生成与 production plan

- 状态：`implemented`；APOE 1000 真实 smoke 等待 Stage 05 唯一 winner。
- 完成时间：2026-07-26T05:20:12+08:00
- 实现提交：`4ec71e2c5782b1651bc88f692e2349276af7a8de`。

### 完成内容

- `smoke-1000` 的 2×500、新候选语义，`production-50000` 的 20×2500 计划，25%
  磁盘余量门，稳定 shard/candidate identity，共享恢复执行，精确 merge、coverage
  report 和不可覆盖发布恢复。

### 验证证据

- `make check`、218 passed/8 skipped、wheel build 和 21/21 wheel 资产通过；非 APOE
  fixture 精确合并 1000 个新候选，资源不足在任务创建前失败，终态 artifact 可按
  identity/bytes 安全恢复。

### 遇到的问题

- 测试临时文件系统会真实触发容量门；Stage 06 初版容量估算缺少正式 Stage 04
  candidate-index 输入；发布中断可能遗留同名 artifact。

### 解决办法

- 测试显式模拟充足/不足磁盘而不削弱规则；candidate index 纳入 manifest 输入；只在
  模型 identity 和原始 bytes 完全一致时复用终态 artifact。

### 遗留问题

- APOE 只有在 Stage 05 唯一 winner 后才授权新 1000；50,000 仅实现计划和恢复能力，
  本轮禁止实际启动。

## VAL-002：APOE Stage 06 未运行边界

- 状态：本轮未运行；Stage 06 通用能力仍为 `implemented`。
- 完成时间：2026-07-26T09:13:48+08:00

### 完成内容

- 审计 APOE Stage 05 终态并冻结 Stage 06 未运行边界。
- 没有创建 1000-candidate task、shard 或伪造 ScaleManifest；50,000 仍未授权。

### 验证证据

- 上游 run `20260726-004-stage05-pilot-filter` 发布
  `stopped-no-scale-winner`，Stage05Bundle 的 `winner_strategy_id=null`。
- `scientific-stop.json` SHA-256：
  `96c71c085d23695c09decb56caf57b60e356d747b7eeb255dce674cee5c602af`。

### 遇到的问题

- Stage 06 通用实现已具备运行能力，但 APOE 没有可由 manifest-only 契约消费的唯一
  胜出策略。

### 解决办法

- 按 scientific-stop 契约终止 APOE 分支，不绕过 Stage 05、不手工指定 winner，也不
  将“未运行”误报为 operational failure。

### 遗留问题

- 只在新的合法 Stage 05 winner 到达后运行真实 `smoke-1000`；production 50,000
  继续等待独立授权。

## S06-003：远程协作执行闭环

- 状态：`implemented`；远程控制、同步和 UI 主线已完成工程 smoke，APOE 50k 本身继续运行。
- 完成时间：2026-07-27T12:53:23+08:00
- 实现提交：`1e3c4ae7742919cca5f909200d8ffa7bad7813d5`。

### 完成内容

- 补齐 whole-run SSH 的新项目提交、结构化 watch、停止后 resume、metadata/complete
  manifest 镜像和版本化远程 job record。
- BoltzGen 长任务增加 `TaskHeartbeat`，经 Stage 04/06 原子 progress 进入 CLI/UI；
  Stage 06 UI runtime 正确读取 `scale-state.json`。
- Workbench 可显式选择当前或 profile 远端，并在运行任务页刷新、同步和恢复远程任务。

### 验证证据

- `make check`、249 passed/8 skipped、dev12 wheel/console-script/package-data 通过。
- Chromium 1440×900、1920×1080 非视觉交互 18/18 通过。
- 对真实 Suzhou2 任务只读观察到 systemd `active/running`、8 running/12 pending、
  50,000 planned；metadata 同步 246 文件、59,263,753 bytes，RunManifest SHA-256 为
  `56a0d8c5ed32c45a17489b3d59a2635db0de40252a7c5013af0481a683a56a5e`。

### 遇到的问题

- 旧 dev11 worker 只在 task transition 更新进度，长时间运行时没有新时间戳或候选数；
  结果仍只在 Suzhou2，合作者控制端无法直接用同一 Workbench 查看。
- Stage 06 UI 的活动 state 文件名被误写成 Stage 04 的 `task-state.json`。

### 解决办法

- 新版由后端进程周期性发出不带候选数量的存活心跳；远程 watch 同时读取 systemd 和
  `runs watch --once --json`，避免把 SSH 连通当作任务健康。
- 同步只接受 manifest-derived 白名单并重新验证 SHA-256；旧运行保持兼容，不事后伪造
  heartbeat。UI 按 Stage 读取正确 state 文件。

### 遗留问题

- 当前 APOE worker 由 dev11 启动，直到自然结束都不会产生 dev12 heartbeat；新任务或
  合法 resume 才开始记录。50k 完成后仍需 complete 同步、精确 1..50000 merge 和
  ScaleBundle 终态验收。

## S06-004：晋级策略共享 50,000

- 状态：`implemented`；APOE 历史单策略 50k 已完成只读审计，尚未采用为 v1.6 输入。
- 完成时间：2026-07-31T02:44:27+08:00
- 契约提交：`277ab1cabbf866c0ae92398dc5d58c28dd3339a9`。
- 编排提交：`78bfe2200529d1e002f174233f4efcb84b39a0c4`。

### 完成内容

- 新增 ScalePlan/ScaleBundle 0.2、`equal-across-promoted-v1` 和逐策略 shard coverage。
- 1/2/3 个晋级策略分别分配 `50000`、`25000/25000`、
  `16667/16667/16666`；余数严格按 promotion rank 分配。
- candidate ID 同时携带 strategy identity 和策略内 ordinal；merge 同时验证每个策略
  与全局的数量、连续性、无重复和无缺口。
- 复用 Stage 04/06 的 GPU、事件、进度和恢复执行器，不建立第二套生成后端。

### 验证证据

- 分配、尾部分片、缺口、重复、策略错配和旧 ScaleBundle 兼容均进入自动测试；
  Stage 05–07 聚焦回归为 71 passed。
- 最终不可变快照 `stage0507-validation-20260731-022` 的 `make check`、`make test`
  和 `make build` 通过：`341 passed, 8 skipped`，Ruff 通过，strict mypy 检查
  142 个源文件无问题，dev27 wheel 及 console script/package data 验证通过。
- Workbench production build 通过；快照 `stage0507-validation-20260731-021`
  的 Chromium 1440×900/1920×1080 非视觉矩阵为 38 passed，视觉回归为 2 passed。
- Suzhou2 历史运行
  `20260727-001-stage06-tier-a-50k-suzhou2` 为 20×2500、50,000 候选；
  RunManifest SHA-256
  `54d90bb65d183bc9d7412e002e2765dd636d225bf42101a0c04073b874a43505`，
  ScaleBundle 0.1 SHA-256
  `dc63553e2f4eb9fd98b32c21c1fcdec4bb24cd2aa42b08b3f626162c283bfea8`，
  candidate index SHA-256
  `e75f809fa0f187b71c56c6f9bc873fa41ce2d2ecd6cc7d01c84b3d6c4353334c`。

### 遇到的问题

- “最多三组”容易被错误理解成每组 50,000；旧 APOE 50k 又属于 v1.5 科学停止后的
  manual override。

### 解决办法

- 将 50,000 固定为 ScalePlan 全局预算，并用不可变 EvidenceLink/adoption record
  引用历史证据；不复制 39 GB、不使用 symlink、不修改旧 manifest。

### 遗留问题

- VAL-007 adoption 尚未发布；需要第二真实案例验证 2–3 策略的真实共享运行。

## 2026-07-31 — VAL-007：Suzhou2 50k 不可变证据采用

- 状态：`smoke-validated`
- 完成时间：2026-07-31T12:48:00+08:00
- 提交：以本记录所在 `main` 提交和推送后核对的远端完整 SHA 为准。

### 完成内容

- 新增 `RunEvidenceLink`、policy reevaluation 与 scale evidence adoption；本地只保存
  manifest、checksum、统计和远程 executor 身份，不复制约 39 GB candidate 数据。
- 验证 Suzhou2 原运行 20/20 shard、50,000/50,000 candidate、唯一连续编号和来源
  strategy 一致后，允许 v1.6 continuation 只读消费该结果。
- UI 现在显示 Stage 06 已完成、100% 进度、20 个分片以及八张 GPU 的历史；旧 v1.5
  scientific stop 和 manual override 说明仍可审计。

### 遇到的问题

- 历史 50k 主体约 39 GB，位于 Suzhou2；直接复制会浪费空间，symlink 或按目录猜测又
  无法满足跨服务器 artifact、checksum 和 lineage 审计。

### 解决办法

- 新增不可变远程证据采用契约，逐一验证远端 manifest、任务、覆盖和候选索引，并只在
  本地保存 checksum、统计和 executor identity；源 run 与候选主体保持原位不改写。

### 验证证据

- 远端 RunManifest SHA-256
  `54d90bb65d183bc9d7412e002e2765dd636d225bf42101a0c04073b874a43505`。
- ScaleBundle SHA-256
  `dc63553e2f4eb9fd98b32c21c1fcdec4bb24cd2aa42b08b3f626162c283bfea8`。
- candidate index 为 542,420,436 bytes，SHA-256
  `e75f809fa0f187b71c56c6f9bc873fa41ce2d2ecd6cc7d01c84b3d6c4353334c`。
- GPU 0–3 各收集 7,500，GPU 4–7 各收集 5,000，总计 50,000。

### 遗留问题

- Stage 07 仍需在 Suzhou2 登记 Protenix/TNP 与模型，并在不终止其他任务的前提下完成
  adapter probe；多策略真实共享规模还需要第二个案例。
