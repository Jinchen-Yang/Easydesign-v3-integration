# 02 — 候选表面区域发现

**总体状态：** `planned`

**选区与审批契约版本：** `0.3`

## 目的与科学边界

Stage 02 在 Stage 01 规范结构上提出可审计的 `candidate_surface_region`，供人工比较后选择。
区域成员只描述区域边界，不是已经确认的 binding residues、真实抗体表位或能量学 hotspot。

1.0 提供三种明确模式：

- `detect`：只对包含 PSE `source-annotations.json` 的 Target Bundle 检查固定
  `easydesign-rby-v1` 红/蓝/黄；命中则按用户区域处理，未命中才执行配置中的
  automatic fallback。
- `automatic`：显式忽略任何 PSE 颜色，只运行 SASA、ScanNet 或二者。
- `user-provided`：显式读取 PSE 固定颜色或 YAML 人工残基。

自动路线中，用户可在最初的七阶段 YAML 中选择只运行 SASA、只运行 ScanNet，或同时
运行两者：

```text
                         ┌─ SASA + 三维几何 ─→ 独立 Top 3 ─┐
Target Bundle/target.cif ┤                                ├─→ 重叠报告 → 人工选择
                         └─ ScanNet epitope ─→ 独立 Top 3 ┘
```

两种方法同时运行时也不融合、不产生综合分数或默认赢家。`review-gated` 自动计算完成后
RunManifest 保持 `running/awaiting-human-approval`；只有人工批准同一方法的 2–3 个完整
区域后才发布 `hotspots.yaml`。automatic 的 `unattended` 必须只配置一种方法，并由带
policy ID 的硬规则批准完整 Top 2–3。用户提供区域的 `unattended` 仍记录
`approval_authority: human`，审批人、逐区理由和两个 acknowledgement 必须已经写入
初始 YAML；不允许 LLM、跨方法混选或隐藏参数。

## 输入

- 成功的 Stage 01 `StageManifest`。
- Stage 01 正式发布的 `target-bundle`、`target-structure` 和 `residue-mapping`。
- `stage02.mode: detect|automatic|user-provided` 配置。
- automatic/detect fallback 使用 `stage02.methods` 显式选择 `sasa`、`scannet` 或
  二者。
- 可选、由用户明确给出的 `avoid_label_seq_ids`。
- 新 Target Bundle 中 Stage 01 冻结的 UniProt identity/retrieval artifact；旧 Bundle
  才使用兼容联网路径。不提供身份时不猜测 accession。

Stage 02 只能读取上游 manifest 声明且通过大小/SHA-256 校验的 artifact。`automatic`
不会读取 PSE `source-annotations.json`，因此 PSE 颜色不会影响 SASA/ScanNet。PSE 颜色
只在 `detect` 或显式 `user-provided/pse-colors` 路线消费。

## 用户配置

```yaml
schema_version: "0.6"
project_id: apoe

design:
  binder_profile: vhh
  intent: blocking

workflow:
  execution_mode: review-gated
  stop_after_stage: 2
  cache_mode: offline

stage01:
  target:
    id: apoe
    source:
      type: local-file
      path: inputs/apoe.pse
      format: auto
      identity:
        uniprot_accession: null
    scope:
      type: full-sequence
  structure_prediction: null

stage02:
  mode: automatic
  methods: [sasa, scannet]
  annotations:
    uniprot: if_available
  automatic:
    requested_region_count: 3
    minimum_region_count: 2
    sasa:
      rsasa_threshold: 0.25
      relaxed_threshold: 0.20
      probe_radius_angstrom: 1.4
      sphere_points: 960
      ensemble_consensus_fraction: 0.70
    patch:
      target_member_count: 12
      minimum_member_count: 5
      heavy_atom_neighbor_angstrom: 5.0
      anchor_neighbor_angstrom: 12.0
      compactness_radius_angstrom: 14.0
    evidence:
      scannet_mode: epitope
      use_msa: false
    avoid_label_seq_ids: []

stage03: null
stage04: null
stage05: null
stage06: null
stage07: null
```

PSE 输入由 `easydesign init --target FILE.pse --stop-after 2` 默认生成 `mode: detect`。
普通 PDB/mmCIF、FASTA、UniProt 等入口默认生成 `automatic`。

显式 PSE 颜色输入：

