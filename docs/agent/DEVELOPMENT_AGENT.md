# EasyDesign 开发 Agent 必读

本文件是 EasyDesign 仓库工程任务的总入口。根 `AGENTS.md` 只定义研究 Agent；代码、测试、
文档、开发策略、仓库 Skill、Viewer、runtime 配置和发布相关工作由
`$easydesign-development` 加载本文件。

## 产品与分支边界

只在 `easydesign-local` 开发，不整体合并到 UI `main`。产品只在当前 clone 所在的本地
Linux GPU 主机运行；仓库根由 `easydesign-workspace.yaml` 定位，禁止硬编码主机名、数据盘
或 clone 绝对路径。不得调用旧 UI、远程 executor、受管队列或其他 clone 的环境/模型。

保留用户和其他 Agent 的非重叠修改；发现重叠修改时停止。没有明确修改请求时只读检查，
不得写文件或启动科学任务。

## 最小开发上下文

先为本次逻辑任务涉及的路径运行：

```bash
.venv/bin/python scripts/dev.py context --mode MODE --path PATH
```

完整读取输出中的 `required_reading`。同一逻辑任务保存 `policy_bundle_id`；上下文压缩后传
`--known-bundle-id`，策略与范围未变化时不重复加载。

- `inspect`：只读分析。
- `dev-local`：默认局部实现；不升版本、不构建 wheel、不调用其他执行主机。
- `integration`：科学契约、backend、orchestration、CLI/worker、Skill、Agent 策略或 Viewer
  变更。
- `release`：仅用户明确要求时使用，不得静默升级。
- `ops`：仅当前 clone 的 runtime install、诊断和恢复。

按路径补读专题指南：

| 路径 | 指南 |
| --- | --- |
| `core/`、`stages/`、`backends/`、`filtering/`、`orchestration/stage*` | `docs/agent/SCIENTIFIC_PIPELINE.md` |
| `cli.py`、`local_worker.py`、`orchestration/local_*`、`reporting/`、Viewer、Skill、Agent 策略 | `docs/agent/LOCAL_CLI_AND_VIEWER.md` |
| workspace、runtime、registry、环境、资产、run | `docs/agent/RUNTIME_AND_DATA.md` |

产品边界变化才读 `docs/CHARTER.md` 和 `docs/ARCHITECTURE.md`；Stage 契约变化只补读对应
`docs/workflow/<stage>.md` 与 status。相邻问题不阻塞当前验收时只报告，不扩大范围。

## 工程与数据底线

1. 用户输入、run、manifest、attempt、唯一证据、环境和模型禁止覆盖或擅自删除；相关任务
   完整读取 `DATA_SAFETY.md`。
2. `examples/apoe-ui-demo/` 内容和 checksum 必须不变。
3. 环境、模型、cache 和运行状态只能属于当前 clone 的 `runtime/`；产品只写自己的
   `runtime/` 和 `workspace/`。
4. 不扫描目录猜 artifact，不绕过 manifest/checksum，不静默 fallback 或伪造成功。
5. 测试使用合成 registry/asset fixture，不修改真实 env/model 或科学证据。

## 验证与提交

运行 `.venv/bin/python scripts/dev.py verify --mode MODE`；验证器可以拒绝过低模式。提交前
检查 scoped diff、`git diff --check`、APOE tree hash 和结构禁区。共享科学路径单独使用
`core:` commit，并运行
`.venv/bin/python scripts/dev.py core-sync-report --against main`。

普通开发不升版本、不构建 wheel。只推送 `easydesign-local`。Skill 的正式经验变更必须
包含适用范围、证据 run、反例、置信度、审核人和日期，并取得研究者批准。
