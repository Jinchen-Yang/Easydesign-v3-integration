# EasyDesign Local 路线图

## 当前产品

- 永久 worktree：`/root/autodl-tmp/Protein_design/easydesign-vscode`。
- 永久分支：`easydesign-local`；禁止整体 merge 到 UI main。
- 独立 distribution：`easydesign-local 0.1.0.dev1`，import/命令仍为 `easydesign`。
- 产品入口：`runtime link`、`doctor` 和逐阶段 `step` CLI。
- 可视化：只读 Target Viewer；不包含 Workbench、HTTP API 或远程提交。

## 已冻结的科学边界

- core manifest/artifact/attempt/decision/checksum 不降级。
- Stage 1–7 模型、算法、科学 backend、filter profile 和 VHH scaffold 保留。
- Stage 2 SASA 与 ScanNet 独立；A/B/C 只有批准后进入正式 hotspots。
- Stage 4–7 使用 canonical 预算，无 `--confirm` 不执行。
- 科学停止、运维失败与可审计空结果严格区分。
- Git 跟踪的 `examples/apoe-ui-demo/` 保持内容/checksum 不变。

## 本地产品验收

- 六类 Stage 1 输入、decision continuation。
- Stage 2 SASA/ScanNet 双方法、manual、approval 与只读 overlay。
- canonical config revisions、同 run continuation、配置漂移拒绝。
- persistent worker 的 foreground/detach/watch/drain/resume/lost/Ctrl-C 语义。
- runtime link 的 registry/lock/inventory/asset identity 与 source zero-write。
- Python、Ruff、mypy、结构检查、Target Viewer Chromium 和 local wheel 安装。
- APOE evidence manifest/report 只读回归。

## 后续工作

1. 用第二个独立 target 做非 APOE Stage 1/2 真实回归。
2. 在获得明确高成本授权时验证 Stage 4–7 persistent worker 的长时恢复。
3. 共享科学修复只形成独立 `core:` commit，供未来逐个 cherry-pick。

本路线图不跟踪 UI、18769、Manager 或 Suzhou2；这些只属于主产品仓库。
