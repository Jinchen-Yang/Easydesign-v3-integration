# 06 — 分片式规模生成与复折叠

**状态：** `implemented`

**契约版本：** `0.2`（继续读取 `0.1`）

**实现任务：** `S06-001`、`S06-002`、`S06-003`、`S06-004`

## 目的

Stage 06 只做一件事：把 Stage 05 v1.6 晋级的 1–3 个 Tier A 按已授权的全局预算生成
一批全新的、完整且可追溯的 BoltzGen 候选，并把每组及全局都无缺口地交给 Stage 07。
旧 Stage05Bundle 0.1 的唯一赢家或负责人明确授权的单一 Tier A 仍按历史契约读取。

本阶段不会重新选择策略，也不会把 Stage 04/05 的候选计入 scale 数量。新任务使用
`user-defined-v1`，由用户通过 `total_candidate_count` 决定精确总数；产品推荐并默认
50,000，但较小正整数可以用于真实 Stage 05→06→07 连通验证。`smoke-1000` 和
`production-50000` 继续只读兼容 dev34 已冻结运行。APOE 于 2026-07-27 获得一次独立的
人工探索性 50k 授权；该授权不改变 Stage 05 科学停止。

这里的“复折叠”指固定 BoltzGen 0.3.2 pipeline 内的 folding/refolding/analysis 产物。
多 seed Protenix 深度复合物预测属于 Stage 07，不能混入 Stage 06。

## 输入与读取边界

Stage 06 只读取当前 `RunManifest` 声明且逐一通过大小与 SHA-256 校验的：

- Stage 03 `StrategyBundle` 和每个晋级策略的 `design.yaml`；
- Stage 04 `CandidateIndex`，仅用于冻结实测候选磁盘基线；
- Stage 05 `Stage05Bundle`；
- schema 0.7 的 `stage04.executor` 与 `stage06` 配置；
- runtime profile 显式声明的 BoltzGen backend。

v1.6 默认要求 `strategies-promoted`。`total_candidate_count` 是所有晋级策略共享的
总预算，不是每组各生成该数量；按 `F_YAML` 晋级顺序等额分配，余数优先给排名靠前的
策略。旧 v1.5
`stopped-no-scale-winner` 只有在配置提供双重确认的
`manual_strategy_authorization` 时才能选择 Stage 05 已经扩展过的 Tier A；Stage 05
结论不被重写。`stopped-no-tier-a` 永远不得越过。代码不扫描上游目录猜策略，也不从
文件名推断候选。

## 配置

新任务的规范配置：

```yaml
stage06:
  scale_profile: user-defined-v1
  total_candidate_count: 50000  # 推荐值；最终以用户输入为准
  allocation_policy: equal-across-promoted-v1
```

开发者真实连通检查可以显式缩小总数，例如：

```yaml
stage06:
  scale_profile: user-defined-v1
  total_candidate_count: 37
  allocation_policy: equal-across-promoted-v1
```

v1.5 历史人工 override 继续使用：

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

新 profile 冻结精确用户预算并按每组最多 2,500 条切分；旧 profile 只用于兼容：

| Profile | 新候选总数 | Shard 布局 | 适用范围 |
| --- | ---: | --- | --- |
| `user-defined-v1` | 用户正整数；推荐 50,000 | 每组最多 2,500，尾片可更小 | 所有新任务 |
| `smoke-1000` | 1,000 | 历史 2×500 | dev34 兼容恢复 |
| `production-50000` | 50,000 | 历史 20×2,500 | dev34 兼容恢复 |

v1.6 的精确等额分配为：

| 晋级 strategy 数 | strategy budget |
| ---: | --- |
| 1 | `50,000` |
| 2 | `25,000 / 25,000` |
| 3 | `16,667 / 16,667 / 16,666` |

余数按 `F_YAML` promotion rank 分配。每组最后一个 shard 可以少于 2,500；恢复与合并
必须使用同一冻结 allocation，不能因为任务完成先后重新分配。

