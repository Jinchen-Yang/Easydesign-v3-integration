# EasyDesign Local 架构

## Canonical backend architecture — Backend Product Baseline V1

本文件是当前后端架构的唯一 canonical source。日期化 acceptance、closure 和 audit 文档保留
当时的证据与变更历史；它们若与本节冲突，以本节和当前 typed runtime contract 为准。

`easydesign-agent` 是 v3 的主智能入口。Design Scientist 通过公共 DeepAgents Harness 委派
独立 specialist；LangGraph 保存 Agent execution/checkpoint/interrupt/resume，既有 scientific
runtime 拥有真实科学状态、事实校验、artifact 和 Gate transition。模型可以研究、排序和解释，
但不能创建人类批准，也不能覆盖 Runtime 硬事实。

新项目可以只提供自然语言目标。Goal bootstrap 只生成受限的 UniProt 搜索输入和物种假设，
其 authority 为 `discovery-input-only`；Target Intelligence 仍须通过原生 Stage 1 核验 identity、
结构候选、mapping、scope 和 chain，Gate 1 才能批准。PDB/mmCIF 是可选 seed，不是项目准入条件。

```text
Natural-language goal ───────────────┐
Optional local PDB/mmCIF seed ───────┤
                                     ▼
Target Intelligence → Runtime identity / structure facts → Target Judge → Gate 1
                                     │
                                     ▼
Site Research → Handoff → Dossier → SiteDecision → Runtime fact hydration → Gate 2
                                      └──── optional Site Judge ────────────────┘
                                     │
                                     ▼
Binder Strategy → Design YAML → compiler/backend validation → Design Judge → Gate 3
                                     │
                                     ▼
Pilot → BoltzGen-native evidence → Ranking & Recovery Specialist → Gate 4
                                      └──── optional second opinion ────────────┘
                                     │
                                     ▼
Scale → global PASS pool → deduplication → multi-metric Final Selection → Gate 5
                                      └──── optional second opinion ────────────┘
                                     │
                                     ▼
                              Wet-lab handoff
```

### Five Gates and authority

| Gate | Scientist approves | Runtime boundary | Judge role |
| --- | --- | --- | --- |
| 1 · Target / Structure | biological target、construct、structure、scope、chain | verified Stage 1 identity/mapping/structure evidence | required independent review on the current path |
| 2 · Site / Hotspot | one selectable candidate from the complete ranked portfolio | candidate membership、residue/mapping、topology、hard constraints | optional second opinion; cannot rerank or block valid candidates by availability alone |
| 3 · Design Specification | exact executable design arms and YAML | approved Site inheritance、scaffold registry、binding/not_binding、compiler/backend validation | required review of the compiled specification |
| 4 · Pilot Promotion | promote、another pilot、revise or stop, plus resource intent | completed native evidence、eligible candidates、plan binding | optional second opinion |
| 5 · Wet-lab Handoff | exact primary/backup final candidates | global pool provenance、dedup、selection identity、artifact completeness | optional second opinion |

Gate 2 is ranking-first: every hard-valid candidate remains selectable as A/B/C (or a longer portfolio);
risks and uncertainty change rank, confidence and explanation. Only deterministic invalidity blocks a
candidate. Gate 4 and Gate 5 reuse the Phase 3 multi-metric candidate evidence semantics. AFO is optional
enrichment and does not turn native-complete evidence into unevaluable evidence. Scale adds batch/shard
recovery, a global candidate pool, cross-arm competition, diversity and panel selection; it does not create
a second filter science.

`--through target|site|design|pilot|handoff` defines the authorized stopping scope. A transition occurs only
when the preceding current Gate has an applied Scientist outcome and the runtime validates the exact bound
revision. Restart/resume reuses verified work and never converts model prose, a stale card or a prior pending
state into approval. Technical failure, scientific FAIL and missing optional review remain separate states.

External Codex is a development and compatibility tool, not the product's scientific authority. The pure
backend can be used from VS Code/terminal without the Workbench UI; UI/Product API integration is a separate
consumer of these same contracts.

### Workbench product transport

Workbench 是 v3 Runtime 的本地浏览器投影与人工 Gate 操作面，不是第二套科学 authority。
默认 live 路径固定为：

```text
same-origin browser
  → versioned Product API + idempotent request journal
  → detached background worker + NativeGateway
  → existing v3 Runtime / artifacts / Gate contracts
```

浏览器只提交带版本与幂等键的产品命令，并从 Runtime 的 typed state、Gate card 和已校验 artifact
生成界面；不得从模型文字推断科学状态，也不得直接改写项目文件。刷新、断线和重试复用同一请求
记录，不能重复批准或推进 Gate。模型原始推理、provider/tool payload、密钥和服务器路径不进入浏览器；
界面仅展示结构化的安全进度、可审查依据和持久化的只读对话记录。Gate 1–5 的批准语义、revision
binding、BLOCKED 边界及结构/site/YAML artifact 均继续由上述 canonical v3 contract 决定。

