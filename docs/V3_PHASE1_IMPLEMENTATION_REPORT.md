# EasyDesign v3 Phase 1 实施报告

日期：2026-09-10。**用户配置凭据后，已补齐 DeepSeek 的真实模型闭环验证，并修复了
live smoke 发现的“准备前读取证据”问题。最新结果见
[Phase 1 live 补测报告](V3_PHASE1_LIVE_VALIDATION.md)。工作仍停留在 Phase 1。**

## 交付位置与兼容范围

- 基线：`c93da74660639c095d3de252cddb88a00fd3671d`，原 `easydesign-local`。
- 独立分支：`codex/v3-migration-phase1-20260910`。
- Suzhou2 工作目录：`/data/easydesign-worktrees/v3-phase1-20260910`。
- 原 `/data/Easydesign` 保持原分支、原提交和干净工作树，未合并或推送本次实现。
- 新入口为 `easydesign-agent`；v2 的 `easydesign` 入口和科学代码保留。
- 安装和模型配置见 [AGENT_PHASE1.md](AGENT_PHASE1.md)；README 已提供直接可复制的配置示例。

只支持本地 PDB/mmCIF、`review-gated`、`stop_after_stage=1`。已有项目不符合边界时拒绝，
不自动改写配置。本轮未实现远程身份检索、结构预测、Stage 02–07、Site/Binder specialist、
storage 迁移、Workbench 或 Figure 2。

## 已实现的纵向路径

1. 独立 CLI 直接装配模型 API、一个 `create_deep_agent` harness 和两个 isolated 专家。
2. Target Intelligence 通过 typed `prepare_target` 调用旧 `target_prepare(detach=True)`。
   合成双链 fixture 使用真实 local worker，触发原 `chain-selection` DecisionRequest。
3. Evidence Judge 只读冻结输入、链选项与当前请求。此时没有成功 TargetBundle，程序也不伪造。
4. Judge 完成回调校验结构化结果，由运行时登记 assessment ID。Coordinator 不能伪造 Judge 通过。
5. 决定卡经公开 LangGraph `interrupt` 暂停；关闭进程后用同一 thread 恢复。
   展示问题、选项、证据引用、局限和批准动作，内部 SHA/修订绑定不要求用户编辑。
6. 真实 CLI 输入 approve/reject，用户身份来自本地 UID。批准后经兼容 YAML 输入调用旧
   `target_approve`，在原 run 的 `attempt-0002` 完成 Stage 01；拒绝不写批准 record。
7. 从原 manifest/ref 验证 bundle、mapping、identity、provenance 和既有 Viewer；最终由
   Judge 给出有限结论并停止。结构-only 结果保留 biological identity 未确认、reference
   completeness 未知、结构质量不等于亲和力或功能证据等局限。

支持 `start`、`resume`、`status`、CLI 交互式 approve/reject 和受限进度事件。
完成或拒绝一个 turn 后可用 `--message` 提供新澄清；有待批卡时先拒绝旧卡，再形成新卡。
框架任意 edit/respond 没有开放。Ctrl-C 只终止 Agent 观察，不停止科学 worker。

## 代码与状态归属

| 文件或对象 | 本轮职责 |
| --- | --- |
| `agent/cli.py` | 单 asyncio 事件循环、会话启动/恢复、真实用户响应、卡片展示 |
| `agent/harness.py` | 一个公开装配点、两个专家、profile、权限 middleware、可信专家回调 |
| `agent/models.py` | 显式 provider/model/secret 环境变量名，公开 `init_chat_model` 适配 |
| `agent/contracts.py` | 有界且 `extra=forbid` 的任务、评估、决定卡 DTO |
| `agent/tools.py` | 原科学接口桥接、引用验证、角色 handler 检查、最小恢复对账 |
| `agent/session_store.py` | 具体 SQLite 会话/事件/command/response intent 实现 |
| 两份包内 `SKILL.md` | 自含 Target Intelligence / Evidence Judge 工作边界 |
| `metadata/agent.sqlite` | Agent 会话历史、幂等提交关联、人工响应 intent |
| `metadata/agent-checkpoints.sqlite` | 完全由公开 AsyncSqliteSaver 管理的执行 checkpoint |
| 原 job receipt / DecisionRecord / run / manifest | 科学任务、批准和不可变科学证据的原有权威 |

