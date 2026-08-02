# Stage 04 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态状态和验证证据。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `smoke-validated` | Proteindigger BoltzGen lock 已统一 cuequivariance 0.10.0；setup 按部署者要求固定保留 10 GiB，当前磁盘已满足新环境发布门。 | 使用 append-only setup 发布并探测 `boltzgen-b9a8a41b3512`；同时寻找能合法产生 Tier A 的第二真实 fixture。 | 环境安装与 probe 尚待完成；1UBQ 仍科学停止于 Stage 05。 | 2026-08-02 |

## 当前结论

- 阶段状态：`smoke-validated`；通用实现、最小 backend smoke 和 APOE 21×40
  真实矩阵均通过。
- 正式 run 为
  `runs/apoe-s02-006-pse/20260726-003-stage04-pilot`：21 个策略各 40 个完整候选，
  共 840 个，candidate ID 全部唯一，RunManifest revision 3 完整性验证通过。
- 完整候选固定为 metric row、原始 complex CIF 和 refold CIF 三者一致；BoltzGen
  `budget=30` 不是 Stage 04 候选预算。
- Stage 04 不按官方 `pass_filters` 选择策略；840 个候选中该字段为 true 的 28 个、
  false 的 812 个，全部如实交给 Stage 05。
- 新任务的 Stage 04 配置页不再显示三张重复事实卡，也不预选当前机器；执行位置卡与
  远端资源请求解耦，用户选择后才出现逐卡状态、最大卡数和确认门。探针失败不暴露
  SSH 命令或工作区路径。

## 功能矩阵

| 能力 | 状态 | 当前证据 |
| --- | --- | --- |
| BoltzGen backend | `smoke-validated` | 固定 0.3.2 完整 pipeline 完成 APOE 21×40；严格收集原始/refold CIF、官方 design mask 和指标 |
| local executor | `smoke-validated` | 双 GPU、每 GPU 一个串行 strategy；7xl0 首次 39/40 后只补跑缺失的 1 个，最终 840/840 |
| 本机自动 GPU 发现与租约 | `implemented` | `nvidia-smi`、外部进程/显存门、append-only lease、无卡等待与 resume 契约测试 |
| Suzhou2 Managed Worker | `smoke-validated` | activation revision 8；固定 1UBQ 40-candidate 真实任务完成 40/40、queue revision 104、0 operational failure |
| SSH 配对与观察 | `implemented` | host fingerprint、已有 key pair 复用、一次性密码幂等安装公钥、逻辑解绑、15 秒轮询和分层同步 |
| Slurm/SMART executor | `planned` | 无 |
| 任务终态和候选索引 | `smoke-validated` | 61 条 append-only 事件、840 个唯一 CandidateRecord、终态 ProgressSnapshot、PilotBundle 与 checksummed manifest-only handoff 均通过 |

## Now

- `[S04-002/DATA-005]` 四个 cuequivariance 包与 sidecar 已固定为同一 0.10.0 family，
  锁回归通过；setup 固定保留 10 GiB 后当前磁盘计划通过，使用 setup API 将新环境发布为
  `runtime/envs/boltzgen-b9a8a41b3512`，再执行最小真实 probe。旧混装环境和历史运行
  保留，不删除或覆盖。
- `[VAL-008]` 固定非 APOE 1UBQ 极小 Stage 04→05 已完成并科学停止；下一步更换合法
  Tier A fixture 验收 Stage 06→07，不重跑 APOE 21×40。

## Next

- Stage 05 只消费本次 succeeded StageManifest 声明的 PilotBundle 与 CandidateIndex，
  执行 v1.5 逐规则筛选、Tier 分层和科学停止判断。

## Blocked

- 不终止服务器上的非 EasyDesign GPU 任务；资源繁忙时等待或明确失败。

## 验证证据

- Stage 03 正式输入：
  `/root/autodl-tmp/Protein_design/easydesign-clean/runs/apoe-s02-006-pse/`
  `20260726-002-stage03-basic-vhh`，StrategyBundle 21 个 strategy，SHA-256
  `a8451f5f7f7d09e69fbf7cf966c04b70aef01a3863132671b756aa4fe64b87`。
- 当前服务器审计：两张 RTX 4080 可见；实际启动前仍须重新检查占用。
- Suzhou2 Manager 真实任务
  `val008-1ubq-region8-tier-a-20260801t1631z`：40/40 candidate 收集、0 failed task、
  Manager queue revision 104；Stage 04 backend、GPU lease 和 immutable run 发布均成功。
- 自动检查：199 passed、8 skipped；Ruff、mypy、wheel build 和 wheel asset
  21/21 均通过。
- S04-002/ENG-033/UI-026：lock family 精确集合测试、8 秒探针参数传递、Stage 04
  表单与 8 GPU 投影测试通过；全量 Python 420 passed、8 skipped，Ruff、mypy、静态
  资产检查均通过。Workbench 关键 Stage 04/受管链在 Chromium 1440/1920 与 Firefox
  6/6 通过；全矩阵 75 passed、1 skipped，仅设置页两张既有视觉基线因平台字体栅格
  约 1% 差异失败，人工对比布局和内容一致，未重写基线。真实 18792 浏览器验证了
  加载中两卡可见、无默认目标、选择门、8 秒失败态与简洁文案，console 0 error。
  隔离 staging wheel 安装与新 UI 资产字节校验通过，SHA-256
  `f4200ceee4b2b8597eed5ba1980da603b62cfbb17e95ee0ab091cf7df1c73bb5`；正式 `make build`
  按不可变门拒绝覆盖已有 dev36 wheel，因此该同版本 staging wheel 未发布到 `dist/`。
