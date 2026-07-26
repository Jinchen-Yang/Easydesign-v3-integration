# Stage 04 2026-07 历史

## S04-001 / ENG-008：可恢复多 GPU pilot generation 工程实现

- 状态：`implemented`；APOE 21×40 真实门仍在运行，不能提前记为
  `smoke-validated`。
- 完成时间：2026-07-26T04:30:28+08:00
- 实现提交：`39ce49144fe1098fa7ddca3556ab97ec3492332f`。
- 终态共享执行器提交：`e7bbe8f725b940feb68f09c09476fb1f7ed7d124`。

### 完成内容

- 固定 BoltzGen 0.3.2 文件协议、严格完整候选定义、双 GPU 串行调度、
  `TaskRecord`、原子 `progress.json`、append-only events、deficit resume、正式
  design-mask 证据和 cumulative ETA。

### 验证证据

- 自动检查 199 passed/8 skipped；固定 BoltzGen 单候选真实 smoke 产生原始 CIF
  `bfe9fdca4d8ba075de43b0b0dbed5352db9a3c9a66d7b29dc749d79c1454d274` 与 refold CIF
  `a760f8e3b37935f7c0ae733842a898de0a711888213df34ad72b2b0a0ad12a27`。

### 遇到的问题

- 拼接序列不能在重复片段中唯一恢复 CDR；旧 resume state 缺少新 evidence；短时
  resume 使累计吞吐率失真；Stage 04/05 最初存在重复 task loop 风险。

### 解决办法

- 改读官方 NPZ `design_mask` 并纳入 ArtifactRef；resume 严格升级证据；elapsed time
  从 attempt 创建时间累计；抽取共享 BoltzGen task executor。

### 遗留问题

- APOE 必须实际达到 21×40 共 840 个完整候选并发布 checksummed StageManifest 后才能
  提升状态；不终止其他 GPU 作业，不把 `pass_filters=false` 当成软件失败。
- 相关修复：
  `5b37b1583bb8434bd02cd16a9e874a40b9a330b4`、
  `a367cb9bf67e213f4c61491a4ad5e06e6e8e95ec`、
  `e35b8cafa706632260cd95b5df6599dbfb266b32`、
  `6581626d74dadd2950b008138cd47b5409bd5d98`、
  `9b56915a19e0edf3e693383a89442c213dbd34ef`、
  `d96a87b4d21607fd714b1551d6c9e1d884a43ae4`。

## S04-001 / ENG-008：APOE 21×40 真实验收

- 状态：`smoke-validated`。
- 完成时间：2026-07-26T07:54:40+08:00
- 验收提交：由本次文档提交记录；完整 SHA 在提交完成后追加更正记录。

### 完成内容

- 在固定 BoltzGen 0.3.2、官方 VHH7 和双 RTX 4080 上完成 21 个策略，每个策略严格
  收集 40 个完整候选，共 840 个。
- 发布 CandidateIndex、PilotBundle、TaskTable、终态 ProgressSnapshot、61 条
  append-only TaskEvent、StageManifest、AttemptManifest 和 RunManifest revision 3。
- 保留全部 840 个候选，包括 BoltzGen 官方 `pass_filters=true` 的 28 个和 false 的
  812 个；Stage 04 未提前代替 Stage 05 做科学选择。

### 验证证据

- run：
  `/root/autodl-tmp/Protein_design/easydesign-clean/runs/apoe-s02-006-pse/`
  `20260726-003-stage04-pilot`。
- 终态：21/21 task succeeded、840/840 candidate、0 terminal failure；
  840 个 candidate ID 唯一，每个 strategy 恰好 40 个。
- `easydesign runs show 20260726-003-stage04-pilot --json`：
  `status=succeeded`、`manifest_revision=3`、`integrity_status=verified`。
- CandidateIndex SHA-256：
  `432ebb9638dbc50585ebd4d930bdc7e17f6a1b675320961dfadea4f3cfd299c5`；
  StageManifest SHA-256：
  `7fc7930a4b525f4b2e0d10aab0e06bb3f4e04463c9620e8e8d34c3d1eb240285`；
  RunManifest SHA-256：
  `fd93c28823b35f17a6f595ad2d1aa623f5b0a376ab2f1ad923f16f0933babe04`。
- 累计运行 20,914.80052 秒，终态吞吐率 144.5866 candidate/hour。

### 遇到的问题

- `region-c-h-all-c-full-scaffold-7xl0` 首次后端零退出但只形成 39/40 个完整候选。
- runtime `progress.json` 在策略全部完成后仍保留运行快照；终态事实来源位于已发布的
  `artifacts/progress-final.json`，不能继续把 runtime 快照当终态。
- `runs show` 接口按 run ID 查询；将绝对路径误作 run ID 会返回索引无匹配。

### 解决办法

- 共享执行器把 39/40 识别为结构化 incomplete-output，保留证据并只补跑缺少的 1 个；
  已完成的 39 个没有重跑。
- 验收只读取当前 StageManifest 声明的 `progress-final.json`、CandidateIndex 与
  PilotBundle，并通过 ArtifactRef 的大小和 SHA-256 校验。
- 使用 `easydesign runs show 20260726-003-stage04-pilot --json` 验证 run-index 和
  RunManifest 完整性。

### 遗留问题

- 28 个官方 hard-pass 只是 BoltzGen 自身字段，不代表满足 Nanobody Filter Standard
  v1.5；Stage 05 必须对 840 个候选逐条重新计算和留痕。
- APOE 是否存在 Tier A 或唯一 scale winner 仍未知；若没有，必须记录 scientific
  stop，不能放宽阈值迎合历史结果。
