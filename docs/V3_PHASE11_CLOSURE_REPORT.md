# EasyDesign v3 Phase 1.1 closure report

日期：2026-09-10。范围：Agent runtime / evidence contract closure。

本轮继续使用 `codex/v3-migration-phase1-20260910`，工作目录为
`/data/easydesign-worktrees/v3-phase1-20260910`。Phase 1 基线是
`da5507ed2124fc4a471ea5c39cb440aa8c48a089`；最终提交见交付包的 `DELIVERY.json`。
生产仓库 `/data/Easydesign` 保持在 `c93da74660639c095d3de252cddb88a00fd3671d`。

## 修订与证据

| 请求 | 实现后的行为 | 回归证据 |
| --- | --- | --- |
| Model-call budget 生命周期 | 默认每个用户轮次 32 次，Coordinator、Target、Judge 共享；新 follow-up 开新轮；HITL、重启和 unfinished resume 继续同轮；lifetime 仅遥测 | 同 thread 3 轮累计 37 次（17/10/10）通过；预算耗尽后重启不能绕过；follow-up intent 写入后、checkpoint 前崩溃可以继续 |
| Judge contract | LLM 只输出 `verdict / reasons / limitations`；trusted callback 附加 canonical binding、assessment ID、source role | 模型携带机械身份字段时拒绝；无委派 context 时拒绝；证据漂移拒绝；已存 assessment 与当前 canonical refs 一致 |
| Completed provenance | 从 SHA 校验通过的旧 provenance artifact 读取有科学意义的值；保留严格布尔值 `false`；未知值为 null | 真实 CPU Stage 01 的 Judge tool 输出含 origin、source、selected_chain、fallback_used=false；无 fields-only 结构；字符串 `"false"` 拒绝 |
| Approval lineage | 采用请求中的第二个方案：声明最终 snapshot 不验证审批来源，禁止 final Judge 推断批准者或从 selected chain 推断 authority | snapshot 明示 `approval_provenance.status=not-in-snapshot`；Judge skill 和 Coordinator contract 都约束该边界 |
| Immutable goal / follow-up | 专家 task 的 `user_goal` 始终为原研究目标，`current_user_message` 独立携带当前澄清；LangGraph history 保留原始消息和后续消息 | 真实 graph、saver、CPU worker 的 multi-turn 测试，两个专家均保留原目标；修改已有 thread 原目标被拒绝 |
| 普通输出 | 默认科学结果、链、局限、Viewer 入口；CLI display / stream 省略底层校验标识；显式 `--technical-details` 可查看诊断 | 普通输出不含样例 SHA/assessment ID，保留科学局限；technical 输出还原原记录；底层存储不被显示层修改 |

### 预算与 replay 边界

`agent-execution` 和 `model-call.execution_id` 是原 events 表中的事件，不是新工作流对象。
运行时先保存当前轮次与用户消息，再用同一 execution ID 写入 LangGraph HumanMessage。
若进程在保存 intent 后、写 checkpoint 前退出，恢复时继续提交同一个消息 ID。
同一轮的每次模型调用先保留一个预算名额；失败调用也不退回，避免重试绕过安全上限。

普通 resume 不创建新轮，也不重置预算。等待审批或尚未完成时，新的 follow-up 被拒绝，
需先处理当前轮次。完成或拒绝后的明确 `--message` 才创建新轮。达到单轮预算后不会重启
scientific job；既有 context 字符预算仍保留，本轮不新增对话压缩或其他长记忆机制。

`session_store / command ledger` 继续只承担 Agent replay 与原 scientific job 的最小幂等桥。
没有新 SQL 表、ORM、scheduler、DAG、依赖计算或 workflow abstraction。真实科学任务的
恢复、重跑、attempt 和批准记录仍由旧服务处理。

### Judge 的科学意见与 trusted binding

EvidenceBinding 是 frozen runtime DTO。委派 Judge 时捕获 evidence ID、完整 SHA-bound refs
和 pending request binding；Judge 的只读 tool 和 callback 都重新验证当前快照与它一致。
模型不再复制这些字段。Coordinator 只能使用 trusted callback 生成并存储的 assessment；
它不能用自然语言或自造 assessment ID 获得 `ready-to-ask` 权限。

保存的 EvidenceAssessment 仍包括 canonical refs、request binding、随机 assessment ID 和
`source_role=evidence-judge`。回到 Coordinator 的 receipt 省去重复的完整 refs/request/source，
保留执行后续决定所需的 assessment ID；这些内部信息不会默认显示给普通用户。

Completed provenance 白名单包括 origin、source、selected_chain、fallback_used。它们来自旧
artifact 的已校验内容，不由 LLM 补齐；`StrictBool` 防止 `"false"` 被当作真值。`false` 明确
表示未使用 fallback，null 才表示未提供该值。科学意见仍是模型自然语言输出：本轮通过
输入契约、明确指令和回归/live 检查纠正该问题，不声称能机械证明任意自然语言没有幻觉。

本轮没有把 DecisionRecord 加入最终 Judge snapshot。`not-in-snapshot` 是评估范围限制，
不表示旧 decision service 没有执行或没有保存有效批准。Judge 可以说明自己的范围限制，
但不能声称自己独立验证了 human approval lineage。测试 receipt 对旧记录的独立核验与
Judge 所见的科学快照分开记录。

## 验证结果

| 验证 | 结果 |
| --- | --- |
| 定向 Judge / multi-turn / HITL 回归 | 10 passed，39.49 秒 |
| 完整 Agent 专项（unit + integration） | 44 passed，1 skipped，95.65 秒 |
| `scripts/dev.py verify --mode integration` | passed；repository/assets/compile/Ruff/mypy 通过；mypy 检查 169 个文件 |
| 完整离线 regression | **656 passed，9 skipped，211.23 秒** |
| 新 wheel 构建、独立安装、CLI/import 检查 | passed；43 个静态资源及两份专家 skill 按字节核验；v2/v3 入口可用 |
| 生产与受保护科学目录完整性 | passed；463 tracked files 未变；依赖锁与 model adapter 未变 |