原计划 `permissions.py` 的职责直接放在 harness 的 middleware 与工具 handler 中，避免
再建立一层仅转发接口。没有引入 ORM、通用 Store 抽象、任务队列、scheduler、DAG 或 workflow engine。

command identity 基于绑定项目、操作和科学输入，不使用易变化的模型 tool-call ID。
对于已提交操作，恢复先检查原 receipt；唯一匹配才 attach。无法确定提交身份时返回
`reconciliation-required`，不重新执行 prepare。DecisionRecord 已存在但尚未提交 worker 时，
先用原函数验证 record，再补接原 decision worker。queued receipt 无确认 PID 时保留并提示对账。

两个 SQLite 文件和科学文件之间没有跨存储原子事务保证；恢复依赖持久化 intent 和原引用。
旧 CLI 不使用新锁，因此同一项目需要单一写入口；本轮不宣称解决新旧 CLI 并发写入。

## 权限与输出边界

运行时关闭默认 general-purpose 专家和 shell、通用写入、编辑、删除、目录枚举等工具。
每个角色的最终工具集有测试断言，同时在执行 middleware 与 typed handler 检查权限。
Judge 无 launch、approve、job 状态写入或再委派能力。项目根、科学 run、请求身份与 approved_by
由可信入口绑定，模型不能通过多余参数覆盖。路径逃逸、symlink、过期请求和被篡改证据被拒绝。

只给模型挂载包内相关技能和当前 thread 的 Agent 结果目录，不挂整个仓库、科学 run 或环境文件。
工具摘要以约 8 KiB 为界，较大摘要写入 Agent 结果目录后返回引用；超过 256 KB 则要求缩小查询。
不复制完整 PDB/MSA/原始日志到 checkpoint。保留 fixture checkpoint 最大值为 344,064 bytes；
这是测试样本观测值，不是所有未来对话体积的保证。

密钥仅从配置指定的环境变量传给 SDK，配置和会话不存密钥值；构建客户端后移除该进程中的
对应变量，科学 worker 启动边界另外去除 API key/token 环境变量。远程 tracing 默认关闭。
模型调用预算跨进程持久化，模板最多 32 次、单次最多输出 2,048 tokens、90 秒超时，SDK 重试为 0。

## 模型配置与依赖验证

