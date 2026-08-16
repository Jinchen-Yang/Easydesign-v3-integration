# 07 — 最终筛选、多 seed 复核与候选审核包

**状态：** `implemented`

**契约版本：** `0.2`（继续读取 `0.1`）

**实现任务：** `S07-001`、`S07-002`、`DATA-003`

## 目的

Stage 07 消费 Stage 06 新生成的完整候选，按固定的
按后端冻结的 final profile 完成序列预筛、深度结构筛选、多 seed 复合物复核、
TNP 可开发性证据和质量/多样性联合选择，最后发布供人审阅的候选包。

本阶段最多建议 20 个 primary 和 20 个 backup；通过者不足时输出实际数量，不能用失败
候选凑满。真实零通过是合法、可审计的 `stopped-no-final-candidate` 科学负结果。

候选包不是订单。Stage 07 不调用供应商接口，不把软件 smoke 描述成生产下单包，也不把
计算结果描述成实验验证。

Stage 07 对 ScaleBundle 0.2 中全部晋级策略做全局竞争：使用完全相同的门槛、分数和
多样性规则，不为不同 YAML 硬留名额。每个候选始终保留 `strategy_id`、
promotion rank 与来源 allocation；最终包同时展示主备候选的 YAML 来源和来源分布。
旧单策略 ScaleBundle 0.1 仍是合法历史输入。

## 输入与读取边界

Stage 07 只读取当前 `RunManifest` 声明并逐一通过大小和 SHA-256 校验的：

- Stage 01 `target.cif`、target sequence；
- Stage 03 `StrategyBundle`，用于确认每个晋级策略的 hotspot 成员；
- Stage 05 `Stage05Bundle` 0.1/0.2 与 required target MSA；
- Stage 06 `ScaleBundle` / `ScaleBundleV0_2` 和对应 candidate index；
- schema 0.7 的 Stage 04 executor / Stage 07 scientific profile；
- run 冻结 runtime profile 显式声明的 AFO 或 Protenix-v2，以及 TNP backend。

Stage 05 v1.6 必须是 `strategies-promoted`；旧 v1.5 可为 `winner-selected` 或经明确
授权采用的历史单策略证据。Stage 06 必须完整发布，每个 candidate 都必须属于冻结的
晋级集合、落在对应 allocation 内、携带 design-mask identity，并拥有 checksum 正确的
original/refold 结构。代码不能扫描目录补齐候选，也不能从文件名猜测 lineage。

## 配置

```yaml
stage07:
  final_filter_profile: nanobody-final-v1.5 # AFO 使用 nanobody-final-v1.6
  primary_count: 20
  backup_count: 20
  review_cohort_size: 200
  tnp_required: true
  full_target_prediction:
    backend: protenix-v2 # 或显式 openfold3-af3-jax
    target_msa:
      mode: remote
      providers:
        - provider: colabfold-public
    target_paired_msa: {mode: query-only}
    binder_msa: {mode: query-only}
    binder_paired_msa: {mode: query-only}
    target_templates: {mode: disabled}
    binder_templates: {mode: disabled}
  target_conditioned_prediction:
    backend: openfold3-af3-jax # 可与 de-novo 不同
    target_msa:
      mode: remote
      providers:
        - provider: colabfold-public
    target_paired_msa: {mode: query-only}
    binder_msa: {mode: query-only}
    binder_paired_msa: {mode: query-only}
    target_templates: {mode: target-structure}
    binder_templates: {mode: disabled}
```

约束：

- `target_msa.mode: remote` 仅表示在线获取 MSA 数据，不是远程计算或跨主机执行；
- de-novo 的 `full_target_prediction.backend` 与
  `target_conditioned_prediction.backend` 分别必选，且允许混用 AFO/Protenix；
- `primary_count + backup_count` 至少为 1；
- TNP 在非空候选包中固定为必需证据，不能关掉；
- target unpaired MSA 复用 Stage 05 冻结的 required MSA；
- target/binder 的 paired MSA、binder unpaired MSA 可逐链选择
  `remote / precomputed / query-only / disabled`；
- target/binder template 可分别选择 disabled 或 checksum 固定的 precomputed 0..N 模板，
  target 还可显式选择当前 run 的 `target-structure`；这些选择不再由 scientific label 限制；
- remote MSA 失败不得静默 fallback；自动 template search 在本地数据库 provider 发布前不
  宣称可用；
- Protenix 初轮 seed 101、复核 seed 202/303，均为单 sample；AFO 按 v1.6 执行
  seed 101 初筛及五 seed × 五 sample 深筛；
- GPU 来自 Stage 04 明确配置，一张 GPU 同时只运行一个预测任务。

## 执行流程

