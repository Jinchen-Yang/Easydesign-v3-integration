# 05 — Pilot 筛选与放大策略选择

**状态：** `implemented`

**契约版本：** `0.1`

**实现任务：** `S05-001`

## 目的

Stage 05 回答两个彼此独立的问题：

1. Stage 04 的每个候选是否满足冻结的 pilot 硬门？
2. 哪一个 BoltzGen strategy 有足够证据进入 Stage 06 放大？

本阶段不是“挑看起来最漂亮的结构”。它必须为每个候选保存指标、阈值、通过状态和
原因；没有合格策略时发布可审计的科学负结果，而不是降低门槛或伪造成功。

## 输入与读取边界

Stage 05 只读取当前 `RunManifest` 声明且通过 SHA-256 校验的：

- Stage 01 `target.cif` 与 `sequence.fasta`；
- Stage 03 `StrategyBundle` 和每个 strategy 的 BoltzGen YAML；
- Stage 04 `PilotBundle` 与 `CandidateIndex`；
- schema 0.7 中的 `stage05`、`stage04.executor`；
- runtime profile 中显式配置的 BoltzGen 和 Protenix backend。

候选必须同时具有原始 complex、refold complex、官方 NPZ `design_mask` 和 BoltzGen
metrics。CDR/设计残基身份只能来自官方 `design_mask`，禁止根据 CSV 的短序列猜测。

## 配置

```yaml
stage05:
  filter_profile: nanobody-filter-standard-v1.5
  expanded_total_per_strategy: 100
  maximum_tier_a_strategies: 3
  strategy_selection:
    full_target_refold_top_n: 10
    require_unique_winner: true
  full_target_prediction:
    backend: protenix-v2
    target_msa:
      mode: remote
      cache_mode: online
      providers:
        - provider: colabfold-public
    binder_msa: query-only
    template_mode: disabled
    parameter_profile: model-default
    prediction_timeout_seconds: 7200
```

`expanded_total_per_strategy: 100` 表示 pilot 与新增候选合计 100；它不是再生成 100。
只有 Tier A strategy 会扩展，最多三组。target 必须使用 required MSA，de novo binder
固定使用 query-only A3M；不允许 no-MSA fallback。

## 执行流程

```text
验证上游 manifest/artifact
→ 逐候选计算结构指标
→ pilot 硬门、去重与 S_screen
→ strategy Tier 与 F_YAML
→ 无 Tier A：stopped-no-tier-a
→ 每个 Tier A 扩展到 100 个完整候选
→ local gate 与 S_expand_structure
→ 每组 top 10 做 full-target Protenix seed 101
→ 唯一胜出策略或 stopped-no-scale-winner
```

### 1. 结构指标

实现版本为 `interface-geometry-v1`：

- heavy-atom contact：跨链重原子距离 `≤ 5.0 Å`；
- severe clash：距离 `< 1.5 Å`；
- moderate clash：`1.5 Å ≤ distance < 1.8 Å`；
- hotspot coverage：发生重原子 contact 的 hotspot 数 / 该 strategy hotspot 总数；
- target CA RMSD：按相同 label residue identity 做 Kabsch 对齐；
- interface BSA：Biopython Shrake–Rupley，probe `1.4 Å`、球面点 `960`，
  `(SASA(target)+SASA(binder)-SASA(complex))/2`；
- CDR dominance/utilization：设计残基在界面接触中的占比与利用率；
- hydrogen-bond count：当前为跨链 N/O/S 重原子 `≤ 3.5 Å` 的几何 proxy，
  未判断供受体、氢和角度，必须按 proxy 解读；
- salt bridge：ASP/GLU 酸性原子与 ARG/HIS/LYS 碱性原子 `≤ 4.0 Å`；
- polar contact fraction：跨链接触原子对中双方均为 N/O/S 的比例。

若标准 BSA 解析失败，筛选报告必须标记 fallback，并使用 BoltzGen
`delta_sasa_refolded`；不能把缺失伪装成零。任何必需指标缺失、NaN、结构身份不一致或
design mask 缺失均为 operational failure。
结构必须携带非重复、正整数 `label_seq_id`；target/binder residue identity 不一致时禁止
按“同样长度”或顺序猜测对应关系。

### 2. Pilot 硬门

每个候选同时满足：

| 规则 | 阈值 |
| --- | --- |
| BoltzGen `pass_filters` | `true` |
| hotspot coverage | `≥ 0.40` |
| design-to-target iPTM | `≥ 0.50` |
| minimum design-to-target PAE | `≤ 10 Å` |
| target CA RMSD | `≤ 3 Å` |
| severe clash | `= 0` |
| moderate clash | `≤ 3` |

序列按完整 `designed_chain_sequence` 的 SHA-256 在每个 strategy 内去重。同序列只允许
一个候选作为独立通过证据；重复项保留 `duplicate_of` 和全部指标。

### 3. `S_screen`

BSA、残基接触密度、原子接触密度、氢键密度和盐桥密度在本次完整 pilot 候选总体内做
1%–99% winsorize 后的确定性经验 midrank。其余指标按 profile 中冻结的 gate/ideal
线性归一化并截断到 `[0,1]`。权重事实来源是随 wheel 分发的
`nanobody-filter-standard-v1.5.yaml`，主要权重为：

- interface BSA `0.25`；
- residue-pair contact density `0.10`；
- hotspot coverage `0.10`；
- CDR dominance/utilization 合计 `0.13`；
- 其余界面与 BoltzGen 质量指标合计 `0.42`。

`S_screen` 只用于工程排序，不是结合亲和力、成功概率或实验置信度。

