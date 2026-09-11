# Resumed autonomous assignment — 2026-09-12

Current user authorization supersedes historical first-live-failure STOP instructions.
Recoverable engineering, runtime and model behavior failures must be diagnosed, patched and retried.
The seven architecture/science stop conditions below remain binding. Existing v2 and the migration
worktree are preserved. Validation fixture Gate responses authorize no real research project.

你现在接手 EasyDesign v3 的一次长周期自主开发任务。

请把当前仓库中的文档、测试、历史 milestone 和实现视为权威上下文，不需要依赖此前聊天历史。

首先阅读并理解当前仓库中与以下内容相关的最新文档：

- v3 architecture / product philosophy
- Phase 1 frozen / Phase 2 当前 closure
- scientific decision / five-gate contract
- V2_TO_V3_CAPABILITY_PARITY_MATRIX
- PHASE2_GOLDEN_CASE_SPEC
- Agent contract / hard-fact ownership
- compute-bounded validation contract
- 当前最新 blocker / review notes

如旧 README / legacy docs 与最新 v3 contract 冲突，以最新 v3 architecture / closure 文档为准。

当前总体目标：

在保持现有 v3 架构原则的前提下，自主完成 Phase 2、Phase 3、Phase 4 的全部开发、调试、测试和真实小规模验证，最终交付一个从 biological goal 到 Gate 5 / Wet-lab handoff 可以完整运行的 first-class EasyDesign scientific-agent path。

你拥有充分的工程自主权。

遇到普通 bug、tool-call mismatch、LLM 行为偏差、prompt/tool description 问题、typed contract 问题、局部 state ownership 问题、recoverable runtime error、测试覆盖缺口等，请自行：

diagnose
→ inspect source
→ patch
→ targeted test
→ live retry
→ continue

不要因为第一次 live failure 就停止。

你可以自主进行多轮 diagnose / patch / retry，直到对应功能真正稳定。

不要把我之前的设计建议当成逐步施工命令；请基于实际源码和测试选择最简单、最可靠的实现。

==================================================
1. 最终科学流程
==================================================

最终 v3 first-class path 应完整支持：

Biological Goal
↓
Target Intelligence
↓
active Literature / Database Evidence Research
↓
Canonical Target Bundle
↓
Gate 1
“我们设计的是谁？”
↓
Site & Mechanism
↓
literature-derived + structure-derived site evidence
↓
Hotspot Proposal
↓
Evidence Judge
↓
Gate 2
“我们到底打哪里？”
↓
Binder Strategy
↓
Design Specification / validated BoltzGen YAML
↓
Gate 3
“我们具体怎么设计，并采用什么 Pilot Plan？”
↓
Scientist-approved Pilot
↓
Pilot Generation
↓
optional compute/triage checkpoint
↓
Structure Prediction
↓
Validation / Filtering
↓
Failure Diagnosis / Alternative Explanation
↓
Evidence Judge
↓
Gate 4
“下一轮怎么走？”
├─ PROMOTE_TO_SCALE
├─ RUN_ANOTHER_PILOT
├─ REVISE_DESIGN
├─ REVISE_SITE
└─ STOP
↓
Scale
↓
Prediction / Filtering
↓
Global Candidate Selection
↓
Evidence Judge
↓
Gate 5
“哪些进入 Wet Lab？”
↓
Wet-lab Handoff Package

Phase 4 完成后停止，不继续后续 architecture cleanup / storage / Workbench / benchmark。

==================================================
2. 你的开发自主权
==================================================

你可以自行决定如何解决实现过程中发现的问题，包括但不限于：

- prompts / skills
- typed tool interfaces
- structured output
- specialist contracts
- bounded recovery
- middleware
- context management
- evidence retrieval
- state ownership
- tests
- compatibility adapters
- small refactors within the v3 Agent layer

如果真实 Agent 出现：

- tool sequence error
- no-progress loop
- malformed structured output
- repetitive tool call
- evidence retrieval mismatch
- recoverable model behavior
- specialist prompt weakness

不要立即停止。

自行定位根因，并允许进行多轮修复和重新验证。

