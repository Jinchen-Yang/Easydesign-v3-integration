# 仓库布局

[English](REPOSITORY_LAYOUT.md)

仓库把规范、实现、配置、证据和运行状态分离：

- `workflow/`：面向人的规范性阶段契约。
- `src/easydesign/stages/`：镜像工作流 ID 的 Python 实现边界。
- `src/easydesign/backends/`：可替换科学工具和执行器 adapter。
- `configs/`：可移植默认值和版本化 profile，不保存密钥。
- `tests/`：unit、integration、end-to-end 和小型 fixture。
- `docs/`：架构、ADR、方法、验证、历史、论文、产品和旧仓审计。
- `resources/`：小型已审查资产和来源记录。
- `examples/`：最小且允许再分发的示例。
- `runs/` 和 `models/`：被忽略的本地状态。

未来 CLI 和 UI 必须调用 orchestration API，不得形成第二套 pipeline 实现。
