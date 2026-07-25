# Stage 07 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态状态和验证证据。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `implemented` | S07-001 已实现 v1.5 预筛、Protenix 三 seed、一致性、TNP 证据和确定性主备候选包，固定 TNP batch smoke 已通过。 | 完成全仓质量门和实现提交；APOE 只在 Stage 04–06 上游门通过后运行。 | APOE 验收依赖 Stage 04/05/06；当前实现不能提前宣称真实 Stage 07 smoke。 | 2026-07-26 |

## 当前结论

- 阶段状态：`implemented`，不是 `smoke-validated`。
- 通用实现已经覆盖全部 Stage 06 candidate 的逐级处置、seed-101 冻结归一化、Top 60
  additional seeds、TNP required evidence 和 20+20 上限。
- 非 APOE 1000-candidate 集成 fixture 已产生非空 `smoke-review-package`，证明代码没有
  APOE ID、固定残基或固定三分区依赖。
- TNP adapter 固定官方 commit、license、Python 3.10、原生库环境和文件协议；官方
  7EOW VHH 单候选真实 batch 已完成并由严格 parser 收集，DATA-003 达到
  `smoke-validated`。
- APOE 如果 Stage 05 合法科学停止，Stage 07 不伪造结果；通用实现状态与 APOE 科学结果
  分开。
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
| APOE Stage 07 真实运行 | `planned` | 依赖 Stage 04 840、Stage 05 winner 与 Stage 06 新 1000 |
| 真实 production-50000 候选包 | `planned` | 50k 本轮没有运行授权 |

## Now

- Stage 07 不占用顶层 `Now`；顶层仍只跟踪正在运行的 `[S04-001]`。
- 形成独立功能提交、追加带完整 SHA 的 history，并核对 GitHub `main`。

## Next

- Stage 04 840 个候选发布后运行 APOE Stage 05。
- 只有 Stage 05 发布唯一 winner 才运行 Stage 06 新 1000。
- APOE 到达 Stage 07 后，按冻结 v1.5 规则产生真实非空或空
  `smoke-review-package`，不修改门槛迎合结果。
- 增加第二条独立真实 target、正式候选 review gate、湿实验反馈和阈值校准。

## Blocked

- APOE Stage 07 真实验收依赖 Stage 04/05/06 顺序完成，不是 Stage 07 代码阻塞。
- production 50k 未授权，不能用当前 smoke 结果声称 production readiness。

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
- APOE real run：待上游 gate。

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

## 历史索引

- [2026-07 工程实现与 TNP backend smoke](history/2026-07.md)。APOE 到达本阶段后
  必须追加真实候选或 scientific stop，不改写本条工程记录。