- UI-027：补齐逐卡弹窗的独立加载态，并将受管探针上界校准为 60 秒。真实 Suzhou2
  满载探针用时 35.58 秒，返回 8/8 条 A100 快照、0/8 可立即使用和 1 条运行中任务；
  真实 18769 弹窗先显示“正在读取逐卡状态”，随后原地更新为 8 张卡，不再误报不可用。
- 最小真实 backend smoke：
  `/root/autodl-tmp/Protein_design/boltzgen_work/`
  `easydesign_stage04_backend_smoke_20260726_01/backend-output`。固定
  BoltzGen 0.3.2 在 GPU 0 完成 design → inverse folding → folding →
  analysis → filtering，严格收集 1/1 个候选；原始 CIF SHA-256
  `bfe9fdca4d8ba075de43b0b0dbed5352db9a3c9a66d7b29dc749d79c1454d274`，
  refold CIF SHA-256
  `a760f8e3b37935f7c0ae733842a898de0a711888213df34ad72b2b0a0ad12a27`。
  该单样本 `pass_filters=false` 是候选科学结果，不是后端失败。
- APOE 全矩阵真实 smoke：
  `/root/autodl-tmp/Protein_design/easydesign-clean/runs/apoe-s02-006-pse/`
  `20260726-003-stage04-pilot`。终态为 21/21 task、840/840 candidate、0 个终态失败，
  累计 20,914.80052 秒，吞吐率 144.5866 candidate/hour。`candidate-index.json`
  SHA-256 为
  `432ebb9638dbc50585ebd4d930bdc7e17f6a1b675320961dfadea4f3cfd299c5`，
  `stage-manifest.json` SHA-256 为
  `7fc7930a4b525f4b2e0d10aab0e06bb3f4e04463c9620e8e8d34c3d1eb240285`，
  RunManifest revision 3 SHA-256 为
  `fd93c28823b35f17a6f595ad2d1aa623f5b0a376ab2f1ad923f16f0933babe04`；
  `easydesign runs show 20260726-003-stage04-pilot --json` 返回
  `integrity_status=verified`。

## 工作日志

- 2026-07-26：启动 S04-001/ENG-008；审计 BoltzGen 0.3.2 CLI、官方输出和旧运行，
  区分 `num_designs`、`budget`、`pass_filters` 与 EasyDesign 完整候选。
- 2026-07-26：完成通用实现、故障注入、恢复测试和单候选真实 backend smoke；
  Stage 状态升级为 `implemented`，等待 21×40 APOE 真实门槛。
- 2026-07-26：真实候选审计发现 CSV 拼接序列在重复片段下不能唯一恢复 CDR；改为读取
  BoltzGen 官方 NPZ `design_mask`，同时校验 mask、完整 binder 序列、designed sequence、
  `num_design` 和结构 residue 数，并将 mask 文件纳入 ArtifactRef。APOE 7eow 40 个真实
  candidate 已通过新收集器验证。
- 2026-07-26：resume 增加旧 runtime state 的 design-mask 证据升级；仅重读每个
  TaskRecord 明确声明的 task-attempt output，candidate identity 或数量变化即失败，
  已完成候选不会重新生成。
- 2026-07-26：修正 resume 后吞吐率/ETA 将历史候选除以本次短时长的问题；进度快照现
  使用 attempt 创建时间起算的累计 wall-clock elapsed time。
- 2026-07-26：将单个 BoltzGen task 的 deficit、attempt、严格收集和错误状态抽成共享
  执行组件；Stage 04 回归和恢复测试通过，Stage 05 扩展将调用同一实现。
- 2026-07-26：APOE 21×40 正式完成；7xl0 首次只产生 39 个完整候选，resume 仅补齐
  1 个缺口。最终 21 个策略均为 40 个、840 个 candidate ID 唯一、0 个终态失败，
  状态提升为 `smoke-validated` 并移交 Stage 05。
- 2026-08-02：统一 Proteindigger BoltzGen cuequivariance 0.10.0 family；Stage 04/06
  资源请求改为 8 秒上界，位置卡先渲染且初始不选中，删除 Stage 04 三张重复事实卡，
  选择后才展示逐卡资源与确认门。新环境因数据盘安全余量合法暂停，旧环境和运行未动。
- 2026-08-02：发现 Suzhou2 满载时受管 probe 的三后端活性检查真实需 35.58 秒；将
  上界校准为 60 秒，并区分“读取中”和“已失败”，已打开的逐卡弹窗会自动更新为 8 卡。
- 2026-08-02：按部署者明确要求将 setup 安装后可用空间保留策略从数据盘容量的 10%
  改为固定 10 GiB；BoltzGen 新锁环境的 24 GiB 增量峰值在当前磁盘上通过计划门。旧环境、
  模型、缓存、项目和运行均保持不动，新环境继续走 append-only 发布。

## 历史索引

- [2026-07 工程实现与 APOE 真实验收归档](history/2026-07.md)。
- [2026-08 双执行目标与 Suzhou2 受管队列](history/2026-08.md)。