### 4. Strategy 分层

- Tier A：至少 2 个去重后的 final-gate 候选；
- Tier B：恰好 1 个；
- Tier C：没有 final-gate 候选，但至少 2 个去重后的 BoltzGen hard-pass；
- Tier D：少于 2 个 BoltzGen hard-pass。

`F_YAML = 0.40 × final_gate_pass_rate
+ 0.35 × qualified_top_quartile_mean
+ 0.25 × all_candidates_median`。

只保留 `F_YAML` 最高的最多三个 Tier A；禁止用 Tier B/C 补足名额。没有 Tier A 时发布
`stopped-no-tier-a`，Stage 06 不运行。

### 5. 小规模扩展

每个选中的 Tier A 复用 Stage 04 的 BoltzGen adapter、TaskRecord、GPU 调度、严格
collector 和恢复协议，扩展到总计 100 个完整候选。新增 candidate ordinal 接续 pilot，
例如 pilot 为 1–40，则新增为 41–100。

扩展候选重新计算相同的结构指标，应用 local gate 后计算
`S_expand_structure`。每个 strategy 只把 local-pass 中最高的 top N 送入 full-target
Protenix；失败候选不会为了凑数进入预测。

### 6. Full-target Protenix 与唯一赢家

Protenix 输入固定为：

- chain A：Stage 01 的完整 design-scope target，required MSA；
- chain B：完整设计 binder，query-only；
- template disabled；
- seed `101`、单 sample；
- 必须输出 summary confidence、full confidence 和结构。

从真实 cross-chain PAE 矩阵与 chain-pair confidence 读取 pairwise iPTM、minimum
interface PAE 和 binder pTM。结构门审计 target CA RMSD、target-aligned binder pose
RMSD 以及 clash。每个 strategy 至少一个 full-target structure-gate pass 才有资格放大。

胜出排序依次比较：

1. full-target 通过数量；
2. full-target 通过率；
3. 通过候选的 median binder-pose RMSD；
4. 被选候选 mean `S_expand_structure`；
5. 若以上科学排序指标仍完全相同，则没有唯一赢家。

最终必须唯一发布一个 winner。无人通过或最佳策略在全部科学排序指标上并列时发布
`stopped-no-scale-winner`；strategy ID 只保证输出顺序稳定，不能被当成科学
tie-break。

## 恢复、进度与并发

- 结构指标逐 candidate 缓存，cache identity 包含候选结构、target、design mask、
  hotspot 和指标版本 SHA-256；
- expansion 与 full-target prediction 都使用稳定 TaskRecord 和不可覆盖 attempt；
- 中断的 BoltzGen attempt 会先严格收集已完成候选，再建立新 attempt 补足差额；
- 中断的 Protenix attempt 被关闭为失败证据，再用新 attempt 重试；
- target MSA、query-only A3M 和已验证 prediction 可在 identity 不变时复用；
- `progress.json` 原子替换，`task-events.jsonl` 只追加；
- `easydesign runs watch RUN_DIR` 只读取上述结构化文件；
- `easydesign runs resume RUN_DIR` 只恢复未完成任务。

两张 GPU 默认各执行一个重型任务，同一 GPU 不并发多个 BoltzGen strategy。资源探针不
终止其他进程；资源门未满足时等待或明确失败。

## 输出

```text
05-pilot-filtering/attempt-0001/
├── artifacts/
│   ├── filter-profile.yaml
│   ├── pilot-filter-report.json
│   ├── expansion-candidate-index.json       # 有 Tier A 时
│   ├── expansion-validation-report.json     # 完成扩展时
│   ├── target-msa.a3m                       # 发生 full-target 时
│   ├── target-msa-evidence.json
│   ├── scientific-stop.json                 # 科学负结果时
│   ├── progress-final.json
│   ├── task-events.jsonl
│   ├── stage05-bundle.json
│   └── stage-manifest.json
├── runtime/
│   ├── structure-metrics/
│   ├── expansion-state.json
│   ├── full-target-state.json
│   ├── progress.json
│   └── task-events.jsonl
├── tasks/
└── work/
```

Stage 06 只能读取 StageManifest 声明的 `stage05-bundle.json`。科学停止仍发布 succeeded
StageManifest，但 Run 终止并保存 stop code；backend、checksum、任务预算或必需指标失败
则是 operational failure，不能伪装成 scientific stop。

## CLI

```bash
easydesign run easydesign.yaml
easydesign runs watch RUN_DIR
easydesign runs resume RUN_DIR
easydesign runs show RUN_DIR
```

## 完成门槛

- 每个 Stage 04 候选都有完整逐指标、逐规则处置；
- 每个 strategy 有去重计数、Tier 和排序证据；
- expansion 精确达到配置总量并可恢复；
- 每个 full-target 选择都有 seed 101 的 Protenix 结构与 confidence；
- 发布唯一 winner，或合法的 `stopped-no-tier-a` /
  `stopped-no-scale-winner`；
- 非 APOE fixture、自动测试和 APOE 真实 run 均有证据后，本阶段才可标
  `smoke-validated`。

## 非目标与后续提高款

- 不为通过 APOE 而调整 v1.5 阈值；
- 不把结构分数称为亲和力或实验成功率；
- 不在本阶段运行 1000/50,000 候选；
- 不执行 Stage 07 多 seed、TNP 或多样性选样；
- 氢键完整供受体/角度模型、体系专属阈值校准、实验反馈学习和更丰富的聚类属于后续；
- 1.0 不使用 LLM/Agent 做筛选判断。