```yaml
stage02:
  mode: user-provided
  annotations:
    uniprot: if_available
  automatic: null
  methods: []
  user_regions:
    source:
      type: pse-colors
      color_scheme: easydesign-rby-v1
    approval: null
```

YAML 人工区域输入：

```yaml
stage02:
  mode: user-provided
  annotations:
    uniprot: if_available
  automatic: null
  methods: []
  user_regions:
    source:
      type: residue-list
      numbering: auth
      chain: A
      regions:
        - id: A
          residues: ["32", "36", "39", "46"]
        - id: B
          residues: ["58", "61", "65", "69"]
    approval: null
```

人工编号支持 `sequence`、规范 CIF 的 `label`、原结构 `auth` 和可靠映射后的 `uniprot`。
`auth` 必须给 chain；`uniprot` 在 mapping 不完整或不唯一时明确失败。用户区域允许
A/B/C 的任意 1–3 个非空子集；成员不扩展、不删除、不重新排名。

固定色板 `easydesign-rby-v1` 为红 `#FF0000 → A`、蓝 `#0000FF → B`、黄
`#FFFF00 → C`。只读取逐残基 CA 的 RGB/hex；其他颜色均为背景。普通 PDB/mmCIF 不定义
私有颜色字段，必须使用 YAML 残基列表。

## 工作台交互式重选区

成功的 Stage 01 Target Bundle 都可以从工作台进入“重新选择结合区域”，不要求原始输入
是 PSE，也不要求已经存在 Stage 02。编辑器把显示状态分成三个互不覆盖的事实层：

1. PSE 来源颜色：来自 Stage 01 `source-annotations.json`，只读，可隐藏/恢复。
2. 当前批准区域：来自当前 Stage 02 `hotspots.yaml`，只读参考，可隐藏/恢复。
3. 本次编辑区域：A=红、B=蓝、C=黄，可通过结构点击、序列点击、Shift 连选、粘贴规范
   `label_seq_id` 修改。同一画笔再次点击已属于该区域的残基即取消选择。

进入手工编辑时，系统先把“当前批准区域”复制到本次编辑层；若尚无 Stage 02，则复制
PSE 来源红/蓝/黄。这样左侧 A/B/C 数量始终描述当前可保存的编辑成员，不会出现结构已
着色但三组均显示 0 的假象。没有任何上游区域时才从 0 开始。

“从空白开始”同时清空第三层并隐藏两个只读参考层，但不删除 PSE annotation 或历史批准
结果；“恢复上游区域”可以重新复制。A/B/C 按钮只切换画笔，实际成员必须通过点击结构、
点击序列或粘贴编号加入，每次操作都显示规范残基编号反馈。一个残基在编辑层只能属于一个
区域；再次点击同一区域即取消，改用另一支画笔会把它从旧区域移动到新区。最终 typed approval 要为每个非空区域
保存 design goal、生物学说明和结构说明，并记录批准人及 evidence limitation 确认。

工作台不再把这些稳定字段作为 A/B/C 三套重复表单展示：`design_goal` 继承项目级
`design.intent`；生物学说明固定如实记录“用户明确选择、当前未提供独立生物学证据”；
结构说明只记录 EasyDesign 已完成编号映射和代表模型坐标验证，并明确“未执行自动结构
优选”。用户仍须填写一次真实批准人，并确认人工区域不等于已经验证的结合位点。直接
编写 YAML 或调用底层 API 时，完整的逐区 typed selection 仍是科学契约的一部分。

保存永远建立新的 Stage 02 continuation run：

```text
已验证 Stage 01 run
→ 新 config revision（manual-residue-list / label numbering）
→ 新 Stage 02 run
→ 显式人工提交直接记录 human authority；automatic review-gated 等待候选确认
```

旧 RunManifest、StageManifest、`hotspots.yaml` 和下游结果保持不变。UI 只是编辑和调用
同一 Python API；编号校验、授权和科学交接仍由 Stage 02 契约执行。

重新运行 Stage 02 时只要求来源 run 的 Stage 01 成功前缀完整、checksum 正确；来源 run
可以因为旧 Stage 02 正在等待确认或已经存在后续结果而尚未终态。新任务创建后，工作台
轮询结构化 job record，显示排队/运行进度，并在终态自动打开新分支。固定时长等待和
目录扫描都不是状态判断依据。