9 项离线 skip 中，8 项为未配置独立 PyMOL 环境的集成测试，另 1 项为默认不调用付费模型的
live fixture；后者在下节单独启用。没有用 skip 代替 live 通过。既有 Viewer 实现未修改，未新增
浏览器 UI 测试或 Workbench 验证。

### 受控 live Stage 01

使用已有私有配置中的 `deepseek / deepseek-flash`，固定官方 endpoint，SDK retry=0，
默认单轮预算 32、单次输出上限 2048 tokens。本轮进行了两次受控尝试：

| 尝试 | 结果 | 调用 / 时间 | 说明 |
| --- | --- | --- | --- |
| `agent-live-ce53856931` | 失败，停在审批前 | 7 次，21.04 秒 | Coordinator 用普通文字问确认，未委派 Judge、未生成 runtime 审批卡；没有 human response 或批准 |
| `agent-live-9d9c59ef9f` | **通过** | **16 次，38.48 秒** | Target → Judge → 正式卡/HITL → 原 decision service / Stage 01 → final Judge → 停止 |

首次失败后，只收紧 Coordinator 和 Target 的既有指令：偏好链已明确时，先 Judge 再正式审批卡，
不先用聊天询问；调用卡工具会在批准前 interrupt，不代表批准。没有新增自动审批、调度或
workflow 逻辑。指令修改后重新跑了完整离线 regression、Agent 专项和 wheel 校验；上表及
上一节主结果均包含最终版本的验证。首次完整离线结果也保留：656 passed、9 skipped。
两次 live 总计 23 次模型调用；成功闭环按角色为 Coordinator 8、Target 4、Judge 4。

成功 fixture 核验：

- 一个持久 execution，审批恢复后仍使用相同预算；一次 fixture human response。
- 两个原 scientific job、一个 run、一个 DecisionRecord，最终 bundle 为 attempt-0002。
- 选中 auth chain A，sequence length / mapping entries 均为 6，Viewer 验证通过。
- provenance 实值为 origin=experimental、source=local-file、selected_chain=A、fallback_used=false。
- 两次 Judge verdict 分别是 `ready-to-ask` 与 `assessed`；canonical refs、request binding 和
  source_role 由 runtime 保存。completed assessment 的 request binding 为 null。
- final Judge 明确写出 `fallback_used=false` 是验证后的值，意为未发生 fallback；未将它解释成
  “可能使用 fallback”。它明确将 DecisionRecord / human approval lineage 排除在自身证据范围外，
  未由 selected chain 声称独立验证人工批准。
- 最终普通输出说明链 A、6 位点 mapping、本地来源和未使用 fallback，保留生物学身份、参考
  完整性及功能推断限制和 Viewer 路径；不含 SHA 或内部 assessment ID。
- 扫描成功 fixture 与日志中的 82 份文件，未发现配置密钥；交付打包另做密钥值扫描。
- 未启动 Stage 02 或任何后续设计阶段。该合成 fixture 不证明真实目标的生物学身份或功能。

原始失败日志、成功日志、`phase11-first-live.json`、`phase11-live-result.json` 和完整性核验
均在交付包 `evidence/` 中。成功结果是一次受控 live 验收，不声称消除了模型输出的全部随机性。

## 兼容性与未扩展范围

- 保留 v2 `easydesign` 入口；v2 import 不提前加载 optional DeepAgents。
- 本轮 contract/fingerprint 更新，旧 Phase 1 Agent checkpoint 不迁移；旧 thread 的恢复会明确
  拒绝不兼容 fingerprint，应创建新 thread。既有 scientific job/run/decision record 不变。
- 463 份受保护 tracked 文件与生产基线保持一致，包括 core、所有 stages、backends、filtering、
  orchestration、reporting、local_worker 和既有 Viewer 示例。生产目录 clean，HEAD 不变。
- Model adapter、`pyproject.toml`、`uv.lock` 没有变化；未改 backend 环境或已发布环境。
- 未进行 storage migration、Workbench、Site/Mechanism、Binder Strategy、Figure 2 或 Phase 2。
- 仓库 context 的拓扑检查仍列出原生产目录和历史 worktree；沿用用户已明确授权的独立 migration
  branch，保留所有历史 worktree，没有修改 policy 或为满足拓扑检查删除已有工作。

## 复现

在 migration worktree 使用已锁定的独立 Agent 环境：

```bash
runtime/tmp/agent-locked-staging/bin/python -m pytest -q \
  tests/unit/agent tests/integration/test_agent_target_vertical_slice.py

PYTHON="$PWD/runtime/tmp/agent-locked-staging/bin/python" \
EASYDESIGN="$PWD/runtime/tmp/agent-locked-staging/bin/easydesign" \
  .venv/bin/python scripts/dev.py verify --mode integration
```

模型配置及私有 `.env.local` 的显式加载见 [Agent 安装配置指南](AGENT_PHASE1.md)。live fixture
使用合成双链结构和独立 workspace，由测试代码模拟该 fixture 的一次人工确认，不代表
授权任何真实研究项目。默认离线 regression 跳过付费 live，显式启用时才执行。

交付包含 closure report、配置指南与无密钥模板、Phase 1.1 增量补丁和从 Phase 0 基线开始的
完整 migration 补丁、新 wheel、测试/完整性日志及校验和。私有配置和真实 key 不进入交付包。
完成本轮 closure 后停止，不自动进入下一阶段。
