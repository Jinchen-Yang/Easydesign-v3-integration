# Stage 07 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态状态和验证证据。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `implemented` | S07-002 多策略筛选保持；dev32 已将受管 Stage 06→07 原地运行与 review 同步固化为执行契约。 | 完成 Suzhou2 Stage 07 后端 probe，再对已验证历史 50k 原地运行。 | Suzhou2 缺少 Protenix/TNP 登记，GPU 当前全部繁忙。 | 2026-08-01 |

## 当前结论

- 阶段状态：`implemented`，不是 `smoke-validated`。
- ScaleBundle 0.2 的 candidate strategy 集合、allocation、ordinal 和 Stage 05 晋级
  identity 会在进入筛选前完整校验；旧单策略 Bundle 0.1 继续兼容。
- 全部 strategy 共享同一门槛、分数和 lazy-greedy pool，不为 YAML 硬留名额；每个
  primary/backup 保留 strategy lineage，候选包发布来源分布。
- 通用实现已经覆盖全部 Stage 06 candidate 的逐级处置、seed-101 冻结归一化、Top 60
  additional seeds、TNP required evidence 和 20+20 上限。
- 非 APOE 1000-candidate 集成 fixture 已产生非空 `smoke-review-package`，证明代码没有
  APOE ID、固定残基或固定三分区依赖。
- TNP adapter 固定官方 commit、license、Python 3.10、原生库环境和文件协议；官方
  7EOW VHH 单候选真实 batch 已完成并由严格 parser 收集，DATA-003 达到
  `smoke-validated`。
- APOE 的 v1.5 scientific stop 与后来人工授权完成的单策略 50k 必须并列保留；
  Stage 07 只有在不可变采用记录和远端后端预检通过后才消费该历史 ScaleBundle，不能
  以新 v1.6 语义改写旧运行。
- 候选包始终 `awaiting-human-review/not-ordered`；实际下单不属于本阶段。

## 功能矩阵

| 能力 | 状态 | 当前证据 |
| --- | --- | --- |
| 全候选序列合法性、liability、Cys、BoltzGen 和去重处置 | `implemented` | 单元测试覆盖通过、重复、未知残基和未配对新生 Cys |
| `S_refold`、absolute gate、`S_deep` 与 Top 400 | `implemented` | 复用 v1.5/geometry 模块；非 APOE 集成 fixture |
| Protenix seed 101 与冻结经验归一化 | `implemented` | `Seed101Normalization` 与复用参考池测试 |
| seed 202/303 和两 seed 一致性门 | `implemented` | 单 seed/seed-pair/consensus 测试 |
| TNP strict adapter 与风险记录 | `smoke-validated` | JSON/CSV identity、nonfinite、IMGT insertion code 与真实结果 parser |
| TNP Python 3.10 真实环境 | `smoke-validated` | fixed-source/import/help/native-library probe；官方 7EOW VHH batch 成功 |
| 90/10 lazy-greedy 主备选择 | `implemented` | quality/diversity/tie 与不足 40 不补齐测试 |
| 可恢复进度、事件与 operational failure | `implemented` | 原子 state、append-only 日志、非发布 failure 测试 |
| 非 APOE 1000-candidate 完整集成 | `implemented` | Stage 03→07 fixture，三 seed、TNP、2 primary |
| 多策略 ScaleBundle 0.2 输入 | `implemented` | allocation/lineage/全局竞争与旧 Bundle 0.1 兼容测试 |
| 最终 YAML 来源分布 | `implemented` | primary/backup 来源计数与 candidate lineage 契约 |
| Suzhou2 原地 Stage 06→07 | `implemented` | 受管 stage range 6→7、managed-run manifest SHA-256 引用、review 同步和断线后继续观察 |
| APOE Stage 07 真实运行 | `planned` | 历史 50k 已完成，等待 adoption record、Protenix/TNP 与空闲 GPU |

## Now

- `[S07-002/VAL-007]` 在不复制 39 GB 的前提下消费经过采用记录授权的 Suzhou2
  ScaleBundle 0.1；先完成后端和资源 probe，不能直接启动高成本任务。
- `[VAL-008]` 在新 Suzhou2 worker 完成单候选 Stage 07 adapter probe，验证原地输入、
  review 同步和断线恢复；不触发真实 50k 筛选。

## Next

- 新的真实 target 在 Stage 05 v1.6 晋级 1–3 个 Tier A 并完成共享 Stage 06 population
  后，按同一冻结规则产生真实非空或空 `smoke-review-package`。
- 增加第二条独立真实 target、正式候选 review gate、湿实验反馈和阈值校准。

## Blocked

- Suzhou2 尚未登记 Protenix/TNP 环境；八张 GPU 当前均被其他任务占用。等待自然释放，
  不终止外部任务。
