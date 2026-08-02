# Stage 06 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态状态和验证证据。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `smoke-validated` | dev35 已在 Suzhou2 Manager 真实完成 APOE 8-candidate Stage 06→07；计划、分片、coverage 与终态均精确为 8。 | 在第二真实 target 验证 2–3 组 Tier A 的共享预算和深筛非空路径。 | Manager 私有 remote 仍缺推送权限；本次 8/8 均未通过 BoltzGen `pass_filters`，未进入 Protenix/TNP。 | 2026-08-02 |

## 当前结论

- 阶段状态：`smoke-validated`；已真实验证单策略 50k 采用路径和 dev35 用户输入 8 的
  Managed Worker 新生成路径，多策略真实规模仍待第二案例。
- `ScalePlanV0_2` / `ScaleBundleV0_2` 已实现 1/2/3 个 strategy 的精确等额分配、每组
  strategy-local ordinal、尾部分片和全局 coverage；4 个 Tier A 时只消费 F_YAML
  前三。
- 新任务使用 `user-defined-v1` 和唯一 `total_candidate_count`；默认/推荐 50,000，用户
  输入的任意合法总数会原样进入本机计划或远程 bundle、授权、分片和 coverage。
- `val008-apoe-0607-smoke-20260802t0214z` 已将用户输入 8 冻结为一个 1–8 的 shard，
  在 GPU 6 完成 8/8 新候选、零缺口、零重复、零 operational failure，并原地进入
  Stage 07；这是一条工程 smoke，不改变旧 APOE Stage 05 科学停止。
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
| 用户可调精确总数 | `implemented` | 默认 50,000；37/5,001 等任意正整数、尾部分片、旧配置迁移和 managed bundle 单元测试 |
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
| Suzhou2 Managed Worker 分片 | `smoke-validated` | revision 8 使用 wheel `8d4a3c…d69d`；真实 APOE dev35 job 以 1 GPU/1 shard 精确生成 8/8，bundle/YAML budget 不一致会 fail closed |
| Suzhou2 配对引导 | `implemented` | 工作区 key pair 检测/复用、一次性密码公钥安装、严格 known-host 与免密 worker 探测 |
| 6→7 远程数据本地性 | `smoke-validated` | APOE 8-candidate run 已在 Suzhou2 原地完成 Stage 07，并只同步 270 个 review 文件、59,440,065 bytes |
| APOE 新 1000 候选 | `not_applicable` | 本次负责人直接授权独立的 50,000 profile，不把旧 100/840 计入 |
| APOE 历史真实 50,000 | `succeeded` | Suzhou2 20×2500、50,000 candidates；ScaleBundle SHA-256 `dc63553e…bfea8` |

## Now

- `[S06-004]` 在第二条独立真实 target 上验证两组或三组 Tier A 的共享预算、尾分片、
  恢复和全局 coverage；不能把 50,000 解释成每组各 50,000。

## Next

- 在第二条独立真实 target 上真实验证两组或三组 strategy 的共享 50k 调度。
- 用真实运行重新测量每 candidate 磁盘峰值，并评估当前 20×安全倍率。
- 50k 完成后执行 `complete` 同步，并用同一 Workbench 投影复核候选与 ScaleBundle。

## Blocked

- Suzhou2 6→7 单 shard 工程连通已无运行阻塞；第二真实 target 的 2–3 组 Tier A
  科学输入尚未产生，不得降低门槛或伪造赢家。外部 GPU 任务继续等待自然释放，禁止
  终止非 EasyDesign 进程。
- APOE 的旧 `stopped-no-scale-winner` 仍是冻结科学结果；历史人工授权只批准生成预算。
- Manager 提交 `09ffcc2c3d80b160e98a0540991c272175c39016` 已在 Suzhou2 干净 `main`
  并激活，但 GitHub deploy key/host 权限不可用，暂不能核对或推送私有 `origin/main`。

## 验证证据

- Suzhou2 APOE dev35 受管任务 `val008-apoe-0607-smoke-20260802t0214z`：bundle
  `a49743a8…eff3`，queue revision 36、attempt 1、GPU 6；Stage 06 一个 shard 精确
  8/8，coverage ordinal `1..8`、无 gap、candidate ID 唯一、0 operational failure。
  ScaleBundle SHA-256 `75997585…3b73`，Stage 06 manifest SHA-256
  `77828970…06c1`。
- ProteinDigger 的历史 Stage 05 控制端镜像缺少 2,676 个 manifest 引用文件，提交前按
  设计 fail closed。只读从 Suzhou2 历史 run 复制到全新 staging 后，逐一验证 2,943
  个文件、393,519,306 bytes 和 RunManifest SHA-256 `d7c618b5…0e07`；没有修补或
  改写历史 run。
- review 同步验证 270 个文件、59,440,065 bytes，终态 RunManifest SHA-256
  `bb54dd54…0747`。运行前后旧 APOE 50k 保持 413,147 个文件、40,303,410,564 bytes，
  inode/mtime 及两个旧环境和 `Easycontrol` 均完全一致。
- dev35 可调预算定向门：任意 37/5,001 条、末尾不足 2,500 的分片、dev34 fixed profile
  迁移、远程 bundle 精确预算、UI request 与 production build 均通过。
- dev35 全量工程门：`make check`、413 passed/8 skipped 的 Python 回归、Target Viewer
  3 passed/2 skipped、Workbench Chromium 双尺寸与 Firefox 71 passed/1 skipped；新增浏览器
  用例验证默认 50,000、输入 37 后 YAML 与提交均严格为 37、非正整数被拒绝。
- Suzhou2 固定 1UBQ 40-candidate 真实任务
  `val008-1ubq-region8-tier-a-20260801t1631z`：Manager queue revision 104、40/40 收集、
  0 operational failure；Stage 05 为 `stopped-no-tier-a`。失败分布为 iPTM 40、interface
  PAE 31、BoltzGen pass-filter 32、severe clash 5、hotspot coverage 4，属于可审计科学停止。
- Suzhou2 activation revision 8：Manager commit `09ffcc2…9016`，EasyDesign wheel
  SHA-256 `8d4a3ca5…d69d`，Manager wheel SHA-256 `407e2e74…16a6`；probe 为 8 GPU、
  三后端 ready、`[(4,5),(6,7)]`、queue 0/running 0。升级前后六个受保护路径完全一致。
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

### 2026-08-02

- 将 canonical Stage 06 预算改为 `total_candidate_count`；默认/推荐 50,000，最终严格
  采用用户输入值，任意正整数均可形成连续尾部分片。旧 `smoke-1000` 与
  `production-50000` 只作为 dev34 固定配置兼容入口。
- 新建设计与 Stage continuation 都显示同一个精确数量字段；本机执行、远程 bundle、
  授权、计划、coverage 和 Stage 07 package 分类消费同一数值。
- 固定 1UBQ 40-candidate 真实任务自然结束；队列、租约、后端和落盘无 operational
  failure，但 40 条均未达到 iPTM 门。保留科学停止，不通过调低阈值换取连通结果。
- APOE 8-candidate 工程 smoke 使用源 Stage05Bundle `40125962…9073`、负责人 Knitua、
  双重 scientific-stop acknowledgement 和 `user-defined-v1`；Manager 只租赁 GPU 6，
  448.66 秒后发布精确 8/8 ScaleBundle，再原地进入 Stage 07。旧 50k 和旧 Stage 05
  manifest 全程保持不变。

## 历史索引

- [2026-07 工程实现、远程协作闭环与 APOE 运行边界](history/2026-07.md)。
- [2026-08 双执行目标、受管分片与 6→7 就地交接](history/2026-08.md)。
