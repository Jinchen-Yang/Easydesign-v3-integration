# 05 — Pilot 筛选与放大策略选择

**状态：** `implemented`

**契约版本：** `0.2`（继续读取 `0.1`）

**实现任务：** `S05-001`、`S05-002`

## 目的

Stage 05 回答三个彼此独立的问题：

1. Stage 04 的每个候选是否满足冻结的 pilot 硬门？
2. 哪些 BoltzGen strategy 属于 Tier A，并按 `F_YAML` 排名前三？
3. 这些晋级 strategy 的 100 条诊断性扩增揭示了哪些风险？

本阶段不是“挑看起来最漂亮的结构”。它必须为每个候选保存指标、阈值、通过状态和
原因；没有 Tier A 时发布可审计的科学负结果，而不是降低门槛或伪造成功。

从 `nanobody-filter-standard-v1.6` 开始，Tier A 和 `F_YAML` 在诊断前决定晋级资格。
100 条扩增和 full-target 复核是诊断证据：零结构通过会产生 warning，但不会撤销已经
形成的 Tier A 晋级。后端崩溃、文件缺失、任务数量不足或 checksum 错误仍是必须恢复的
operational failure。历史 v1.5 的唯一赢家与 `stopped-no-scale-winner` 语义保持不变。

## 输入与读取边界

Stage 05 只读取当前 `RunManifest` 声明且通过 SHA-256 校验的：

- Stage 01 `target.cif` 与 `sequence.fasta`；
- Stage 03 `StrategyBundle` 和每个 strategy 的 BoltzGen YAML；
- Stage 04 `PilotBundle` 与 `CandidateIndex`；
- schema 0.9 中显式选择 backend 的 `stage05`、`stage04.executor`；
- runtime profile 中显式配置的 BoltzGen 和 Protenix backend。

候选必须同时具有原始 complex、refold complex、官方 NPZ `design_mask` 和 BoltzGen
metrics。CDR/设计残基身份只能来自官方 `design_mask`，禁止根据 CSV 的短序列猜测。

## 配置

```yaml
prediction_policy:
  selection_mode: explicit-per-stage
stage05:
  filter_profile: nanobody-filter-standard-v1.6
  maximum_tier_a_strategies: 3
  advisory_validation:
    expanded_total_per_strategy: 100
    full_target_refold_top_n: 10
  full_target_prediction:
    backend: protenix-v2
    target_msa:
      mode: remote
      cache_mode: online
      providers:
        - provider: colabfold-public
    target_paired_msa:
      mode: query-only
    binder_msa:
      mode: query-only # 也可 remote / precomputed / disabled
    binder_paired_msa:
      mode: query-only # 也可 remote / precomputed / disabled
    target_templates:
      mode: disabled # 也可 precomputed；conditioned 证据可用 target-structure
    binder_templates:
      mode: disabled # 也可 precomputed，支持 0..N 个模板
    parameter_profile: model-default
    prediction_timeout_seconds: 7200
```

`stage05.full_target_prediction.backend` 是本次 Stage 5 的必选项；不得从项目、Stage 1、
上一次 pilot 或 runtime profile 推导。de-novo 与 target-conditioned 证据在 Stage 5
共用这一次显式选择。

`expanded_total_per_strategy: 100` 表示 pilot 与新增候选合计 100；它不是再生成 100。
`target_msa.mode: remote` 是既有 schema 对“在线获取 MSA 数据”的名称，不会把 Stage 05、
Protenix 或 GPU task 提交到外部主机。
只有按 `F_YAML` 排名前三的 Tier A strategy 会扩展；不足三组时不得用 Tier B–D
补足。target 的 required MSA 仍是 Stage 05 冻结证据；target/binder 的 paired MSA、binder
unpaired MSA 以及两条链的 template 来源由每次 prediction 配置独立选择。默认值保持历史的
query-only/no-template，但不再以 de-novo/target-conditioned 标签禁止合法组合。远程搜索失败
是可恢复 operational failure，不会静默回退成 query-only 或 no-MSA。

## 执行流程