`total_candidate_count` 本身就是本次不可变生成授权，计划、资源预检、远程 bundle、分片
和 coverage 必须使用同一个值。旧配置中的 `preauthorized_candidate_limit` 继续校验，
但新 UI 不要求用户维护第二个容易与总数冲突的字段。

人工 override 不是补写 `winner_strategy_id`：系统会发布
`scale-strategy-authorization.json`，保存授权人、理由、Stage05Bundle SHA-256、
`stopped-no-scale-winner` 与双重 acknowledgement。它只批准生成预算，不表示候选通过
Protenix 或具备实验成功概率。

## 执行流程

```text
验证 Stage 03/04/05 manifest 和 artifact
→ 验证 1–3 个晋级策略及每份 design.yaml identity
→ 从 Stage 04 声明的 candidate artifact 计算磁盘基线
→ 检查执行后是否仍保留文件系统总容量的 25%
→ 等额分配全局预算并冻结 ScalePlan 0.2
→ 为每组建立独立 shard/task/strategy-local ordinal identity
→ 等待显式 GPU 空闲门
→ 每张 GPU 同时最多执行一个 shard
→ 严格收集完整候选并原子更新 progress/state
→ 合并时分别检查每组及全局 identity、ordinal 无重复且无缺口
→ 发布精确等于 total_candidate_count 的“全新候选” ScaleBundle
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

`user-defined-v1` 从 ordinal 1 连续切到用户总数，每片最多 2,500，最后一片可以更小。
历史 `smoke-1000` / `production-50000` 仍严格验证原 1,000/50,000 identity。ordinal
断裂、重叠、重复 task 或超出授权都会在执行前失败。

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

`S06-003` 将远程执行补齐为可协作的闭环：

- 可以提交已有 continuation，也可以把含 `easydesign.yaml` 与 `inputs/` 的新项目从
  Stage 01 起提交；远端会先执行配置校验和按需 doctor。
- `remote watch` 同时读取 systemd worker 和远端 `runs watch --once --json`，不会把
  SSH 连通误当成科学任务仍在推进。
- BoltzGen 长任务每 30 秒把 process-alive heartbeat 原子写入 `ProgressSnapshot`；
  heartbeat 只证明后端进程存活，不把中间 CIF 计作完整候选。
- worker 停止或主机重启后，`remote resume` 创建新的 systemd unit；原 unit 与恢复次数
  保存在控制端 `SshRemoteJobRecord`，运行中的 worker 禁止重复恢复。
- `remote sync --mode metadata` 拉取 Run/Stage manifest、顶层声明 artifact 与
  progress/state/events；`complete` 再递归拉取 JSON 中声明的候选 ArtifactRef。

### 采用既有远程 50k 证据

远程 50k 已经完成、且候选主体留在远程数据盘时，可以发布不可变证据采用记录：

```bash
easydesign remote adopt-scale SUZHOU2 \
  --project-id PROJECT_ID \
  --adoption-id ADOPTION_ID \
  --local-stage05-run LOCAL_STAGE05_RUN \
  --remote-stage06-run REMOTE_STAGE06_RUN
