# 06 — 分片式规模生成与复折叠

**状态：** `implemented`

**契约版本：** `0.1`

**实现任务：** `S06-001`、`S06-002`

## 目的

Stage 06 只做一件事：把 Stage 05 唯一批准的策略，或负责人明确授权的已扩展 Tier A，
按已授权预算生成一批全新的、完整且可追溯的 BoltzGen 候选，并把它们无缺口地交给
Stage 07。

本阶段不会重新选择策略，也不会把 Stage 04/05 的候选计入 scale 数量。当前
`smoke-1000` 必须新生成 1000 个候选；`production-50000` 是可规划、可恢复的正式规模
profile。APOE 于 2026-07-27 获得一次独立的人工作为探索性生成的真实 50k 授权；该授权
不改变 Stage 05 科学停止。

这里的“复折叠”指固定 BoltzGen 0.3.2 pipeline 内的 folding/refolding/analysis 产物。
多 seed Protenix 深度复合物预测属于 Stage 07，不能混入 Stage 06。

## 输入与读取边界

Stage 06 只读取当前 `RunManifest` 声明且逐一通过大小与 SHA-256 校验的：

- Stage 03 `StrategyBundle` 和唯一胜出策略的 `design.yaml`；
- Stage 04 `CandidateIndex`，仅用于冻结实测候选磁盘基线；
- Stage 05 `Stage05Bundle`；
- schema 0.7 的 `stage04.executor` 与 `stage06` 配置；
- runtime profile 显式声明的 BoltzGen backend。

默认要求 `winner-selected`。`stopped-no-scale-winner` 只有在配置提供双重确认的
`manual_strategy_authorization` 时才能选择 Stage 05 已经扩展过的 Tier A；Stage 05
结论不被重写。`stopped-no-tier-a` 永远不得越过。代码不扫描上游目录猜策略，也不从
文件名推断候选。

## 配置

当前真实 smoke：

```yaml
stage06:
  scale_profile: smoke-1000
  preauthorized_candidate_limit: 1000
```

production profile：

```yaml
stage06:
  scale_profile: production-50000
  preauthorized_candidate_limit: 50000
  manual_strategy_authorization:
    strategy_id: selected-tier-a-strategy
    authorized_by: principal-investigator
    reason: "Exploratory scale generation despite the frozen Stage 05 scientific stop."
    source_stage05_bundle_sha256: 64-character-lowercase-sha256
    acknowledge_stage05_scientific_stop: true
    acknowledge_not_scientifically_eligible: true
```

profile 冻结以下布局：

| Profile | 新候选总数 | Shard 数 | 每 shard 数 | 本轮真实授权 |
| --- | ---: | ---: | ---: | --- |
| `smoke-1000` | 1,000 | 2 | 500 | 是 |
| `production-50000` | 50,000 | 20 | 2,500 | 必须逐 run 显式授权 |

`preauthorized_candidate_limit` 小于 profile 规模时配置校验直接失败。50,000 不是代码中
到处散落的常数，而是 `ScaleProfile` 的一个版本化能力。

人工 override 不是补写 `winner_strategy_id`：系统会发布
`scale-strategy-authorization.json`，保存授权人、理由、Stage05Bundle SHA-256、
`stopped-no-scale-winner` 与双重 acknowledgement。它只批准生成预算，不表示候选通过
Protenix 或具备实验成功概率。

## 执行流程

```text
验证 Stage 03/04/05 manifest 和 artifact
→ 验证唯一 Stage 05 winner 与其 design.yaml identity
→ 从 Stage 04 声明的 candidate artifact 计算磁盘基线
→ 检查执行后是否仍保留文件系统总容量的 25%
→ 冻结 ScalePlan 和稳定 shard/task/ordinal identity
→ 等待显式 GPU 空闲门
→ 每张 GPU 同时最多执行一个 shard
→ 严格收集完整候选并原子更新 progress/state
→ 合并时检查 candidate identity、ordinal 无重复且无缺口
→ 发布精确 1000/50000 个“全新候选”的 ScaleBundle
```

