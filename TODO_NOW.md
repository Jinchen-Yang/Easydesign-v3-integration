# EasyDesign 当前工作

## Now

- **Stage 01 APOE MSA-backed Protenix-v2 验证。**
- 已完成部分：用户 YAML、自动输入识别、统一 Run Workspace、sequence/FASTA、
  no-MSA smoke 和完整 Target Bundle；详细记录已经归档，不再占用当前工作项。
- 当前门槛：取得与 143-aa APOE 输入严格匹配且来源可追溯的 MSA，运行
  `MSA enabled + template disabled` 预测并由同一 adapter 发布 Target Bundle。
- 详细任务、功能矩阵和验证证据：
  [`workflow/01-target-preparation/STATUS.md`](workflow/01-target-preparation/STATUS.md)。

## Next

- 完成 Stage 01 其余五类入口。
- 启动 Stage 02 hotspot discovery 的机器契约和 APOE 基线。

## Blocked

- Stage 01：两个公共 MSA 服务 attempt 超时；旧仓在本服务器没有保存 APOE MSA，
  历史记录指向的 SMART target feature cache 尚未取回。
- 公开许可证和公开 release 等待 IP/release 决策。
- 第三方 VHH scaffold 迁移等待来源与权利审查。

## 历史索引

- [2026-07 项目历史](docs/history/2026-07/TODO_NOW.md)

阶段内部历史从对应 `workflow/<stage>/STATUS.md` 进入。历史不得改写；原记录有误时追加更正。
