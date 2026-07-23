# EasyDesign 当前工作

## Now

### M2-01：设计 Stage 01 的 TargetRequest 与 TargetBundle 机器契约

- 状态：`planned`
- 完成门槛：
  - 六类入口共享一个带类型的 `TargetRequest`，且来源选择必须显式；
  - `TargetBundle` 覆盖结构、序列、残基编号映射、质量报告和来源清单；
  - 机器契约与 `workflow/01-target-preparation/README.md` 一致；
  - 正常、缺字段、冲突输入和未知字段的契约测试通过；
  - 本阶段只定义契约，不下载结构、不调用预测模型。

## Next

- M2-02：先实现本地 PDB/mmCIF 与标准 Target Bundle 两条无网络入口。
- M2-03：再实现 PDB ID、sequence/FASTA、UniProt 和 PSE adapter。

## Blocked

- 公开许可证和公开 release 等待 IP/release 决策。
- 第三方 VHH scaffold 迁移等待来源与权利审查。

## 只追加工作日志

### 2026-07-24

- 决定全部环境先使用 Conda；EasyDesign 主环境固定 Python 3.11，重型工具保持独立。
- 创建 `/root/autodl-tmp/conda_envs/easydesign-core`，完成 editable 安装及
  check/test/build 验证。
- 扩充 `docs/ARCHITECTURE.md`，明确源码子孙层级、依赖方向、环境和运行目录。
- 扩充 `AGENTS.md`，使 Agent 自动维护测试、架构、workflow、TODO 和本地 commit。
- 开始 M1-01 基础运行契约。
- 完成 M1-01：实现 `ArtifactRef`、`Attempt`、`StageManifest`、`RunManifest`、规范
  JSON、SHA-256、相对路径安全、原子拒绝覆盖和 revision 审计链。
- M1-01 工程证据：`make check`、43 个 pytest 契约测试和 wheel build 全部通过；
  提交为 `feat(core): implement foundational run contracts`。
- 创建私有 GitHub 仓库 `Knitua/Easydesign`，使用仅限本仓库的 Proteindigger1
  deploy key 推送 `main`；本地与远端 HEAD 验证一致。

### 2026-07-23

- 建立版本 `0.1.0.dev0` 的 clean-room 仓库架构。
- 定义七阶段职责、运行边界、项目治理和旧仓审计基线。

每月开始时将上月日志归档到 `docs/history/YYYY-MM/`。不得改写历史；原记录有误时追加更正。