```text
验证 Stage 01/03/05/06 manifest 与 artifact
→ 对全部 Stage 06 候选计算序列/结构预证据
→ 验证 candidate strategy 集合、allocation 与 Stage 05 晋级完全一致
→ 序列合法性、liability、新生未配对 Cys、BoltzGen pass_filters、全序列去重
→ 按 S_refold 取最多 20,000
→ absolute gate 与 S_deep
→ Top 400 做 Protenix seed 101
→ seed-101 门并冻结经验归一化参考池
→ Top 60 做 Protenix seed 202/303
→ 单 seed 严格门和 seed-pair 一致性门
→ S_final
→ TNP required evidence
→ 90% quality + 10% diversity 的 lazy-greedy
→ 最多 20 primary + 20 backup
→ 发布主备候选 YAML 来源分布
```

### 1. 序列与 refold 预筛

每个 Stage 06 candidate 都生成 `SequencePrefilterRecord`，无论通过与否均保留：

1. 完整 binder sequence 只能含 20 种标准氨基酸；
2. 由 BoltzGen design mask 标识的新生 Cys 必须在 refold 结构中存在
   `1.8–2.3 Å` 的 SG–SG 配对；缺 SG 也按未配对处理；
3. 官方 BoltzGen `pass_filters` 必须为真；
4. 按完整 binder sequence 去重，等分时由 `S_refold` 和 candidate ID 确定唯一代表；
5. N-linked motif、Met/Trp oxidation、Asn deamidation、Asp isomerisation、
   Lys glycation 和 Asp-Pro fragmentation 作为 warning 保存，不在本步单独硬拒绝。

`S_refold` 使用固定的 iPTM、minimum PAE、整体 RMSD、design RMSD 和 design pTM 归一化
权重。最多 20,000 个 hard-pass 唯一序列进入深筛。

### 2. Absolute gate 与 S_deep

Stage 05/07 共用同一套 `interface-geometry-v1` 与 Nanobody Filter Standard v1.5
指标定义，禁止复制另一套距离阈值。至少审计：

- hotspot coverage；
- iPTM 与 minimum PAE；
- target CA RMSD；
- severe/moderate clash；
- interface BSA；
- binder contact、CDR dominance/utilization；
- residue/atom contact、hydrogen bond、salt bridge 和 polar fraction。

本步复用固定 absolute gate，然后按 `S_deep` 取最多 400 个候选进入 seed 101。缺少标准
interface BSA、design mask 或必需指标是 operational failure，不能把指标填成零继续。

### 3. Protenix seed 101 与冻结参考池

每个候选使用阶段显式选择的 AFO 或 Protenix-v2 执行完整 target + binder 复合物预测：

- target chain A：Stage 05 required unpaired MSA；
- binder chain B：默认 query-only，也可按 resolved config 搜索或读取预计算 MSA；
- 两条链默认无模板，也可同时读取各自 checksum 固定的 0..N 预计算模板；
- 单 seed、单 sample；
- 输出结构、summary confidence 和 full confidence 都必须存在且校验。

seed-101 初轮硬门：

| 指标 | 门槛 |
| --- | ---: |
| pairwise iPTM | `≥ 0.60` |
| minimum interface PAE | `≤ 10 Å` |
| binder pose RMSD | `≤ 3 Å` |
| target CA RMSD | `≤ 3 Å` |
| binder pTM | `≥ 0.60` |
| hotspot coverage | `≥ 0.40` |
| severe clash | `= 0` |
| moderate clash | `≤ 3` |

`S_full` 同时使用固定区间归一化和本批次 seed-101 经验分位数。经验池的 candidate identity
及全部 reference values 单独冻结为 `seed101-normalization.json`；seed 202/303 只能使用
这一份参考，不能用后续结果重新归一化或改变排名。

### 4. 多 seed 一致性

seed-101 通过者按 `S_full` 取最多 60 个，再分别预测 seed 202、303。每个 additional
seed 必须通过更严格的单 seed 门：

- minimum interface PAE `≤ 7 Å`；
- binder pose RMSD `≤ 2.5 Å`；
- 其余 iPTM、target RMSD、pTM、hotspot coverage 和 clash 门保持不变。

任意 seed pair 还必须同时满足：

- binder CA RMSD `≤ 3 Å`；
- hotspot contact Jaccard `≥ 0.50`。

至少两个独立 seed 本身通过且构成一个通过的一致 pair，候选才得到 consensus。最终分数：

```text
S_final = 0.70 × consensus seeds 的 median S_full
        + 0.30 × S_deep
```

seed 101 未通过或不足三个预测的候选仍保存明确 consensus-fail 记录，不从审计表消失。

### 5. TNP required evidence

非空 consensus pool 必须调用固定 Therapeutic Nanobody Profiler：