目标不是让模型永远严格按照预设步骤行动，而是让 Harness 在合理的 LLM 行为波动下仍然可靠工作。

==================================================
3. 只冻结以下真正的红线
==================================================

除非发现明确 bug 并有充分证据，否则不要重写现有 deterministic scientific kernel，包括：

- target identity / residue mapping semantics
- Stage scientific algorithms
- BoltzGen scientific semantics
- AFO / prediction semantics
- filtering semantics
- existing compute-job recovery

保持：

Agent / Specialist
= scientific reasoning / interpretation

Trusted runtime
= hard facts / state / gates / constraints

Deterministic kernel
= calculations / mapping / compilation / execution

Evidence Judge
= independent critique

Scientist
= consequential decision authority

硬事实必须来自 deterministic computation、verified source 或 trusted project state。

LLM 不应成为 canonical accession、sequence length、residue numbering、mapping、approved hotspot 等 hard facts 的 authoritative producer。

开放科学问题可以没有唯一答案，但必须：

- evidence-grounded
- constraint-consistent
- uncertainty-aware
- scientifically coherent
- free of known failure modes

不要绕过 Gate 1–5。

不要创建第二套 scheduler、workflow engine、checkpoint system、decision system 或 artifact system。

保留 v2 compatibility path；在我回来验收前不要大规模删除旧 orchestration。

==================================================
4. Legacy capability parity
==================================================

持续维护：

docs/V2_TO_V3_CAPABILITY_PARITY_MATRIX.md

旧 EasyDesign 已经具备的 consequential scientific capability，必须迁入 v3 或明确说明为何被 intentionally retired。

特别确保：

Phase 2：
- active literature / database research
- primary-source evidence
- canonical identity
- structure/state reasoning
- literature-derived + scan-derived site reasoning
- hotspot
- standard Binder Strategy
- native expert strategy/YAML
- Gate 1/2/3

Phase 3：
- pilot generation
- prediction/filtering
- pilot diagnosis
- metric interpretation
- failure attribution
- alternative explanation
- next-experiment reasoning
- promotion / stop / revision

Phase 4：
- scale execution semantics
- candidate aggregation
- global competition
- diversity / quality / risk reasoning
- final candidate selection
- Gate 5 / Wet-lab handoff

不要再出现“旧 Codex/Skill 会做，但 v3 忘记迁移”的能力回退。

==================================================
5. Golden-case validation
==================================================

Golden Case 不是要求开放科学问题只有唯一答案。

遵循：

Hard facts must be correct.
Open scientific conclusions must be evidence-grounded, constraint-consistent, uncertainty-aware, and free of known scientific failure modes.

Phase 2 至少真实验证：

1. soluble protein → Gate 2
2. GPCR / membrane target → Gate 2
3. canonical / construct identity trap → Gate 1
4. standard Binder Strategy → Gate 3
5. native expert YAML → Gate 3

到 Gate 并不自动等于 PASS。

必须检查 hard oracle、evidence、scientific reasoning、known failure conditions。

如果 live case 失败：
先自己诊断和修复。
不要第一次失败就停止。

==================================================
6. Pilot / Phase 3
==================================================

Pilot 的定义是：

Generation
+ Prediction
+ Validation / Filtering
+ Scientific Interpretation
+ Failure Diagnosis
+ Next-step Decision

不是 BoltzGen 后面的单独一步。

正常模式下 Pilot 应由 Scientist 在 Gate 3 批准后启动。

Pilot Generation 后允许一个 optional compute/triage checkpoint，用于高成本 prediction 前决定是否继续、改 subset、修改设计等；它不是第六个 Scientific Gate。

Gate 4 不应只是 Scale / Stop。

必须允许：

PROMOTE_TO_SCALE
RUN_ANOTHER_PILOT
REVISE_DESIGN
REVISE_SITE
STOP

优先先实现可靠的 Scientist-steered Pilot loop。

本任务不要求你额外实现 unrestricted Autonomous Pilot Loop；如现有架构自然支持 bounded autonomy，可以记录后续设计建议，但不要让它阻塞 Phase 3/4 完成。

