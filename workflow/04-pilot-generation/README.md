# 04 — 小批量生成

**状态：** `smoke-validated`

**契约版本：** `0.1`

## 目的

Stage 04 消费 Stage 03 当前 manifest 声明的 `StrategyBundle`，为每个策略执行相同、
有边界的完整 BoltzGen pilot。它负责后端执行、任务状态、恢复、进度和候选完整性，不负责
筛选策略或宣布科学赢家。

```text
StrategyBundle
→ PilotPlan
→ local-current-host 或 managed-ssh executor
→ BoltzGen full pipeline
→ candidate completeness collection
→ PilotBundle + CandidateIndex
```

## 1. 使用场景与边界

EasyDesign 1.0 的主线是：

- BoltzGen `0.3.2`，源码 commit
  `a3149cf18eeb58648d1abbb27539bd73f746cdda`。
- `nanobody-anything` protocol。
- 每个物理 GPU 同时只运行一个 strategy。
- 每个策略收集配置声明数量的完整候选；APOE 首个案例为 40。
- 完整执行 `design → inverse_folding → folding → analysis → filtering`。
- 任务、日志、原始输出和失败均保留。

本阶段不做：

- Stage 05 的 scientific hard gate、Tier 或策略排名。
- production 规模生成。
- Slurm/SMART 调度。
- 伪造 BoltzGen 0.3.2 不支持的随机种子。
- 从目录中挑看起来“最好”的文件作为成功。

Stage 04 与 Stage 05 的扩展生成共用
`orchestration.boltzgen_tasks.execute_boltzgen_candidate_task`。它统一负责 deficit、不可变
task attempt、严格收集、错误分类和 collection report；后续阶段不得复制一套近似执行器。

## 2. 输入

Stage 04 只读取当前 RunManifest 声明、通过 SHA-256 验证的 Stage 03 manifest，并从其
正式输出读取：

- `strategy-bundle.json`；
- `design-matrix.json`；
- 每个 strategy 的 `design.yaml` 和 `strategy-manifest.json`；
- Stage 03 记录的 BoltzGen/backend/scaffold 身份。

用户配置：

```yaml
stage04:
  backend: boltzgen-0.3.2
  executor:
    type: local-multi-gpu
    workers_per_device: 1
  required_complete_candidates_per_strategy: 40
```

`workers_per_device` 在 1.0 固定为 `1`。它表示一个物理 GPU 同时运行一个独立 strategy，
不是 BoltzGen DataLoader worker 数量。

`devices` 可省略；此时在真正创建 attempt 前根据当前主机的 GPU 、显存、外部进程和
EasyDesign 租约自动冻结可用设备。用户显式填写 `devices` 时仍只能使用通过资源检查的
卡。“当前机器 / Suzhou2”是运行时 `ExecutionTarget`，不进入这份科学 YAML。

## 3. 固定科学参数

每个 strategy 使用同一组版本化参数：

| 参数 | 1.0 值 |
| --- | --- |
| protocol | `nanobody-anything` |
| inverse-fold sequences/backbone | `1` |
| design checkpoints | BoltzGen 0.3.2 默认 diverse + adherence pair |
| folding checkpoint | BoltzGen 0.3.2 默认 `boltz2_conf_final.ckpt` |
| filter budget | `30` |
| alpha | `0.001` |
| filter biased | `true` |
| devices inside one task | `1` |

`filter budget=30` 只控制 BoltzGen 官方最终多样性目录，不表示 EasyDesign 只保留 30 个
候选。Stage 04 收集完整的候选池，Stage 05 再独立执行 Nanobody Filter Standard。

BoltzGen 0.3.2 没有可靠的公开 seed 参数，因此 manifest 必须记录：

```text
random_seed_status: unsupported-by-boltzgen-0.3.2
```

不得填入虚构 seed 或宣称 bitwise deterministic。

## 4. 任务、GPU 与执行

### 4.1 TaskRecord

每个 strategy 对应一个稳定 `TaskRecord`：

- task/strategy identity；
- 请求和已收集候选数；
- 当前状态；
- 每次执行 attempt 的 GPU、命令摘要、开始/结束时间和结构化错误；
- backend output 相对路径；
- candidate identities。

重试不会覆盖旧 attempt。一个未达标 strategy 可以在新 task attempt 中只请求 deficit；
旧 attempt 中完整且 checksum 正确的候选不重跑。