- TNP commit `29dcac72f1380e8538e8870f45a699d3c6156162`；
- BSD-3-Clause；
- 独立 Python 3.10 环境；
- ANARCI Bioconda `2024.05.21`、Biopython `1.77`、ImmuneBuilder/NanoBodyBuilder2
  `1.2`、DSSP `4.6.1`、OpenMM `8.5.2`、PDBFixer `1.9`、scikit-learn `1.7.2`
  与 setuptools `80.9.0` 均由环境契约固定；
- core 不导入 TNP、Torch、ANARCI 或 ImmuneBuilder。

adapter 使用无 shell subprocess、batch FASTA 和文件协议，严格验证官方 JSON、
每候选 CDR/Vernier liability CSV、candidate identity 和有限数值。adapter 显式绑定
该 Conda prefix 的 PATH/native library，禁用 user-site 和 GPU 可见性，防止 TNP 与
BoltzGen/Protenix 抢卡。TNP 保存 total CDR length、CDR3 length/compactness、
PSH/PPC/PNC、六类 flag、CDR/Vernier liabilities 和含 insertion code 的原始 IMGT
numbering。

TNP 在 v1.5 中不作为单候选硬门，而是 final package 的必需风险证据：

- red flag 或至少两个 CDR/Vernier liability：high；
- 至少两个 amber 或一个 liability：medium；
- 其余：low。

TNP 缺失、身份漂移、输出损坏或运行失败属于 operational failure；此时不能发布完整非空
候选包。

### 6. 多样性选择

对全部 consensus pass 且 TNP 完整的候选执行确定性 lazy-greedy：

```text
gain = 0.90 × S_final
     + 0.10 × (1 - 与已选候选的最大设计序列 identity)
```

tie-break 依次为：

1. 较低 TNP risk；
2. 较高 `S_final`；
3. 较高 median pairwise iPTM；
4. 字典序较小的 candidate ID。

先选择 primary，再从剩余候选中选择 backup。序列 identity 使用固定
Biopython `PairwiseAligner` 定义；算法不会聚类后偷偷补回失败候选。

## 公共类型

Stage 07 版本化并导出：

- `SequencePrefilterRecord`：序列、warning、新生 Cys、去重与 `S_refold`；
- `DeepFilterRecord`：absolute gate、结构指标和 `S_deep`；
- `RawFinalPrediction` / `FinalPredictionRecord`：完整 Protenix 原始与评分证据；
- `Seed101Normalization`：冻结的 seed-101 经验参考池；
- `SeedPairConsistency` / `MultiSeedConsensusRecord`：多 seed 单体与配对结论；
- `TnpCandidateRecord` / `TnpReport`：TNP 指标、liability 和风险；
- `FinalSelectionRecord` / `FinalCandidatePackage`：主备候选及人工审核状态；
- `CandidateStrategyLineage` / `StrategySourceDistribution`：多策略来源与最终分布；
- `FinalCandidatePackageV0_2` / `Stage07BundleV0_2`：全局竞争和来源完整交接；
- `Stage07ReviewCohortIndex`：absolute-gate pass 中按固定排序冻结的最多 200 条审查母集；
- `Stage07PredictionComparisonReport`：de-novo/target-conditioned 代表 sample 与模型中立几何；
- `Stage07AdvisoryComparisonProfile`：可选、独立冻结且只产生 advisory 判词的比较规则；
- `OperationalFailure`：必需工具、任务数、错误和可重试性；
- `Stage07Bundle`：Stage 07 唯一下游/报告交接。

通用 `TaskRecord`、`CandidateRecord`、`FilterMetric`、`FilterDecision`、
`ProgressSnapshot` 和 `ScientificStop` 与上游复用。

## 输出

```text
07-final-filtering-and-selection/attempt-0001/
├── artifacts/
│   ├── filter-profile.yaml
│   ├── seed101-normalization.json        # 有 seed-101 预测时
│   ├── final-filter-report.json
│   ├── review-cohort-index.json
│   ├── prediction-comparison-report.json
│   ├── tnp-report.json                   # 有 consensus pass 时
│   ├── final-candidate-package.json
│   ├── scientific-stop.json              # 零最终候选时
│   ├── operational-failures.jsonl        # 恢复过 operational failure 时
│   ├── progress-final.json
│   ├── task-events.jsonl
│   ├── stage07-bundle.json
│   └── stage-manifest.json
├── runtime/
│   ├── local-metric-state.json
│   ├── prediction-state.json
│   ├── progress.json
│   ├── task-events.jsonl
│   └── operational-failures.jsonl
└── work/
    ├── local-metrics/
    ├── protenix/<candidate>/seed-<seed>/attempt-XXXX/
    └── tnp/attempt-XXXX/
```