==================================================
7. Compute Budget
==================================================

本任务的目标是验证架构和科学闭环，不是做正式大规模蛋白设计实验。

真实 backend smoke 必须有。

production-scale compute 禁止。

使用 validation_micro 或等价模式：

- BoltzGen 只跑 backend 能真实验证路径的最小规模
- AFO / structure prediction 只跑最小代表 subset
- Phase 4 只做 tiny real scale-mode execution
- 大规模行为用 synthetic / precomputed stress fixtures 验证

如果正式科学计划是：

50,000 candidates

开发验证可以是：

requested_production_scale = 50,000
validation_execution_scale = tiny

必须明确二者不同。

特别重要：

validation_micro 中：

0 passing candidates
≠ scientific failure

样本过小时必须使用：

INCONCLUSIVE / insufficient evidence

不得据此宣称：

- site failed
- design failed
- one arm is scientifically superior
- project should terminate

除非是 deterministic hard failure，例如 mapping 非法、YAML 非法、backend 不支持等。

==================================================
8. 测试策略
==================================================

不要每改一小处就跑完整 700+ suite。

开发过程中：

先跑最相关 targeted tests。

一个 blocker 修复后：

跑相关 Agent/integration test + 对应 real golden case。

在 Phase milestone 冻结前：

再跑 full regression。

建议：

development:
targeted tests

feature closure:
relevant integration + live case

Phase 2 freeze:
full regression + five Phase-2 golden cases

Phase 3 freeze:
full regression + pilot golden cases + real micro backend

Phase 4 closure:
full regression + micro-scale path + synthetic scale stress

==================================================
9. 自主推进规则
==================================================

不要因为普通工程 bug 停止。

只有出现以下情况之一，才需要停止并等待人工：

1. 需要改变已经冻结的五个 Scientific Gates；
2. 需要大幅重写 deterministic scientific kernel；
3. 发现 Golden truth / scientific oracle 本身可能错误；
4. 需要不可逆或大规模删除 legacy data/code；
5. 需要 production-scale GPU compute 才能继续；
6. 发现可能造成数据损坏、cross-project contamination 或严重安全风险；
7. 需要根本改变 v3 architecture，而不只是局部实现优化。

除此之外：

请自己解决。

==================================================
10. Phase milestones
==================================================

不要把 Phase 2→4 合并成一个不可追踪的大 commit。

仍然保留 milestone：

Phase 2 complete
→ closure report
→ commit/tag

Phase 3 complete
→ closure report
→ commit/tag

Phase 4 complete
→ closure report
→ commit/tag

但是 milestone 之间不需要等待我的确认。

只要上一阶段科学/工程 acceptance 达标，就继续下一阶段。

==================================================
11. 最终交付
==================================================

完成 Phase 4 后停止。

请交付：

- final full repository
- PHASE2_CLOSURE.md
- PHASE3_CLOSURE.md
- PHASE4_CLOSURE.md
- updated V2_TO_V3_CAPABILITY_PARITY_MATRIX.md
- Golden case reports
- real model / real backend smoke reports
- test summaries
- compute/resource summary
- context/model-call summary
- changed-files inventory
- protected-kernel diff/verification
- milestone commits/tags
- known limitations
- proposed next steps

最终请清楚区分：

DETERMINISTIC TEST
MOCK / SYNTHETIC TEST
REAL MODEL LIVE TEST
REAL SCIENTIFIC BACKEND MICRO TEST

不要把 synthetic fixture 描述成真实科学实验。

==================================================
12. 最终目标
==================================================

不要优化“完成最多代码”。

优化：

scientific correctness
+
agent robustness
+
legacy capability parity
+
clear responsibility ownership
+
controlled compute
+
end-to-end usability

你可以自主思考、自主调试、自主修复。

当前 repo 中的 standing contracts 是边界，不是逐步施工脚本。

请先阅读当前仓库、理解最新状态，然后从当前 Phase 2 blocker 开始，持续工作直到 Phase 4 closure。

Phase 4 完成后停止，等待人工验收。