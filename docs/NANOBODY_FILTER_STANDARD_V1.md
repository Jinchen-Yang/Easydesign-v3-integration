# Nanobody 设计筛选规范

版本：1.5
适用范围：BoltzGen nanobody 设计；适用于 crop 与 non-crop 输入。

## 1. 通用原则

1. 硬门控用于判定候选是否有效；连续评分仅用于有效候选之间的排序。
2. `quality_score` 仅保留展示，不参与综合评分。
3. crop 结果不做刚性投影评分；最终候选统一使用完整 target+binder Protenix 预测。
4. 不同 crop 范围分别评价，不进行 crop-refold 百分位混排。
5. ipTM、PAE、pTM 等指标表示结构预测置信度，不解释为实验结合亲和力。

## 2. 指标定义

| 指标 | 定义 |
|---|---|
| hotspot contact | hotspot 与 binder 任一重原子距离 ≤ 5.0 Å |
| hotspot coverage | 接触的 YAML binding hotspot 数 / YAML binding hotspot 总数 |
| binder contact coverage | 接触 target 的 binder 残基数 / binder 总残基数 |
| CDR dominance | 接触 target 的 binder 残基中，CDR 残基所占比例 |
| CDR utilization | 全部 CDR 残基中，接触 target 的比例 |
| interface PAE | target–binder 跨链 PAE 的最小值 |
| residue-pair contact | 跨链残基间存在 ≤ 5.0 Å 重原子接触 |
| severe clash | 跨链重原子距离 < 1.5 Å；数量必须为 0 |
| moderate clash | 跨链重原子距离为 1.5–1.8 Å；数量 ≤ 3 |
| interface BSA | `(SASA_target + SASA_binder - SASA_complex) / 2` |

氢原子、预期共价键和预设二硫键不计入 clash。全靶点 hotspot coverage 仅报告，不作为门控。界面面积优先使用标准 interface BSA；无法计算时允许以 `delta_sasa_refolded` 作为同批次内的替代指标，两者不得同时计分。

## 3. 小规模参数筛选

每个 YAML 固定一套 binding-site 参数和一种 scaffold，生成 30–40 个有效候选。YAML 是独立评价和晋级单位。

### 3.1 候选硬门控

候选必须同时满足：

- BoltzGen `pass_filters = true`
- hotspot coverage ≥ 0.40
- `design_to_target_iptm` ≥ 0.50
- `min_design_to_target_pae` ≤ 10 Å
- target Cα RMSD ≤ 3 Å
- severe clash = 0
- moderate clash ≤ 3

crop YAML 必须包含全部 YAML binding hotspots；crop 外 hotspot 不计入门控分母。

### 3.2 候选质量分

归一化函数：

```text
up(x; l, u)   = clip((x - l) / (u - l), 0, 1)
down(x; g, b) = clip((g - x) / (g - b), 0, 1)
```

`clip` 将结果限制在 `[0,1]`：优于理想值时记为 1，差于门槛值时记为 0。例如 ipTM ≥ 0.85 均记为 1，PAE ≤ 3 Å 均记为 1。

| 指标 | 归一化 |
|---|---|
| ipTM | `up(x; 0.50, 0.85)` |
| min interface PAE | `down(x; 10, 3)` |
| filter RMSD | `down(x; 2.5, 0.5)` |
| filter RMSD design | `down(x; 2.5, 0.5)` |
| target RMSD | `down(x; 3, 0.5)` |
| binder pTM | `up(x; 0.75, 0.90)` |
| hotspot coverage | `up(x; 0.40, 1.00)` |

无可靠通用绝对区间的界面指标，在同一 target、crop范围和评价阶段的候选池内进行1%–99% winsorize后做经验百分位归一化。所有密度按每1,000 Å² interface BSA归一化。

```text
S_screen =
  25% interface BSA
+ 10% residue-pair contact density
+  5% atom-contact density

+ 10% hotspot coverage
+  5% binder contact coverage
+  7% CDR dominance
+  6% CDR utilization
+  5% H-bond density
+  4% salt-bridge density
+  3% polar-contact fraction

+  6% ipTM
+  4% min interface PAE
+  4% filter RMSD
+  2% filter RMSD design
+  2% target RMSD
+  2% binder pTM
```

三个分块依次为：界面面积与堆积40%、接触与界面化学40%、结构姿态与官方指标20%。标准interface BSA不可得时，用 `delta_sasa_refolded` 替代上述25%的面积项。

未通过门控的候选不乘惩罚系数；保留其连续指标用于全组分布统计。

### 3.3 YAML 排名

