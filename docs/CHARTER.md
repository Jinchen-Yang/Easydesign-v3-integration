# EasyDesign Local 产品宪章

本文只保存稳定、强制的产品边界；设计动机、循环工作流和知识成熟机制见
[`PRODUCT_PHILOSOPHY.md`](PRODUCT_PHILOSOPHY.md)。

## 使命

把团队的蛋白设计经验与 Codex 的通用推理能力结合：Codex 不从零猜流程，EasyDesign 也不
把经验冻结成僵硬向导。产品用确定性工具、严格输入输出和不可变证据规范研究过程，同时
保留研究者对关键科学判断的最终批准权。

## 四方职责

- EasyDesign：执行、校验、backend、worker、manifest、checksum 和审计；
- Skill：何时调用工具、怎样比较方案、已审核经验及其适用边界；
- Codex：理解合作者信息、讨论假设、起草策略、诊断 pilot、调用工具并报告不确定性；
- 研究者：批准 site、freeze strategy、启动/提升 pilot、scale/select 和正式经验发布。

公开流程固定为 `prepare → strategize → pilot loop → scale → select`。内部七阶段契约继续
存在，但不成为研究者操作界面。

## 产品范围

Local 0.1 保留完整 VHH 科学主线、本地 backend、filter、manifest 和只读 evidence viewer；
只在当前 Linux GPU 主机执行。它不包含新手 Workbench、远程算力池、Manager、正式 UI
activation 或供应商下单。

一条成功软件运行不等于科学候选成功。无候选通过 filter 是有效负结果；backend failure
不是负结果；空结果必须可审计。

## 不可妥协的规则

1. 只读取 manifest 声明且 checksum 正确的上游 artifact。
2. run、attempt、foundation、strategy revision、promotion 和 job receipt 不覆盖历史。
3. 禁止静默 fallback、扫描目录猜事实、伪造成功、吞异常或混淆科学负结果与运行失败。
4. 保存配置、代码 SHA、版本、backend/model/environment identity 和可获得的随机性状态。
5. 读取/校验/染色/扫描可直接执行；site、strategy、pilot、scale、select 具有明确人工 gate。
6. Viewer 只读；Ctrl-C 不终止 worker；drain 只在安全检查点生效。
7. 正式经验必须包含适用范围、证据 run、反例、置信度、审核人和日期，研究者批准后发布。
8. 用户输入、科学 runs、manifest、环境、模型和唯一证据受 `DATA_SAFETY.md` 保护。

本 worktree 独立拥有 `.venv`、`runtime/` 和 `workspace/`。全新机器可从锁定配方和资产清单
逐组件安装自己的 scientific runtime；同机复用已有共享 runtime 时来源严格只读。旧 UI
projects/runs 不读取、不索引、不继续；APOE Git evidence 只读用于回归。

本产品永久位于 `easydesign-local`，不整体 merge 回 UI `main`。共享科学修复单独形成
`core:` commit；本地 façade、Skill、runtime install/link、worker 和 Viewer 提交永不回 main。

版本和 wheel 只在明确 release 指令下处理。任何开发任务不得触碰 18769、Suzhou2、
Manager 或主仓库。