旧的 deterministic demo 只能通过显式 `?mode=demo` 启用，不属于默认产品路径。接口、恢复、
安全投影和部署约束见 [`WORKBENCH_INTEGRATION.md`](WORKBENCH_INTEGRATION.md)。

## Lower-level scientific kernel and compatibility path

The sections below describe the durable kernel, data layout and the older `easydesign`/Codex compatibility
entry used by v3. They remain implementation background; they do not replace the canonical v3 flow above.


下述产品模型描述 v2 兼容入口，以及 v3 复用的现有科学执行与数据基础。

## 产品模型

```text
研究者批准 ───────────────┐
                          ▼
Codex + easydesign-research Skill
        │  project status / typed ActionIntent
        ▼
Agent-native façade (CommandResult)
        │
        ├── immutable ExecutionPlan + plan-bound approval
        ├── append-only Research Graph + ClaimReceipt
        ├── project/site/strategy immutable revisions
        ├── LocalStepJob + detached local_worker
        └── read-only evidence viewer
                          │
                          ▼
internal Stage 01–07 / backends / filters
                          │
                          ▼
manifest + artifact + attempt + checksum
```

EasyDesign 提供工具与审计，Skill 提供经验和判断框架，Codex 负责推理与调用，研究者掌握
site、strategy、pilot、scale、select 以及经验发布的确认权。公开接口只使用
`prepare / strategize / pilot / scale / select`，数字 Stage 仅保留为内部科学身份。

## 源码职责

```text
src/easydesign/
├── core/             manifest、artifact、attempt、decision、claim、Target Identity、hash
├── stages/           内部七阶段科学模型和算法
├── backends/         PSE、UniProt/PDB、Protenix、ScanNet、BoltzGen、TNP、本地 GPU
├── filtering/        冻结的 VHH filter profile
├── orchestration/    Stage、research façade/actions/plans/graph/approval、project/job/runtime
├── reporting/        manifest 验证后的报告和只读 Viewer
├── resources/        VHH scaffold 与 filter profile package data
├── cli.py            语义化参数解析与 CommandResult 输出
├── local_worker.py   持久本地科学 worker
└── workspace_context.py
```

`.agents/skills/easydesign-research/` 只有指令和经验 reference，不复制科学脚本。依赖方向
保持 `core/stages/backends/filtering → orchestration → CLI/worker/reporting`，科学层不依赖
Agent 产品壳。

## Target Identity v2

TargetBundle 0.5 将 biological identity 与结构来源拆开，并冻结四层身份：canonical biological
identity、experimental construct、observed coordinates、design scope。纯函数 resolver 使用带
显式参数的 deterministic Biopython global alignment；exact native/唯一 exact subsequence 可走
自动路径，engineered construct、isoform、ortholog、chimera、多解 mapping 或 scope 缺坐标进入
human review，mismatch/reject fail closed。显式 PDB ID 只证明 source identity，不能自动证明
canonical biological identity。

`residue-mapping.json`/TSV 将每个 design residue 映射到 canonical、construct、label/auth
coordinate，并记录 mapping status、edit type 和 coordinate presence。Stage 02/03 以后只消费该
冻结 mapping；mapping SHA 改变会使旧 plan/approval 失效。0.3/0.4 bundle 保持只读兼容，旧内容
不会被原地升级或改写。

## Research Graph、typed action 与 approval

`orchestration/research_graph.py` 保存 hypothesis、experiment、observation、interpretation、decision
五类 append-only event。Observation 只能引用 checksum-verified artifact；解释不能伪装成观察；
状态摘要由 event 重建并通过 `project status --json` 的 `research_state` 返回。ClaimReceipt 区分
observation、inference、hypothesis、human decision 与 external fact，结构计算指标不能自动成为
affinity/function observation。

Scientific Loop 的实际写入路径是：冻结 Strategy 时追加 `HypothesisEvent` 与
`ExperimentEvent`；`pilot review` 从完整 Stage 05 artifact 追加 deterministic
`ObservationEvent`；`pilot interpret --input` 追加引用 Observation 的 Agent-proposed
`InterpretationEvent`；reducer 由事件顺序派生 hypothesis 的
`unassessed/supported/weakened/rejected/unresolved` 当前状态；`strategy draft --from-pilot`
只在存在连通的 Hypothesis→Observation→Interpretation lineage 时创建 Strategy 1.3 草稿。
状态变化记录 interpretation 与 observation trace，不修改历史 event。Research Graph 1.0 与
Strategy 1.0–1.2 保持读取兼容；新事件使用 1.1，新策略使用 1.3。历史链身份按磁盘 JSON 的
规范化内容计算，schema 新默认字段不会改变旧事件 SHA。

`research_actions.py` 的 discriminated ActionIntent 是 Agent JSON 协议；shell command 仅由 renderer
生成以兼容人类 CLI。freeze、pilot、promotion、scale、selection 先发布 content-addressed plan，
随后 DecisionRequest/Record 绑定 plan SHA。执行前重新核验 foundation、target mapping、backend、
count/allocation 与输入 checksum。

