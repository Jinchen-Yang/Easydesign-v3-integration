# Agent 指南：科学流水线

仅在修改 `core/`、`stages/`、科学 backend/filter、Stage orchestration 或
`docs/workflow/` 时读取。

## 边界

- `core/` 只定义跨 Stage 契约；不得依赖具体 Stage 或重型 backend。
- `stages/` 实现领域转换，`backends/` 只做外部工具适配，`orchestration/` 只组织流程；
  CLI/UI/scripts 不得复制科学逻辑。
- 下游只读取上游 manifest 声明且 SHA-256 正确的 ArtifactRef；禁止目录扫描和绝对路径。
- run、StageManifest、终态 attempt 和已发布 artifact 只追加不覆盖；恢复创建新 attempt。
- backend、模型、结构来源、executor、filter profile 和 cache mode 都不得静默 fallback。
- 工程成功、科学负结果、人工等待和 operational failure 必须分别表达。

## Stage 规则

- 只读取本次涉及 Stage 的 `docs/workflow/<stage>.md` 与 `<stage>-status.md`。
- Stage 02 自动结果不等于人工批准；Stage 03 只消费正式 `hotspots.yaml`。
- review-gated/unattended 共享科学实现；LLM/PML 不是 1.0 科学事实来源。
- 多模型结构保持 ensemble 身份；不支持时显式拒绝，不得静默选 model 1。
- Stage 04→05、06→07 使用同一计划、任务、候选、进度和 manifest 契约。
- scientific stop 是成功执行得到的负结果，不能当作后端失败或候选成功。

## 验证与文档

- 变更公共科学契约、core manifest 或 managed protocol 自动使用 `integration`。
- 增加与风险相称的 unit/contract/integration 测试；重型真实运行只在用户授权的 fixture、
  环境和预算内执行。
- 只有 Stage 行为、契约、状态或验证等级变化才更新 Stage README/STATUS；完成跟踪事项前
  先追加当月 history，再同步顶层 rollup。
- 详细稳定架构只在依赖方向或接口变化时读取 `docs/ARCHITECTURE.md`。