| 等级 | 条件 |
|---|---|
| Tier A | 最终门控通过数 ≥ 2 |
| Tier B | 最终门控通过数 = 1 |
| Tier C | 最终门控通过数 = 0，且 BoltzGen 硬过滤通过数 ≥ 2 |
| Tier D | BoltzGen 硬过滤通过数 < 2 |

先按 Tier 排序；同 Tier 内计算：

```text
F_YAML =
  40% 最终门控通过率
+ 35% 合格候选 S_screen 的 Top 25% 均值
+ 25% 全部候选 S_screen 中位数
```

无合格候选时 Top 25% 项记为 0。重复序列只保留一次，不计为独立通过者。

### 3.4 YAML 晋级与100条扩增

只允许Tier A YAML晋级。按 `F_YAML` 选择最多3个YAML；Tier A不足3个时不从Tier B–D补足。

每个晋级YAML扩增至100个有效候选，并执行：

1. 在原局部/crop条件下生成100个候选。
2. 应用局部结构门控，并按 `S_expand_structure` 排序。
3. 每个YAML选择局部结构分最高的10个；不足10个合格候选时不以失败者补足。
4. 只对这10个候选运行完整target+binder Protenix或AF3。
5. 检查完整预测中的binder能否稳定回到原设计位置。

局部结构门控：

- BoltzGen `pass_filters = true`
- target Cα RMSD ≤ 3 Å
- severe clash = 0
- moderate clash ≤ 3

局部结构分：

```text
S_expand_structure =
  10% design_to_target_iptm
+ 10% min_design_to_target_pae
+ 30% filter RMSD
+ 25% filter RMSD design
+ 20% target RMSD
+  5% binder pTM
```

各项使用第3.2节的固定归一化区间。

前10名的完整target验证门控：

- target-aligned binder backbone RMSD ≤ 3 Å
- target Cα RMSD ≤ 3 Å
- severe clash = 0
- moderate clash ≤ 3

以下指标只用于置信度标记和同分排序，不作为硬门控：

- pairwise target–binder ipTM，参考线 ≥ 0.50
- min target–binder PAE，参考线 ≤ 15 Å
- binder pTM，参考线 ≥ 0.70

三项参考线均未达到时，标记为“低置信结构通过者”，但不因置信指标单独淘汰。

10个完整预测中至少1个通过结构门控，才认为该YAML通过扩增验证。多个YAML均通过时，依次按完整target结构通过数量、通过率、通过者的target-aligned binder RMSD升序、`S_expand_structure`均值降序排序；零通过YAML不得进入生产阶段。选出排名最高的单一YAML进入生产阶段。

## 4. 五万条生产筛选

### 4.1 序列与 BoltzGen 初筛

对最佳 YAML 生成的 50,000 条候选执行：

- 去除重复序列
- 排除未知残基
- 排除非预设的未配对新生 Cys
- 记录 CDR/vernier 区 N-糖基化、氧化、脱酰胺、异构化和断裂风险
- 要求 BoltzGen `pass_filters = true`

```text
S_refold =
  35% ipTM
+ 10% min PAE
+ 25% filter RMSD
+ 15% filter RMSD design
+ 15% design pTM
```

各项使用第 3.2 节的固定归一化区间。`min_design_to_target_pae` 仅用于初筛。

- 硬过滤通过者 > 20,000：按 `S_refold` 保留前 20,000。
- 硬过滤通过者 ≤ 20,000：全部保留，不以失败候选补足。

### 4.2 深评估

对第4.1节保留的最多20,000条候选应用第3.1节绝对门控。只有通过该门控的候选参与深评估排名；未通过者仅保留在审计表中。

无通用绝对区间的指标按第3.2节方法进行批内归一化，所有密度按每1,000 Å² interface BSA归一化。

```text
S_deep =
  25% interface BSA
+ 10% residue-pair contact density
+  5% atom-contact density

+ 10% hotspot coverage
+  5% binder contact coverage
+  7% CDR dominance
+  6% CDR utilization
+  5% H-bond density
+  4% salt-bridge density
+  3% polar-contact fraction

+  6% ipTM
+  4% min interface PAE
+  4% filter RMSD
+  2% filter RMSD design
+  2% target RMSD
+  2% binder pTM
```

标准interface BSA不可得时，允许用 `delta_sasa_refolded` 替代25%的面积项；不得同时加权两者。`quality_score`、`final_rank`仅保留展示。

## 5. 完整 target Protenix 验证

### 5.1 单种子筛选

按 `S_deep` 选择前 400 条，每条运行一次完整 target+binder Protenix。

门控：

