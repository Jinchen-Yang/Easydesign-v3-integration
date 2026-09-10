# EasyDesign v3 Phase 1：DeepSeek live 补测报告

日期：2026-09-10。分支：`codex/v3-migration-phase1-20260910`。
初次实现提交：`4287b39444f36a83128e16abbf69390392646c5a`。

**DeepSeek 实际 API 调用和 Phase 1 真实模型闭环已通过。** 本轮补上先前因无凭据而跳过的
验证，并修复 live 调用暴露的一个 Agent 工具边界问题。未进入 Phase 2。

## 连通性与真实模型闭环

| 验证 | 结果 |
| --- | --- |
| 模型配置 | `deepseek` / `deepseek-flash`，官方 endpoint |
| 独立 API 连通性 | 成功返回预期 `OK`；0.588 秒；输入 13、输出 1，共 14 tokens |
| 完整 live smoke | `1 passed, 2 deselected`；56.16 秒 |
| 模型调用次数 | 共 20 次：Coordinator 9、Target Intelligence 5、Evidence Judge 6 |
| 科学流程 | 本地合成双链 → 原 chain-selection gate → 测试确认 → 原 run 第二个 attempt |
| Judge | 第一次 `ready-to-ask`，完成后 `assessed` |
| 科学任务数量 | 2 个旧 job receipt、1 个 run、1 份 DecisionRecord；目标产物来自 `attempt-0002` |
| 结果 | chain A；6 个残基映射；bundle / identity / mapping / provenance 通过原引用验证 |
| Viewer | 原 Viewer 引用验证通过 |
| 后续阶段 | Stage 02 未启动 |

本次测试使用真实模型 API、真实 CPU scientific worker 和真实 LangGraph SQLite saver。
两次 `run_session` 之间关闭并重开 saver，恢复同一 thread 的待批卡。人工确认由测试程序
针对合成 fixture 明确模拟，不代表真实研究者审阅或批准任何真实研究项目。
独立 CLI 进程退出/重开的覆盖仍来自既有脚本化模型集成测试；本次没有把它写成真实 API
跨进程测试。连通性、模型协议、科学执行与持久化的证据分别保留。

模型最终保留了 biological identity 未确认、reference completeness 未知，以及结构质量
不等于亲和力或功能证据等局限。科学产物的真实性由原 manifest/ref/hash 验证支持，
不以模型的文字陈述替代科学证据。

## Live smoke 暴露并修复的问题

第一次完整调用在 10.55 秒后失败：Target specialist 同时请求读取技能和目标证据。
项目尚未创建 run，原 Agent 证据工具直接传播“项目没有匹配 run”的异常，中断了对话。
当时只消耗 2 次模型调用，没有启动科学 job。

修复仅位于 `agent/tools.py`：当 Target 或 Coordinator 未指定 run、项目也确实尚无 run 时，
读取工具返回 `status: not-prepared`、空证据引用和下一步提示。它不创建 run，不返回虚构
bundle/evidence ID，也不吞掉指定了无效 run 的真正错误。Judge 的证据绑定要求保持。

新增两个参数化回归用例验证 Target/Coordinator 的准备前读取无科学副作用，且显式错误 run
仍失败。修复后的局部回归为 **5 passed，9.52 秒**；随后重新执行真实 API smoke 并通过。

## 修复后的回归与安装验证

`scripts/dev.py verify --mode integration` 通过：结构检查、既有 Viewer 资源校验、compileall、
Ruff 均通过，mypy 在 169 个源码文件中未发现问题。完整离线回归为
**649 passed，9 skipped，182.47 秒**。

默认回归未开启 live 标志，因此仍跳过 1 项 live 测试和 8 项独立 PyMOL 测试；该 live
测试已在上面的显式运行中单独通过，不应把默认跳过误读为本轮尚未验证。

修复后的 wheel 已重新构建，并在新的独立安装环境验证：两个 console 入口、包导入位置、
v2 不提前加载 Agent 依赖，以及两份专家技能和共 43 份资源字节一致，全部通过。
安装验证复用已锁定的依赖目录，不代表全新主机的完整离线分发验证。

本轮只有上述 Agent 工具修复、对应测试和报告更新。原 scientific kernel、Stage 02–07、
backends、filtering、真实 compute recovery 与 v2 入口未变更。没有更新原生产环境。

## 凭据与证据文件

key 存于用户自行配置的 `.env.local`，权限 `600`，Git 忽略。测试启动时显式加载；
程序仍不会自动读取该文件。诊断输出仅包含 provider、model、结果和用量等非秘密字段。
完整测试日志通过父进程按实际凭据值脱敏后保存；对保留 fixture 与成功日志共 82 个文件进行
实际凭据值扫描，未发现泄漏，结果记录在验证 receipt 中。
不将 `.env.local` 或真实 key 放入提交和交付包。

Suzhou2 工作树 `runtime/tmp/agent-bootstrap/` 中保留：

- `live-preflight-result.json`：实际 API 连通性结果。
- `agent-live-8f128b234e.log`：首次失败记录。
- `agent-live-28a65e7cd7.log`：修复后的完整成功记录。
- `live-validation-result.json`：实际 job/run/record、bundle/Viewer 与凭据扫描核验。
- `live-fix-regression-1.log`、`verify-live-fix.log`、`wheel-smoke-live.log`：修复后的检查。

20 次调用是成功闭环的模型请求次数；另有首次失败的 2 次和连通性检查的 1 次。
这里只记录可核验调用数，不把连通性测试的 14 tokens 当成全部测试 token 用量。

## 仍未覆盖的内容

- OpenAI 和 Anthropic 尚未配置各自账号凭据，保留已有 HTTP mock 契约测试；DeepSeek 成功
  不代表它们的真实 API 已验证。
- 8 项 PyMOL 集成测试要求独立 PyMOL 环境，与模型 key 无关；本轮没有安装该科学 backend。
- 这是一个合成双链样本的一次成功模型闭环，不是科学性能基准或所有输入的可靠性保证。

本轮止于 Phase 1 的补测、必要修复和结果交付，不自动开展后续迁移。