模板路径为 `config/llm.template.yaml`，与本仓库既有 `config/` 目录一致。
默认 `provider: deepseek`、`model: deepseek-flash`、`secret_env: DEEPSEEK_API_KEY`，
使用固定官方 endpoint `https://api.deepseek.com` 和非 thinking 工具调用。
该别名在 2026-09-10 的 [DeepSeek 官方文档](https://api-docs.deepseek.com/) 中对应 V4.1 Flash；
provider 管理的别名可能变化，并非不可变权重身份。

另外支持 OpenAI、Anthropic 的官方 endpoint。切换时同时修改 provider、model、secret_env。
不因 CatMaster 示例而扩展 OAuth、OpenRouter、Gemini、自定义 endpoint。
`config/llm.yaml` 和 `.env.local` 被 Git 忽略；使用 `cp -n` 保留已有文件，私有 env 文件
`chmod 600` 后由用户手动加载，程序不会自动 source 文件。

| 依赖 | 验证版本 |
| --- | --- |
| Python | 3.11.15 |
| uv | 0.12.3 |
| deepagents | 0.7.13 |
| langchain / langchain-core | 1.4.0 / 1.6.2 |
| langgraph / langgraph-checkpoint-sqlite | 1.2.11 / 3.1.1 |
| langchain-openai / langchain-anthropic | 1.6.1 / 1.7.1 |
| pydantic / httpx | 2.13.4 / 0.28.1 |
| OpenAI SDK / Anthropic SDK | 3.11.0 / 1.4.0 |

锁文件的独立包名由 41 增至 92，原有包版本没有变化。框架引入 LangSmith、Google GenAI 等
传递依赖，但本轮未启用对应远端服务。原生产环境和科学 backend 独立环境没有更新。
新测试环境位于迁移 worktree 的 `runtime/tmp/agent-locked-staging`，安装后以该环境执行验证。
官方包源下载受阻时使用仓库已有配置允许的阿里云镜像；随后 `uv lock --check --offline` 通过。
同机暖文件缓存、独立 Python 进程的 harness 导入用时为 6.347 / 6.911 / 6.842 秒，
包含当时主机负载影响，不是冷机器安装或推理延迟基准。

## 首次交付验证结果（live 补测前）

`scripts/dev.py verify --mode integration` **通过**（总计 245.957 秒）：结构检查、既有
Mol* 资源校验、compileall、Ruff 全部通过；mypy 在 169 个源码文件中未发现问题。
完整 pytest 为 **647 passed，9 skipped，178.24 秒**。跳过项是 1 项显式启用的 live model
smoke 和 8 项要求独立 PyMOL 环境的既有集成测试；本轮没有为它们安装科学 backend。

- Agent 专项：**35 passed，1 skipped，71.72 秒**。覆盖真实 CPU worker、三个 provider 的
  HTTP mock 适配、角色权限、可信 Judge、证据篡改、真实 saver/HITL、关闭重开 CLI、拒绝、
  重复/错误响应、结果 offload 与各关键 crash window。默认唯一跳过项为 live model smoke。
- v2 指定回归：**69 passed，5.08 秒**，覆盖 target_identity_v2、s01_target_bundle、
  stage01_sources、decision_gates、application、workspace/run_layout、local_jobs、Target Viewer。
- wheel：在新 staging 构建，并在独立 wheel 安装环境验证导入位置、两份技能及 43 份既有资源
  字节一致、两个 console 入口和 `--help`。v2 导入不会提前加载 deepagents。
  安装烟测复用已验证的锁定依赖目录；没有从 checkout 偷用 EasyDesign 包，也不等于全新主机离线分发。
- 科学保护：对 core、stages、backends、filtering、orchestration、reporting、local_worker
  和 APOE 示例共 **463 个 tracked 文件**计算 Git blob hash，全部等于基线。
  文件清单聚合 SHA-256：`8a9efb490b8d976f7c90e81691e999e6f43e951cb883153010f45d1eddb64632`。

新增 console 入口要求对 `scripts/check_repository.py` 和既有 `test_uv_onboarding.py` 做精确
兼容调整：从只允许 v2 一个入口改为要求 v2 + agent 两个入口，其他结构规则保留。
这是 Phase 1 的必要检查调整，未修改科学实现或拓扑政策。

`scripts/dev.py context` 所依赖的政策文件未改动。最终 scope 包含已读的 CLI 指南，bundle 为
`7a5790981deac87b9eacd14d4208d9bbb146044d8d65bcbe5328c7669f2d63c0`，仍报告两个既存 worktree 拓扑阻断项
（chain-feature-inputs、openfold3-314）。本轮依据用户明确授权创建独立迁移分支，未清理这些
既存 worktree，也未修改 policy 规避检查。context 的拓扑结果与 integration 代码验证分开报告。

证据日志在 Suzhou2 本工作树 `runtime/tmp/agent-bootstrap/`：
`agent-suite-final.log`、`v2-regression.log`、`verify-integration-2.log`、
`wheel-smoke-delivery.log`、`integrity-final.json`、`context-final.json`。

## Live smoke 补测状态

首次交付时尚无 key，live smoke 未运行。用户随后安全配置凭据，本次已通过 DeepSeek
连通性测试及真实模型 Stage 01 闭环；详情与新一轮回归结果见
[补测报告](V3_PHASE1_LIVE_VALIDATION.md)。OpenAI / Anthropic 仍只有 HTTP mock 适配验证，
没有使用 DeepSeek key 冒充其他 provider 的真实账号验证。

按 README 配置私有 key 后，在独立 Agent 环境执行：

```bash
EASYDESIGN_AGENT_LIVE=1 EASYDESIGN_AGENT_MODEL_CONFIG="$PWD/config/llm.yaml" \
  python -m pytest tests/integration/test_agent_target_vertical_slice.py -k live -s
```

该显式测试只创建合成双链输入和新测试 workspace，测试程序模拟该 fixture 的人工确认；
不批准真实研究项目。本次已验证当前 DeepSeek 账号、模型配置与合成 fixture 的调用闭环；
这不代表所有输入或所有 provider 都已完成真实模型测试。不扩展 provider 范围。

本轮不进入 Phase 2，不提前退休 Phase 0 迁移矩阵中的旧科学或产品入口。
