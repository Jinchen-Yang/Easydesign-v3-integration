# EasyDesign 当前工作

## Now

- **Stage 01 sequence/FASTA → Protenix-v2 → Target Bundle 纵向切片。**
- 状态：`implemented`；no-MSA smoke 和完整 Target Bundle 已通过，两个远程 MSA
  服务 attempt 均因上游持续 `PENDING` 达到工程超时。
- 剩余宏观门槛：APOE 远程 MSA、无模板预测成功并由同一 adapter 发布 Target Bundle。
- 详细任务、功能矩阵和验证证据：
  [`workflow/01-target-preparation/STATUS.md`](workflow/01-target-preparation/STATUS.md)。

## Next

- 完成 Stage 01 其余五类入口。
- 启动 Stage 02 hotspot discovery 的机器契约和 APOE 基线。

## Blocked

- 公开许可证和公开 release 等待 IP/release 决策。
- 第三方 VHH scaffold 迁移等待来源与权利审查。

## 历史索引

- [2026-07 项目历史](docs/history/2026-07/TODO_NOW.md)

阶段内部历史从对应 `workflow/<stage>/STATUS.md` 进入。历史不得改写；原记录有误时追加更正。