Developer Preview 使用同一个 YAML 继续当前 run：

```bash
easydesign init PROJECT_DIR --target TARGET_FILE --stop-after 2
easydesign doctor --config PROJECT_DIR/easydesign.yaml
easydesign run PROJECT_DIR/easydesign.yaml
```

Stage 02 科学参数全部来自生成后仍可审阅的 `stage02` YAML 区块；CLI 没有隐藏阈值或
设备 fallback。ScanNet 的 CPU/GPU 选择属于本机 runtime profile，当前默认并验证的是
CPU。

## 方法 A：SASA 表面多样性采样

本节是当前 `sasa-surface-diversity` v0.1 的可复现算法说明。后续修改阈值、权重、归一化
常数、邻接关系或选区规则都属于科学行为变化，必须同步修改本节、配置、测试和 Stage
状态，不能只改代码。

### A1. 结构与编号预处理

1. 从成功的 Stage 01 Target Bundle 定位 `target.cif` 和 `residue-mapping.json`，验证
   文件大小和 SHA-256。
2. 要求结构与 mapping 的 target、序列 hash、残基数和 residue identity 一致；v0.1
   接受一条 label chain 和 Target Bundle 明确声明的一个或多个 coordinate model。
3. 只使用标准蛋白 `ATOM` 重原子；氢和氘不进入距离或 SASA 计算。
4. 同名原子有多条记录时保留 occupancy 最高者；同分时使用确定性坐标次序。
5. 每个残基的几何 anchor 定义为：
   - 非 Gly 优先 `CB`；
   - Gly 使用 `CA`；
   - 缺少 `CB` 时回退 `CA`；
   - `CA/CB` 均不存在时明确失败。
6. 所有内部几何运算使用连续 `label_seq_id`；输出成员同时保存 label/auth 编号，不把
   PyMOL PSE 颜色读入本方法。

### A2. 计算 raw SASA 和 rSASA

使用 Biopython `Bio.PDB.SASA.ShrakeRupley`，对每个 coordinate model 独立按 residue
level 计算：

- 水探针半径：`1.4 Å`；
- 每原子球面采样点：`960`；
- `raw_sasa(i)`：残基 `i` 所有重原子的可接触表面积之和，单位 `Å²`；
- `rSASA(i) = raw_sasa(i) / MAX_ASA(residue_type)`。

当前 v0.2 使用以下 `MAX_ASA` 归一化常数：

| 残基 | Å² | 残基 | Å² | 残基 | Å² | 残基 | Å² |
| --- | ---: | --- | ---: | --- | ---: | --- | ---: |
| ALA | 129 | ARG | 274 | ASN | 195 | ASP | 193 |
| CYS | 167 | GLN | 225 | GLU | 223 | GLY | 104 |
| HIS | 224 | ILE | 197 | LEU | 201 | LYS | 236 |
| MET | 224 | PHE | 240 | PRO | 159 | SER | 155 |
| THR | 172 | TRP | 285 | TYR | 263 | VAL | 174 |

这些常数是当前实现事实，但来源登记和不同归一化表的 benchmark 尚未完成，因此 v0.2
rSASA 和下游分数不能宣称已经科学校准。`residue-evidence.json` 为全部残基保存 raw
SASA、rSASA、是否可选、排除原因和逐模型证据。

跨模型汇总固定为：

- raw SASA/rSASA：仅在该残基存在的模型中取中位数；
- `model_presence_fraction`：有可用残基坐标的模型数 / 全部模型数；
- `exposure_frequency`：达到阈值的模型数 / 全部模型数；缺失模型按未暴露计；
- 默认同时要求 presence 和当前阈值 exposure frequency `≥ 0.70`。

因此 10 个模型中 7 个支持可通过，6 个支持不能通过。单模型是严格的 `N=1` 特例：
presence/exposure 只能为 0 或 1，中位数就是该模型数值。

默认先用 `rSASA ≥ 0.25` 形成严格表面集合。只有严格集合无法选出三个满足空间分散要求的
区域时，才显式放宽为 `rSASA ≥ 0.20`。低于 `0.20` 的残基不会进入 v0.1 候选；用户在
`avoid_label_seq_ids` 中明确列出的残基也会排除。当前没有自动功能位点排除。

### A3. 建立三维表面残基图

