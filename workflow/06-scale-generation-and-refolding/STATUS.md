# Stage 06 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态状态和验证证据。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `smoke-validated` | APOE 历史单策略 50k 证据保持；dev35 本机直跑不变，Suzhou2 6→7 交给独立 Manager。 | 完成 Manager 单 shard Stage 06→07 真实探针和断线/恢复验收。 | 新 Manager 尚未启动；旧 50k 不重跑。 | 2026-08-01 |

## 当前结论

- 阶段状态：`smoke-validated`；已真实验证单策略 50k 采用路径，多策略真实规模仍待第二案例。
- `ScalePlanV0_2` / `ScaleBundleV0_2` 已实现 1/2/3 个 strategy 的精确等额分配、每组
  strategy-local ordinal、尾部分片和全局 coverage；4 个 Tier A 时只消费 F_YAML
  前三。
- `smoke-1000` 表示全新 1000 个候选，固定为两个 500-candidate shard。
- 历史 APOE 单策略 `production-50000` 已完成 20×2500、50,000/50,000；它仍是
  ScaleBundle 0.1 人工 override 证据，不伪装成原生 v1.6 多策略 run。
- Stage 06 复用 Stage 04 的 BoltzGen adapter、collector、TaskRecord、事件与恢复执行器。
- Stage 04/05 候选不计入 scale 数量；Stage 07 才执行 Protenix 深度筛选和 TNP。
- 软件能力与 APOE 科学结果分别报告；人工授权生成不会修改 Stage 05 科学停止。
- 远程科学事实仍由远端 run 发布；控制端镜像只是 checksum 验证后的只读副本。
- 新 v1.6 continuation 通过 `RunEvidenceLink` 引用 Suzhou2 原始 39 GB 结果，没有复制
  candidate 数据、没有 symlink、没有修改旧 Stage 05/06 manifest。Workbench 据采用记录
  显示 Stage 06 已完成；Stage 07 仍为 `not-reached`。

## 功能矩阵

| 能力 | 状态 | 当前证据 |
| --- | --- | --- |
| `smoke-1000` 2×500 计划 | `implemented` | `ScaleProfile`/`ScalePlan` 类型与单元测试 |
| `production-50000` 20×2500 旧单策略路径 | `smoke-validated` | Suzhou2 历史运行已真实完成 20×2500；v1.6 多策略尾部分片另由契约测试覆盖 |
| 多策略全局 50k allocation | `implemented` | 1/2/3 strategy 精确 50000、25000/25000、16667/16667/16666 |
| 每组/全局 coverage 与 lineage | `implemented` | 尾部分片、重复、缺口、策略错配和恢复测试 |
| 25% 磁盘余量门 | `implemented` | Stage 04 声明 artifact 基线、20×保守倍率、任务前二次检查 |
| 多 GPU shard 调度 | `implemented` | 复用 ENG-008，一张 GPU 同时一个 shard |
| 中断恢复与增量收集 | `implemented` | 稳定 task/shard/ordinal、共享恢复状态机 |
| 精确 merge 与覆盖报告 | `implemented` | 1000 fixture 校验 identity 唯一和 ordinal `1..1000` |
| 发布中断恢复 | `implemented` | 终态 artifact identity/bytes 校验后复用，不覆盖 |
| Stage 05 停止后的人工探索性授权 | `implemented` | 只接受已扩展 Tier A、源 Bundle SHA-256、授权人/理由和双重确认；`stopped-no-tier-a` 禁止越过 |
| SSH whole-run 提交 | `smoke-validated` | Suzhou2 dedicated key、strict known-host、dev11 精确版本、rsync、systemd worker 与远端独立 run 真实通过 |
| 远程状态、恢复与结果同步 | `smoke-validated` | dev12 从控制端真实读取 8 running/12 pending，并同步 246 文件、59,263,753 bytes 的 metadata 镜像 |
| 长任务结构化 heartbeat | `implemented` | BoltzGen adapter → TaskHeartbeat → 原子 ProgressSnapshot → CLI/UI；旧 dev11 运行不追写伪心跳 |
| UI 可选执行位置 | `smoke-validated` | 新建设计可选当前/远程 executor；运行任务页提供状态、metadata 同步和显式 resume；1440/1920 Chromium 通过 |
| 本机自动 GPU 发现与租约 | `implemented` | 省略 devices 时自动冻结符合门槛的 GPU，支持最大卡数限制和无资源等待 |
| Suzhou2 Managed Worker 多 shard | `implemented` | 独立 Manager dev1 拥有中央队列、8 GPU 租约、尾分片、heartbeat/恢复和 managed-run SHA-256；待部署 smoke |
| Suzhou2 配对引导 | `implemented` | 工作区 key pair 检测/复用、一次性密码公钥安装、严格 known-host 与免密 worker 探测 |
| 6→7 远程数据本地性 | `implemented` | Scale 候选留在 Suzhou2，Stage 07 原地消费；默认仅 review 同步 |
| APOE 新 1000 候选 | `not_applicable` | 本次负责人直接授权独立的 50,000 profile，不把旧 100/840 计入 |
| APOE 历史真实 50,000 | `succeeded` | Suzhou2 20×2500、50,000 candidates；ScaleBundle SHA-256 `dc63553e…bfea8` |

