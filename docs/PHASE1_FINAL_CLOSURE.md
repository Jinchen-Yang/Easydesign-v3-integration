# EasyDesign v3 Phase 1 — Final Closure / Freeze

Phase 1 / 1.1 的主体保留，本轮只收尾 terminal consistency 与 Scientist Steering。
正式 contract：[五个 Scientific Approval Gates 与统一 decision semantics](V3_SCIENTIFIC_DECISION_CONTRACT.md)。
实现、复现和配置：[Agent 指南](AGENT_PHASE1.md)。最终 commit/tag 见交付包 `DELIVERY.json`。

## Terminal-state invariant

`run_session()` 的两个结束路径——本次 graph 结束、重开已结束 checkpoint——都调用同一
`TargetBridge.terminal_result()`。它通过旧 project/run resolver 读取并验证 authoritative
manifest/evidence，不信任聊天文字或仅属于该 thread 的 job receipt。
终态响应使用原 controller 中当前 run 的最新 job，避免 follow-up 重新挂接旧 prepare receipt 后
将其历史待审批状态当成当前科学状态。旧 job 记录与恢复机制不变。

科学 gate 未解决时不会返回 `finished`：缺正式 interrupt 返回 `incomplete-turn`；已交付
REJECT 返回 `rejected`，明确科学 gate 仍 pending。已有 card 或仅保存了 APPROVE intent
也不表示 gate 已解除。running/未完成/校验失败不伪装成功；普通无 scientific job 的对话可结束。
原始模型文本保留审计，普通输出说明真实未完成状态。没有新增自动 repair 或 orchestration。

## 冻结的五个 Gates

1. **Target / Structure**：我们设计谁；接受 target interpretation、construct/chain mapping 和结构状态。
   可 conditional，无 consequential ambiguity 才能由确定性 policy 继续；真实歧义必须人工决定。
2. **Site / Hotspot**：我们打哪里；批准 site 与 hotspot residues/region，独立于 YAML approval。
3. **Design Specification / YAML**：我们怎么设计；批准 binder/约束/arms/规模等，之后才允许正式 pilot。
4. **Pilot → Scale Promotion**：方案是否值得放大；真实 pilot evidence 加计算资源承诺。
5. **Final Candidates → Wet Lab**：哪些候选进入 synthesis/实验验证；计算结果不自动授权实验动作。

## Scientist Steering 与权限

- **APPROVE**：接受当前 proposal；只有可信 human action 经旧服务应用后才解除科学 gate。
- **REVISE + instruction**：持久保存人类修订，回到当前 Gate owner，保留有效上游 evidence，
  重新评估并形成新 proposal/card；不覆盖原研究目标，不自动重跑 Input，不把项目标为失败。
- **REJECT + optional reason**：拒绝当前 proposal 并停止推进；科学 gate 保留。
- **OVERRIDE + acknowledgement + warning/rationale**：研究者坚持可执行的 DISCOURAGED 假设；
  保存完整警告、明确确认和理由，旧 DecisionRecord 记录 override 标识与完整 outcome 的摘要绑定。

SUPPORTED 是证据支持的可执行选择；DISCOURAGED 是可检验但不推荐的假设，显示 warning 和
alternative 后允许人类 override；BLOCKED 是已验证硬事实/约束冲突，不能通过 override 消除。
负面 Judge opinion 本身不是硬约束；带显式 DISCOURAGED recommendation 的 reject 仍能呈现卡。
本轮用 mocked recommendation 证明此权限路径，不实现真实 hotspot/binder 风险判断。

## Gate 1 已实现的最小范围

统一 `DecisionProposal/Card/Outcome` 与原 `DecisionRequest/Record` 配合使用；action、human actor、
instruction、acknowledgement、warning 和 rationale 原子写入既有 SQLite 表。无新表、ORM、scheduler、
DAG 或 workflow engine。Model tool surface 不包含人类 action 或 authority 参数。

Gate 1 的 Chain A → REVISE Chain B → Target → Judge → 新 card → Approve 循环使用真实 saver
与 CPU Stage 01。新卡保留 parent-card lineage，且必须使用修订后的 owner/Judge assessment。
旧 request/input 与有效 upstream refs 保持原样；重新出卡前不新增 scientific job。

原研究目标、当前消息、当前 revision instruction、graph history、科学 state 分别保留。
REVISE 有自己的模型调用预算；同一 revision 的进程恢复继续该预算。即便模型再次用文本结束，
显式要求重新审阅时也保留尚未解决的 trusted steering，仍不把文字当作批准。

Gate 1 当前只是本地结构 chain-choice 子集，未声称 canonical biological identity 已完全确认。
旧 Phase 1 / 1.1 checkpoint 因 contract fingerprint 更新拒绝原样恢复；使用新 thread，
不做 checkpoint/storage migration。v2 入口、科学任务、旧记录与真实 compute recovery 保留。

## 验证与 freeze

- 全仓 integration verification：**664 passed，9 skipped**（265.01 秒）；repository/assets/compile/Ruff/mypy 通过。
- Agent 专项：**52 passed，1 skipped**；最终 terminal/revision/multiturn/HITL 定向回归：**14 passed**。
- 三处 revision 崩溃恢复均通过：human outcome 后、revision execution intent 后、steering delivery 后；
  每次为两个 human executions，调用数 11/16；原 request/refs 不变，新卡指向旧卡。
- 本轮唯一一次 DeepSeek `deepseek-flash` live smoke：**通过，16 次调用，42.52 秒**。
  真实待审批 gate 上的 prose-finalization probe 返回 `incomplete-turn / awaiting-human-approval`；
  正式 fixture approval 后为 `finished / succeeded`。该 probe 无额外 API 调用，也不创建人类响应。
- live 共一个 execution、一次 fixture human response、两个原 job、一个 run、一个 DecisionRecord；
  auth chain A，6 个 mapping entries，Viewer 校验通过。final Judge 保留 fallback=false 与 approval
  lineage 不在快照范围内的限制。未启动后续阶段。合成 fixture 不代表批准任何真实研究项目。
- 9 项 offline skip：8 项缺独立 PyMOL 环境，1 项默认关闭的 live；live 已单独显式运行通过。
- 冻结 wheel 独立安装、两个 CLI 入口与 43 个静态资源/skill 核验通过；未污染已发布环境。
- 463 份受保护文件、生产 HEAD、依赖锁和 model adapter 保持不变；成功 live 的 82 份文件未发现 key。

日志、原始 live probe 与 revision/保护范围 receipt 均在交付包 `evidence/` 中。

受保护 scientific kernel、Stage 02–07、backends、filtering、旧 recovery 与 Viewer 代码不变。
生产仓库和既有环境保持原样；本轮仅在既有 migration 分支提交，不合并或推送生产。
仓库 context 仍列出历史 worktree 拓扑提醒，沿用用户已授权的独立 migration branch，不删除它们。

Phase 1 到此正式冻结。Gate 2–5 只冻结 architecture contract，没有科学 handler。
Phase 2 的明确起点是 **Site & Mechanism / Hotspot reasoning / Gate 2**，再接入
**Binder Strategy / Design Specification / Gate 3**；Gate 4/5 在对应后续阶段实现。
未开展 Stage 02–07、Hotspot/YAML redesign、storage migration、Workbench 或 Figure 2，完成后停止。