每个可选残基是一个节点。对每个模型独立检查一条潜在边是否同时满足：

1. 两个 anchor 的欧氏距离 `≤ 12 Å`；
2. 两个残基任意重原子的最小距离 `≤ 5 Å`。

共识图要求至少 `ceil(model_count × ensemble_consensus_fraction)` 个模型支持该边；
缺失任一残基的模型不支持。边长度取支持模型 anchor 距离的中位数。图连通性来自三维
坐标，不要求序列连续。残基对最小重原子距离在一次运行内缓存，缓存只优化速度，不改变
成员、分数或排序。

### A4. 从每个种子生成候选区域

对当前阈值的每个可选残基依次作为 seed：

1. 区域最大成员数为
   `min(target_member_count, floor(eligible_residue_count / requested_region_count))`；
   默认目标为 12 个成员、3 个区域。
2. 从最大成员数开始逐级缩小，最低尝试 5 个成员。
3. 在共识残基图上运行 Dijkstra；单模型边权是 anchor 距离，多模型边权是支持模型
   anchor 距离中位数。
4. 取从 seed 出发图最短路径距离最小的前 `N` 个节点，构成一个连通候选区域。
5. seed 所在连通分量不足 `N` 个节点时，该 seed 在当前成员数下不产生候选。
6. 成员集合完全相同的区域去重；所有 tie break 使用 label 编号，保证相同输入和配置得到
   确定性结果。

### A5. 候选区域评分

对成员集合 `P` 计算：

```text
score(P) =
    0.35 × min(mean_rSASA(P), 1)
  + 0.25 × min(q25_rSASA(P), 1)
  + 0.20 × graph_density(P)
  + 0.20 × compactness(P)
```

其中：

- `mean_rSASA`：成员平均 rSASA；
- `q25_rSASA`：排序后索引 `floor((N-1) × 0.25)` 的值，当前不做插值；
- `graph_density`：区域内部实际边数除以 `N × (N-1) / 2`；
- `radius_of_gyration`：每个具有完整区域坐标的模型分别计算，再取模型间中位数；
- `compactness = max(0, 1 - radius_of_gyration / 14 Å)`。

候选先按 score 降序排列，再按成员 label tuple 和 seed label 排序。这个分数只是项目自定义
的表面区域排序启发式，不是结合能、表位概率或实验置信度。

### A6. 选择空间分散的 Top 3

两个候选区域必须没有共同核心成员，并通过对应 relaxation tier：

| 选择层级 | rSASA | 最小中心距离 | 最大 shell overlap | 最小核心重原子距离 |
| --- | ---: | ---: | ---: | ---: |
| strict tier 0 | 0.25 | 18 Å | 0.10 | 6 Å |
| strict tier 1 | 0.25 | 15 Å | 0.20 | 6 Å |
| relaxed tier 2 | 0.20 | 12 Å | 0.30 | 6 Å |

输出质心优先使用代表模型；代表模型缺少区域成员时使用可完整计算模型的坐标中位数。
一个区域的 `8 Å shell` 是 target 中与任一核心成员最小
重原子距离 `≤ 8 Å` 的全部残基；两个区域的 shell overlap 定义为：

```text
|shell_left ∩ shell_right| / min(|shell_left|, |shell_right|)
```

多模型的区域分离采用保守最坏情况：中心距离取各完整模型最小值，shell overlap 取最大值，
核心最小重原子距离取最小值；区域或区域对在至少 70% 模型中不完整时不得推荐。程序在
当前成员数和层级下枚举兼容的三元组，选择三个区域 score 之和最高者；不使用
ScanNet、PSE 颜色或 annotation 分数。如果没有三个区域，则依次：

1. 在 `rSASA ≥ 0.25` 下，对当前成员数先尝试 strict tier 0，再尝试 strict tier 1；
2. 当前成员数失败后缩小一个成员，重复两个 strict tier，最低到 5 个成员；
3. 严格表面全部失败时切换 `rSASA ≥ 0.20`，从最大可用成员数到 6 依次尝试
   relaxed tier 2；
4. 仍无法得到三个区域时，若能得到至少 `minimum_region_count`（默认 2）个区域，则返回
   可人工审阅的部分推荐；低于最低数量时标记
   `insufficient_surface_for_requested_regions`，并禁止审批。