- pairwise target–binder ipTM ≥ 0.60
- min target–binder PAE ≤ 10 Å
- target-aligned binder backbone RMSD ≤ 3 Å
- target Cα RMSD ≤ 3 Å
- binder pTM ≥ 0.60
- full-target hotspot coverage ≥ 0.40
- severe clash = 0
- moderate clash ≤ 3

```text
S_full =
  25% interface BSA
+ 10% residue-pair contact density
+  5% atom-contact density

+ 10% hotspot coverage
+  5% binder contact coverage
+  7% CDR dominance
+  6% CDR utilization
+  5% H-bond density
+  4% salt-bridge density
+  3% polar-contact fraction

+  6% pairwise ipTM
+  4% min target–binder PAE
+  4% binder pose RMSD
+  2% target RMSD
+  2% binder pTM
+  2% S_refold
```

从门控通过者中选择前 60 条，每条补跑另外 2 个种子。

### 5.2 三种子高置信门控

候选必须存在至少 2 个一致种子，同时满足：

- pairwise ipTM ≥ 0.60
- min target–binder PAE ≤ 7 Å
- target-aligned binder RMSD ≤ 2.5 Å
- target Cα RMSD ≤ 3 Å
- binder pTM ≥ 0.60
- hotspot coverage ≥ 0.40
- severe clash = 0
- moderate clash ≤ 3
- 两种子的 target-aligned binder Cα RMSD ≤ 3 Å
- 两种子的 hotspot 接触集合 Jaccard ≥ 0.50

```text
S_final = 70% median(S_full) + 30% S_deep
```

当前版本不要求 AF3；AF3 仅作为实验前可选正交确认。

`pairwise ipTM ≥ 0.80`仅标记为“很高置信”，不作为硬淘汰线。

## 6. 可开发性风险

对三种子复核池运行 Therapeutic Nanobody Profiler，记录：

- 总 CDR 长度
- CDR3 长度
- CDR3 compactness
- CDR 附近表面疏水斑块
- 正电斑块
- 负电斑块
- TNP 绿/黄/红旗
- CDR 与 vernier 序列 liability

| 风险 | 条件 |
|---|---|
| 低风险 | 无红旗、黄旗 ≤ 1、无 CDR liability |
| 中风险 | 无红旗，但黄旗 ≥ 2 或存在 1 项 CDR liability |
| 高风险 | 至少 1 项红旗或至少 2 项 CDR liability |

可开发性不进入 `S_final`；仅用于同分排序和人工复核。

## 7. 多样性选择

仅在通过三种子高置信门控的候选池中运行 BoltzGen 式 lazy-greedy 选择：

```text
gain =
  0.90 × S_final
+ 0.10 × (1 - 与已选集合的最大 design-sequence identity)
```

- sequence identity 使用 BoltzGen `design_seq`。
- 先选择 20 条首选；从剩余候选中再选择 20 条备选。
- gain 相同时依次优先：较低可开发性风险、较高 `S_final`、较高 ipTM。
- 合格候选不足 40 条时，输出全部合格候选，不以失败候选补足。

## 8. 固定输出

1. YAML 表：scaffold、候选数、重复率、各门控通过数、Tier、`F_YAML`。
2. 100条扩增表：局部结构门控结果、`S_expand_structure`前10名、前10名完整target验证结果、最佳YAML。
3. 候选表：原始指标、门控状态、`S_screen`、`S_refold`、`S_deep`、三个Protenix种子指标、`S_final`、TNP风险、首选/备选标签。

## 9. 验收规则

- 有最终门控通过者的 YAML 必须排在零通过 YAML 之前。
- 不同 crop 范围不得使用 crop-refold 百分位混排。
- crop 流程不得使用刚性投影碰撞作为门控。
- 100条扩增阶段先按局部结构指标选择前10，只对前10运行完整target预测；该阶段不使用界面面积或界面化学评分，ipTM/PAE/pTM仅作参考而不作全长硬门控。
- `quality_score` 不得进入综合公式。
- 硬过滤不足 20,000 时不得补入失败候选。
- 三种子不一致候选不得进入最终名单。
- interface BSA优先采用第2节定义；只能在标准BSA不可得时以 `delta_sasa_refolded` 替代，且不得同时计分。
- 最终名单必须来自通过完整 target 门控的候选，并保留完整审计字段。

## 10. 参考资料

- AlphaFold 3 prediction quality：<https://www.ebi.ac.uk/training/online/courses/alphafold/alphafold-3-and-alphafold-server/how-to-assess-the-quality-of-alphafold-3-predictions/>
- PXDesign：<https://github.com/bytedance/PXDesign>
- Therapeutic Nanobody Profiler：<https://www.nature.com/articles/s42003-026-09594-y>
- TNP source code：<https://github.com/oxpig/TNP>
