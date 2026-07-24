# 02 — 候选表面区域发现

**总体状态：** `planned`

**自动选区契约版本：** `0.1`

## 目的与科学边界

Stage 02 在 Stage 01 规范结构上提出可审计的 `candidate_surface_region`，供人工比较后选择。
区域成员只描述区域边界，不是已经确认的 binding residues、真实抗体表位或能量学 hotspot。

首版只实现 `automatic`：

```text
                         ┌─ SASA + 三维几何 ─→ 独立 Top 3 ─┐
Target Bundle/target.cif ┤                                ├─→ 重叠报告 → 人工选择
                         └─ ScanNet epitope ─→ 独立 Top 3 ┘
```

两种方法不融合、不产生综合分数或默认赢家。人工批准前 Stage 03 状态必须是
`awaiting_region_selection`。

## 输入

- 成功的 Stage 01 `StageManifest`。
- Stage 01 正式发布的 `target-bundle`、`target-structure` 和 `residue-mapping`。
- `stage02.mode: automatic` 配置。
- 可选、由用户明确给出的 `avoid_label_seq_ids`。

Stage 02 只能读取上游 manifest 声明且通过大小/SHA-256 校验的 artifact。自动模式不会
读取 PSE `source-annotations.json`，因此 PSE 颜色不会影响自动区域。

## 用户配置

```yaml
workflow:
  stop_after_stage: 2

stage02:
  mode: automatic
  automatic:
    region_count: 3
    sasa:
      rsasa_threshold: 0.25
      relaxed_threshold: 0.20
      probe_radius_angstrom: 1.4
      sphere_points: 960
    patch:
      target_member_count: 12
      minimum_member_count: 6
      heavy_atom_neighbor_angstrom: 5.0
      anchor_neighbor_angstrom: 12.0
      compactness_radius_angstrom: 14.0
    evidence:
      scannet_mode: epitope
      use_msa: false
    avoid_label_seq_ids: []
```

`pse_annotations` 和 `manual` 已定义 provider 接口，但当前调用会明确返回
`not implemented`，不会回退到 automatic。

## 方法 A：SASA 表面多样性采样

本节是当前 `sasa-surface-diversity` v0.1 的可复现算法说明。后续修改阈值、权重、归一化
常数、邻接关系或选区规则都属于科学行为变化，必须同步修改本节、配置、测试和 Stage
状态，不能只改代码。

### A1. 结构与编号预处理

1. 从成功的 Stage 01 Target Bundle 定位 `target.cif` 和 `residue-mapping.json`，验证
   文件大小和 SHA-256。
2. 要求结构与 mapping 的 target、序列 hash、残基数和 residue identity 一致；v0.1
   只接受一条 label chain 和一个 coordinate model。
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

使用 Biopython `Bio.PDB.SASA.ShrakeRupley`，对唯一 model 按 residue level 计算：

- 水探针半径：`1.4 Å`；
- 每原子球面采样点：`960`；
- `raw_sasa(i)`：残基 `i` 所有重原子的可接触表面积之和，单位 `Å²`；
- `rSASA(i) = raw_sasa(i) / MAX_ASA(residue_type)`。

当前 v0.1 使用以下 `MAX_ASA` 归一化常数：

| 残基 | Å² | 残基 | Å² | 残基 | Å² | 残基 | Å² |
| --- | ---: | --- | ---: | --- | ---: | --- | ---: |
| ALA | 129 | ARG | 274 | ASN | 195 | ASP | 193 |
| CYS | 167 | GLN | 225 | GLU | 223 | GLY | 104 |
| HIS | 224 | ILE | 197 | LEU | 201 | LYS | 236 |
| MET | 224 | PHE | 240 | PRO | 159 | SER | 155 |
| THR | 172 | TRP | 285 | TYR | 263 | VAL | 174 |

这些常数是当前实现事实，但来源登记和不同归一化表的 benchmark 尚未完成，因此 v0.1
rSASA 和下游分数不能宣称已经科学校准。`residue-evidence.json` 为全部残基保存 raw
SASA、rSASA、是否可选和排除原因。

默认先用 `rSASA ≥ 0.25` 形成严格表面集合。只有严格集合无法选出三个满足空间分散要求的
区域时，才显式放宽为 `rSASA ≥ 0.20`。低于 `0.20` 的残基不会进入 v0.1 候选；用户在
`avoid_label_seq_ids` 中明确列出的残基也会排除。当前没有自动功能位点排除。

### A3. 建立三维表面残基图

每个可选残基是一个节点。两个残基只有同时满足以下条件才连边：

1. 两个 anchor 的欧氏距离 `≤ 12 Å`；
2. 两个残基任意重原子的最小距离 `≤ 5 Å`。

因此图连通性来自三维坐标，不要求序列连续。残基对最小重原子距离在一次运行内缓存，缓存
只优化速度，不改变成员、分数或排序。

### A4. 从每个种子生成候选区域

对当前阈值的每个可选残基依次作为 seed：

1. 区域最大成员数为
   `min(target_member_count, floor(eligible_residue_count / requested_region_count))`；
   默认目标为 12 个成员、3 个区域。
2. 从最大成员数开始逐级缩小，最低尝试 6 个成员。
3. 在残基图上运行 Dijkstra；每条边的权重是两个 anchor 的欧氏距离。
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
- `radius_of_gyration`：成员 anchor 相对区域 anchor centroid 的均方根距离；
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

