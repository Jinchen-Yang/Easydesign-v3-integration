# EasyDesign v3 Scientific Decision Contract

## 当前 Gate 2 产品契约：合法候选全部排序

2026-09-14，经用户明确确认，Gate 2 采用
[Ranked Site Portfolio 契约](GATE2_RANKED_SITE_PORTFOLIO_20260914.md)：
**VALID candidates are ranked. INVALID candidates are blocked.**
所有通过 Runtime 硬事实与显式硬约束检查的候选都进入相对排序并可由 Scientist 选择。
科学风险、证据薄弱、表面暴露差、whole-VHH accessibility 未知影响排序、置信度和说明，
不得单独取消展示或选择资格；Judge 不可用也不阻塞已有合法候选的排序与选择。
Gate 2 主输出为 A / B / C 等完整候选比较，每项绑定自己的 residues、evidence、risks
和 selection identity。Scientist 明确选择后才推进，Runtime 硬冲突仍不可绕过。

本补充已实现为 `ranked-site-portfolio-v1`，见
[实现与验证记录](PHASE2_RANKED_SITE_IMPLEMENTATION_20260914.md)。它优先于下文及所链接历史文档中
Gate 2 的单 winner、以 DISCOURAGED / Judge availability 限制普通选择、或要求额外
OVERRIDE 的规则；其他 Gate 不受此补充影响。

已验收的 Phase 2 实现仍由提交 `0859a5e583b7f44bf417e77741a8914831ca9e25` 和标签
`easydesign-v3-phase2-frozen-20260914` 固定。旧验收、记录、标签和科学意见保持原样；
以下 Phase 1/2 说明描述对应历史实现，不覆盖上述新 Gate 2 产品契约。

## 已冻结实现及历史补充

Gate 2 工程修订（2026-09-14，已纳入 Phase 2 冻结）：
[Judge 正常路径修复与显式不可用审查](PHASE2_JUDGE_RESILIENCE_20260914.md)。
有 Dossier 的 Gate 2 在独立审查因已分类技术故障耗尽修复次数后，可以显示明确标注
“审查未完成”的 Scientist 卡片。必须保留全部硬事实校验与风险；不得伪造 assessment
或 ready-to-ask。继续仍需人类确认缺失审查并填写理由，已有负面意见不得被降级覆盖。
Judge 正常完成审查与安全降级是两项独立验收，后者不能替代前者。

Phase 2 流程权限补充（2026-09-13，已纳入冻结）：
[控制流权限审计](V3_CONTROL_FLOW_AUTHORITY.md)。Phase 2 运行时直接派发当前范围内
尚未完成且获授权的动作；模型文字不能重开已完成 Gate，也不能用提前结束阻止接续。
Gate 3 REVISE 默认回到 Design；需要回到 Site 时，Scientist 必须通过可信入口明确设置
`--revision-gate site-hotspot`。新字段只作用于 REVISE，历史 outcome 的缺省值表示原 Gate。
重启不重置预算、不重做已验证的阶段。未启用的 Gate 4/5 仍不可执行，Phase 3 未开启。

Phase 2 Gate 2 补充（2026-09-13，已纳入冻结；其选择策略由上述新契约替代）：
[Judge / Gate 2 契约审计](PHASE2_JUDGE_GATE2_CONSOLIDATION_20260913.md)。
Gate 2 保护早期位点选择的科学底线，不要求完整 VHH 的后续功能和空间验证已完成。
硬事实错误、无效位点或显式约束冲突仍阻断；可纠正的科学夸大通过
`site_claim_corrections` 保留原断言和独立限定，随 warnings/limitations 进入人工卡片及下游。
合理位点可在风险、未知项明确的前提下获得 `ready-to-ask`；有警告的 DISCOURAGED 仍需
显式 OVERRIDE。当前 Site adapter 的 `reject/insufficient` 不能通过 DISCOURAGED 自动
变为 readiness。下文 Phase 1 的历史实现说明不覆盖此 Gate 2 规则，五 Gate 架构不变。

本文件是 v3 的正式 Scientific Approval Gate 与 Scientist Steering contract。
它细化 v3 architecture contract 的 human approval 原则；研究者批准科学问题及 consequential
行动，技术 artifact、manifest、SHA 与 request binding 由 trusted runtime 校验。

五个 Gate 共用 decision infrastructure。Gate type、scientific payload、owner specialist 和
policy 可以不同；不能因此创建五套 workflow、scheduler 或独立 recovery engine。
本轮仅有 Gate 1 的本地 chain-selection adapter；下表不注册或执行 Gate 2–5 handler。

## 五个 Scientific Approval Gates

