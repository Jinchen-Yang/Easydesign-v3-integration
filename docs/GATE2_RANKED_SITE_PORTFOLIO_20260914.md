# Gate 2：Ranked Site Portfolio

状态：2026-09-14 产品契约已落地为 `ranked-site-portfolio-v1`；
实施与验收见 [实现记录](PHASE2_RANKED_SITE_IMPLEMENTATION_20260914.md)。
适用范围：Gate 2 `site-hotspot`。其他 Gate、Scientist 的最终决策权与 Runtime 事实权不变。

## 核心原则

**VALID candidates are ranked. INVALID candidates are blocked.**

只要候选通过硬事实与用户明确硬约束检查，就必须进入相对排序，并成为可选择的选项。
科学未知、风险和不完美主要影响排名、置信度及后续验证任务，不决定是否有资格展示或选择。

Gate 2 要明确回答：“基于当前目标和有限证据，我先试哪一个，第二方案是什么，为什么，
以及我可能错在哪里？”A 可以是多个较弱候选中最值得先验证的一个。B 可以直接称为
“备选候选 / Alternative”，C 可以称为“探索候选 / Exploratory”；这些名称不承诺
whole-VHH 可达性、结合能力或功能效应已经得到验证。

## 硬合法性与科学排序独立

Runtime 负责确认候选具有有效的 target、chain、revision、residue numbering/mapping、
坐标/输入和证据绑定，位于允许的 design scope，且没有违反用户明确 hard constraint。
只有可指向具体受验证事实的硬错误或硬冲突，才将候选标为 `Blocked` 并禁用选择。
例如：引用不存在的残基、错误的链/编号、超出设计范围、违反明确 avoid，或已明确为
intracellular 而任务明确要求 extracellular。硬冲突不能由模型措辞或人工 override 绕过。

表面暴露差、几何或空间连续性弱、机制证据薄弱、功能风险高、whole-VHH accessibility
未知、缺少 downstream docking/预测/实验，均作为排序依据、风险或 unresolved item。
不得通过提高“scientifically viable”的门槛、把未知写成已证实冲突，或增加一个新的资格
状态，将这些候选移出可选择集合。Gate 1 已接受并绑定的条件性映射限制，也不能仅凭
其保留的 ambiguous 标签重新关闭 Gate 1 或取消 Gate 2 排序。

每个已供给的候选应能在卡片中找到：合法候选位于有序列表；硬冲突候选在独立的不可选
区域显示具体事实与原因。无效候选不占 A/B/C 顺位，其存在不能阻断其他合法候选。
全部候选均有硬冲突时，显示明确原因并允许修订目标或重新搜索，不伪造可选候选。

## 排序与展示

主输出为 Ranked Site Portfolio，所有合法候选都保留：

- A — Preferred：当前优先尝试。
- B — Alternative：第二方案。
- C — Exploratory：较低优先级的探索方案。
- 当前 Research/kernel 提供 1–3 个候选；数量不足时如实展示，不补造候选。

有比较依据就明确排序。两个候选都有未知，不能成为拒绝排序或反复并列的理由。
应结合用户目标、现有结构/几何、证据、机制假设和风险，给出最合理的尝试顺序。
确实无法区分时才允许并列，并说明缺少哪项可区分的信息。低置信度排序仍然是排序。

每个候选必须显示：

| 字段 | 要求 |
| --- | --- |
| rank / role | 相对顺位与 Preferred / Alternative / Exploratory |
| candidate identity | 稳定候选 ID，不能用易变的 A/B/C 字母充当身份 |
| exact site / hotspots | Runtime 渲染精确链、残基、编号映射与成员 |
| why it ranks here | 对照其他候选说明优先或退后的具体原因 |
| supporting evidence | 绑定的结构、文献或事实引用；缺少某类证据如实说明 |
| major risks | 会影响选择或后续设计的主要风险，负面证据不得隐藏 |
| unresolved items | 后续设计、预测或实验需要验证的问题 |
| confidence | 对当前比较判断的信心及依据，不伪装成校准后的成功概率 |
| selectability | Runtime 独立给出的 Selectable / Blocked |
| review availability | completed / unavailable / inconclusive，保留来源和实际状态 |

