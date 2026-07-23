# EasyDesign 当前工作

## Now

### M1-01：实现基础运行契约

- 状态：`in_progress`
- 完成门槛：
  - `ArtifactRef`、`Attempt`、`StageManifest`、`RunManifest` 已实现；
  - JSON round-trip、SHA-256、相对路径和不可变终态规则已实现；
  - 契约测试、`make check`、`make test`、`make build` 全部通过；
  - `docs/ARCHITECTURE.md`、`TODO.md` 和本文件与实现一致。

## Next

- M2-01：设计 Stage 01 的 `TargetRequest` 与 `TargetBundle` 机器契约。
- M2-02：先实现本地 PDB/mmCIF 与标准 Target Bundle 两条无网络入口。
- M2-03：再实现 PDB ID、sequence/FASTA、UniProt 和 PSE adapter。

## Blocked

- 公开许可证和远程托管等待 IP/release 决策。
- 第三方 VHH scaffold 迁移等待来源与权利审查。

## 只追加工作日志

### 2026-07-24

- 决定全部环境先使用 Conda；EasyDesign 主环境固定 Python 3.11，重型工具保持独立。
- 创建 `/root/autodl-tmp/conda_envs/easydesign-core`，完成 editable 安装及
  check/test/build 验证。
- 扩充 `docs/ARCHITECTURE.md`，明确源码子孙层级、依赖方向、环境和运行目录。
- 扩充 `AGENTS.md`，使 Agent 自动维护测试、架构、workflow、TODO 和本地 commit。
- 开始 M1-01 基础运行契约。

### 2026-07-23

- 建立版本 `0.1.0.dev0` 的 clean-room 仓库架构。
- 定义七阶段职责、运行边界、项目治理和旧仓审计基线。

每月开始时将上月日志归档到 `docs/history/YYYY-MM/`。不得改写历史；原记录有误时追加更正。