区域中心是成员 anchor centroid。一个区域的 `8 Å shell` 是 target 中与任一核心成员最小
重原子距离 `≤ 8 Å` 的全部残基；两个区域的 shell overlap 定义为：

```text
|shell_left ∩ shell_right| / min(|shell_left|, |shell_right|)
```

程序在当前成员数和层级下枚举兼容的三元组，选择三个区域 score 之和最高者；不使用
ScanNet、PSE 颜色或 annotation 分数。如果没有三个区域，则依次：

1. 在 `rSASA ≥ 0.25` 下，对当前成员数先尝试 strict tier 0，再尝试 strict tier 1；
2. 当前成员数失败后缩小一个成员，重复两个 strict tier，最低到 6 个成员；
3. 严格表面全部失败时切换 `rSASA ≥ 0.20`，从最大可用成员数到 6 依次尝试
   relaxed tier 2；
4. 仍无法得到三个区域时，只返回 relaxed tier 2 下可得到的 2 个或 1 个区域，并标记
   `insufficient_surface_for_requested_regions`，不得伪装为 Top 3 成功。

最终使用的表面阈值、成员数和 relaxation tier 都写入候选池/推荐区域产物。

### A7. SASA 方法产物与当前局限

SASA 方法独立输出：

- `residue-evidence.json`：全部残基的 raw SASA、rSASA 和排除原因；
- `candidate-regions.json`：最终采用的阈值/成员数下的完整去重候选池；
- `recommended-regions.json`：Top 3 或显式不足状态、逐区指标和两两距离；
- `review-regions.pml`：只用于人工查看的 PyMOL 脚本。

当前尚未实现或校准：

- 多模型/构象 ensemble 的暴露频率；
- MAX_ASA 来源登记及不同归一化标准 benchmark；
- 按 target 大小、曲率或沟槽自适应的区域面积；
- 柔性、二级结构、静电、疏水、糖基化、PTM、天然界面和功能位点 annotation；
- 评分权重的 VHH、蛋白 binder 或肽 binder 专属科学 benchmark；
- 将表面区域进一步解释成真实 binding residues 或能量学 hotspot。

这些项目必须作为后续优化分别验证，不能在未实现时以空字段或默认分数混入当前结果。
SASA 路径在任何情况下都不会调用或读取 ScanNet。

## 方法 B：ScanNet epitope no-MSA

- 固定代码 commit `a61623cd98d243c2ff4cd03fc3619d2d22ec50e7`。
- 使用五折 ensemble 的 `ScanNet_epitope_noMSA`。
- adapter 将结构写成单链、连续工具编号 PDB，并保存工具编号到 label/auth 编号映射。
- 候选以逐残基原始 probability 为种子，在纯坐标邻接图中扩展。
- 区域只按 ScanNet probability 排名；不计算或读取 SASA。
- 必须在独立 GPU 环境运行；GPU 探针、模型执行或映射失败时明确失败，禁止 CPU fallback。

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
    │   ├── raw-predictions.csv
    │   ├── residue-evidence.json
    │   ├── candidate-regions.json
    │   ├── recommended-regions.json
    │   └── review-regions.pml
    ├── method-comparison.json
    ├── review-comparison.pml
    ├── stage02-report.json
    └── stage-manifest.json
```

每个区域成员同时保存：

- `label_asym_id`、`label_seq_id`；
- `auth_asym_id`、`auth_seq_id`、insertion code；
- sequence index 和标准氨基酸。

`method-comparison.json` 保存两套 Top 3 的全部 `3 × 3` Jaccard、双向覆盖率、中心距离、
最小重原子距离和一一最佳匹配。`fused_score` 和 `winner` 固定为 `null`。

## Annotation 状态

UniProt 功能位点、PTM、糖基化和天然界面自动拉取尚未实现。报告必须写：

```json
{"annotation_status": "not_implemented"}
```

不能用空数组暗示已经查询但没有发现。只有用户明确提供的 `avoid_label_seq_ids` 会硬排除；
未来自动 annotation 默认只提供 warning，不替 Stage 03 决定结合策略。

## 失败与重试

以下情况明确失败：

- Target Bundle、结构或 residue mapping checksum/编号不一致；
- 多链或多 coordinate model 超出 v0.1 边界；
- ScanNet 环境、commit、GPU、超时或输出不满足契约；
- ScanNet residue 数量、序列或工具编号无法完整映射；
- 无法得到请求数量的空间分散区域。

ScanNet 失败时允许在 attempt 中保留已经计算的 SASA 文件作为诊断证据，但失败 Stage 不
发布任何正式 output。重试必须新建 attempt，不得覆盖历史。

GPU probe 只证明 TensorFlow 能识别并执行一个最小 GPU op，不等于官方模型 smoke。验收
必须继续运行官方 epitope/no-MSA 实例和目标体系；任一真实模型运行失败都按 ScanNet
失败处理。

## 完成门槛

- 两种方法分别生成完整候选池和 Top 3。
- ScanNet 的 TensorFlow GPU 探针及 APOE真实执行通过。
- 138-aa PSE APOE结构全部残基能映射到 label/auth 编号。
- 生成无融合分数的 `3 × 3` 对比报告和 PyMOL 人工检查脚本。
- `make check`、`make test`、`make build` 通过。

工程 smoke 通过只能标记 `smoke-validated`；完成 VHH–抗原 benchmark 前不得标记
`scientifically-validated`。