- APOE 历史 v1.5 stop 与 manual override 必须并列显示；新政策 continuation 不修改
  任何旧 manifest。

## 验证证据

- 单元测试：sequence prefilter、归一化、multi-seed、TNP strict parser、风险和多样性。
- 集成测试：非 APOE、单 region、单 scaffold、1000 scale candidate；只有两个唯一序列，
  最终如实输出两个 primary、零 backup，不凑足 40。
- operational failure 测试：缺少正式上游时保存结构化失败但不发布 Stage 07 manifest。
- `make check`：repository/status/assets/compile/Ruff/strict mypy 全部通过，mypy 检查
  99 个源文件。
- 全仓 pytest：`230 passed, 8 skipped`；8 项仅因默认未显式设置独立 PyMOL 环境而
  按设计跳过。
- `make build`：dev5 wheel 构建、21/21 固定资产和隔离 console-script smoke 通过；
  新增 `nanobody-final-v1.5.yaml` 已确认存在于 wheel。
- dev27 集成前完整回归：不可变快照 `stage0507-validation-20260731-022` 中
  `make check/test/build`、`341 passed, 8 skipped`、Ruff、142 个源文件的 strict
  mypy 以及 wheel smoke 通过；快照
  `stage0507-validation-20260731-021` 中 Workbench production build、Chromium
  双尺寸 38 项非视觉测试和 2 项视觉回归通过。
- Proteindigger1 安装 profile 已增加显式 TNP runtime；真实
  `easydesign doctor --config <stage07-config> --json` 同时通过 Protenix 2.0.0、
  PyMOL 3.1.0、BoltzGen 0.3.2 和 TNP fixed commit，profile SHA-256
  `61f84e4bc6e9ca90f4574f466bede82cdf60c958fc0319d5f360544c93f0de0b`。
- TNP live smoke：
  `/root/autodl-tmp/Protein_design/easydesign-clean/runs/_development/tnp/`
  `20260726-official-vhh-smoke`；官方 7EOW chain B VHH 从
  `2026-07-25T22:50:38Z` 运行至 `22:55:54Z`，return code 0。结果 JSON SHA-256
  `7f91531ce5645392e4ec1416021f61be5f760d7f596eaea37f4969ccaf2570f6`，
  normalized record SHA-256
  `04681aaa17bf0b7b50c8dc3da8068d61ea1893fc04388d3c45b4739d55006601`。
- 上述 TNP 样本如实得到 high risk、3 amber、0 red 和 6 条 liability；这只验证
  backend/证据链，不代表最终 APOE 候选结论。
- APOE Stage 07 real run：未创建。Stage 05
  `20260726-004-stage05-pilot-filter` 保持合法停止；独立历史 Stage 06 run 已在
  Suzhou2 发布 ScaleBundle 0.1，当前等待采用记录和后端 probe。

## 工作日志

### 2026-07-26

- 将 Nanobody Filter Standard v1.5 后半部分实现为版本化、确定性 scientific profile。
- Stage 05/07 共用 Protenix complex request 和结构指标，未建立第二套阈值或后端逻辑。
- 审计 TNP 固定 commit 后确认其 liability 文件扩展名虽为 `.json`，实际为 CSV；adapter
  以内容契约解析并将原始文件作为正式 artifact，不按扩展名猜格式。
- 纠正环境草案中的无效 `ANARCI==2024.5.21`：官方 Bioconda package identity 是
  `2024.05.21`，Python distribution metadata 为 `1.3`。
- TNP 官方链接的 salilab DSSP `3.0.0` 在真实环境中错误请求
  `libboost_thread.so.1.73.0`；改为严格固定且可启动的 conda-forge DSSP `4.6.1` /
  Boost `1.90`，并将 ImmuneBuilder/PDBFixer 的 `pkg_resources` 兼容边界固定为
  setuptools `80.9.0`。
- 真实 help probe 随后发现 TNP `setup.py` 未声明却直接导入 scikit-learn；显式固定
  `1.7.2` 并纳入 runtime identity，禁止依赖碰巧存在。
- 首个真实 liability 文件包含 `111A/111B/111C`；模型与 parser 增加原始
  `numbering_label`，防止 insertion code 被无声压成同一个 `111`。
- 发现根分区接近满载，所有 TNP pip 临时文件和 cache 改用数据盘，不清理其他任务缓存。
- APOE Stage 04 继续独立运行，本次 Stage 07 开发未终止或抢占现有 GPU 任务。
- APOE Stage 05 于 `2026-07-26T09:13:48+08:00` 发布
  `stopped-no-scale-winner`；按契约未创建 Stage 06/07 APOE 任务或候选包。

## 历史索引

- [2026-07 工程实现、TNP backend smoke 与 APOE 未运行边界](history/2026-07.md)。
- [2026-08 Stage 06→07 远程数据本地性](history/2026-08.md)。
