# Agent-native CLI 与 Viewer 指南

- 研究接口只使用 `prepare / strategize / pilot / scale / select`；数字 Stage 不进入公开 JSON、
  guidance 或命令名。
- `project status --json` 是恢复项目状态的唯一入口；不得扫描目录或解析日志猜下一步。
- CLI 文本与 JSON 必须来自同一 `CommandResult` 和结构化 `NextAction`。
- 新项目不生成七份 Stage YAML。旧项目识别为 `legacy-stage-project`，只读且不原地迁移。
- target/site foundation、strategy revision、pilot、production 和 selection 都具有不可变身份。
- SASA/ScanNet 结果独立；自动结果不等于 approval。A/B/C 固定红、蓝、黄。
- 读取、校验、染色、扫描、计划、review、status 和 view 无需逐项确认。
- site approve、strategy freeze、pilot run/promote、scale run、select run 必须显式确认；未确认
  不得创建 revision、run、job、Stage 或 attempt。
- LocalStepJob receipt append-only，worker 使用独立 process session。Ctrl-C 只脱离观察；
  drain 只允许安全检查点。
- Viewer 只读取 manifest 验证后的 target/site、pilot/final evidence；不得编辑、上传、批准、
  提交远程任务或自动打开浏览器。
- CLI 禁止导入 UI、SSH、Manager、Managed Worker、Suzhou2 或正式 release 模块。

验证至少覆盖：CommandResult 一致性、六类 source、foundation identity、strategy revision、
显式 variant/crop/binding/CDR/native YAML、独立 pilot、人工 promotion、50k/Top200 确认门、
worker detach/watch/drain/resume/lost，以及只读 Viewer。