| Gate | 科学问题 / Decision | 批准的内容 | 位置与 revision owner |
| --- | --- | --- | --- |
| 1 · `target-structure` | 我们设计的到底是谁？Target / Structure Decision | biological target、construct/chain mapping、结构状态和 target interpretation 是否可作为设计依据 | Input → Target Intelligence → Canonical Target Bundle → Structure Decision → Gate 1；owner 为 Target Intelligence / Structure Decision |
| 2 · `site-hotspot` | 我们到底要打哪里？Site / Hotspot Approval | 当前 site 与 hotspot residues / region | Structure Decision → Site Intelligence → Hotspot Selection → Gate 2 → Design Specification；owner 为 Site & Mechanism / Hotspot reasoning |
| 3 · `design-specification` | 我们具体准备怎么设计？Design Specification / YAML Approval | binder 类型、设计约束、hotspot conditioning、排除区域、scaffold/CDR 条件、design arms、generation scale 与设计参数 | Hotspot Approval → Design Specification / YAML → Gate 3 → Pilot Generation；owner 为 Binder Strategy / Design Specification |
| 4 · `pilot-promotion` | 这个方案值得放大吗？Pilot → Scale Promotion Approval | 基于真实 pilot evidence，哪些 strategy/arm promote、哪些停止，以及是否投入更大计算规模 | Pilot → prediction → validation/filtering → Evidence Judge → Gate 4 → Scale；owner 为 Pilot strategy / promotion planning |
| 5 · `wet-lab-handoff` | 哪些最终候选真正进入实验？Final Candidates → Wet Lab Approval | 哪些 candidates 进入 synthesis、experimental validation 或 wet-lab handoff | Scale → prediction → validation/filtering → Final Candidates → Evidence Judge → Gate 5 → Wet Lab；owner 为 Final candidate selection / experimental handoff |

Gate 1 可以 conditional：identity、construct、chain、state、mapping 没有 consequential ambiguity
时，可由经过验证的确定性 policy 自动继续；存在真实歧义时必须人工决定。Agent 的自然语言
判断不创建“无歧义”policy。本轮继续复用旧 Stage 01 的 chain gate；单链自动准备不意味着
已确认 canonical biological identity，也不新增完整 target identity reasoning。

Gate 2 与 Gate 3 永久分开：Hotspot 是“选择打哪里”；Design Specification 是“准备怎么打”。
生成 YAML 不能自动批准 hotspot，批准 hotspot 也不能授权正式 pilot。Gate 3 通过后才允许
正式 pilot generation。Gate 4 同时是 scientific evidence decision 和 resource commitment gate。
Gate 5 是进入现实实验行动前的最终人工 gate；计算筛选成功不等于批准 synthesis 或实验。

## 一套 Scientist Steering semantics

通用数据在 Agent 层表示为 `DecisionProposal / DecisionCard / DecisionOutcome`，与原
`DecisionRequest / DecisionRecord` 配合表达一个 ScientificDecision；不另造一个重复容器。

- Proposal/Card：`gate_type`、owner、scientific payload（Gate 1 为原 request 的选项）、
  `judge_status`、warnings、recommended alternative、`parent_card_id`。
- Runtime binding：card/assessment ID、project/run、canonical refs、request binding 和 source role。
- Outcome：`card_id`、action、`human_actor`、`human_instruction`、`optional_reason`、
  `explicit_acknowledgement`、`recorded_warnings`、`source_role=human-cli`。
- Outcome 由可信 CLI/未来可信交互入口创建；model tool 参数没有 action、human actor 或 approve
  authority。普通 chat，包括“我批准”“请确认”，都不构成该 Outcome。

| Action | 数据要求 | 科学与 runtime 语义 |
| --- | --- | --- |
| APPROVE | 已识别的人类、当前绑定的可批准 proposal | 接受当前科学提案，允许进入下一个 consequential state；仍须旧 decision service 校验并真正应用 |
| REVISE | 非空 `human_instruction` | 结束当前 proposal 的待决状态，回到该 Gate owner 做局部修订；保留有效上游证据，生成新 proposal，必要时重新 Judge，再进入同一 Gate；不是项目失败，也不批准旧选择 |
| REJECT | 可选 `optional_reason` | 拒绝当前 proposal，停止推进；不把科学项目标为 operational failure，不自动清除原科学 gate，不擅自重跑输入 |
| OVERRIDE | explicit acknowledgement、已展示并记录的 warning、必填 human rationale | 对 DISCOURAGED 但仍可执行的假设坚持推进；记录“selected by explicit human override against current Evidence Judge recommendation”；不改写 Judge 的意见，不绕过硬约束 |

对同一卡的完全相同响应是幂等的；不同 action、actor、instruction、acknowledgement 或 rationale
是冲突响应，不能覆盖原记录。新 proposal 必须有新 card，并通过 parent-card lineage 保留修订来源。
每个 outcome 与完整 human-response event 在一次 SQLite 事务中保存，使用既有表，无 schema migration。

本轮 OVERRIDE 在完整 Agent outcome 保存 warnings/acknowledgement/rationale。旧 DecisionRecord
继续使用 `authority=human`，其 acknowledgement 明确标识 override，并绑定完整 outcome 的摘要。
不修改旧 record schema；旧服务仍独立拒绝不存在或不合格的选项。

## Recommendation 与 Hard Constraint

