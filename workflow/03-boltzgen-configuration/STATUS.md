# Stage 03 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态状态和验证证据。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `implemented` | S03-001 已实现通用 region×official VHH7 基础策略编译、固定资产校验和 BoltzGen 0.3.2 官方检查。 | 完成 APOE 21/21 真实 YAML 验收与 wheel smoke，满足后切换 Stage 04。 | 无代码契约阻塞；APOE 官方校验正在运行。 | 2026-07-26 |

## 当前结论

- 阶段状态：`implemented`，尚未在本文件中宣称真实 smoke 完成。
- 基础模板固定为 `H_all + C_full`；所有 hotspot 为 positive binding，其他 residue
  中性。
- 区域数量来自 `hotspots.yaml`；APOE 的 3×7 只是验收案例，不是代码常数。
- `official-vhh7-v1` 已从固定 BoltzGen commit 审计并作为 wheel package data 引入，
  不使用旧仓来源不明资产。

## 功能矩阵

| 能力 | 状态 | 当前证据 |
| --- | --- | --- |
| manifest-only Target/hotspot 输入 | `implemented` | 只接受当前成功 Stage 01/02 正式输出并验证 SHA-256 |
| 终态 Stage 02 continuation | `implemented` | 新 downstream run 复制并复验 Stage 01/02，不改写源 run |
| VHH scaffold registry | `implemented` | 7 个官方 scaffold、14 个文件、MIT license 和固定 commit/hash |
| 基础 BoltzGen YAML 编译 | `implemented` | 通用 region×scaffold 笛卡尔积；positive binding only |
| BoltzGen 0.3.2 官方校验 | `implemented` | 精确 version/commit/clean-tree probe 和逐 YAML `boltzgen check` |
| StrategyBundle/矩阵/manifest | `implemented` | 类型化 JSON、TSV、逐策略 manifest 和全部 ArtifactRef |
| APOE 21/21 真实 smoke | `implemented` | 正在完成最终 runtime evidence；未结束前不升为 smoke-validated |

## Now

- `[S03-001]` 完成 APOE 三个已批准 PSE 区域 × 七个官方 scaffold 的 21/21
  BoltzGen 0.3.2 校验、正式 continuation run 和 wheel console-script smoke。
- `[DATA-002]` 核对 wheel 中 14 个 scaffold 与 license 的固定 SHA-256。

## Next

- `[S04-001]` 在 StrategyBundle 上实现可恢复的 21×40 pilot generation。
- `[ENG-008]` 建立 TaskRecord、append-only event、progress snapshot、多 GPU 调度与
  resume。
- Stage 03 提高款：crop、H_core/H_cluster、CDR 优化、区域几何选模、自适应预算和
  多策略轮次。
- 1.0 后再评估 `guides/` 高级草案和可选 Agent 建议层；1.0 不依赖 Agent。

## Blocked

- 无 Stage 03 实现阻塞。
- Stage 04 真实 GPU 运行必须等待服务器现有非 EasyDesign GPU 任务释放；不得终止它们。

## 验证证据

- Python 3.11 全仓：`188 passed, 8 skipped`。
- `make check`：ruff、mypy、结构、状态汇总和 Viewer 资产检查通过。
- 通用 fixture：1/2/3 区域、非 A/B/C ID、不同预算、完整矩阵、禁止
  `not_binding`、target checksum 和不可覆盖均通过。
- APOE runtime 校验：进行中；完成后在本节追加正式 run、strategy count 与 hash。

## 工作日志

- 2026-07-26：冻结 BoltzGen `0.3.2` 与 commit
  `a3149cf18eeb58648d1abbb27539bd73f746cdda`；完成基础编译器、adapter、typed config、
  continuation API 和官方 scaffold registry。
- 2026-07-26：发现逐 YAML 官方 check 有明显初始化成本；仍逐个保留官方检查结果，
  不以只解析 YAML 替代 backend 校验。

## 历史索引

已结束日志按月移动到 `history/YYYY-MM.md`；S03-001 完成门槛满足后追加
[`history/2026-07.md`](history/2026-07.md)。