## Now

- `[S07-002/VAL-007]` 在 Suzhou2 恢复并登记 Protenix/TNP 与模型资产，完成真实 adapter
  probe 后原地消费已采用的 50,000 候选；源 39 GB 保持在 Suzhou2 原位。
- `[VAL-008]` 在审核并启动的 Suzhou2 Manager 上运行一个 Stage 06→07 单 shard 探针；
  不改写或重跑历史 50k。

## Next

- 在第二条独立真实 target 上真实验证两组或三组 strategy 的共享 50k 调度。
- 用真实运行重新测量每 candidate 磁盘峰值，并评估当前 20×安全倍率。
- 50k 完成后执行 `complete` 同步，并用同一 Workbench 投影复核候选与 ScaleBundle。

## Blocked

- Suzhou2 当前没有通过新 Stage 07 profile 登记的 Protenix/TNP 后端，八张 GPU 在
  2026-07-31 审计时均被其他任务使用。等待自然释放，禁止终止非 EasyDesign 进程。
- APOE 的旧 `stopped-no-scale-winner` 仍是冻结科学结果；历史人工授权只批准生成预算。

## 验证证据

- 模型与计划测试：1000/50000 profile、连续 shard、预授权拒绝、coverage 失败。
- 集成 fixture：非 APOE target 精确生成 1000 个新候选；发布恢复复用同一 bundle
  SHA-256；磁盘门失败时没有创建 task。
- dev12 回归：`make check`、247 passed/8 skipped；strict Ruff/mypy 通过；Workbench
  非视觉交互在 Chromium 1440×900 与 1920×1080 共 18/18 通过。
- 2026-07-31 只读复核：Suzhou2 RunManifest revision 3 为 `succeeded`；
  `progress-final` 为 20/20 tasks、50,000/50,000 candidates、0 failure，run 总量约
  39 GB。RunManifest SHA-256 `54d90bb6…3505`，ScaleBundle SHA-256
  `dc63553e…bfea8`，candidate index SHA-256 `e75f809f…3334c`。
- 2026-07-31：不可变采用记录发布在
  `projects/apoe-s02-006-pse/evidence-adoptions/`
  `apoe-v16-adopt-suzhou2-50k-20260731/record.json`。记录验证 50,000 个唯一连续
  candidate、20 个成功 shard；GPU 0–3 各 7,500，GPU 4–7 各 5,000。UI 从该记录
  投影 100% 完成状态，不扫描远端目录或复制 39 GB。