### 1. 资源预检

`ScaleResourceReport` 从 Stage 04 `CandidateIndex` 中声明的 original structure、
refolded structure 和 design mask 的实际字节数计算每候选基线。当前 v0.1 使用固定
`20×` 安全倍数，覆盖后端私有中间产物、日志和基线低估；它是保守容量代理，不是对未来
每个 BoltzGen 版本的精确磁盘预测。

只有同时满足以下条件才冻结计划并创建任务：

- 当前可用空间足以容纳估计峰值；
- 扣除估计峰值后仍至少保留文件系统总容量的 25%。

资源失败发生在任务创建前，属于 operational failure；不能伪装成“生成了零候选”。
真正启动任务前再次读取当前磁盘状态，防止预检后被其他任务占满。

### 2. 稳定分片与身份

`ScalePlan` 保存：

- 胜出 strategy、Stage 03/05 SHA-256 和 design specification `ArtifactRef`；
- profile、预授权上限、GPU 和 `workers_per_device=1`；
- 每个 shard 的稳定 ID、task ID、候选 ordinal 起止和数量；
- 冻结的资源报告 identity。
- 正常 Stage 05 winner 或人工探索性 override 的完整授权 identity。

`smoke-1000` 的两个 shard 固定覆盖 `1–500` 与 `501–1000`；
`production-50000` 的二十个 shard 连续覆盖 `1–50000`。ordinal 断裂、重叠、重复 task
或超出授权都会在执行前失败。

### 3. BoltzGen 与多 GPU

Stage 06 复用 Stage 04 的同一 BoltzGen adapter、严格 collector、任务状态机和多 GPU
executor，不维护第二套生成逻辑：

```text
design
→ inverse_folding
→ folding
→ analysis
→ filtering
```

固定后端仍是 BoltzGen `0.3.2` 与 commit
`a3149cf18eeb58648d1abbb27539bd73f746cdda`。每张 GPU 同时只运行一个重型 shard；
执行器只等待资源，不终止服务器上的其他进程。BoltzGen 0.3.2 没有可靠公开 seed，
因此 provenance 如实保存
`random_seed_status: unsupported-by-boltzgen-0.3.2`。

运行可位于本机，也可由控制端通过 `easydesign remote submit` 复制整个 succeeded
continuation source 到另一台服务器。SSH 只负责提交；远端仍使用本节的
`local-multi-gpu` executor，并独立写 manifest、progress 和 events。断开 SSH 不会终止
systemd worker。

### 4. 恢复与不可变发布

- `progress.json` 和 `scale-state.json` 原子替换；
- `task-events.jsonl` 只追加，不解析终端文本；
- 每个 shard/task attempt 有独立目录、命令、日志和终态；
- 中断后先严格收集完整候选，再建立新 attempt 补足差额；
- checksum 正确的候选绝不重跑；
- 已失败且未达标的 shard 可在显式 resume 中重试；
- 发布途中崩溃后，已有终态 artifact 必须身份一致才可复用，禁止覆盖或静默采用；
- `requested_new_candidates` 未精确完成时不发布成功 StageManifest。

merge 只接受候选 ordinal `1..N` 连续、candidate ID 唯一、backend lineage 唯一且全部
结构/design-mask checksum 正确的集合。

## 公共类型

Stage 06 版本化并导出：

- `ScaleProfile`：1000/50000 profile；
- `ScaleShard`：稳定分片与 ordinal 范围；
- `ScaleResourceReport`：容量测量、估算和 25% 门；
- `ScalePlan`：获得授权的完整执行计划；
- `ScaleTaskTable` / `ScaleExecutionState`：终态与可恢复运行状态；
- `ScaleCoverageReport`：无重复、无缺口的 merge 证明；
- `ScaleBundle`：Stage 07 唯一交接。