Stage 发布成功后自动生成 `results/07-final-filtering-and-selection/review-dashboard/report-NNNN/`。
页面失败不回滚本阶段，但 execution status 会给出 reporting warning 和重建命令。

Protenix 与 TNP 上游原始文件可以位于 `work/`，但只有 StageManifest 明确声明且 checksum
正确的 ArtifactRef 才构成正式证据。候选包中保留序列、结构引用、逐级分数、consensus、
TNP 风险、选择理由和完整 lineage。

## 恢复、进度与不可变性

- Protenix 每个 `(candidate, seed)` 是独立 TaskRecord；
- `progress.json` 与 `prediction-state.json` 原子替换；
- `task-events.jsonl` 和 operational failure 日志只追加；
- 中断的 running attempt 在 resume 时先关闭为失败，再创建新 attempt；
- checksum 正确的预测不重跑；
- seed-101 参考池、final report、package 和终态 bundle 不覆盖；
- TNP 失败保留 evidence，resume 创建新 TNP attempt；
- 发布途中恢复只能复用 identity/bytes 一致的终态 artifact。

`easydesign job watch PROJECT --run RUN_ID` 只读取结构化 progress 和事件，不解析终端文本。它显示阶段、
phase、总任务、成功/失败/待重试、GPU 分配、吞吐与 ETA。

## CLI

```bash
easydesign doctor --full
easydesign select plan workspace/projects/PROJECT --run SCALE_RUN --top 200 \
  --de-novo-backend afo --target-conditioned-backend protenix
easydesign select run workspace/projects/PROJECT --run SCALE_RUN --top 200 \
  --de-novo-backend afo --target-conditioned-backend protenix --confirm --detach
easydesign job watch workspace/projects/PROJECT --run FINAL_RUN
easydesign project status workspace/projects/PROJECT --json
```

CLI 只调用统一 orchestration API。`doctor` 只探测配置实际需要的 Protenix/TNP；不会安装
依赖、扫描 Conda 环境或做 fallback。

## 科学停止、软件失败与审核状态

`stopped-no-final-candidate` 表示规则真实运行完成但无人通过，是成功记录的科学负结果。

以下属于 operational failure：

- 上游 manifest、winner、candidate 数或 checksum 不一致；
- 缺 MSA/design mask/标准结构指标；
- Protenix 某个必需 task 未完整成功；
- TNP 环境、commit、license、依赖或输出不符合固定契约；
- seed identity、candidate identity、normalization 或发布 artifact 不一致。

operational failure 不能转换为空科学成功。失败调用写入结构化日志，修复条件后由
`runs resume` 继续。

候选包始终为 `awaiting-human-review` 和 `not-ordered`。`required_reviews` 含 biosafety
时只能生成 `draft-order-package`。当前 1000 候选路径标记为
`smoke-review-package`；即使 50k 未来执行完成，也不能自动下单。

## 完成门槛

工程 `smoke-validated` 必须同时满足：

- 预筛、阈值、S_full/S_final、归一化、consensus、TNP risk 和多样性单元测试通过；
- manifest-only、checksum、failure evidence、resume 和不可变发布测试通过；
- 非 APOE 1000-candidate fixture 完成三 seed、TNP 与非空审核包；
- 固定 TNP 环境通过 import/help/source/license probe 和最小真实 batch smoke；
- 若 APOE 到达 Stage 07，真实产生完整或可审计空的 smoke review package；
- wheel 安装后的 `easydesign` 命令运行同一 API。

在真实 TNP backend smoke 与 APOE 上游门完成前，本阶段只能是 `implemented`，不能写成
`smoke-validated` 或科学验证。

## 非目标与后续提高款

本轮不做：

- 自动供应商下单；
- 用 TNP risk 隐式删除候选；
- 修改 v1.5 阈值迎合 APOE 历史结果；
- 用失败候选凑足 40；
- 无 MSA fallback 或 Agent/LLM 选择；
- 自动湿实验、免疫原性/毒理结论或 production-ready 宣称；
- 真实 50k 后的生产发布。

后续需要第二个独立真实 target、湿实验反馈、阈值校准、可制造性扩展、正式 review gate、
产品 UI 和经授权的 production 运行。

## 本地筛选与持久状态边界

Stage 06 与 Stage 07 只在当前 clone 所在主机运行。Stage 07 在同一 workspace 中验证并
消费 ScaleBundle 和 candidate index，不向控制端或第二执行主机同步 50k 原始候选。需要
人工确认时，本地流程发布 review 证据并等待不可变批准记录；未批准的任务不会自行越过
科学决策点。

持久 job receipt 和 manifest 是状态来源。终端观察暂时断开不改变本机 job/run 状态；
恢复观察后按最后合法 revision 继续读取。最终候选包、科学停止和 operational failure
只能由本地正式 StageManifest 与通过 checksum 的 artifact 宣告。