| Status | 含义 | 人类行动边界 |
| --- | --- | --- |
| SUPPORTED | 当前证据支持在明确局限下提出该选择 | 可 APPROVE、REVISE、REJECT；Gate 1 的支持是结构选择问题可执行，不是生物学身份确认 |
| DISCOURAGED | 有科学风险或不是推荐方案，但仍可执行、可检验 | 显示不推荐原因和推荐 alternative；可 REVISE、REJECT，或明确 OVERRIDE；普通 APPROVE 不能悄悄忽略 warning |
| BLOCKED | 与已验证硬事实或不可满足约束冲突 | 不能用普通 override 伪装成功；解释需要修订的 upstream assumption/input/constraint |

例如 accessibility 差、membrane clash 风险高、pilot 成功概率低、geometry 不理想或替代方案更强，
本身属于 recommendation 问题。缺失 residue、target/mapping 不匹配、逻辑互斥约束或缺少合法执行
输入，才可能构成硬阻断。研究者坚持不消除硬约束；Agent 不推荐也不剥夺研究者测试可行假设的权力。

本轮 Judge 的可选 `recommendation` 只含一个有科学意义的 option identifier、SUPPORTED/DISCOURAGED、
warnings 与 alternative，不复制 evidence identity。BLOCKED 由 runtime 的硬事实校验落实。真正的
protein-design 风险判断与 hotspot/binder 约束解释属于 Phase 2；本轮只通过 mocked recommendation
证明权限和数据语义，不能把测试警告当作真实科学判断。

`ready-to-ask` 表示问题和证据足以让人决定，不等于“我推荐此选项”，也不是 approval。一个有风险
但可检验的 proposal 可以同时 ready-to-ask 和 DISCOURAGED。明确的 DISCOURAGED recommendation
即使伴随负面 `reject` opinion，也可以呈现 warning card；不会把不推荐机械升级为禁令。`insufficient/reject` 不能作为未被验证的
硬事实；应补齐或重新构造可评估的问题，而不是把个人偏好描述为不可执行。

## 最小局部 revision 与研究目标

REVISE 由当前 Gate owner 接回：1→Target/Structure；2→Site/Hotspot；3→Binder/Specification；
4→Pilot strategy/promotion；5→Final selection/handoff。下游修订不自动使仍有效的上游状态失效。
例如 Target/Structure 有效而 Hotspot 需要调整，只回到 Site/Hotspot，不重跑 Target。

以下上下文分别保留，不相互覆盖：

1. immutable thread/research goal；
2. current user message；
3. current revision instruction 与其来源 card；
4. LangGraph conversation history；
5. authoritative scientific state。

本轮 Gate 1：REVISE 在中断处持久保存，开启新的 human execution budget（恢复同一 revision
不再重置）。`Command(resume)` 把 outcome 放入原工具的结果与 graph history，避免在尚未完成的
AI tool call 与 ToolMessage 之间插入非法用户消息。Target 收到独立的 revision instruction、原目标、
当前消息和经过验证的现有 run/refs。既有 prepare bridge 只 reattach，不创建新的 scientific job。

新卡必须使用 revision 之后的 Target 评估和 Judge 评估。原 DecisionRequest 若仍能表达 A/B 选项，
保持不变；重新选择 B 是新的 proposal/card，不是改写 input、request 或旧科学 attempt。

## Terminal-state invariant

每个返回 `finished` 的路径，包括重新打开已结束 graph 的 resume，都调用相同的 deterministic
finalization guard。该 guard 从原 project/run 解析入口读取并校验 authoritative manifest/evidence，
不以模型文字、thread-bound job receipt 或“graph 没有 next node”作为科学完成的依据。

- 真正的 trusted LangGraph decision interrupt 返回审批状态与 runtime card。
- graph 已结束而科学 gate 仍 pending：返回 `incomplete-turn`；已交付的 REJECT 返回 `rejected`，
  明确科学 gate 仍未解决。已有 card 或已保存但未应用的 APPROVE intent 都不能伪装 `finished`。
- 科学任务仍运行、未完成或状态校验失败：不返回 `finished`；不自动重提计算或执行 repair。
- 没有 scientific run/job/gate 的普通对话可以结束；成功的科学准备须由已校验结果支持。
- 原始 assistant 文本保留用于诊断，普通响应使用真实状态说明，不能显示伪造的完成结论。

该检查只是终态校验，不创建 scheduler、DAG、polling loop 或第二套 orchestration。
外部旧 CLI 与 Agent 仍不得并发写同一项目；本轮没有引入跨入口锁或修改旧 compute recovery。

## 冻结范围与 Phase 2 起点

Phase 1 冻结：first-class harness、Model API、Target Intelligence、Evidence Judge、Gate/HITL runtime、
四类 Scientist Steering、可信 human input/provenance、interrupt/resume、terminal consistency。
Gate 1 实现的是本地结构 chain-choice 子集；Gate 2–5 只有本 contract，没有科学 handler。

Phase 2 从 Site & Mechanism / Site Intelligence / Hotspot reasoning 与 Gate 2 科学实现开始，
再连接 Binder Strategy / Design Specification reasoning 与独立的 Gate 3。它负责真正的
SUPPORTED/DISCOURAGED/BLOCKED protein-design 判断。Gate 4/5 在各自后续阶段接入。
不提前实现 Stage 02–07、hotspot/YAML redesign、storage migration、Workbench 或 Figure 2。