```text
验证上游 manifest/artifact
→ 逐候选计算结构指标
→ pilot 硬门、去重与 S_screen
→ strategy Tier 与 F_YAML
→ 无 Tier A：stopped-no-tier-a
→ 按 F_YAML 晋级最多 3 个 Tier A
→ 每个晋级 strategy 诊断性扩增到 100 个完整候选
→ local gate 与 S_expand_structure
→ 每组 top 10 做 full-target Protenix seed 101
→ advisory-supported / advisory-warning
→ 晋级 strategy 共享 Stage 06 全局预算
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
`nanobody-filter-standard-v1.6.yaml`，主要权重为：

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

### 5. 诊断性扩展

每个选中的 Tier A 复用 Stage 04 的 BoltzGen adapter、TaskRecord、GPU 调度、严格
collector 和恢复协议，扩展到总计 100 个完整候选。新增 candidate ordinal 接续 pilot，
例如 pilot 为 1–40，则新增为 41–100。

扩展候选重新计算相同的结构指标，应用 local gate 后计算
`S_expand_structure`。每个 strategy 只把 local-pass 中最高的 top N 送入 full-target
Protenix；失败候选不会为了凑数进入预测。

### 6. Full-target 结构预测诊断

默认输入保持既有基线：

- chain A：Stage 01 的完整 design-scope target，required MSA；
- chain B：完整设计 binder，query-only；
- template disabled；
- seed `101`、单 sample；
- 必须输出 summary confidence、full confidence 和结构。

研究者可以在同一请求中独立配置 target/binder 的 paired/unpaired MSA，以及任意一条链
0..N 个预计算模板。AFO 和 Protenix 都消费同一份逐链合同；AFO 的远程 MSA 会先生成冻结的
updated AF3 JSON，再进入推理。输入 A3M 的 query、模板 JSON、绝对只读路径和 SHA-256
均严格校验。自动 template search 仍需要独立、版本固定的本地数据库 provider；当前配置
只承诺预计算模板，不把缺失资产伪装成自动搜索。

从真实 cross-chain PAE 矩阵与 chain-pair confidence 读取 pairwise iPTM、minimum
interface PAE 和 binder pTM。结构门审计 target CA RMSD、target-aligned binder pose
RMSD 以及 clash。每个 strategy 的结果形成 `advisory-supported` 或
`advisory-warning`。零通过只表示当前 full-target 模式没有复现稳定位姿，不会取消由
pilot Tier A 和 `F_YAML` 形成的晋级资格。

诊断报告仍按以下顺序排列证据，便于人工比较：

1. full-target 通过数量；
2. full-target 通过率；
3. 通过候选的 median binder-pose RMSD；
4. 被选候选 mean `S_expand_structure`；
5. strategy ID 只保证显示顺序稳定，不能被当成科学 tie-break。

v1.6 发布 `promoted_strategy_ids` 与 `promotion_rank`，不发布
`winner_strategy_id`，也不产生 `stopped-no-scale-winner`。唯一允许阻止 Stage 06 的
科学停止是 `stopped-no-tier-a`。旧 v1.5 Bundle 0.1 继续按原唯一赢家契约读取，不能
回写成新结论。

### 7. v1.5 历史兼容

旧配置继续使用 `expanded_total_per_strategy`、`strategy_selection` 和
`require_unique_winner: true`。旧 run 的 `winner-selected`、
`stopped-no-scale-winner`、Bundle 0.1、manifest 与科学停止结论全部不可变。若需要用
新政策解释旧 pilot，只能发布新的 `PolicyReevaluationRecord`，其中明确冻结旧 Bundle
SHA-256、相同 pilot 门、Tier 定义和 `F_YAML`。

## 恢复、进度与并发

- 结构指标逐 candidate 缓存，cache identity 包含候选结构、target、design mask、
  hotspot 和指标版本 SHA-256；
- expansion 与 full-target prediction 都使用稳定 TaskRecord 和不可覆盖 attempt；
- 中断的 BoltzGen attempt 会先严格收集已完成候选，再建立新 attempt 补足差额；
- 中断的 Protenix attempt 被关闭为失败证据，再用新 attempt 重试；
- target MSA、query-only A3M 和已验证 prediction 可在 identity 不变时复用；
- `progress.json` 原子替换，`task-events.jsonl` 只追加；
- `easydesign job watch PROJECT --run RUN_ID` 只读取上述结构化文件；
- `easydesign job resume PROJECT --run RUN_ID` 只恢复未完成任务。

两张 GPU 默认各执行一个重型任务，同一 GPU 不并发多个 BoltzGen strategy。资源探针不
终止其他进程；资源门未满足时等待或明确失败。

## 输出

```text
05-pilot-filtering/attempt-0001/
├── artifacts/
│   ├── filter-profile.yaml
│   ├── pilot-filter-report.json
│   ├── expansion-candidate-index.json       # 有 Tier A 时
│   ├── advisory-validation-report.json      # v1.6 诊断完成时
│   ├── target-msa.a3m                       # 发生 full-target 时
│   ├── target-msa-evidence.json
│   ├── scientific-stop.json                 # 无 Tier A 时
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
easydesign pilot plan workspace/projects/PROJECT --strategy STRATEGY_REVISION \
  --prediction-backend afo