`DISCOURAGED` 可以保留为历史或独立科学意见，但不能作为主展示结论、取消选项或增加
选择门槛的原因。A/B/C 的相对排序与科学评价必须能同时表达，例如 A 风险很高但仍优先。
主要风险直接随候选展示，不要求用户先完成一场“可行性证明”才能看到它。

## Site、Judge、Runtime 与 Scientist

Site & Mechanism 提出完整候选比较和明确排序。Judge 检查比较理由、证据解释、重要风险
及可能改变排序的信息，可以提出有依据的调整建议和 claim qualification。
SiteDecision 是唯一排序作者；Judge 不直接修改顺序。需要调整时由 SiteDecision 修订，
Runtime 为新版本重新绑定卡片。
某句因果推断过强时，保留原 claim 与独立限定，把相关内容转为风险/未知；候选仍合法就
继续形成可选择卡片。Judge 的不推荐或科学意见分歧不能自行改变 Runtime 合法性。
Judge 指出的具体硬事实冲突须通过 Runtime 的结构化一致性检查落实。

Judge 因 max_tokens、provider 故障或结构化提交失败，在既有恢复策略耗尽后，可显示
`review unavailable / inconclusive`，保留 Site 已提交的排序，降低/限定比较置信度，
继续交付全部合法候选。Runtime 不伪造 Judge verdict 或科学排序；卡片明确标记排序来自
Site、独立审查缺失。已有 Judge 的负面发现不能因后来的技术故障被抹掉。
正常 Judge 路径仍须修复并验证，降级不替代正常路径质量。

Scientist 可选择任何 `Selectable` 候选，包括 B/C、高风险候选及 Judge 不可用时的候选，
也可拒绝或要求重新搜索。A 是推荐默认项，不自动批准或提交。
风险、低置信度、负面科学意见及 Judge 不可用本身，不触发额外的 OVERRIDE 资格门槛、
强制自由文本理由或额外确认回合。一次明确的人类选择即可授权该合法候选的 Gate 2
决定；记录选择时展示的风险、未知项和审查状态，不虚构用户作过额外 acknowledgement。
Scientist 可自愿附理由。硬冲突仍不可选择，选择 Gate 2 不批准 Gate 3 或启动 generation。

## 选择必须真正作用于所选候选

Portfolio 与每个选项须绑定当前 target/chain/revision、精确 residues、证据、风险和
portfolio revision/digest。人类响应引用稳定 candidate ID 和当前 card binding。
选择 B 后，下游使用 B 的 residues、evidence、risks 和 unresolved items；不能只改变
显示名称而仍使用 A 的 SiteIntent 或 hotspot 文件。
下游 SiteIntent.alternatives 只保留其他可选候选作为 backup；Blocked 候选仅保留在完整
ranked_portfolio 中供审计与展示，不能作为下游备选。

排名变化不改变候选身份。重新排序、候选内容变化或 evidence revision 变化时刷新卡片
绑定；旧卡不能批准新版本。沿用现有可信 human entry、事务、幂等和 revision lineage。
旧冻结卡片、审批记录和科学证据保持不可变；新契约通过明确的新 portfolio 版本落地。

## 局部实施验收

使用保存的 Dossier / 候选 / 映射 / SiteDecision / Judge packet 验证，先覆盖：

1. ADRB2 现有三个无硬冲突候选完整展示并可选择；给出 A/B/C 理由、风险和置信度。
2. 低暴露、证据薄弱、高风险、whole-VHH 未知只影响比较，不取消任何合法选项。
3. 有依据时明确排序；共同存在未知不会造成无理由的并列或拒绝推荐。
4. Judge 成功时输出正常审查；技术失败时保留 Site 排序与 unavailable 标记，所有合法
   选项仍可由 Scientist 一次明确选择，且既有负面证据不丢失。
5. 硬冲突候选明确不可选，不影响其余候选；全体无效时不伪造排名。
6. 分别选择 A/B/C，核对下游精确 residues/evidence/risks 绑定；覆盖 stale card、
   重排、重复提交和 restart，保证不越过 Scientist 或其他 Gate。
7. 可纠正的 claim 进入 qualification/uncertainty，不使合法候选或整张卡失败。

实现状态与验收证据记录在独立的实现记录中。原 Phase 2 冻结提交与验收保持有效历史记录；
新 portfolio 的实现与验证另行记录，不修改原 GPCR 运行或伪造新的 frozen PASS。