```

命令逐一验证本地 Stage 05 RunManifest、Stage05Bundle、远程 Stage 06 RunManifest、
ScaleBundle、计划、任务、进度、覆盖报告和 candidate index 的大小与 SHA-256，并验证
候选编号连续、无重复、分片与设备计数一致。成功后只在
`projects/<project_id>/evidence-adoptions/` 发布新的记录；不复制约 39 GB 候选、不创建
symlink，也不改写旧 v1.5 run。APOE 的采用证据验证了 20/20 shard 和
50,000/50,000 候选，并让产品投影把 Stage 06 显示为已经完成。
  两种模式都逐一验证大小和 SHA-256，不扫描目录猜结果。

### 4. 恢复与不可变发布

- `progress.json` 和 `scale-state.json` 原子替换；
- 运行中 `task_heartbeats` 按 task identity 覆盖更新，任务结束时移除；
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

- `ScaleProfile`：用户定义 profile 与 dev34 固定 profile 兼容身份；
- `ScaleShard`：稳定分片与 ordinal 范围；
- `ScaleResourceReport`：容量测量、估算和 25% 门；
- `ScalePlan`：获得授权的完整执行计划；
- `ScaleTaskTable` / `ScaleExecutionState`：终态与可恢复运行状态；
- `ScaleCoverageReport`：无重复、无缺口的 merge 证明；
- `ScaleBundleV0_2`：全局预算、每组 allocation、coverage 和 Stage 07 唯一交接；
- `ScaleBundle` 0.1：旧单策略运行的只读兼容交接。

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

统一入口会在 Stage 05 v1.6 有晋级策略时继续；旧 v1.5 唯一 winner 仍兼容：

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
easydesign remote watch REMOTE_ID JOB_ID
easydesign remote sync REMOTE_ID JOB_ID \
  --to runs/PROJECT_ID/RUN_ID --mode metadata
easydesign remote resume REMOTE_ID JOB_ID

# 从 Stage 01 起把整个项目提交到远端
easydesign remote submit REMOTE_ID \
  --job-id JOB_ID --run-id RUN_ID \
  --config PROJECT/easydesign.yaml --project-root PROJECT
```

`watch` 只读取结构化 progress；显示 stage、phase、总数、成功/失败/重试、GPU 分配、
吞吐率、ETA 与 task heartbeat。CLI 不包含分片、资源或科学逻辑。Workbench 的“在哪里
运行”选择框和“运行任务”远程卡片调用同一组 API。

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
- 远程 metadata/complete 镜像有缺失、篡改或 symlink/path traversal。

这些情况不能发布 succeeded ScaleBundle，也不能被记成合法科学负结果。

## 完成门槛

工程 `smoke-validated` 需要同时满足：

- 2×500 与 20×2500 计划契约测试通过；
- 资源门在任务创建前正确允许/拒绝；
- 中断、部分输出、损坏、resume 和发布恢复测试通过；
- 非 APOE fixture 精确生成 1000 个新候选并无重复/缺口；
- 新 run 对 1/2/3 个晋级策略精确生成用户指定的全局总数；旧固定 profile 继续兼容；
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
50,000 推荐预算预演。所有后续 executor 必须复用相同 ScalePlan、TaskRecord、
CandidateRecord 和 manifest 契约。

## 双执行位置与远端交接

Stage 06 与 Stage 04 复用同一 GPU 发现、租约、TaskRecord、事件、进度和恢复
执行器。“当前机器”按 shard 将任务分配到通过资源门的 GPU；“Suzhou2”将通过
校验的 `RemoteJobBundle` 加入受管中央队列。运行位置不修改 ScalePlan 或候选
identity。

Suzhou2 上新运行的持久根是 `/data/easydesign/managed-worker`。默认不复用旧
dev11/dev12 环境作为新 worker 正式环境，不移动、覆盖或改写旧 APOE 50k 产物。
控制端配对复用工作区完整 SSH key pair；首次公钥授权可由 localhost UI 通过一次性
密码完成，密码不会进入配置、日志、参数、环境或磁盘，授权完成后只使用专用私钥。
对于已在受管 worker 完成 Stage 05 的 run，Stage 06 通过远端 RunManifest SHA-256 和
`runs/<project>/<run>` 相对引用就地继续，无需重传大型上游闭包。

受管 Stage 06 job 的固定阶段范围是 `6→7`：50k 候选主体保留在 Suzhou2，
Stage 07 原地消费。只有用户显式请求 `complete` 同步时才会回传全部大型结果；
默认 `review` 仅同步审阅所需的 manifest、报告、指标和少量结构。