最终使用的表面阈值、成员数和 relaxation tier 都写入候选池/推荐区域产物。

### A7. SASA 方法产物与当前局限

SASA 方法独立输出：

- `residue-evidence.json`：全部残基的 raw SASA、rSASA 和排除原因；
- `candidate-regions.json`：最终采用的阈值/成员数下的完整去重候选池；
- `recommended-regions.json`：Top 3 或显式不足状态、逐区指标和两两距离；
- `review-regions.pml`：只用于人工查看的 PyMOL 脚本。

当前尚未实现或校准：

- MAX_ASA 来源登记及不同归一化标准 benchmark；
- 按 target 大小、曲率或沟槽自适应的区域面积；
- 柔性、二级结构、静电、疏水、糖基化、PTM、天然界面和功能位点 annotation；
- 评分权重的 VHH、蛋白 binder 或肽 binder 专属科学 benchmark；
- 将表面区域进一步解释成真实 binding residues 或能量学 hotspot。
- 多 state PSE、Protenix 多 seed/sample 和其他入口产生 ensemble 的策略。

这些项目必须作为后续优化分别验证，不能在未实现时以空字段或默认分数混入当前结果。
SASA 路径在任何情况下都不会调用或读取 ScanNet。

## 方法 B：ScanNet epitope no-MSA

- 固定代码 commit `a61623cd98d243c2ff4cd03fc3619d2d22ec50e7`。
- 使用五折 ensemble 的 `ScanNet_epitope_noMSA`。
- adapter 将结构写成单链、连续工具编号 PDB，并保存工具编号到 label/auth 编号映射。
- 候选以逐残基原始 probability 为种子，在纯坐标邻接图中扩展。
- 区域只按 ScanNet probability 排名；不计算或读取 SASA。
- 必须在独立环境运行，执行设备只能显式选择 `cpu` 或 `gpu`，当前默认 `cpu`。
- CPU 模式设置 `CUDA_VISIBLE_DEVICES=-1` 并通过 CPU runtime probe；GPU 模式要求真实 GPU
  probe。探针返回的计算设备必须与请求一致。
- 任一模式的探针、模型执行或映射失败都明确失败；禁止 CPU/GPU 之间静默 fallback。
- 当前 1.0 工程主线使用已通过官方 1BRS 与 APOE smoke 的 CPU；GPU 只作为后续性能优化，
  当前 RTX 4080 与遗留 TensorFlow/CUDA 模型栈的真实推理不兼容。
- ScanNet v0.1 只接受单模型 Target Bundle；多模型配置选择 ScanNet 时明确返回
  `unsupported_ensemble`，不会静默选择代表模型或回退 SASA。

ScanNet probability 在 EasyDesign 中只叫 `region_propensity`，不叫科学置信度。

## 输出

```text
02-hotspot-discovery/attempt-0001/
├── work/
├── logs/
├── attempt-manifest.json
└── artifacts/
    ├── sasa/
    │   ├── residue-evidence.json
    │   ├── candidate-regions.json
    │   ├── recommended-regions.json
    │   └── review-regions.pml
    ├── scannet-epitope/
    │   ├── runtime-probe.json
    │   ├── raw-predictions.csv
    │   ├── residue-evidence.json
    │   ├── candidate-regions.json
    │   ├── recommended-regions.json
    │   └── review-regions.pml
    ├── method-comparison.json
    ├── review-comparison.pml
    ├── annotations/
    │   └── annotation-report.json
    ├── stage02-report.json
    └── stage-manifest.json
```

只选择一种方法时只创建该方法目录，不生成伪造的 comparison。自动阶段成功后仍不产生
Stage 03 输入。PSE 颜色和 YAML 残基列表则共享以下标准产物：

```text
02-hotspot-discovery/attempt-0001/artifacts/
├── user-provided/
│   ├── source-evidence.json
│   ├── normalized-regions.json
│   ├── region-validation.json
│   └── review-regions.pml
├── annotations/annotation-report.json
├── stage02-report.json
└── stage-manifest.json
```

`normalized-regions.json` 是不可变 `UserProvidedRegionSet`：保存 target/structure/sequence
identity、完整 ResidueIdentity、原始 selector、配置或 annotation SHA-256、代表模型
存在性、区域空间连通性 warning 和跨区域重叠 warning。连通性或区域间重叠不会偷偷修改
用户成员。

