# EasyDesign 研究 Agent 协议

## Current v3 primary architecture

v3 的用户智能运行于 EasyDesign 自身的 first-class Agent Harness：Design Scientist 委派
科学 specialist，Evidence Judge 独立审阅，真实人类通过统一 Scientific Gates 提供 steering。
外部 Codex 不再是 v3 的概念主 runtime；Codex 开发工作必须遵循
`docs/V3_SCIENTIFIC_DECISION_CONTRACT.md` 与当前 Phase closure/Agent 文档。
本协议的通用科学与数据底线仍适用；下述 Codex + `easydesign-research` 操作方式仅为
**V2 compatibility / legacy Codex-driven path**，不得据此重新定义 v3 架构。

## V2 compatibility / legacy Codex-driven path

本文件只定义 EasyDesign 研究 Agent 的行为。EasyDesign 在当前 clone 所在的本地 Linux GPU
主机执行确定性工具并保存科学证据；仓库根由 `easydesign-workspace.yaml` 定位，禁止硬编码
主机名、数据盘或 clone 绝对路径。不得调用旧 UI、远程 executor、受管队列或其他 clone 的
环境与模型。

## 研究入口

处理蛋白设计研究任务时，先执行 `easydesign project status PROJECT --json`，根据当前
phase 使用 `$easydesign-research`，并且只加载该 phase 所需的一份 reference。没有项目
状态和研究者明确目标时，不创建 run、job 或 attempt。

EasyDesign 负责可重复工具、严格输入输出、manifest/checksum、worker 和审计；Skill 负责
经验、决策框架及何时调用工具；Codex 负责理解研究上下文、提出方案、诊断结果并调用工具；
研究者负责 site approval、strategy freeze、pilot/scale/select 启动和经验发布。

公开流程固定为 `prepare → strategize → pilot loop → scale → select`。数字 Stage 只属于
内部科学实现，不作为研究者的操作接口。

## 科学与数据底线

1. 用户输入、run、manifest、attempt、唯一证据、环境和模型禁止覆盖或擅自删除；涉及这些
   内容时完整读取 `DATA_SAFETY.md`。
2. `examples/apoe-ui-demo/` 内容和 checksum 必须不变。
3. 环境、模型、cache 和运行状态只能属于当前 clone 的 `runtime/`；产品只写自己的
   `runtime/` 和 `workspace/`。
4. 不扫描目录猜 artifact，不绕过 manifest/checksum，不静默 fallback 或伪造成功。
5. scientific stop、awaiting approval、operational failure、科学负结果和空结果必须区分。
6. 读取、校验、染色和扫描可直接执行；site approve、strategy freeze、pilot、scale、select
   必须取得研究者显式确认。
7. `Ctrl-C` 只脱离观察；`drain` 只在安全检查点停止新调度，不粗暴终止科学进程。

## 决策与经验

每项建议都要能回指输入、配置、manifest、checksum 和证据 run。不得把未经验证的经验写成
确定结论。正式经验必须包含适用范围、证据 run、反例、置信度、审核人和日期；只有研究者
批准后才能发布到 `$easydesign-research`。
