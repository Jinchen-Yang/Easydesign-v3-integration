# Stage 04 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态状态和验证证据。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `planned` | 尚未实现；clean 仓还没有真实 BoltzGen pilot。 | Stage 03 稳定后定义 pilot request/result 与执行器边界。 | 依赖已校验的 Stage 03 策略 bundle。 | 2026-07-24 |

## 当前结论

- 阶段状态：`planned`。
- 尚未开始实现；旧仓运行结果不能作为 clean 仓验收证据。

## 功能矩阵

| 能力 | 状态 | 当前证据 |
| --- | --- | --- |
| BoltzGen backend | `planned` | 无 |
| local executor | `planned` | 无 |
| Slurm/SMART executor | `planned` | 无 |
| 任务终态和候选索引 | `planned` | 无 |

## Now

- 无本阶段实现；项目当前重心是 Stage 02，旧仓结果不作为本阶段证据。

## Next

- 在 Stage 03 策略契约稳定后定义 pilot request/result。
- 建立执行器与 BoltzGen backend 分离的契约测试。

## Blocked

- 依赖 Stage 03 的已校验策略 bundle。

## 验证证据

- 尚无工程或科学验证。

## 工作日志

- 尚无。

## 历史索引

已结束日志按月移动到 `history/YYYY-MM.md`；当前尚无归档。