- dev27 集成前完整回归：不可变快照 `stage0507-validation-20260731-022` 中
  `make check/test/build`、`341 passed, 8 skipped`、Ruff、142 个源文件的 strict
  mypy 以及 wheel smoke 通过；快照
  `stage0507-validation-20260731-021` 中 Workbench production build、Chromium
  双尺寸 38 项非视觉测试和 2 项视觉回归通过。
- SSH 单元/类型检查：严格 host identity、精确 config staging、persistent systemd、
  profile 绝对路径和双 acknowledgement 已覆盖。
- Suzhou2 真实提交：`easydesign-apoe-tier-a-50k-20260727` 已完成；远端 run
  `/data/easydesign/runs/apoe-s02-006-pse/20260727-001-stage06-tier-a-50k-suzhou2`。
  20 个 shard 均成功并发布 50,000/50,000 终态；首批 shard 0001–0008 曾分别绑定
  GPU 0–7，八张 A100 均观测到 BoltzGen 进程约 4.5–5.3 GiB、95–97% utilization。
- 2026-07-27 dev12 控制端 `remote watch --once` 读取到 worker
  `active/running`、8 running、12 pending、50,000 planned；`metadata` 同步到
  Proteindigger1 的同项目/run 路径，验证 246 个文件、59,263,753 bytes 和
  RunManifest SHA-256
  `56a0d8c5ed32c45a17489b3d59a2635db0de40252a7c5013af0481a683a56a5e`。
- APOE source：Stage 05 run `20260726-004-stage05-pilot-filter` 保持
  `stopped-no-scale-winner`；Stage05Bundle SHA-256
  `401259623dd43cf5a17dfed20fd81b6868d61002bcc1eabfab1b68134b5d9073`。

## 工作日志

### 2026-07-26

- 建立 `ScaleProfile`、`ScalePlan`、`ScaleShard`、`ScaleResourceReport`、
  `ScaleCoverageReport` 与 `ScaleBundle`。
- 资源门测试首次在临时文件系统触发拒绝，确认执行器在任务创建前停止；测试改为显式模拟
  足量磁盘，没有削弱 25% 产品规则。
- 将 Stage 04 candidate index 正式加入 Stage 06 input artifact，避免容量测量成为未声明
  的隐式读取。
- 增加终态发布恢复：崩溃遗留 artifact 只能在模型 identity 或原始 bytes 一致时复用。
- APOE Stage 05 于 `2026-07-26T09:13:48+08:00` 发布
  `stopped-no-scale-winner`；统一 run 中仅保留预创建的空阶段目录，没有创建 Stage 06
  attempt、task、shard 或 manifest。

### 2026-07-27

- 负责人明确要求跳过 APOE Tier A 的 100-candidate 科学结果，直接在 Suzhou2 八张卡做
  50k 探索性生成。
- 没有改写 Stage 05 winner；新增 `ScaleStrategyAuthorization`，只允许
  `stopped-no-scale-winner` 中已扩展 Tier A，并冻结源 Bundle hash 与双重确认。
- SSH 采用 whole-run control plane：控制端 staging，远端 systemd worker 继续调用同一
  local multi-GPU Stage 06。
- 提交前曾观察到 GPU 0 上有两条既有 BindCraft，未终止或挤占；正式提交时八张卡均已
  释放，resource gate 通过后首批八个 shard 同时启动。
- 增加远程 watch/sync/resume、Stage 06 `scale-state.json` UI 读取、长任务 heartbeat
  和 Workbench executor 选择。当前运行由 dev11 启动，因此保持空 heartbeat，而不是
  事后伪造；后续 dev12 新任务或合法 resume 自动开始记录。

## 历史索引

- [2026-07 工程实现、远程协作闭环与 APOE 运行边界](history/2026-07.md)。
- [2026-08 双执行目标、受管分片与 6→7 就地交接](history/2026-08.md)。
