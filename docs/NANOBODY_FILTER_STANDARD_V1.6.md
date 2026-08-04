# Nanobody Filter Standard v1.6

状态：版本化工程标准
适用范围：EasyDesign Stage 05–07 的 VHH 基础流程
前一版本：v1.5（SHA-256
`c28c82d30420c49d5f55dc2c055c6ee2520e3a7f9ed021c3efcba7681a5be905`）

## 1. 版本边界

v1.6 保留 v1.5 的 pilot 硬门、指标定义、归一化区间、`S_screen`、
`F_YAML`、Tier A/B/C/D 定义和扩增局部结构门。唯一科学策略变化是：

- Tier A 与 `F_YAML` 在 100 条诊断性扩增前决定晋级资格。
- 最多晋级三个 Tier A；Tier A 不足三个时不从 Tier B–D 补足。
- full-target 复核用于产生支持证据或 warning，不再撤销 Tier A 晋级。
- 晋级策略共同分享 Stage 06 的总候选预算。
- Stage 07 对全部策略候选做统一的全局竞争，不预留策略配额。

旧 v1.5 report、bundle、manifest 和科学停止结论不得重写或按 v1.6
静默重新解释。历史结果只能通过显式的政策重评记录进入新 continuation。

## 2. Pilot 候选硬门

每个候选必须逐项审计：

- BoltzGen `pass_filters = true`。
- hotspot coverage `>= 0.40`。
- design-to-target iPTM `>= 0.50`。
- minimum design-to-target PAE `<= 10 Å`。
- target Cα RMSD `<= 3 Å`。
- severe clash `= 0`。
- moderate clash `<= 3`。

序列去重在策略内执行。重复序列只保留一个独立通过者，不能通过重复
构象抬高策略的通过数量。

## 3. 候选和策略评分

`S_screen` 沿用 v1.5，综合界面面积、接触密度、hotspot coverage、
CDR 使用、氢键、盐桥、极性接触、BoltzGen 置信度和结构偏移。

固定方向归一化：

- 越大越好的指标用 `(value - gate) / (ideal - gate)`。
- 越小越好的指标用 `(gate - value) / (gate - ideal)`。
- 所有结果截断到 `[0, 1]`。

`F_YAML`：

```text
40% final-gate pass rate
+ 35% qualified top-quartile mean S_screen
+ 25% all-candidate median S_screen
```

Tier：

- Tier A：至少 2 个 final-gate 独立候选。
- Tier B：恰好 1 个 final-gate 独立候选。
- Tier C：0 个 final-gate，但至少 2 个 BoltzGen hard-pass。
- Tier D：少于 2 个 BoltzGen hard-pass。

## 4. YAML 晋级与 100 条诊断性扩增

只允许 Tier A 晋级。按 `F_YAML` 降序、strategy ID 升序作为确定性
tie-break，选择最多三个 YAML。Tier A 不足三个时不补位；没有 Tier A
时发布 `stopped-no-tier-a`。

每个晋级 YAML 扩增至 100 个完整候选。后端崩溃、候选缺失、文件损坏、
checksum 错误或数量不足属于 operational failure，必须恢复后才能结束
Stage 05。

局部结构门：

- BoltzGen `pass_filters = true`。
- target Cα RMSD `<= 3 Å`。
- severe clash `= 0`。
- moderate clash `<= 3`。

局部结构分：

```text
S_expand_structure =
  10% normalized design_to_target_iptm
+ 10% normalized min_design_to_target_pae
+ 30% normalized filter RMSD
+ 25% normalized filter RMSD design
+ 20% normalized target Cα RMSD
+  5% normalized binder pTM
```

以上各项均先按指标方向归一化为 `[0, 1]`，因此公式中的权重全部为正。
每个策略选择局部结构分最高的 10 个合格候选做完整 target+binder
复核；不足 10 个时不以失败候选补足。

完整 target 结构门：

- target-aligned binder backbone RMSD `<= 3 Å`。
- target Cα RMSD `<= 3 Å`。
- severe clash `= 0`。
- moderate clash `<= 3`。

以下指标仅提供置信度标记和同分证据，不作硬门：

- pairwise target–binder iPTM，参考线 `>= 0.50`。
- minimum target–binder PAE，参考线 `<= 15 Å`。
- binder pTM，参考线 `>= 0.70`。

若一个策略没有任何 full-target 结构通过者，发布
`full-target-structure-gate-zero-pass` warning。该 warning 不撤销晋级，
也不阻止连续运行；它必须随 Stage 06/07 结果展示，提醒人工审阅。

## 5. Stage 06 共享总预算

Stage 06 的 production 总预算为 50,000，不是每个策略各 50,000。
采用 `equal-across-promoted-v1`：

- 1 个策略：50,000。
- 2 个策略：25,000 / 25,000。
- 3 个策略：16,667 / 16,667 / 16,666。

通用规则是先给每个策略 `floor(total/N)`，余数按 `F_YAML` 晋级排名从前
到后逐一分配。每个 candidate ID 必须携带 strategy identity 和策略内
ordinal。每个策略以及全局都必须验证无重复、无缺口和数量准确。

## 6. Stage 07 全局筛选

Stage 07 将全部晋级策略的候选合并为一个全局候选池，使用同一套阈值和
评分完成：

```text
序列合法性与去重
→ BoltzGen 质量
→ 深度结构门
→ Protenix 多 seed
→ TNP 与多样性
→ 主候选 / 备选
```

不为不同 YAML 硬保留名额。去重、筛选、聚类和最终候选均保留完整
strategy lineage，并在最终候选包中报告来源分布。

## 7. 状态解释

- `strategies-promoted`：至少一个 Tier A 已晋级，诊断完整；可以进入
  Stage 06，即使存在科学 warning。
- `stopped-no-tier-a`：软件正常完成，但没有 Tier A；停止于 Stage 05。
- operational failure：后端、资源、数量、文件或完整性失败；不能伪装成
  warning，也不能发布成功 handoff。

本标准是确定性工程规则，不等同于实验验证或 scientifically validated。
