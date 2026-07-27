# Stage 06 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态状态和验证证据。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `implemented` | S06-001 的分片/恢复已完成；S06-002 新增带科学边界的人工规模授权与 SSH whole-run 提交。 | 在 Suzhou2 八张 A100 上运行 APOE 唯一已扩展 Tier A 的 20×2500 探索性 50k。 | 无代码阻塞；50k 为长任务，完成前保持 Now，Stage 05 科学停止不变。 | 2026-07-27 |

## 当前结论

- 阶段状态：`implemented`，不是 `smoke-validated`。
- `smoke-1000` 表示全新 1000 个候选，固定为两个 500-candidate shard。
- `production-50000` 的二十个 2500-candidate shard 已获得一次 APOE 探索性真实授权。
- Stage 06 复用 Stage 04 的 BoltzGen adapter、collector、TaskRecord、事件与恢复执行器。
- Stage 04/05 候选不计入 scale 数量；Stage 07 才执行 Protenix 深度筛选和 TNP。
- 软件能力与 APOE 科学结果分别报告；人工授权生成不会修改 Stage 05 科学停止。

## 功能矩阵

| 能力 | 状态 | 当前证据 |
| --- | --- | --- |
| `smoke-1000` 2×500 计划 | `implemented` | `ScaleProfile`/`ScalePlan` 类型与单元测试 |
| `production-50000` 20×2500 计划 | `implemented` | 只验证计划和授权边界，不执行真实 50k |
| 25% 磁盘余量门 | `implemented` | Stage 04 声明 artifact 基线、20×保守倍率、任务前二次检查 |
| 多 GPU shard 调度 | `implemented` | 复用 ENG-008，一张 GPU 同时一个 shard |
| 中断恢复与增量收集 | `implemented` | 稳定 task/shard/ordinal、共享恢复状态机 |
| 精确 merge 与覆盖报告 | `implemented` | 1000 fixture 校验 identity 唯一和 ordinal `1..1000` |
| 发布中断恢复 | `implemented` | 终态 artifact identity/bytes 校验后复用，不覆盖 |
| Stage 05 停止后的人工探索性授权 | `implemented` | 只接受已扩展 Tier A、源 Bundle SHA-256、授权人/理由和双重确认；`stopped-no-tier-a` 禁止越过 |
| SSH whole-run 提交 | `implemented` | dedicated key、strict known-host、精确版本探针、rsync、systemd worker、远端独立 run |
| APOE 新 1000 候选 | `not_applicable` | 本次负责人直接授权独立的 50,000 profile，不把旧 100/840 计入 |
| APOE 真实 50,000 | `running` | Suzhou2 8×A100，20×2500；完成前不得称为 ScaleBundle 成功 |

## Now

- `[S06-002]` 跟踪 APOE `region-a-h-all-c-full-scaffold-gontivimab` 的
  `production-50000`，验证 20 个 shard 的任务、候选 identity、GPU 分配、断线后
  systemd 存活和 resume。
- `[ENG-013]` 用 Suzhou2 真实部署验证 SSH probe/submit/status；远端 run 才是科学事实
  来源，控制端 job record 只用于定位。

## Next

- APOE 50k 完成后验证精确 1..50000 ordinal、无重复/缺口、ScaleBundle 与所有 checksum。
- 在第二条独立真实 target 或未来新版本策略产生唯一 Stage 05 winner 后，按正常主线执行
  `smoke-1000`。
- 用真实运行重新测量每 candidate 磁盘峰值，并评估当前 20×安全倍率。
- 把 remote job/progress 纳入 UI 长任务页；科学配置继续不保存 SSH 主机或密钥。

## Blocked

- 无当前 blocker。APOE 的 `stopped-no-scale-winner` 仍是冻结科学结果；本次人工授权
  只批准探索性生成预算，不批准科学结论或进入 Stage 07。

## 验证证据

- 模型与计划测试：1000/50000 profile、连续 shard、预授权拒绝、coverage 失败。
- 集成 fixture：非 APOE target 精确生成 1000 个新候选；发布恢复复用同一 bundle
  SHA-256；磁盘门失败时没有创建 task。
- 全仓：`make check`、`218 passed, 8 skipped`、`make build` 通过；wheel 的
  `21/21` 个资产和 console script 校验通过。
- 最小真实 backend smoke：待完成。
- SSH 单元/类型检查：严格 host identity、精确 config staging、persistent systemd、
  profile 绝对路径和双 acknowledgement 已覆盖。
- APOE source：Stage 05 run `20260726-004-stage05-pilot-filter` 保持
  `stopped-no-scale-winner`；Stage05Bundle SHA-256
  `401259623dd43cf5a17dfed20fd81b6868d61002bcc1eabfab1b68134b5d9073`。

## 工作日志

### 2026-07-26

- 建立 `ScaleProfile`、`ScalePlan`、`ScaleShard`、`ScaleResourceReport`、
  `ScaleCoverageReport` 与 `ScaleBundle`。
- 资源门测试首次在临时文件系统触发拒绝，确认执行器在任务创建前停止；测试改为显式模拟
  足量磁盘，没有削弱 25% 产品规则。
- 将 Stage 04 candidate index 正式加入 Stage 06 input artifact，避免容量测量成为未声明
  的隐式读取。
- 增加终态发布恢复：崩溃遗留 artifact 只能在模型 identity 或原始 bytes 一致时复用。
- APOE Stage 05 于 `2026-07-26T09:13:48+08:00` 发布
  `stopped-no-scale-winner`；统一 run 中仅保留预创建的空阶段目录，没有创建 Stage 06
  attempt、task、shard 或 manifest。

### 2026-07-27

- 负责人明确要求跳过 APOE Tier A 的 100-candidate 科学结果，直接在 Suzhou2 八张卡做
  50k 探索性生成。
- 没有改写 Stage 05 winner；新增 `ScaleStrategyAuthorization`，只允许
  `stopped-no-scale-winner` 中已扩展 Tier A，并冻结源 Bundle hash 与双重确认。
- SSH 采用 whole-run control plane：控制端 staging，远端 systemd worker 继续调用同一
  local multi-GPU Stage 06。

## 历史索引

- [2026-07 工程实现与 APOE 未运行边界](history/2026-07.md)。production 50k 未授权。
