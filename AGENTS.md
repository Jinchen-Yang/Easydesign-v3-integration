# Coding Agent 工作协议（VS Code Local）

本分支是永久本地研究者产品，只在 `codex/vscode-local` 开发。不要整体 merge 回 UI
`main`，不要操作 18769、Suzhou2、Manager 或原仓库 runtime/workspace。

## 1. 安全底线

1. 用户输入、科学 run/manifest/attempt、唯一证据、环境和模型禁止覆盖或擅自删除；涉及
   这些路径先完整读取 `DATA_SAFETY.md`。
2. `examples/apoe-ui-demo/` 是 Git 跟踪的科学证据，内容和 checksum 必须保持不变。
3. 共享 runtime 仅允许通过 `easydesign runtime link` 读取登记的 `envs/`、`models/`、
   registry 和 inventory；禁止向来源写 cache、bytecode、setup、下载或 job 状态。
4. 本产品只写自己的 `runtime/` 与 `workspace/`。旧 UI 的 projects/runs 即使显式传入也
   拒绝，不扫描目录猜测 artifact，不绕过 manifest/checksum。
5. 保留用户和其他 Agent 的修改。先检查工作树；重叠修改停止，非重叠修改精确提交。
6. 可再生 cache、bytecode 和无引用 build 经精确检查后可直接删除；科学数据不以归档
   代替判断。

## 2. 任务模式

- `inspect`：只读分析。
- `dev-local`：默认；局部实现和聚焦验证，不升版本、不构建正式 UI、不访问远端。
- `integration`：科学契约、backend、orchestration、CLI/worker 或 Viewer 变更；完整回归。
- `release`：仅指本地产品 wheel staging，必须由用户明确要求；没有 UI activation。
- `ops`：仅限本地 runtime link、诊断和恢复；不得顺带改科学代码。

任务不得静默升级到 `release`/`ops`。相邻问题不阻塞当前验收时只报告，不扩大范围。

## 3. 每个逻辑任务读取一次

```bash
.venv/bin/python scripts/dev.py context --mode MODE --path PATH
```

首次读取输出中的 `required_reading` 并保存 `policy_bundle_id`。同一任务后续轮次或上下文
压缩后传 `--known-bundle-id ID`；ID 未变不重读。范围扩大只读新增指南，新 Agent 独立执行。

| 路径 | 指南 |
| --- | --- |
| `core/`、`stages/`、`backends/`、`filtering/`、`orchestration/stage*` | `docs/agent/SCIENTIFIC_PIPELINE.md` |
| `cli.py`、`local_worker.py`、`orchestration/local_*`、`reporting/`、Target Viewer | `docs/agent/LOCAL_CLI_AND_VIEWER.md` |
| workspace、runtime link、registry、环境、资产、run、迁移 | `docs/agent/RUNTIME_AND_DATA.md` |

Stage 任务只补读对应 `docs/workflow/<stage>.md` 和 status。产品范围变化才读
`docs/CHARTER.md`，稳定接口变化才读 `docs/ARCHITECTURE.md`。

## 4. 科学与产品边界

科学逻辑只在 `src/easydesign/`。CLI、worker、Viewer 和 scripts 只调用统一 API。禁止静默
fallback、伪造成功、把 smoke 当科学验证，或混淆 scientific stop、awaiting approval、
operational failure 与空结果。

Stage 只能顺序继续同一 run；已完成 Stage 是只读 no-op，配置漂移必须新建实验。Stage 2
无论自动还是手动都要显式 approve。长任务未给 `--confirm` 时不得创建 worker/attempt。
`Ctrl-C` 只脱离观察；`drain` 只在安全检查点停止调度，禁止粗暴终止科学进程。

共享科学路径的修复使用独立 `core:` commit。同步前运行：

```bash
.venv/bin/python scripts/dev.py core-sync-report --against main
```

UI 恢复开发时只能逐个 cherry-pick 已验证的 `core:` commit；本地产品裁剪提交不得回合并。

## 5. 验证与提交

```bash
.venv/bin/python scripts/dev.py verify --mode MODE
```

验证器根据路径拒绝过低模式。提交前检查 scoped diff、`git diff --check`、APOE tree hash 和
结构禁区；使用 Conventional Commit。推送只针对 `codex/vscode-local`，不得推送 main。

只有产品/科学选择、不可逆操作、权限扩大或重叠修改需要询问；依赖和测试问题先在上述
边界内诊断解决。
