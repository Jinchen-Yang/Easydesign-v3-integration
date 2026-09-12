EasyDesign v3 — Finish Phase 2 Completely
你现在接手 EasyDesign v3 Phase 2 的最终收口任务。
本轮唯一目标：彻底完成并冻结 Phase 2。
不要进入 Phase 3。
不要开始 Pilot Generation。
不要开始 Scale。
不要做 Workbench、storage overhaul、旧 orchestration 删除或 Figure 2。
请保留当前所有已经接受的 milestones、commits、tags、Golden Case snapshots 和 scientific kernel。
当前 Phase 2 已有 4/5 个主要 Golden Cases 被接受：
Case 1 — Soluble protein → Gate 2        PASS
Case 3 — Identity trap → Gate 1          PASS
Case 4 — Standard Binder → Gate 3        PASS
Case 5 — Native expert YAML → Gate 3     PASS

Case 2 — GPCR / membrane target → Gate 2 NOT YET PASS
当前最重要的问题不是 YAML、BoltzGen 或 Target identity。
真正 blocker 是：
GPCR Evidence Research 已经能够找到结构、数据库、primary literature 和反证，但系统仍不能稳定、简洁地把这些 evidence 收敛为一个正确的 Site decision / SiteIntent，然后经过独立 Judge 到达 Gate 2。
不要继续通过增加 message pointer、alias、history compression、更多 repair plumbing 或不断提高 context limit 来解决这个问题。
本轮请从职责边界上把它彻底简化。
1. 冻结核心原则
保持：
Evidence Research
→ 搜索、读取、核验、发现反证

Trusted Runtime
→ hard facts、mapping、candidate identity、evidence binding

Site Synthesis
→ scientific choice / interpretation

Evidence Judge
→ independent critique

Scientist
→ Gate 2 decision
核心原则：
Trusted runtime owns scientific facts.
The model owns scientific judgment.
模型不应重新生成已经由 runtime 确定的 residue numbering、canonical/design mapping、chain、SASA、candidate membership 或 evidence identity。
2. Site Research 保持 Agentic，但以 Decision Sufficiency 为停止条件
Site Research 可以继续使用：
literature
UniProt
PDB/RCSB
GPCRdb
structure tools
functional / antibody / epitope evidence
但默认 Standard Research 的目标不是完成 literature review。
原则：
Search for decision sufficiency, not literature completeness.
先根据：
user biological objective
+
approved Target
+
current Gate
形成少量 decision-critical evidence questions，通常约 3–6 个。
例如：
- 哪些 candidate 真正 extracellular / binder-accessible？
- 哪些 region 与用户要求的 functional effect 相关？
- state / ligand / partner 是否影响 candidate ranking？
- membrane / glycan / disulfide 是否形成 consequential risk？
- 是否存在 known antibody / epitope / competition evidence？
- 哪些证据真正区分 candidate A / B / C？
不要机械遍历全部 evidence taxonomy。
每个关键问题允许最终状态：
VERIFIED
SEARCHED_NO_EVIDENCE
CONFLICTING_EVIDENCE
UNRESOLVED
经过合理检索仍然 unresolved 是合法科学状态。
在形成初步 candidate ranking 后，执行一次有针对性的 contradiction / alternative search。
如果：
关键问题已经被处理
+
主要 hard facts 已确认
+
关键反证已检查
+
remaining uncertainty 已显式记录
+
继续检索不太可能改变 candidate ranking、
hard constraint 或主要 risk assessment
则：
STOP RESEARCH
不要因为“可能还有相关文章”继续搜索。
3. 保留 Research → Dossier → isolated synthesis 架构，但继续做减法
保留现有正确边界：
Site Research
↓
durable Evidence Store
↓
Site Research Handoff
↓
Trusted Runtime
↓
Site Evidence Dossier
↓
fresh isolated synthesis
Site synthesis 不应继承 Research / tool-call history。
完整原文、数据库记录、详细计算结果继续保存在 Evidence Store。
Dossier 只是当前 Gate 2 所需的 trusted decision working set。
4. Dossier 不再是 evidence dump
不要再试图把所有已读 passages、所有 residue rows、所有 metadata 都送入最终 synthesis。
Dossier 应优先包含：
A. User design objective

B. Approved target hard facts
   - identity
   - state
   - chain
   - mapping context

