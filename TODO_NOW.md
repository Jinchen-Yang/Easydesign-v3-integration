# EasyDesign 当前工作

## Now

- **当前没有可在既定 ScanNet 约束下继续的未提交实现。**
- Stage 02 automatic 代码与 SASA APOE smoke 已完成；真实双方法 smoke 已进入 Blocked。
- 详细任务、未实现模型、annotation和验证证据：
  [`workflow/02-hotspot-discovery/STATUS.md`](workflow/02-hotspot-discovery/STATUS.md)。
- Stage 01 APOE MSA-backed Protenix-v2 仍为独立 Blocked 工作，状态见
  [`workflow/01-target-preparation/STATUS.md`](workflow/01-target-preparation/STATUS.md)。

## Next

- 为 ScanNet runtime 解阻建立 ADR：选择兼容旧 CUDA 10 的硬件/容器，或评审后采用
  可验证的现代化模型路径；之后重跑官方 no-MSA 和 APOE。
- 双方法成功后再人工检查两套 Top 3 和重合关系，批准后定义 Stage 03 handoff。
- 完成 Stage 01 其余入口和 MSA-backed 验证。

## Blocked

- Stage 01：两个公共 MSA 服务 attempt 超时；旧仓在本服务器没有保存 APOE MSA，
  历史记录指向的 SMART target feature cache 尚未取回。
- Stage 02：TensorFlow 1.14 GPU probe 通过，但官方 1BRS 与 APOE真实推理均在 RTX 4080
  报 cuBLAS GEMM execution failure；commit/权重未改变，禁止 CPU fallback。证据 run 为
  `runs/apoe/20260724-003-stage02-auto`。
- 公开许可证和公开 release 等待 IP/release 决策。
- 第三方 VHH scaffold 迁移等待来源与权利审查。

## 历史索引

- [2026-07 项目历史](docs/history/2026-07/TODO_NOW.md)

阶段内部历史从对应 `workflow/<stage>/STATUS.md` 进入。历史不得改写；原记录有误时追加更正。
