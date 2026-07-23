# Stage 06 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态状态和验证证据。

## 当前结论

- 阶段状态：`planned`。
- 通用结构预测接口会先在 Stage 01 的 target 预测中验证，再由本阶段复用。
- 1.0 默认预测实现计划使用 Protenix-v2；AFO/AF3 只保留可替换接口。

## 功能矩阵

| 能力 | 状态 | 当前证据 |
| --- | --- | --- |
| 放大预算与生成 | `planned` | 无 |
| 候选规范化和去重 | `planned` | 无 |
| 通用结构预测接口 | `implemented` | Stage 01 adapter 契约与单元测试已实现 |
| Protenix-v2 复合物预测 | `planned` | 无 |
| 覆盖率和失败偏差报告 | `planned` | 无 |

## Now

- 无本阶段实现；跟踪 Stage 01 通用预测接口，避免未来重复实现。

## Next

- Stage 05 shortlist 稳定后定义 scale request/result 和 smoke 预算。

## Blocked

- 依赖 Stage 05 的入选策略和证据。

## 验证证据

- 尚无本阶段工程或科学验证。

## 工作日志

### 2026-07-24

- 决定 Protenix-v2 作为 EasyDesign 1.0 默认预测实现；AFO/AF3 通过同一通用接口扩展。
- Stage 01 已实现与重型环境隔离的通用 prediction request/invocation/product 契约和
  Protenix-v2 adapter；本阶段只复用接口，复合物预测仍未验证。

## 历史索引

已结束日志按月移动到 `history/YYYY-MM.md`；当前尚无归档。
