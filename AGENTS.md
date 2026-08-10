# EasyDesign Local Agent 协议

本分支是 Codex 主导、研究者批准、EasyDesign 执行确定性工具并保存科学证据的本地产品。
只在 `easydesign-local` 开发，不整体合并到 UI `main`。产品只在当前 clone 所在的本地
Linux GPU 主机执行；仓库根由 `easydesign-workspace.yaml` 定位，禁止硬编码主机名、数据盘
或 clone 绝对路径。不得调用旧 UI、远程 executor、受管队列或共享 runtime 的可写能力。

## 先判断任务入口

- **蛋白设计任务**：不要运行开发 context。先执行
  `easydesign project status PROJECT --json`，再使用 `$easydesign-research`；仅加载当前
  phase 所需的一份 reference。
- **仓库开发任务**：运行
  `.venv/bin/python scripts/dev.py context --mode MODE --path PATH`，按输出读取开发指南。
- **只读说明或审计**：先 inspect；没有明确修改请求时不要写文件或启动科学任务。

EasyDesign 负责可重复工具、严格输入输出、manifest/checksum、worker 和审计；Skill 负责
经验、决策框架及何时调用工具；Codex 负责理解上下文、提出方案、诊断结果并调用工具；
研究者负责 site approval、strategy freeze、pilot/scale/select 启动和经验发布。

公开流程固定为 `prepare → strategize → pilot loop → scale → select`。数字 Stage 只属于
内部科学实现，不作为对研究者的操作接口。

## 科学与数据底线

1. 用户输入、run、manifest、attempt、唯一证据、环境和模型禁止覆盖或擅自删除；相关任务
   完整读取 `DATA_SAFETY.md`。
2. `examples/apoe-ui-demo/` 内容和 checksum 必须不变。
3. 共享 runtime 只读；本产品只写自己的 `runtime/` 和 `workspace/`。
4. 不扫描目录猜 artifact，不绕过 manifest/checksum，不静默 fallback 或伪造成功。
5. scientific stop、awaiting approval、operational failure、科学负结果和空结果必须区分。
6. 读取、校验、染色和扫描可直接执行；site approve、strategy freeze、pilot、scale、select
   必须取得研究者显式确认。未确认不得创建 run、job 或 attempt。
7. `Ctrl-C` 只脱离观察；`drain` 只在安全检查点停止新调度，不粗暴终止科学进程。

## 开发模式与按需指南

- `inspect`：只读分析。
- `dev-local`：默认局部实现；不升版本、不构建 wheel、不调用其他执行主机。
- `integration`：科学契约、backend、orchestration、CLI/worker、Skill 或 Viewer 变更。
- `release`：仅用户明确要求时；不得静默升级。
- `ops`：仅当前 clone 的 runtime install/link、诊断和恢复。

同一逻辑开发任务只读取一次 context，保存 `policy_bundle_id`；上下文压缩后传
`--known-bundle-id`，未变化不重读。路径路由：

| 路径 | 指南 |
| --- | --- |
| `core/`、`stages/`、`backends/`、`filtering/`、`orchestration/stage*` | `docs/agent/SCIENTIFIC_PIPELINE.md` |
| `cli.py`、`local_worker.py`、`orchestration/local_*`、`reporting/`、Viewer、Skill | `docs/agent/LOCAL_CLI_AND_VIEWER.md` |
| workspace、runtime、registry、环境、资产、run | `docs/agent/RUNTIME_AND_DATA.md` |

产品边界变化才读 `docs/CHARTER.md` 和 `docs/ARCHITECTURE.md`；Stage 契约变化只补读对应
`docs/workflow/<stage>.md` 与 status。相邻问题不阻塞当前验收时只报告，不扩大范围。

## 验证、提交与经验发布

运行 `.venv/bin/python scripts/dev.py verify --mode MODE`；验证器可拒绝过低模式。提交前
检查 scoped diff、`git diff --check`、APOE tree hash 和结构禁区。共享科学路径单独使用
`core:` commit，并运行 `.venv/bin/python scripts/dev.py core-sync-report --against main`。

普通开发不升版本、不构建 wheel。只推送 `easydesign-local`。正式经验先写入项目候选，
必须包含适用范围、证据 run、反例、置信度、审核人和日期；研究者批准后才可修改正式
Skill。保留用户和其他 Agent 的非重叠修改，发现重叠修改时停止。