### 4.2 GPU 门槛

启动真实任务前执行 `nvidia-smi`：

- 请求的 device 必须存在；
- GPU 不得有外部计算进程；
- 显存占用和利用率必须低于 executor 的固定启动门槛；
- EasyDesign 不终止、不暂停、不迁移其他进程。

资源未满足时进入显式等待；达到有界等待期限仍不可用时是 operational failure，不是
“没有科学候选”。

每个 worker 通过无 shell subprocess 调用 BoltzGen，并只给子进程设置对应的
`CUDA_VISIBLE_DEVICES`。一个 task 内传递 `--devices 1`，避免把物理 GPU 编号误当作
后端的本地可见编号。

## 5. 进度与事件

运行中的 attempt 原子更新：

```text
04-pilot-generation/attempt-XXXX/runtime/
├── progress.json
├── task-state.json
└── task-events.jsonl
```

- `progress.json` 使用临时文件、`fsync` 和原子 rename。
- `task-events.jsonl` 只追加，每行是一个完整 JSON event。
- event 记录 sequence、时间、task、attempt、状态变化、GPU 和错误。
- elapsed time 使用 attempt 创建时间到当前快照的累计 wall-clock 时间；resume 和短暂
  停机不会把历史候选错误地当成本次进程刚刚生成。
- `easydesign runs watch` 只读这两个文件，不解析终端文本、不扫描候选目录。
- 吞吐率与 ETA 是运行时估算，不构成科学结果。

## 6. 候选完整性

一个 BoltzGen candidate 只有同时满足下列条件才是 `complete`：

1. `final_ranked_designs/all_designs_metrics.csv` 中存在唯一 candidate 行；
2. 行内 `id` 和 `file_name` 非空且没有歧义；
3. `intermediate_designs_inverse_folded/<file_name>` 是可读非空 mmCIF；
4. `intermediate_designs_inverse_folded/refold_cif/<file_name>` 是可读非空 mmCIF；
5. 同 stem 的官方 NPZ 存在逐 token `design_mask`，且能唯一映射到 binder residue；
6. mask 复原序列必须与 CSV 的 `designed_sequence` 完全一致；
7. 三个文件均保存大小和 SHA-256；
8. candidate identity 在整个 Stage 04 内唯一，并可回溯到 strategy/task/task-attempt。

缺行、重复 ID、缺失原始/refold/mask 证据、零字节文件、CSV 损坏和数量不足都必须明确
记录。不得仅从拼接后的 `designed_sequence` 反推 CDR 位置，因为重复序列会产生多个合法
字符串分割；Stage 05 只消费 Stage 04 已验证并声明 checksum 的官方 `design_mask` 结果。
不能用启动次数、任意目录数、官方 final budget 或仅成功的日志代替完整候选数。

官方 `pass_filters` 被原样保存为指标证据，但不影响 Stage 04 的完整性判断和任务成功。

## 7. 输出

终态 attempt 发布：

```text
04-pilot-generation/attempt-XXXX/
├── runtime/
│   ├── progress.json
│   ├── task-state.json
│   └── task-events.jsonl
├── tasks/<task_id>/attempt-XXXX/
│   ├── backend-output/
│   ├── stdout.log
│   ├── stderr.log
│   └── collection-report.json
└── artifacts/
    ├── pilot-bundle.json
    ├── pilot-plan.json
    ├── task-table.json
    ├── candidate-index.json
    ├── progress-final.json
    ├── task-events.jsonl
    ├── backend-environment.json
    └── stage-manifest.json
```

`CandidateIndex` 是 Stage 05 的唯一候选入口。它包含每个候选的 strategy lineage、原始和
refold 结构相对 ArtifactRef、官方 design-mask ArtifactRef、binder designed residue
identity、对应 metric row、完整性和来源 task attempt。

原始 backend output 不提交 Git，不被收集器改写。Stage 04 artifact 记录实际使用的
backend、commit、模型/checkpoint、molecule dataset、GPU 和执行参数身份。

## 8. 成功、科学停止与软件失败

Stage 04 没有科学筛选停止状态。

成功要求：

- 所有 strategy 都达到
  `required_complete_candidates_per_strategy`；
- 所有 TaskRecord 是终态 succeeded；
- candidate index 数量、唯一性、文件大小和 SHA-256 校验通过；
- 计划、事件、进度终态和 backend environment 已发布；
- StageManifest 和 RunManifest 引用完整。

