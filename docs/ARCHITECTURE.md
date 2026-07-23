# EasyDesign 架构

## 1. 仓库分层

- `workflow/`：七阶段面向人的规范与契约。
- `src/easydesign/stages/`：与七阶段一一对应的 Python 实现边界。
- `src/easydesign/backends/`：target source、hotspot、BoltzGen、预测器和 executor adapter。
- `src/easydesign/orchestration/`：规划、执行、恢复和跨阶段协调。
- `src/easydesign/filtering/`：Stage 05/07 共用的版本化筛选框架。
- `configs/`：可移植默认值、后端能力、filter 和环境 profile，不保存密钥。
- `tests/`：unit、integration、e2e 和小型 fixture。
- `resources/`：经过审查的小型资产和来源登记。
- `runs/`、`models/`：本地状态，禁止进入 Git。

未来 CLI 和 UI 只能调用 orchestration API，不得创建第二套 pipeline。

## 2. 身份与 manifest

一个 run 使用稳定 `project_id` 和 `run_id`；阶段使用稳定编号 `stage_id`；每次执行
创建 `attempt_id`。Artifact 通过逻辑角色和 checksum 定位，不能只依赖偶然路径。

`RunManifest` 管理全局配置快照、阶段状态和依赖；`StageManifest` 记录一次阶段接受的
输入、产生的输出、证据和 attempt；`ArtifactRef` 记录逻辑角色、格式、位置、checksum
和来源。具体字段在 M1 实现时通过 ADR 冻结。

## 3. 状态、不可变性与恢复

运行状态必须区分规划、执行、工程验证、科学结果、取消和失败。执行完成但没有候选
通过科学 filter 是有效结果。

已接受 manifest 和 attempt artifact 不可变。恢复运行验证依赖和配置兼容性后创建
新 attempt，保留旧 attempt 的失败、日志和产物。

## 4. Adapter 隔离

后端专属请求、路径和结果字段留在 adapter 内。Core 只暴露能力和规范化证据，使
RCSB/UniProt、BoltzGen、Phoenix/AFO/AF3 以及 local/Slurm/SMART 可以替换而不重写
阶段边界。SMART 是执行 profile，不是核心代码中的特殊分支。

## 5. 配置优先级

可移植默认值、项目配置、运行 profile 和显式调用参数按声明顺序解析，最终配置写入
snapshot。密钥只来自环境或秘密管理系统。禁止隐式读取用户目录中的未知配置。

## 6. 当前关键决策

2026-07-23 决定从零建立私有 clean repository，旧仓保持只读参考；采用七个稳定
编号阶段、不可变 manifest、可替换后端和 Python-API-first 路线。2026-07-24 决定
开发期只维护中文文档，每阶段只保留一份合并后的 README；英文和发布专属文档在
release 阶段重建。
