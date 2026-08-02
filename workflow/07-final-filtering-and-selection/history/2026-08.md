# Stage 07 2026-08 历史

## ENG-031：Stage 06→07 受管原地交接

- 状态：`implemented`。
- 完成时间：2026-08-01T03:39:51+08:00
- 实现提交：`bede8e13f161987d5ce77658c73121ba0aeac5b5`。

### 完成内容

- Stage 07 可在 Suzhou2 直接消费 Stage 06 受管 run，无需把大型 candidate index 和结构主体先复制到控制端。
- `metadata` / `review` / `complete` 同步档位显式区分；`complete` 仍需用户主动选择。
- Stage 07 科学门槛、Protenix/TNP 需求和最终候选包契约未被执行位置改写。

### 验证证据

- 合同测试验证 managed source run 的路径边界、LATEST 内容与 RunManifest SHA-256。
- 与 Stage 04–06 同一批次的 386 个 Python 回归和 60 个 Workbench 功能回归通过。

### 遇到的问题

- 新 worker 尚未完成 Protenix/TNP 及必需模型资产的真实登记，因此不能把代码能力描述成 Stage 07 运行完成。

### 解决办法

- 保持 Stage 07 为 `implemented`，把真实后端、模型和单候选 adapter probe 明确留给 `VAL-008`。

### 遗留问题

- 经运维审阅并安装 worker 后，先执行 Stage 07 单候选探针，再决定何时原地消费已验证的历史 50k。

## ENG-032：probe 0.2 冻结三后端能力

- 状态：`implemented`；真实 Stage 07 smoke 继续归 `VAL-008`。
- 完成时间：2026-08-01T18:06:33+08:00
- 实现提交：以本记录所在 `main` 提交为准。

### 完成内容

- probe 0.2 显式报告 Manager/EasyDesign 版本、完整阶段链、BoltzGen、Protenix-v2、
  TNP、GPU/队列和磁盘状态。
- 主仓控制端在精确版本、两条链、三后端、8 GPU 或 5 GiB 磁盘门不满足时 fail closed。

### 验证证据

- probe golden JSON、后端锁/资产回执、运行 profile 绑定和缺失能力拒绝测试通过。

### 遇到的问题

- 只报告服务版本和 GPU 数不足以证明 Stage 07 需要的 Protenix/TNP 真实就绪。

### 解决办法

- Manager 从锁定环境、已校验模型副本和绝对 runtime profile 生成只读能力回执。

### 遗留问题

- 在真实 Manager 上完成 Protenix-v2/TNP adapter 和单 shard Stage 06→07 验收。

## S07-002 / VAL-008：APOE 8 条原地 Stage 07 空结果 smoke

- 状态：`smoke-validated`。
- 完成时间：2026-08-02T10:31:17+08:00
- 实现提交：以本记录所在 `main` 提交为准。

### 完成内容

- Suzhou2 Manager 真实原地消费同一作业 Stage 06 的精确 8 条候选，并发布 Stage 07
  终态 `stopped-no-final-candidate`、空 review package 和完整可审计证据。
- Manager 队列终态为 `succeeded`；唯一 GPU lease 已释放，队列和运行槽恢复为空。

### 验证证据

- 作业 ID：`val008-apoe-0607-smoke-20260802t0214z`。
- Stage 07 manifest SHA-256：
  `35ebb4fae86a23f9a66b0902d2533adcf692b6f6be79c3aec2ef7c2351f57b80`。
- 最终 RunManifest SHA-256：
  `bb54dd54592907bd43edcf1af156cf36ccd2878f955dd24a6e9528f5f7c90747`。
- FinalFilterReport SHA-256：
  `e185ef89aa94df4867f453aa512bd508a5ada9387994b40fb12a2aa84413be3e`；
  Stage07Bundle SHA-256：
  `c0d5fc04f19686bb30a87c068babfb40d48f15b37e0c2324da7ca270c3d4e6d1`。
- 8/8 candidate disposition 均为成功处理，0 个 operational failure；review-only 同步
  已落到控制端受管状态目录。

### 遇到的问题

- 8 条候选全部在官方 BoltzGen `pass_filters` 序列预筛被拒绝，因此本作业没有进入
  Protenix 深筛、consensus 或 TNP 调用。

### 解决办法

- 如实保留科学停止和空候选包，不降低阈值、不伪造赢家，也不把“后端 probe ready”
  描述成“本次已调用所有后端”。

### 遗留问题

- 用第二条合法 Tier A 真实目标验证非空候选的 Protenix/TNP 深筛路径。
- 历史 APOE 50k 的 Stage 07 仍是独立高成本授权事项，不因本次 8 条 smoke 自动启动。
