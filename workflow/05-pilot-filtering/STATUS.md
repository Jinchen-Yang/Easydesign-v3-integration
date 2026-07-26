# Stage 05 状态

稳定职责和算法见 [`README.md`](README.md)。本文件只记录动态状态、当前工作和证据。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `smoke-validated` | APOE 840 个 pilot 已完成 v1.5 审计；唯一 Tier A 扩展到 100 后，10/10 full-target Protenix 因 binder pose 不稳定而合法停止。 | 冻结 `stopped-no-scale-winner` 负结果，不启动本轮 APOE Stage 06/07。 | 无 operational failure；APOE 本轮没有通过科学规模化门。 | 2026-07-26 |

## 当前结论

- 阶段状态：`smoke-validated`；通用实现和 APOE 真实 scientific-stop 路径均通过。
- 必需 pilot 硬门、逐候选证据、序列去重、strategy Tier、`S_screen` 和
  `F_YAML` 已实现。
- Tier A 扩展复用 Stage 04 的 BoltzGen task/executor/collector，不存在第二套生成逻辑。
- full-target Protenix 使用 target required MSA、binder query-only、无模板、seed 101。
- 没有 Tier A 或没有 scale winner 会发布 succeeded StageManifest 与明确
  `ScientificStop`，不会修改阈值迎合案例。
- APOE 正式结论为 `stopped-no-scale-winner`，不是软件失败：21 个策略中
  region A × gontivimab 为唯一 Tier A，扩展后 12/100 通过 local gate，但 Top 10
  的 full-target Protenix 结构均未保持原 binder pose。
- 本轮不得启动 APOE Stage 06/07，也不得把 binder pose RMSD 3 Å 门槛放宽来迎合案例。

## 功能矩阵

| 能力 | 状态 | 当前证据 |
| --- | --- | --- |
| FilterMetric / FilterDecision / Stage05Bundle 契约 | `implemented` | Pydantic 严格 schema、mypy strict |
| manifest-only 上游读取与 SHA-256 | `implemented` | Stage05 orchestration 与 scientific-stop 集成测试 |
| 结构、界面、hotspot、clash、BSA | `implemented` | `interface-geometry-v1` 单元测试；40-candidate 运行时性能审计 |
| 官方 design mask → CDR identity | `implemented` | 缺失 mask 明确失败；Stage 04 回归 |
| pilot 硬门与逐规则处置 | `implemented` | Tier A/B/C/D、去重和负结果测试 |
| `S_screen`、Tier 与 `F_YAML` | `implemented` | 冻结 profile 与确定性排序测试 |
| Tier A 扩展到配置总量 | `implemented` | 共用可恢复 BoltzGen executor；通用 fixture |
| full-target Protenix seed 101 | `implemented` | complex input、full confidence 和真实 cross-chain PAE parser 测试 |
| 唯一 scale winner / scientific stop | `implemented` | winner 与 no-tier 集成路径 |
| 原子 progress、append-only event、resume | `implemented` | 结构指标 cache、expansion/full-target TaskRecord、通用 watch |
| APOE 真实 Stage 05 | `smoke-validated` | 840 个 pilot、60 个新增扩展、10 个 full-target Protenix 全部完成；合法发布 `stopped-no-scale-winner` |

## Now

- 无。S05-001 APOE 真实运行和负结果归档已经完成。

## Next

- `[VAL-003]` 使用相同 APOE 候选、target MSA 和 seeds 101/202/303 受控比较
  no-template、target-template 与 target-template+hotspot constraint，并增加已知
  VHH–抗原正对照。当前证据只能说明现有 Protenix 验证模式未保持 binder pose，不能
  直接宣称 Protenix 软件有 bug。
- 在第二条独立真实 target 上复用相同 frozen profile，验证 winner 或另一种 scientific
  stop。
- 通过预注册 benchmark 审视 full-target binder-pose gate；任何阈值或参考对齐方法变化
  必须形成新 profile/ADR，不能回写本次 APOE 结果。

## Blocked

- 公共 ColabFold MSA 无 SLA；网络失败属于 operational failure，可恢复但不能无 MSA
  fallback。
- APOE 没有 scale winner 是已完成的科学负结果，不列为 `Blocked`。

## 验证证据

- 2026-07-26：`ruff check src tests` 通过。
- 2026-07-26：`mypy --strict src` 通过，92 个源文件无问题。
- 2026-07-26：Stage 04/05、filter、Protenix adapter 和 core task 定向测试
  `25 passed`。
- 通用 fixture 验证 scientific stop 会发布完整 Bundle、终态 progress 和 event artifact，
  且不启动 BoltzGen expansion 或 Protenix。
- 真实 Stage 04 strategy 的 40 个候选结构指标审计约 37 秒完成；这只是容量证据，不是
  APOE Stage 05 科学结论。
- APOE 正式 run：
  `/root/autodl-tmp/Protein_design/easydesign-clean/runs/apoe-s02-006-pse/`
  `20260726-004-stage05-pilot-filter`，RunManifest revision 3 为 succeeded，
  `integrity_status=verified`。
- pilot Tier 分布为 1 个 A、1 个 B、5 个 C、14 个 D；唯一 Tier A
  `region-a-h-all-c-full-scaffold-gontivimab` 在首批 40 个中有 6 个 hard-pass、
  5 个 final-gate pass。
- 该策略新增 60 个并达到 100；12 个通过 local gate，Top 10 使用 target required
  MSA（depth 584）、binder query-only、无模板、seed 101 完成 Protenix，10/10
  operational success。
- Top 10 的 target CA RMSD 为 1.266–2.000 Å，全部通过；binder pose RMSD 为
  18.005–31.726 Å，10/10 单独因 `require-binder-pose-rmsd <= 3 Å` 失败。
  Stage05Bundle SHA-256
  `401259623dd43cf5a17dfed20fd81b6868d61002bcc1eabfab1b68134b5d9073`，
  expansion validation SHA-256
  `c9909a6a75f1786bb6ca293ea4944bc8fc40b25e27985e90642a498eb94bfdb7`。
- 终态质量门：`make check` 通过（Ruff、strict mypy 104 个源码文件）；
  全仓 `230 passed, 8 skipped`；dev5 wheel、21/21 固定资产与 console script 验证通过。

## 工作日志

- `2026-07-26T04:33:17+08:00`：完成 S05-001 的类型、指标、筛选、恢复和文档初版；
  状态保持 `implemented`，等待正式 APOE 输入。
- `2026-07-26T09:13:48+08:00`：APOE 真实运行完成；严格执行 840-candidate pilot、
  唯一 Tier A 扩展和 10 个 full-target prediction，最终如实发布
  `stopped-no-scale-winner`，状态提升为 `smoke-validated`。

## 历史索引

- [2026-07 工程实现与 APOE scientific-stop 归档](history/2026-07.md)。