## MSA 数据生产边界

```text
Stockholm/A3M 原始库
        │ maintainer-only 离线构建
        ▼
runtime/databases/gpcr-msa/<release-id>/
        │ canonical sequence SHA-256 resolve
        ▼
project selection → run input-snapshot
        │ 已验证 A3M + source receipt
        ▼
AFO/Protenix adapter → prediction
```

`core/msa.py` 定义 library、release receipt、per-target source receipt 和 remote provider
receipt；`orchestration/msa_precompute.py` 只负责 register/validate/resolve/snapshot。批量
Stockholm 转换仅位于 maintainer script，不进入安装包和公开研究 CLI。MSA 与 template 是
两条独立 feature：选择 library 不会触发模板搜索，precomputed 失败也不会切换 remote。

## 项目与 lineage

```text
workspace/projects/<project>/
├── PROJECT.yaml
├── DECISIONS.md
├── strategy-draft.yaml
├── interpretation.<pilot-run-id>.yaml
├── inputs/
├── strategies/strategy-rNNNNNN.yaml
├── plans/<plan-type>/plan-<sha256>.json
├── approvals/<plan-type>/<plan-sha256>/{request,record}.json
├── research/events/research-event-rNNNNNN.json
├── research/snapshots/research-state-rNNNNNN.json
├── config-revisions/easydesign.rev-NNNNNN.yaml
├── site-proposal.<method>.<run-id>.yaml
├── site-approved.rNNNNNN.yaml
├── CONFIG_CURRENT
├── SITE_CURRENT
├── STRATEGY_CURRENT
├── PROMOTION_CURRENT
└── RESEARCH_CURRENT
```

Draft 是可变讨论区；site approval、strategy revision、promotion receipt 和 canonical config
均只追加。科学结果只写 `workspace/runs/`：foundation 保存内部 Stage 1/2；每轮 pilot 从
foundation 复制并校验前缀后运行内部 Stage 3–5；production 从人工 promotion 的 pilot
前缀派生并执行 Stage 6；最终选择在同一 production lineage 追加 Stage 7。

旧七 YAML 项目识别为 `legacy-stage-project`，仅允许状态和只读查看，不原地迁移。

## Strategy compiler

旧 schema 0.1 basic matrix 保持可读。新 schema 0.2 只编译显式 variant，不强制全局
region × scaffold 笛卡尔积；binding residues 必须属于 approved site，crop 必须覆盖选择
residue，scaffold 必须来自 checksum registry。CDR override 生成 variant-local scaffold YAML；
专家原生 YAML 保存源 SHA-256 并通过同一 BoltzGen 0.3.2 adapter 校验，不能绕过 manifest。

BoltzGen capability manifest 绑定 0.3.2、pinned commit 与 source-tree SHA。已核实的显式
`avoid_label_seq_ids` 被编译为 `not_binding`；binding/avoid 重叠、无坐标、crop 外或 capability
不支持均 deterministic fail。未选择的 non-hotspot residue 保持 neutral，绝不自动变成
`not_binding`。首轮协议由独立 policy 模块严格计算为 `7 × 40 × X`；后续 pilot 才允许显式灵活
budget。Scale 默认 50,000，但任何正整数都以 `user-defined-v1` exact plan 执行。

## Worker、Viewer 与 runtime

LocalStepJob receipt append-only，worker 由独立 process session 持有。前台 Ctrl-C 不向科学
进程发信号；drain 只对分片调度写安全检查点请求。未确认的高成本命令只返回资源计划，
不得创建 revision、run、job 或 attempt。

Viewer 只从 manifest 引用加载 target/site、pilot 代表候选和最终 evidence；无编辑、上传、
批准或跨主机提交控件。Runtime 只通过 `runtime plan/install/jobs` 从锁定配方把环境、模型和
append-only registry 发布到当前 clone；cache、日志、job、validation 和 run 也只属于当前
worktree。worktree 根通过 `easydesign-workspace.yaml` 发现，不允许配置第二执行主机或引用
其他 clone 的环境/模型。

Runtime identity 与 transport 分层：Miniforge 固定 release/size/SHA；Conda explicit lock
固定每包 URL identity 和 SHA；pip 固定 requirements；文件与 Git 资产分别固定 SHA 和
commit。`config/runtime-sources.yaml` 仅定义官方/国内候选与安全前缀映射。来源探测、fallback
和 partial 全部发生在当前 clone，Conda 只消费已验证的本地 `file://` 显式视图。request 与
registry 记录策略和实际来源，但来源不参与环境或资产身份计算。

本分支不得整体合回 UI main。共享科学修复使用独立 `core:` commit，并通过
`scripts/dev.py core-sync-report --against main` 报告；UI 恢复开发后只能逐个 cherry-pick。