C. Candidate sites
   - stable candidate ID
   - location
   - runtime-owned residue mapping
   - accessibility / geometry facts
   - relevant constraints

D. Decision-critical supporting evidence
   - strongest relevant primary evidence

E. Important contradictory evidence

F. Hard constraints / risks

G. Meaningful unresolved uncertainties

H. Source references
完整原文仍然可追溯，但不默认全部注入 synthesis。
不要为了满足某个字符数字损失科学信息；目标是语义精简，不是机械压缩。
5. 最关键的简化：Site synthesis 不再负责生成完整 hard-fact-rich SiteIntent
当前反复出现的问题包括：
canonical / raw / design numbering 混淆
empty SiteIntent
output token exhaustion
evidence ID 重抄
research conclusions 重复表达
这些都说明最终 synthesis 承担了太多本不属于 LLM 的职责。
请把最终 synthesis 降维成一个非常小的 structured scientific decision。
建议概念上建立类似：
SiteDecision
模型只需要表达：
selected_candidate_id

alternative_candidate_ids

recommendation
SUPPORTED / DISCOURAGED

why_selected

mechanistic_rationale

major_risks

uncertainty

optional key evidence references
不要让模型重新生成：
canonical residue numbers
design-label conversion
chain identity
mapping tables
SASA facts
candidate membership
research topic checklist
complete evidence identity
6. Runtime 根据 candidate ID hydrate authoritative SiteIntent
例如 Dossier 已经定义：
SITE_A
SITE_B
SITE_C
且 runtime 已经知道：
SITE_A
→ exact approved design labels
→ canonical correspondence
→ chain
→ coordinate presence
→ structural metrics
→ evidence relations
模型只提交：
selected_candidate_id = SITE_A
然后 trusted runtime：
SITE_A
↓
hydrate exact hotspot / mapping / evidence binding
↓
authoritative SiteIntent
这样模型不再有机会自行把：
canonical 286
错误转换成：
design 286
如果真实对应是：
canonical 286 → design 414
这一事实只能来自 runtime。
7. Site synthesis 应是 bounded structured inference，而不是另一个长 Agent loop
优先实现为：
Compact trusted Site Dossier
↓
one bounded structured inference
↓
SiteDecision
↓
runtime hydration
↓
SiteIntent
最多允许少量 schema / submission repair。
它不应该：
继续搜索
继续翻页
继续调用结构工具
带着 Research history
运行几十次模型调用
Research 负责探索。
Synthesis 负责决策。
不要因为“所有东西都叫 Agent”而强行把 synthesis 做成一个复杂 agent loop。
8. Evidence Judge 保持独立
Judge 读取：
authoritative SiteIntent
+
scoped supporting evidence
+
important contradictory evidence
+
runtime-owned hard facts
+
uncertainties
检查：
- hard facts 是否一致
- recommendation 是否有 evidence
- 是否遗漏关键反证
- 是否存在 unsupported mechanistic claim
- uncertainty 是否诚实
- 是否触犯 Golden known-failure conditions
Judge 不重新搜索文献，也不重新生成 hard facts。
通过后进入：
Gate 2
“我们到底打哪里？”
9. Context budget 不再成为本轮主要优化对象
保持：
~60k = soft working-set target
允许：
configurable/model-aware larger hard guard
当前 100k 左右可以继续作为临时 hard guard。
但不要继续为了：
70k → 59k
增加新的 generic Harness machinery。
本轮真正的成功指标是：
Research 可以很丰富
↓
最终 synthesis working set 明显更小、更干净
而不是某个固定字符数字。
10. 不要再让 Pro/Flash 成为当前 blocker
当前调试模型配置可保持不变。
不要通过：
提升 reasoning level
扩大 context
更换更强模型
掩盖 contract 问题。
Phase 2 完成后再做 controlled model comparison。
产品默认模型策略本轮不修改。
11. 在下一次真实 GPCR run 前，先用现有 evidence 做 replay validation
不要立刻再从头搜索一次。
优先复用当前已经保存的 GPCR evidence / Dossier / candidate facts，先证明：
Test A — Synthesis contract
existing compact Dossier
↓
SiteDecision
模型能够稳定返回非空、合法、简洁的 structured result。
Test B — Runtime hydration
故意使用 non-identity mapping，例如：
canonical 286 → design 414
模型只选择 candidate ID。
Runtime 必须自动产生正确 authoritative SiteIntent。
模型不得参与编号换算。
Test C — Judge
hydrated SiteIntent
+
scoped evidence
↓
Evidence Judge
必须能正常审查。
Test D — restart
Dossier 已存在时：
restart
↓
reuse evidence / Dossier
↓
do not redo research unnecessarily
以上通过后，再做一次新的真实 GPCR Case 2。
12. GPCR Case 2 的真正 PASS 标准
不是仅仅创建 Gate 2 card。
必须满足：
Target hard facts correct