人工审批建立第二个不可变 attempt：

```text
02-hotspot-discovery/attempt-0002/
├── inputs/hotspots-review.yaml
└── artifacts/
    ├── approval-request.yaml
    ├── approval-record.json
    ├── hotspots.yaml
    └── stage-manifest.json
```

```bash
# automatic 双方法需要 --method；用户提供区域不填写 --method
easydesign hotspots export RUN_DIR --method sasa --output hotspots-review.yaml
easydesign hotspots export RUN_DIR --output hotspots-review.yaml
easydesign hotspots approve RUN_DIR --input hotspots-review.yaml
```

automatic 审批必须从同一种方法选择 2–3 个完整推荐区域；用户提供路线批准 1–3 个完整
区域。二者都禁止混合来源或修改成员。外部 YAML/API 必须提供逐区 typed selection；
工作台交互式重选则继承项目设计意图，并生成不夸大证据的逐区说明。系统生成 label/auth
编号、范围、证据和风险，避免手抄残基。用户区域还必须设置
`acknowledge_user_provided_regions: true`；structural-only 必须设置
`acknowledge_evidence_limitations: true`。

`hotspots.yaml` schema 0.3 用 discriminated `region_source` 区分：

- `automatic`：方法、推荐 artifact ID 和 SHA-256；
- `pse-color-annotation`：色板和 source annotation SHA-256；
- `manual-residue-list`：编号体系、chain 和 resolved config SHA-256。

`hotspots.yaml` 是 Stage 03 唯一合法输入。

每个区域成员同时保存：

- `label_asym_id`、`label_seq_id`；
- `auth_asym_id`、`auth_seq_id`、insertion code；
- sequence index 和标准氨基酸。

`method-comparison.json` 保存两套 Top 3 的全部 `3 × 3` Jaccard、双向覆盖率、中心距离、
最小重原子距离和一一最佳匹配。`fused_score` 和 `winner` 固定为 `null`。

## 可选科学 Annotation

`stage02.annotations.uniprot` 有三种明确策略：

- `off`：即使 YAML 有 accession 也不查询；
- `if_available`：有 accession 才查询；没有时不发网络请求并记录 `not_requested`；
- `required`：缺 accession、网络失败或映射不可靠都会阻止审批。

新 schema 0.4 run 优先消费 Stage 01 已冻结的 UniProt JSON，不在 Stage 02 重新获取一个
可能变化的记录；旧 Bundle 仍兼容按用户明确 accession 调用 UniProtKB REST。实现
active/binding/site/domain/PTM/topology 等 feature 的确定性序列比对和 label/auth 映射；
N-X-S/T 只记录为潜在糖基化 motif warning。Annotation 只进入证据和风险，不改变
SASA/ScanNet 原始分数或排序。

没有 accession 时输出：

```yaml
annotation_status: not_requested
evidence_level: structural_only
identity_resolution: not_attempted
```

structural-only 仍可人工批准，但审批文件必须显式设置
`acknowledge_evidence_limitations: true`，且不能标记为科学验证。自动身份发现、天然复合物
界面、文献/疾病突变、P2Rank/fpocket/PeSTo/GraphPPIS/MaSIF/DiscoTope 等仍在 TODO。

## 双查看器与自然语言辅助边界

Stage 02 与 Stage 01 共用默认浏览器 PyMOL、平级 Mol* 和同一份已校验
`target.cif`。PSE 来源颜色、当前批准区域和本次可编辑区域仍是三个独立图层；查看器切换
不能改变成员、编号或 approval 状态。

DeepSeek/智谱 GLM 助手采用 ChatPyMol 原生完整 PML 主循环：

```text
当前完整 PML + 场景/结构 metadata + 最近十轮对话 + 动态 PML Skills + 用户请求
→ assistantMessage / summary / conversationTitle / 完整新 PML
→ 校验 → 不可变 SceneVersion → PyMOL 增量执行或完整重放
```

