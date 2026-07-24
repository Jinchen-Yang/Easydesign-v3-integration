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

- Biopython Shrake–Rupley，水探针半径 `1.4 Å`，每原子 `960` 个球面点。
- 先使用 `rSASA ≥ 0.25`；不足时才显式放宽到 `0.20`。
- 暴露残基按重原子距离 `5 Å`、anchor 距离 `12 Å` 建立三维图。
- 目标区域为 12 个成员，必要时逐级缩小，最低 6 个。
- 区域评分只包含平均/低四分位 rSASA、图密度和紧凑度。
- 推荐区域按 `18/15/12 Å` 中心距离和 `10%/20%/30%` shell overlap 分层放宽。

SASA 路径不会调用或读取 ScanNet。

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