easydesign pilot run workspace/projects/PROJECT --strategy STRATEGY_REVISION \
  --prediction-backend afo --confirm --detach
easydesign job watch workspace/projects/PROJECT --run PILOT_RUN
easydesign pilot review workspace/projects/PROJECT --run PILOT_RUN
easydesign pilot interpret workspace/projects/PROJECT --run PILOT_RUN \
  --input workspace/projects/PROJECT/interpretation.PILOT_RUN.yaml
easydesign strategy draft workspace/projects/PROJECT --from-pilot PILOT_RUN
```

成功 Stage 05 自动生成不可变 Review Dashboard。旧 `pilot review` 页面命令在存在正式
`stage05-bundle` 时转发到同一核心生成器；Pilot/Expansion 完整母集、方案比较与结构证据
不再由旧 Skill 抽取少量代表候选。

`pilot review` 的 deterministic 部分只保存“artifact 显示了什么”的 Observation；
`pilot interpret` 接受 project-local typed YAML，由 Agent 保存 conclusion、alternative
explanations、limitations、suggested next step，以及 hypothesis 的
supports/weakens/rejects/unresolved 作用。当前 hypothesis 状态由 append-only event reducer
派生。没有完整 Observation 的 empty/partial/operational failure 不得进入 scientific
interpretation；`strategy draft --from-pilot` 必须验证连通的
Hypothesis→Observation→Interpretation refs。

## 完成门槛

- 每个 Stage 04 候选都有完整逐指标、逐规则处置；
- 每个 strategy 有去重计数、Tier 和排序证据；
- expansion 精确达到配置总量并可恢复；
- 每个 full-target 选择都有 seed 101 的 Protenix 结构与 confidence；
- v1.6 发布 1–3 个晋级 Tier A，或合法的 `stopped-no-tier-a`；
- full-target 零通过形成 warning，不取消晋级；后端/产物故障仍阻止发布；
- 非 APOE fixture、自动测试和 APOE 真实 run 均有证据后，本阶段才可标
  `smoke-validated`。

## 非目标与后续提高款

- 不为通过 APOE 而调整冻结阈值；
- 不把结构分数称为亲和力或实验成功率；
- 不在本阶段运行 1000/50,000 候选；
- 不执行 Stage 07 多 seed、TNP 或多样性选样；
- 氢键完整供受体/角度模型、体系专属阈值校准、实验反馈学习和更丰富的聚类属于后续；
- 1.0 不使用 LLM/Agent 做筛选判断。

## 本地 worker 与数据边界

Stage 04 与 Stage 05 只在当前 clone 所在主机运行。Stage 05 在同一 workspace 中按
manifest/checksum 消费 Stage 04 闭包；候选、报告、指标和批准材料不经过控制端、受管队列
或第二执行主机。持久 `LocalStepJob` receipt 是状态来源，终端观察连接中断只会脱离观察，
不会把仍在运行的本地任务改写为 operational failure。

科学决定仍由 Stage 05 profile 与审批记录作出，不由 worker 进程状态、终端连接或 GPU
占用改变。缺少本机环境、模型或 GPU 时必须等待或明确失败，不允许切换到远程 fallback。