canonical / construct / design numbering correct

Site research related to actual biological objective

decision-critical primary evidence obtained

important contradiction checked

no literature completeness behavior

candidate comparison scientifically coherent

SiteDecision non-empty and bounded

Runtime-generated SiteIntent mapping correct

Evidence Judge independent review PASS

uncertainty explicit

no known scientific failure mode
开放科学问题不要求唯一 hotspot 答案。
但硬事实必须正确。
13. 不要因为一个实时运行失败就回来询问
本轮请自主：
diagnose
→ patch
→ targeted test
→ replay
→ real retry
普通工程问题自行解决。
不要再每遇到：
schema issue
tool argument issue
minor contract mismatch
recoverable model behavior
就停止。
14. 只有以下情况才需要人工停止
只有：
需要改变五个 Scientific Gates

Golden truth / scientific oracle 本身疑似错误

必须大幅重写 deterministic scientific kernel

需要 production-scale GPU compute

发现 cross-project contamination / data-loss risk

需要根本改变 v3 scientific architecture
才停止等待人工。
除此之外请自行修复。
15. GPCR PASS 后，立即重新确认其余四个 accepted cases
不要重新做完整科学研究。
只做必要的 targeted revalidation，确认本轮共享 contract / runtime 修改没有破坏：
Case 1 — Soluble → Gate 2
Case 3 — Identity trap → Gate 1
Case 4 — Standard Binder → Gate 3
Case 5 — Native expert YAML → Gate 3
accepted scientific snapshots / hard oracle 不得改变。
16. 最后只在 Phase 2 freeze 前跑 full regression
开发中继续使用 targeted tests。
当：
Case 1 PASS
Case 2 PASS
Case 3 PASS
Case 4 PASS
Case 5 PASS
以后，再执行最新完整 regression suite。
Phase 2 只有在：
5 Golden Cases PASS
+
full regression PASS
+
capability parity COMPLETE
+
protected scientific kernel verified
后才正式 frozen。
17. Capability parity
更新：
docs/V2_TO_V3_CAPABILITY_PARITY_MATRIX.md
Phase 2 consequential能力不得存在未解释的：
MISSING
PARTIAL
至少确认：
active literature / DB evidence research      COMPLETE
canonical identity                             COMPLETE
literature-derived site reasoning              COMPLETE
scan-derived site reasoning                    COMPLETE
Hotspot / Gate 2                               COMPLETE
Standard Binder Strategy                       COMPLETE
Native Expert Strategy                         COMPLETE
Gate 1 / 2 / 3                                 COMPLETE
18. 本轮最终交付
完成后创建/更新：
PHASE2_CLOSURE.md
PHASE2_GOLDEN_CASE_SPEC.md
V2_TO_V3_CAPABILITY_PARITY_MATRIX.md
记录：
Research stopping policy
Dossier final semantics
SiteDecision contract
runtime hydration contract
Judge contract
GPCR Case 2 result
revalidation Cases 1/3/4/5
full regression
context metrics
model-call metrics
known limitations
创建正式 Phase 2 frozen milestone/tag。
19. 本轮结束点
本轮只完成 Phase 2。
Phase 2 正式 frozen 后：
STOP
不要进入 Phase 3。
等待人工 review。
最终实现原则
不要继续尝试让 LLM“更准确地复制事实”。
把任务改成：
Research Agent
→ 找够证据

Runtime
→ 整理可信事实

Synthesis model
→ 做科学选择和解释

Runtime
→ 补全 authoritative mapping / hard facts

Judge
→ 独立审查

Scientist
→ Gate decision
本轮目标不是做出最完美、最全面的 GPCR Site Intelligence。
目标是先稳定实现：
足够证据 → 正确候选 → 正确 mapping → 简洁科学判断 → Judge → Gate 2。
先把 Phase 2 可靠跑通，再讨论未来更深的 scientific refinement。