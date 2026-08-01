# Stage 05 状态

稳定职责和算法见 [`README.md`](README.md)。本文件只记录动态状态、当前工作和证据。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `smoke-validated` | v1.5/v1.6 APOE 结论保持冻结；dev35 强制远程 Stage 04→05 为一个原地连续 bundle。 | 在第二真实案例验证 2–3 个 Tier A，并验收 Manager 非 APOE 极小连续链。 | Suzhou2 Manager 真实 Stage 04→05 极小任务待 VAL-008。 | 2026-08-01 |

## 当前结论

- 阶段状态：`smoke-validated`；通用实现和 APOE 真实 scientific-stop 路径均通过。
- `S05-002` 已实现 Stage05Bundle 0.2：按 `F_YAML` 晋级最多三个 Tier A，不从
  Tier B–D 补位；full-target 零通过形成 `advisory-warning`，不撤销晋级。
- v1.6 后端、文件、数量与 checksum 错误仍是 operational failure，不会被 warning
  规则吞掉。
- 必需 pilot 硬门、逐候选证据、序列去重、strategy Tier、`S_screen` 和
  `F_YAML` 已实现。
- Tier A 扩展复用 Stage 04 的 BoltzGen task/executor/collector，不存在第二套生成逻辑。
- full-target Protenix 使用 target required MSA、binder query-only、无模板、seed 101。
- v1.6 只有没有 Tier A 才发布 `stopped-no-tier-a`；旧 v1.5 的 no-winner stop 继续
  按原 Bundle 0.1 只读兼容，不会改写历史。
- APOE 正式结论为 `stopped-no-scale-winner`，不是软件失败：21 个策略中
  region A × gontivimab 为唯一 Tier A，扩展后 12/100 通过 local gate，但 Top 10
  的 full-target Protenix 结构均未保持原 binder pose。
- 冻结 v1.5 run 本身仍不得自动进入 Stage 06/07，也不得把 binder pose RMSD 3 Å
  门槛放宽来迎合案例。v1.6 continuation 只能通过独立 policy reevaluation 采用相同
  pilot Tier/F_YAML；历史人工授权 50k 也必须与旧 scientific stop 并列展示。
- `2026-07-31T12:48:00+08:00` 已发布独立 policy reevaluation/adoption record：
  v1.5 的 `stopped-no-scale-winner` 原样保留；v1.6 从冻结 pilot 证据晋级
  `region-a-h-all-c-full-scaffold-gontivimab`，`F_YAML=0.39102687045`，并将
  full-target 0/10 结构通过记录为诊断 warning。

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
| v1.6 多 Tier A 晋级 / 诊断 warning | `implemented` | 0/1/2/3/4 Tier A、top3、禁止 B–D 补位和零结构通过测试 |
| v1.5 唯一 scale winner / scientific stop | `smoke-validated` | 冻结 APOE Bundle 0.1 与旧 stop 兼容读取 |
| 原子 progress、append-only event、resume | `implemented` | 结构指标 cache、expansion/full-target TaskRecord、通用 watch |
| APOE 真实 Stage 05 | `smoke-validated` | 840 个 pilot、60 个新增扩展、10 个 full-target Protenix 全部完成；合法发布 `stopped-no-scale-winner` |
| Suzhou2 原地 Stage 04→05 | `implemented` | bundle 0.2 只接受完整 `(4,5)`，ProteinDigger 不根据 stop-after 缩成单 Stage；控制端默认只获取 review 证据 |

## Now

- `[VAL-003]` 对同一 APOE 候选、MSA 与 seeds 101/202/303 进行 target-template /
  hotspot-constraint 受控比较；不得修改已发布 v1.5/v1.6 结论。

## Next

- `[VAL-003]` 使用相同 APOE 候选、target MSA 和 seeds 101/202/303 受控比较
  no-template、target-template 与 target-template+hotspot constraint，并增加已知
  VHH–抗原正对照。当前证据只能说明现有 Protenix 验证模式未保持 binder pose，不能
  直接宣称 Protenix 软件有 bug。
- 在第二条独立真实 target 上复用相同 frozen profile，验证 winner 或另一种 scientific
  stop。
- 通过预注册 benchmark 审视 full-target binder-pose gate；任何阈值或参考对齐方法变化
  必须形成新 profile/ADR，不能回写本次 APOE 结果。
- 在第二条独立真实 target 上验证 2–3 个 Tier A 共享预算的运行路径。

## Blocked

- 公共 ColabFold MSA 无 SLA；网络失败属于 operational failure，可恢复但不能无 MSA
  fallback。
- APOE 的旧 v1.5 no-winner 是已完成的科学负结果，不列为 `Blocked`；v1.6 明确把
  同一 full-target 结果降为 advisory warning，但不得回写旧 Bundle。
- Suzhou2 当前缺少已登记的 Protenix/TNP Stage 07 环境，且八张 GPU 正被其他任务使用；
  不终止外部进程，等待资源和后端自然就绪。

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
- dev27 集成前完整回归：不可变快照 `stage0507-validation-20260731-022` 中
  `make check/test/build`、`341 passed, 8 skipped`、Ruff、142 个源文件的 strict
  mypy 以及 wheel smoke 通过；快照
  `stage0507-validation-20260731-021` 中 Workbench production build、Chromium
  双尺寸 38 项非视觉测试和 2 项视觉回归通过。
- 2026-07-31：采用记录校验 Stage 05 RunManifest SHA-256
  `d7c618…80e07`、Stage05Bundle SHA-256 `401259…9073`，重新计算得到唯一 Tier A、
  `F_YAML=0.39102687045`；Workbench 默认显示 A/B/C/D=`1/1/5/14`、1 组晋级和
  1 条诊断提醒。

## 工作日志

- `2026-07-26T04:33:17+08:00`：完成 S05-001 的类型、指标、筛选、恢复和文档初版；
  状态保持 `implemented`，等待正式 APOE 输入。
- `2026-07-26T09:13:48+08:00`：APOE 真实运行完成；严格执行 840-candidate pilot、
  唯一 Tier A 扩展和 10 个 full-target prediction，最终如实发布
  `stopped-no-scale-winner`，状态提升为 `smoke-validated`。

## 历史索引

- [2026-07 工程实现与 APOE scientific-stop 归档](history/2026-07.md)。
- [2026-08 Suzhou2 原地 Stage 04→05 交接](history/2026-08.md)。