以下是 operational failure：

- backend/version/commit/model 或 GPU 能力不符合；
- subprocess 非零退出、超时或被中断；
- 输出损坏、候选不完整或数量不足；
- 任务、候选或 strategy identity 冲突；
- checksum 或 manifest 不一致；
- 全部有界重试后仍未达标。

失败 attempt 必须保留；恢复执行只能建立新的 task attempt，并在最终 artifact 中保留完整
历史。

## 9. 恢复

```bash
easydesign runs show RUN_DIR
easydesign runs watch RUN_DIR
easydesign runs resume RUN_DIR
```

`resume` 的规则：

- 只接受 RunManifest 与 Stage 03 handoff 完整的运行；
- 验证已完成候选全部 checksum；
- 旧 runtime state 缺少 design-mask 证据时，只从 TaskRecord 已声明的 backend output
  重新收集并核对原 candidate identity，不重跑已完成候选；
- 已达标 strategy 不启动新任务；
- 未达标 strategy 请求 deficit，并建立新 task attempt；
- 不覆盖旧日志、配置或 backend output；
- 最终再次执行全局数量和 identity 校验。

## 10. CLI 示例

```bash
easydesign run easydesign.yaml \
  --from-run runs/project/stage03-run \
  --run-id stage04-pilot

easydesign runs watch runs/project/stage04-pilot
easydesign runs resume runs/project/stage04-pilot
```

CLI 只调用 orchestration API；科学参数只能来自 canonical YAML。

## 11. 完成门槛

工程 `smoke-validated` 需要：

- TaskRecord、ProgressSnapshot、append-only event 和 resume 单元测试；
- 非 APOE fixture 覆盖不同 strategy 数量、budget、失败和恢复；
- 固定 BoltzGen 环境的最小真实 backend smoke；
- APOE 21 个策略各 40 个完整候选，共 840 个；
- 全部候选有唯一 lineage、两份结构和 metric row；
- `make check`、`make test`、`make build` 和 wheel CLI smoke 通过。

这不表示 APOE candidate 通过 Stage 05，也不表示科学或实验验证。

## 12. 后续工作

- Slurm/SMART executor。
- 更多受管算力池和设备类型。
- 后端可控 seed（需 BoltzGen 正式支持或经验证 patch）。
- 更细的后端 step checkpoint/restart。
- 多节点 artifact store。

## 13. 双执行位置

Stage 04 的 plan、TaskRecord、CandidateRecord、ProgressSnapshot 和 manifest 不因运行位置
改变。产品层只在创建 attempt 前选择：

```yaml
execution_target:
  type: local-current-host
```

或：

```yaml
execution_target:
  type: managed-ssh
  executor_id: suzhou2
```

这是非科学运行记录，不写入 canonical scientific config。

### 当前机器

- `nvidia-smi` 只读发现 GPU、显存、利用率和运行进程。
- 默认使用全部符合门槛的 GPU；非科学运行选项可限制最大卡数。
- 已被外部进程占用或已有 EasyDesign 租约的 GPU 不会被抢占；无空闲卡时进入
  `waiting-for-resources`，不写成运行失败。
- 租约 revision 记录 run、stage、task/job、PID、heartbeat 和时间；同一 GPU 不会同时
  分配给两个 EasyDesign 任务。

### Suzhou2 受管队列

- 配对前先核对 host fingerprint；控制端复用当前工作区已有的完整 SSH key pair。
  初次授权可在 localhost UI 中输入一次性 Suzhou2 密码，受控 SSH 会话幂等安装公钥后
  立即切换为专用密钥探测；密码不持久化，手动安装公钥仍可回退。
- 控制端只提交通过 schema、SHA-256、版本和资产校验的 `RemoteJobBundle`，
  不提供任意 shell 字段。
- worker 持久根固定为 `/data/easydesign/managed-worker`；`/root/Easydesign/Easycontrol`
  和旧 `/data/easydesign` 运行均保持不动。
- 队列状态和 GPU 租约使用 `flock` 与只追加 revision；服务重启后对账
  queued/admitting/running 任务，不根据目录或终端文本猜测。
- 远端 Stage 04 成功后直接在同一受管 run 执行 Stage 05。控制端运行中只同步
  metadata，默认完成后同步 review 证据，不往返复制候选主体。