通用 `TaskRecord`、`CandidateRecord`、`ProgressSnapshot` 和事件类型与 Stage 04/05 共用。

## 输出

```text
06-scale-generation-and-refolding/attempt-0001/
├── artifacts/
│   ├── resource-report.json
│   ├── scale-strategy-authorization.json
│   ├── scale-plan.json
│   ├── scale-task-table.json
│   ├── scale-candidate-index.json
│   ├── scale-coverage-report.json
│   ├── progress-final.json
│   ├── task-events.jsonl
│   ├── backend-environment.json
│   ├── scale-bundle.json
│   └── stage-manifest.json
├── runtime/
│   ├── resource-preflight.json
│   ├── scale-state.json
│   ├── progress.json
│   └── task-events.jsonl
└── tasks/
    └── scale-shard-XXXX/
        └── attempt-XXXX/
```

`ScaleBundle` 同时引用 plan、资源门、task table、candidate index、coverage、terminal
progress、append-only events、backend environment 和 scale authority。Stage 07 只能通过当前
StageManifest 声明的 `ScaleBundle`/`CandidateIndex` 消费结果。

## CLI

统一入口会在 Stage 05 有唯一 winner 时继续：

```bash
easydesign run easydesign.yaml
easydesign runs watch RUN_DIR
easydesign runs resume RUN_DIR
easydesign runs show RUN_DIR

# 控制端提交到显式 SSH executor
easydesign remote probe REMOTE_ID
easydesign remote submit REMOTE_ID \
  --job-id JOB_ID --run-id RUN_ID \
  --config easydesign.yaml --from-run SUCCEEDED_STAGE05_RUN
easydesign remote status REMOTE_ID JOB_ID
```

`watch` 只读取结构化 progress；显示 stage、phase、总数、成功/失败/重试、GPU 分配、
吞吐率与 ETA。CLI 不包含分片、资源或科学逻辑。

## 科学停止与软件失败

Stage 06 本身没有“候选质量不足”的科学筛选；科学 go/no-go 已在 Stage 05，最终筛选在
Stage 07。

以下属于 operational failure：

- 上游 winner、manifest 或 checksum 不一致；
- 配置规模超过预授权；
- 磁盘/GPU/后端门失败；
- shard 未收集到完整数量；
- candidate identity 重复、ordinal 缺口或 artifact 损坏；
- 后端、日志或终态产物发布不完整。
- 远端版本、known-host、source manifest、配置、GPU 或磁盘探针不满足契约。

这些情况不能发布 succeeded ScaleBundle，也不能被记成合法科学负结果。

## 完成门槛

工程 `smoke-validated` 需要同时满足：

- 2×500 与 20×2500 计划契约测试通过；
- 资源门在任务创建前正确允许/拒绝；
- 中断、部分输出、损坏、resume 和发布恢复测试通过；
- 非 APOE fixture 精确生成 1000 个新候选并无重复/缺口；
- 若 APOE Stage 05 有唯一赢家，真实运行完成新 1000 个候选；
- wheel 安装后的同一 `easydesign` API/CLI 可运行和恢复。

APOE 若在 Stage 05 合法科学停止，不降低门槛；Stage 06 通用工程能力仍用冻结 fixture 与
最小真实 backend smoke 验证。

## 非目标与后续提高款

本轮不做：

- 把 Stage 04/05 候选计入 1000；
- Stage 06 内再次筛选或更换 strategy；
- Protenix 多 seed、TNP、最终排名或候选下单包；
- 自动扩容、Slurm/SMART 和单 run 跨节点调度；
- 为通过结果而修改 scientific threshold；
- 供应商下单或公网运行服务。

后续需要基于真实 1000 运行校准磁盘倍率，再增加 SMART/Slurm executor、配额审批和
production-50000 预演。所有后续 executor 必须复用相同 ScalePlan、TaskRecord、
CandidateRecord 和 manifest 契约。