`safe-pml` 始终注入，再按当前请求最多注入两个
chain-coloring/interface-analysis/ligand-pocket/publication-figure/
structure-alignment Skill。`ed_region_A/B/C` 是受管理 selection；模型直接理解用户
对一个或多个区域的自然语言修改，包括加入、移除、替换和整区清空，并返回表示最终状态
的完整 PML。用户未声明编号体系时，数字固定按序列区显示的 `label_seq_id` 解释；
只有明确写出原始/auth/author/PDB 编号时才按 author 解释。模型依据请求中的编号表把
label 映射为 author selector；服务端不再预解析单个区域操作，而是从返回 PML 反向映射
A/B/C 草稿并验证对象、链、残基和互斥性。同区再次选择可取消，移入另一颜色会从旧区域移除。

“把32、36加入A区”指规范编号 32 和 36，可以由完整 PML 表达；“寻找最佳区域”不能直接产生残基或 hotspot，
只能生成 `requires_confirmation=true` 的 SASA/ScanNet 分析计划。PML 场景变化本身不
发布 Stage 02；用户确认后仍调用现有确定性后端，两种方法保持独立，不融合分数。用户
区域仍属于 `manual-residue-list` 人工先验，必须经过编号/坐标/checksum 校验和人工
批准，随后创建新的不可变 Stage 02 branch；旧 run 不回写。

模型不接收坐标、完整序列或 MSA。provider、模型、endpoint 和 API key 由部署者在
`runtime/secrets/structure-assistant/platform-provider.yaml` 显式配置；普通使用者
界面不提供 provider 或 key 输入。不允许 DeepSeek/GLM 互相静默 fallback；密钥不进入
科学 manifest、普通日志、浏览器存储或任何 API 响应。

完整 PML 必须保留 EasyDesign 结构管理行；Python、系统命令、文件/网络操作、退出和
重初始化明确拒绝，对象、链、selection、括号、占位符和比对对象必须有效。Mol* 只投影
它可靠支持的 representation、颜色、选择、聚焦和背景；PyMOL 专属命令会标记兼容提示，
但不会因为 Mol* 不支持而拒绝保存。

## 失败与重试

以下情况明确失败：

- Target Bundle、结构或 residue mapping checksum/编号不一致；
- 多链，或 Target Bundle 声明的模型集合与 mmCIF 不一致；
- 同一 label residue 在不同模型中残基类型冲突；
- ScanNet 环境、commit、显式执行设备、超时或输出不满足契约；
- 多模型 Target Bundle 选择 ScanNet；
- ScanNet residue 数量、序列或工具编号无法完整映射；
- 无法得到最低数量的空间分散区域；
- required UniProt annotation 缺失、失败或不能可靠映射；
- 用户区域 selector 越界/歧义、PSE annotation checksum/编号不一致、代表模型缺坐标；
- 显式 `pse-colors` 没有固定红/蓝/黄，或 `uniprot` 编号没有可靠 mapping；
- 审批引用旧 revision、混合来源、改变区域成员、缺理由或未完成 acknowledgement。

ScanNet 失败时允许在 attempt 中保留已经计算的 SASA 文件作为诊断证据，但失败 Stage 不
发布任何正式 output。重试必须新建 attempt，不得覆盖历史。

runtime probe 只证明 TensorFlow 能在请求设备执行一个最小 op，不等于官方模型 smoke。
验收必须继续运行官方 epitope/no-MSA 实例和目标体系；任一真实模型运行失败都按 ScanNet
失败处理。CPU 是一个显式、可审计的后端配置，不是 GPU 失败后的 fallback。

## 完成门槛

- 用户选择的方法分别生成完整候选池和 2–3 个可审阅区域。
- ScanNet CPU runtime probe、官方 no-MSA smoke 及 APOE真实执行通过。
- 138-aa PSE APOE结构全部残基能映射到 label/auth 编号。
- 生成无融合分数的 `3 × 3` 对比报告和 PyMOL 人工检查脚本。
- 单模型 APOE SASA 回归不变；多模型 7/10、6/10、边共识、中位数和最坏情况分离测试通过。
- `off/if_available/required` 与无 accession 零网络请求通过测试。
- 人工审批发布带 target/method/mapping/evidence/hash 的 `hotspots.yaml`。
- PSE 颜色和 YAML auth 列表在真实 APOE 上均得到相同 9/14/14 成员，并保留不同
  provenance；两条均发布 `hotspots.yaml` 0.3。
- `make check`、`make test`、`make build` 通过。

工程 smoke 通过只能标记 `smoke-validated`；完成 VHH–抗原 benchmark 前不得标记
`scientifically-validated`。
