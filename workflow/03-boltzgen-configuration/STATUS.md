# Stage 03 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态状态和验证证据。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `smoke-validated` | S03-001 已完成通用基础编译器；APOE 3×7 共 21 个 YAML 全部通过固定 BoltzGen 0.3.2 官方校验。 | 冻结 1.0 基础模板，把开发重心移交 Stage 04 可恢复 pilot generation。 | 无 Stage 03 工程阻塞。 | 2026-07-26 |

## 当前结论

- 阶段状态：`smoke-validated`；这是配置编译工程 smoke，不是 binder 科学验证。
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
| APOE 21/21 真实 smoke | `smoke-validated` | 正式 continuation run succeeded；21/21 官方 check passed |

## Now

- 无 Stage 03 未结束实现；S03-001 与 DATA-002 已归档。

## Next

- `[S04-001]` 在 StrategyBundle 上实现可恢复的 21×40 pilot generation。
- `[ENG-008]` 建立 TaskRecord、append-only event、progress snapshot、多 GPU 调度与
  resume。
- Stage 03 提高款：crop、H_core/H_cluster、CDR 优化、区域几何选模、自适应预算和
  多策略轮次。
- 1.0 后再评估 `guides/` 高级草案和可选 Agent 建议层；1.0 不依赖 Agent。

## Blocked

- 无 Stage 03 实现阻塞。

## 验证证据

- Python 3.11 全仓：`189 passed, 8 skipped`。
- `make check`：ruff、mypy、结构、状态汇总和 Viewer 资产检查通过。
- `make build`：wheel 包含并逐字节核对 Viewer 与 14 个 scaffold、license，共
  `21/21` 个 package asset；隔离安装后的 console script 通过。
- 通用 fixture：1/2/3 区域、非 A/B/C ID、不同预算、完整矩阵、禁止
  `not_binding`、target checksum 和不可覆盖均通过。
- APOE 正式 run：
  `/root/autodl-tmp/Protein_design/easydesign-clean/runs/apoe-s02-006-pse/`
  `20260726-002-stage03-basic-vhh`。
- RunManifest revision 3 为 `succeeded`；`runs show` 完整性为 `verified`，完成 Stage
  01/02/03。
- StrategyBundle：21 个 strategy、A/B/C 三个上游区域、七个 scaffold、每策略预算 40；
  SHA-256 `a8451f5f7f7b7d09e69fbf7cf966c04b70aef01a3863132671b756aa4fe64b87`。
- validation report：21/21 `passed`；SHA-256
  `48c73788cd9a7ef5219d160307ac2dda9f6ac428b21aadb84f726d9e3cbbc9a6`。
- 全部生成 YAML 不包含 `not_binding`；未标注 residue 保持中性。

## 工作日志

- 2026-07-26：冻结 BoltzGen `0.3.2` 与 commit
  `a3149cf18eeb58648d1abbb27539bd73f746cdda`；完成基础编译器、adapter、typed config、
  continuation API 和官方 scaffold registry。
- 2026-07-26：发现逐 YAML 官方 check 有明显初始化成本；仍逐个保留官方检查结果，
  不以只解析 YAML 替代 backend 校验。
- 2026-07-26：首次真实校验因 cache_root 指向错误父目录而尝试联网，21 个任务均明确
  失败；修正为固定 Hugging Face cache、验证 `mols.zip` SHA-256 并设置 offline 后，
  21/21 通过。
- 2026-07-26：首次正式 continuation run 在 capability 抢先写入 artifacts 后被
  immutable compiler 拒绝；调整为先 probe、后编译、再写 capability，新 run 成功，
  失败运行未被覆盖。

## 历史索引

已结束日志按月移动到 [`history/2026-07.md`](history/2026-07.md)。
