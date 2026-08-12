---
name: easydesign-development
description: 用于 EasyDesign 仓库开发（repository engineering），包括 code、test、documentation、developer policy、仓库 Skill、runtime configuration、local worker 和 Viewer；不用于蛋白结合物研究执行（protein-binder research execution）。
---

# EasyDesign 仓库开发

仅用于仓库工程任务。不得创建科学 run、job 或 attempt。

1. 识别本次任务涉及的全部仓库路径。
2. 选择满足任务所需的最低 mode：
   - `inspect`：只读分析；
   - `dev-local`：隔离的局部实现；
   - `integration`：science contract、orchestration、CLI/worker、Agent/Skill policy、
     runtime boundary 或 Viewer integration；
   - `release`：仅在用户明确要求发布时使用；
   - `ops`：仅用于当前 clone 的 runtime install、诊断或恢复。
3. 运行 `.venv/bin/python scripts/dev.py context --mode MODE --path PATH`；每个任务路径重复
   传入 `--path`。
4. 完整读取 `required_reading` 中的所有文件。保存同一逻辑任务的 `policy_bundle_id`；
   上下文压缩后通过 `--known-bundle-id` 传回。
5. 在保留用户数据和非相关修改的前提下，实施最小范围改动。
6. 运行 `.venv/bin/python scripts/dev.py verify --mode MODE`。如果验证器报告 mode 过低，
   使用要求的 mode 重新运行。
7. 检查 scoped diff，并报告验证结果与未解决风险。

开发 context 负责工程策略。根 `AGENTS.md` 是面向研究 Agent 的协议，不得从中推断仓库
工程流程。
