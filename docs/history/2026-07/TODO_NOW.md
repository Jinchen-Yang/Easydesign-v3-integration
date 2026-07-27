# 2026-07 项目历史

本文件从原顶层 `TODO_NOW.md` 归档跨阶段记录。阶段内部历史由各 Stage 单独维护。
`完成时间` 使用带 UTC offset 的 RFC 3339 秒级格式；新记录对应完成门槛实际满足时间。
2026-07-23/24 的批次记录来自旧制度，补录时间取该批最后一个可验证完成提交，不据此
推断批次内每项工作的精确时刻。

## 2026-07-25 — ENG-004：完成历史时间戳治理

- 状态：`implemented`。
- 完成时间：2026-07-25T09:20:00+08:00
- 问题：Stage history 和从顶层 `TODO_NOW` 移出的事项只记录日期，无法可靠判断同一天
  多项工作的完成顺序；原仓库检查也只验证历史区块存在，不验证时间精度。
- 方案：统一使用带 UTC offset 的 RFC 3339 秒级 `完成时间`；Stage 与共享 history
  使用同一字段，并将缺失、重复、仅日期和无时区时间设为 `make check` 失败。
- 历史迁移：Stage 01/02 已结束工作使用首次包含该记录的 Git 提交时间补录；旧顶层
  日期批次明确标注为旧制度，只记录可验证的批次完成时间，不猜测内部事项精确时刻。
- 验证：Proteindigger1 的 Python 3.11 环境完成 `make check`；新增负向测试覆盖缺失、
  格式错误和重复时间戳，完整测试结果为 132 passed、8 skipped。
- 遗留边界：Stage 03–07 尚未产生完成记录，因此保留空 history 目录而不制造假历史；
  今后只有工作项真正关闭时才创建带时间戳的月度记录。
- 提交：`docs: enforce timestamped work history`；远端完整 SHA 以推送后核对结果为准。

## 2026-07-25 — UX-001 / ENG-002：Developer Preview CLI 与可复现安装身份

- 状态：`smoke-validated`。
- 完成时间：2026-07-25T02:17:20+08:00
- 问题：Stage 01/02 已有真实 API，但使用者必须手工构造 adapter、环境变量和开发脚本；
  wheel 安装又无法用旧 `code_commit` 如实描述实际代码。
- 方案：新增 `easydesign` console-script、真实 target 项目初始化、用户级 runtime
  profile、配置验证、doctor、统一 Stage 01/02 run、run index 查询和 Viewer 包装；科学
  参数继续只存在于 YAML，机器路径只存在于 profile。
- 代码身份：RunManifest 1.1 区分 clean Git、dirty working tree 与 installed package，
  后两者保存确定性 package tree SHA-256；旧 1.0 manifest 保持可读。
- 治理：顶层 TODO 新增 ENG、UX、REP、UI、VAL、DATA、REL、PAPER、BIZ 板块；质量门
  检查 TODO_NOW 活跃任务 ID 是否已登记。
- 工程证据：128 个 pytest 通过，8 个需真实 PyMOL 环境的测试按设计跳过；ruff、strict
  mypy、仓库结构、wheel 资源及隔离安装后的 `easydesign --version`、
  `python -m easydesign --help` 均通过。
- 真实 smoke：Proteindigger1 用户 profile
  `proteindigger1-local` 通过 PyMOL 3.1.0 与 ScanNet TensorFlow 1.14 CPU doctor；
  `--dry-run` 未创建 run。随后一条命令完成
  `runs/apoe-cli/20260725-001-ux001-pse-stage02`，RunManifest 1.1 revision 3、
  Stage 01/02 和 Target Viewer 均为 `succeeded`，Stage 03 handoff 为
  `awaiting_region_selection`；comparison 含完整 9 组重叠，`fused_score` 与 `winner`
  保持 `null`。
- sequence smoke：同一 CLI 完成
  `runs/apoe/20260725-002-ux001-sequence-stage01`；required ColabFold MSA depth 609、
  Protenix-v2 predicted 143-aa `target.cif`、RunManifest 1.1 revision 2 和 Target Viewer
  均成功，没有启动 no-MSA fallback。
- Viewer 回归：Playwright 3 passed、2 个浏览器环境相关用例按设计 skipped；服务仍只
  绑定 `127.0.0.1`。
- 遇到的问题：`runs list` 首次真实使用时遇到旧迁移 run 缺少现代 `LATEST`，导致列表
  整体中断。
- 解决办法：列表只读取 index，对不可验证旧条目标记 `integrity_status=unavailable` 并
  保留错误；`runs show` 继续严格验证 manifest/artifact，不把旧记录伪装成成功。
- 遗留边界：Stage 03–07、resume、PDB/mmCIF/UniProt 输入、正式 UI、公开许可证、PyPI
  和跨平台重型 backend 支持仍未实现；Developer Preview 不构成稳定公开 API。
- 提交：本工作项的 `feat(cli): add developer preview command workflow`；推送后以远端
  `main` 核对的完整 SHA 为准。

## 2026-07-24 — 旧制度跨阶段完成批次

- 完成时间：2026-07-24T17:58:46+08:00
- 决定全部环境先使用 Conda；EasyDesign 主环境固定 Python 3.11，重型工具保持独立。
- 创建 `/root/autodl-tmp/conda_envs/easydesign-core`，完成 editable 安装及
  check/test/build 验证。
- 扩充 `docs/ARCHITECTURE.md`，明确源码层级、依赖方向、环境和运行目录。
- 扩充 `AGENTS.md`，使 Agent 自动维护测试、架构、workflow、TODO 和本地 commit。
- 完成 M1-01：实现 `ArtifactRef`、`Attempt`、`StageManifest`、`RunManifest`、规范
  JSON、SHA-256、相对路径安全、原子拒绝覆盖和 revision 审计链。
- M1-01 工程证据：`make check`、43 个 pytest 契约测试和 wheel build 全部通过；
  提交为 `feat(core): implement foundational run contracts`。
- 创建私有 GitHub 仓库 `Knitua/Easydesign`，使用仅限本仓库的 Proteindigger1
  deploy key 推送 `main`；本地与远端 HEAD 验证一致。
- 明确 EasyDesign 的长期产品边界是 VHH、蛋白、肽及后续经过验证类型的多 binder
  一键式平台；VHH 仅是 1.0 的首个 reference profile。TODO 改为短期/中期/长期路线。
- 将七个 Stage STATUS 的一句话摘要设为顶层状态事实来源；TODO 与 TODO_NOW 的实时表
  改为自动生成，`make check` 会拒绝未同步状态。
- 决定 Stage 02 以显式 ScanNet CPU 为当前主线，GPU 兼容性转为后续性能待办；正式
  `runs/apoe/20260724-005-stage02-cpu` 已发布两套 Top 3、9 组比较和成功 manifest，
  下一步是人工批准区域集。

## 2026-07-23 — clean-room 仓库基础

- 完成时间：2026-07-23T23:51:58+08:00
- 建立版本 `0.1.0.dev0` 的 clean-room 仓库架构。
- 定义七阶段职责、运行边界、项目治理和旧仓审计基线。

不得改写历史；原记录有误时追加更正。

## 2026-07-26 — S07-001 / DATA-003：最终候选包与固定 TNP runtime

- 状态：Stage 07 `implemented`；DATA-003 `smoke-validated`。
- 完成时间：2026-07-26T07:15:41+08:00
- 问题：Stage 07 缺少确定性深度筛选、多 seed 复核、TNP required evidence 和
  20+20 人工审核包；TNP 上游又存在未声明依赖、旧 DSSP ABI 和 liability 文件格式/
  IMGT insertion code 不透明的问题。
- 方案：实现 final v1.5 profile、共享结构/Protenix adapter、seed 101/202/303、
  冻结归一化、consensus、TNP strict adapter/receipt、lazy-greedy 多样性和明确
  scientific stop/operational failure。
- 工程证据：`make check`、230 passed/8 skipped、dev5 wheel/console script 通过；
  非 APOE 1000 fixture 产生 2 primary/0 backup；官方 7EOW VHH TNP 真实 batch 与
  Proteindigger1 全 backend doctor 通过。
- 真实边界：APOE 仍停留在正在运行的 Stage 04，不提前伪造 Stage 05–07 结论；
  production 50k 没有执行，实际下单不属于自动流程。
- 提交：`dc68ab0f8f9f0ea7f7ec697ab62ae00cd19195b2`。

## 2026-07-25 — UX-002 / ENG-005：canonical 七阶段配置与确定性审批边界

- 状态：`smoke-validated`。
- 完成时间：2026-07-25T11:37:26+08:00
- 问题：旧用户 YAML 把 Stage 01 字段放在顶层，只局部出现 Stage 02；Target Bundle 与
  RunManifest 也无法表达 coordinate ensemble 和“科学计算完成、等待人工批准”的中间态。
- 方案：schema 0.3 固定展示 `stage01`–`stage07`，跨阶段 binder/intent 放在 `design`；
  旧配置兼容读取并可显式迁移。Target Bundle 0.3、RunManifest 1.2 和 approval attempt
  分别表达模型集合、等待动作与唯一 Stage 03 handoff。
- 灵活性：UniProt accession 与 annotation policy 均可选；没有身份时仍可结构选区，
  但必须以 `structural_only` 留痕并由用户确认局限。
- 智能边界：EasyDesign 1.0 的判断只来自版本化模型、算法、规则和模板，不依赖
  LLM/Agent；1.0 后的 Agent 只能作为可选建议层，输出必须转换成类型化配置、确定性校验
  并经过人工批准。
- 验证：真实 APOE PSE 一条命令完成 canonical Stage 01/02，SASA 和 ScanNet CPU 均成功，
  Run 正确等待审批；151 passed、8 skipped，Playwright 3 passed、2 skipped，wheel
  `0.1.0.dev2` 验证通过。
- 遗留边界：真实多模型输入、自动身份发现、真实 APOE 区域批准、Stage 03–07 和 Agent
  建议层均未完成；本次没有替用户制造批准结果。
- 提交：`f30205d8a10c837ac4e437639800d1d811d41929`；远端包含关系以最终推送后核对。

## 2026-07-25 — ENG-006 / UX-003：六入口、双模式与可恢复决策

- 状态：`implemented`。
- 完成时间：2026-07-25T14:11:39+08:00
- 问题：Stage 01 只有 sequence/PSE 纵向切片，用户无法统一提交本地结构、PDB ID、
  UniProt 或 Target Bundle；人工选择也只能保存结果，不能在同一 run 恢复。
- 方案：schema 0.4 建立六入口 source union、scope 和 experimental-first policy；
  Target Bundle 0.4 冻结身份/候选/网络/context 证据；通用 Decision Gate 支持 human 与
  deterministic-policy authority，并以新 attempt 恢复。
- 双模式：`review-gated` 在 identity/chain/structure/hotspot 选择点等待用户；
  `unattended` 只使用版本化硬规则。两者共享 API 和 artifact，required review 与实际
  下单不能自动绕过。
- 工程证据：`make check`、170 passed/8 默认 skipped、显式 PyMOL 后 178 passed、
  wheel 6/6 和 Playwright 3 passed/2 runtime-only skipped。
- 真实证据：1UBQ PDB ID 直接发布 76-aa Bundle；P0CG48 scope 1–76 先停在多结构 gate，
  批准 1UBQ 后同一 run 的 `attempt-0002`、RunManifest revision 3 和 Viewer 成功。
- 遇到的问题：FASTA 初版绕过 RCSB、approval 不会 resume、Bundle 重导入丢 evidence，
  以及 Makefile 误导入另一份 editable checkout。
- 解决办法：所有 sequence/UniProt 统一走候选检索；approval 新建 attempt 并允许连续
  gate；Bundle 0.4 重发布全部可选 ArtifactRef；PSE 新 run 固定 chain A；每次网络失败
  留 evidence 并发布 failed manifest；测试固定从当前 `src/` 导入。
- 遗留边界：阶段级 `smoke-validated` 仍需完整六入口 live fixture；canonical-only、
  多 state PSE、预计算 MSA、自建 provider、Stage 03/05/06/07 gate 和科学 benchmark
  继续保留在 TODO。
- 提交：`feat(stage01): complete six target source workflows`；最终远端 SHA 由推送后
  HEAD 核对记录确定。

## 2026-07-25 — ENG-007 / UX-004：六入口 dispatcher 与完整读者工作流

- 状态：`smoke-validated`。
- 完成时间：2026-07-25T16:49:02+08:00
- 问题：Stage 01 的 source 编排集中在单个大模块，PSE 仍由 application 特判；用户虽能
  编辑 YAML，却不能在 init 时直接声明 Bundle source run、chain namespace、
  feature scope、precomputed A3M 或 MSA cache 策略。
- 方案：新增六个具名 source handler 和共享 dispatcher，保留旧入口为兼容门面；
  CLI/API 增加六入口、scope/identity、MSA 来源和 cache 参数，暂停时直接提示
  `decisions show/export/approve`，所有科学逻辑继续位于 Python API。
- 可复现性：版本升级到 `0.1.0.dev3`，canonical/resolved config 使用 schema 0.5；
  online cache refresh、显式 prefer-cache/offline 和 precomputed A3M 都保存实际输入
  hash/depth/provenance，禁止隐式 no-MSA。
- 工程证据：`make check`、187 项 Python 测试、dev3 wheel 资产/console-script/
  隔离安装和 Playwright 3 passed/2 skipped 均通过；Proteindigger1 十条真实路径均生成
  Bundle、Viewer 并被 Stage 02 读取。
- 遇到的问题：真实本地 PDB 发现 label subchain `Axp` 与规范 mapping chain A 不一致；
  precomputed doctor 又错误假定 remote provider 一定存在。两项均在真实矩阵中修复并
  增加回归。
- 遗留边界：自建 ColabFold/MMseqs2、跨平台重型 backend、非 canonical isoform、
  复合物 PSE、Stage 03 UX 和公开 release 仍属后续任务。
- 提交：`47af2ae715524d4edd50762a819175a9cfb661dd`
  （`feat(stage01): complete six-entry version-one workflow`）。

## 2026-07-25 — M7 / S02-006-USER-REGIONS：用户区域 Stage 03 交接

- 状态：`smoke-validated`。
- 完成时间：2026-07-25T22:58:22+08:00
- 问题：Stage 01 已保留 PSE 颜色，但 Stage 02 只能自动运行 SASA/ScanNet，无法把 PSE
  染色或初始 YAML 残基作为同一种可审计用户先验。
- 方案：schema 0.6 增加 detect/automatic/user-provided；固定红 A、蓝 B、黄 C，并将
  PSE 颜色和 sequence/label/auth/UniProt selector 统一为不可变
  `UserProvidedRegionSet`。审批后以 hotspots.yaml 0.3 的 discriminated
  `region_source` 交接。
- 真实证据：最终 APOE PSE 与 YAML auth 两条 review-gated run 均得到相同 A/B/C
  9/14/14 规范成员并独立发布 handoff；unattended run 记录真实人员、配置 SHA-256、
  理由和两类 acknowledgement，未伪装成算法批准。
- 工程证据：`make check`、183 passed/8 default-skipped、显式 PyMOL 8 passed、dev4
  wheel 6/6 和 Playwright 3 passed/2 runtime-only skipped 均通过。
- 结果：Stage 03 handoff 已建立；顶层 Now 转向 S03，S02-008 科学 benchmark 独立保留。
- 编号说明：早期历史已经使用 S02-006，因此本条追加限定名而不改写旧记录。
- 提交：本记录所在的 `feat(stage02): import user-provided hotspot regions`；最终 SHA
  以远端 `main` 核对为准。

## 2026-07-26 — S04-001 / ENG-008：APOE 21×40 pilot 真实验收

- 状态：`smoke-validated`。
- 完成时间：2026-07-26T07:54:40+08:00
- 结果：固定 BoltzGen 0.3.2 与官方 VHH7 在双 RTX 4080 上完成 21 个策略，每组
  40 个完整候选，共 840 个；RunManifest revision 3 为 `succeeded` 且完整性验证通过。
- 恢复证据：7xl0 首次只有 39/40，执行器保留原 39 个并精确补跑 1 个；最终
  21/21 task succeeded、0 terminal failure、840 个 candidate ID 唯一。
- 科学边界：官方 `pass_filters=true` 仅 28 个；Stage 04 不筛赢家，全部候选交由
  Stage 05 v1.5 重新审计，APOE 仍可能合法得到 scientific stop。
- 证据路径：
  `/root/autodl-tmp/Protein_design/easydesign-clean/runs/apoe-s02-006-pse/`
  `20260726-003-stage04-pilot`。
- 提交：由本次 Stage 04 验收文档提交记录，完整 SHA 在提交完成后以 Git 历史为准。

## 2026-07-26 — S05-001 / VAL-002：APOE full-target 科学停止

- 状态：Stage 05 `smoke-validated`；VAL-002 已如实完成到 scientific stop。
- 完成时间：2026-07-26T09:13:48+08:00
- 结果：840 个 pilot 得到 Tier A/B/C/D = 1/1/5/14；唯一 Tier A
  region A × gontivimab 新增 60 个后达到 100，12 个通过 local gate。
- full-target 证据：Top 10 全部完成 Protenix seed 101；target required MSA depth
  584、binder query-only、no-template、无 no-MSA fallback。target CA RMSD
  1.266–2.000 Å 全部通过，但 binder pose RMSD 18.005–31.726 Å 全部超过 3 Å。
- 终态：`stopped-no-scale-winner`，RunManifest revision 3 succeeded 且
  integrity verified；没有创建 APOE Stage 06/07 task、ScaleBundle 或候选包。
- 证据路径：
  `/root/autodl-tmp/Protein_design/easydesign-clean/runs/apoe-s02-006-pse/`
  `20260726-004-stage05-pilot-filter`。
- 科学边界：不放宽门槛迎合 APOE；Stage 06/07 通用能力保持 `implemented`，需要新的
  合法 winner 才做真实 smoke。
- 提交：由本次 Stage 05 真实验收文档提交记录，完整 SHA 在提交完成后以 Git 历史为准。

## 2026-07-26 — UI-001 / ENG-009 / UI-002 / UI-003：产品级科研工作台

- 状态：UI-001、ENG-009、UI-003 `smoke-validated`；UI-002 `implemented`。
- 完成时间：2026-07-26T13:19:19+08:00
- 问题：既有 CLI 和 artifact 足以运行科学流程，但缺少面向使用者的项目/run/stage
  工作台，也缺少把科学停止、操作失败、软件能力和单次 run 状态分开的产品语义。
- 方案：建立 React/TypeScript 明亮科研工作台和 FastAPI localhost gateway；所有结构、
  指标、进度和下载只来自 RunManifest → StageManifest → ArtifactRef，artifact 使用
  短期签名 token 并在发送前复验大小与 SHA-256。
- 交互：完成六入口项目向导、canonical YAML、doctor、独立 worker、SSE、完成当前任务
  后停止调度、恢复、Stage 01 Decision、Stage 02 hotspot YAML 审批、只读 replay 和
  draft-order gate；浏览器不包含科学逻辑。
- 七阶段结果：真实 APOE Stage 01–04 为 `succeeded`；Stage 05 如实显示 840 pilot、
  1 个 Tier A、100 expansion、12 local pass、10 个 Protenix prediction 和
  `stopped-no-scale-winner`；Stage 06/07 同时显示通用能力 `implemented` 与该 run
  `not-reached`。
- 安全与可移植性：服务只绑定 `127.0.0.1`，无 CORS/CDN/任意路径读取；React 产物进入
  Python wheel；Node 只用于构建和 Playwright。服务器根分区已满时，构建显式使用
  `/root/autodl-tmp` 的 `TMPDIR` 和 pip cache，没有删除用户数据。
- 验证：Python 3.11 `make check`、235 passed/8 skipped、dev6 wheel/console-script/
  静态资产通过；本机 Chromium 1440/1920 与 Firefox 9/9，Proteindigger1 Chromium
  1440/1920 6/6；真实 APOE localhost health、18 个 project 索引和完整投影通过。
- 遇到的问题：初版 Stage 02 range parser 无法展开 `1..3`；GPU 型号、21 个策略和
  APOE 文案被写死在展示层；服务器只有 Corepack shim 而没有全局 `pnpm`。
- 解决：增加 range 展开和去重、全部数字/设备/项目改为 manifest 投影、补齐 hotspot
  审批 API，并允许 Playwright 通过显式 dev-server command 和 Chromium executable
  在服务器复验。
- 遗留问题：UI-002 仍需在下一条可继续的真实 run 验收完整长任务启动、drain、审批和
  resume；Firefox 服务器专项、Windows shell、REP-002 SASA/ScanNet overlay、正式
  账号/公网/多人系统均未宣称完成。
- 提交：
  `cbbec251db6d224c5d93e7ec05de742f86a711dc`、
  `1a23d7891d6e97cf653dafa1825d2019eed2cb67`、
  `3bbc5c4aafc090eb1cfd432135f6142e47e717b6`、
  `d0e916fd0eeb4d33ea3bdbb34fbd8858b326d633`；最终文档提交以远端 `main`
  核对结果为准。

## 2026-07-26 — UI-004 / ENG-010 / UI-005：科研工作台全面重构

- 状态：`smoke-validated`。
- 完成时间：2026-07-26T15:54:37+08:00
- 问题：dev6 页面普遍使用 7–10px 正文，主导航混入审批、环境和审计等内部功能，
  默认文案直接暴露 manifest、artifact、checksum、run ID 等工程词；第5步只显示
  10 个 Protenix 候选的少量指标，840 个 pilot、100 个 expansion、21 个策略和正式
  指标没有形成可用产品入口。
- 方案：主导航收敛为“我的项目 / 新建设计 / 运行任务”，动态确认进入对应任务，环境
  进入设置，代码身份和文件完整性进入运行内技术记录；视觉全面继承 Stage 01 Viewer，
  正文/表格/元数据基线分别为 16/14/12px，并抽出统一结构工作区。
- 数据层：增加 Stage 05 overview、strategy、metric、candidate page 和 candidate
  detail 投影。大型 JSON 以 artifact SHA-256 为缓存身份，分页最大 100；原始、refold
  和 Protenix 结构从当前 manifest 声明的 candidate index 解析、复验后签发短期 token。
- 产品层：第5步拆成“结果结论 / 策略比较 / 候选筛选 / 指标说明”，支持 840 个 pilot、
  100 个 expansion、10 个 full-target 和 21 个策略；默认表格保持关键列，候选详情提供
  全部正式指标、原始 BoltzGen 指标、逐规则门槛、失败原因和结构切换。
- 验证证据：本地 `make check/test/build` 通过（235 passed、8 skipped），Workbench
  Chromium 1440/1920 与 Firefox 共 20 passed、1 skipped，便携 Stage 01 Viewer
  3 passed、2 个仅真实服务器 fixture 的测试 skipped。Proteindigger1 Python 3.11
  `make check/test` 同样通过，并直接读取真实 APOE run，核对 840 个 pilot、21 个策略、
  100 个 expansion、10 个 Protenix、25 个指标、Stage 05 `scientific-stop`、Stage
  06/07 `not-reached` 和 run integrity `verified`。
- 真实浏览器：通过 SSH localhost 转发打开 Proteindigger1 dev7 工作台，确认真实项目页、
  动态 2 个待确认事项、七阶段中文轨道、第5步结论、840 候选分页和
  `bb_target_aligned_rmsd_design` 中文指标列均来自服务器运行记录。
- 额外问题：服务器核心环境仍保留旧 dev6 distribution metadata；旧 wheel smoke 将依赖
  环境的 site-packages 放在临时 wheel 前面，导致 console script 错读 dev6。
- 解决：wheel smoke 显式将临时安装 site-packages 放在依赖 PYTHONPATH 最前面，隔离旧
  metadata 后再验证 console script 和 wheel 资产，避免通过重装服务器环境掩盖测试污染。
- 科学边界：没有改变 Stage 05 阈值、APOE `stopped-no-scale-winner`、Stage 06/07
  `not-reached` 或任何历史 manifest；VAL-003 继续作为独立受控实验。
- 遗留问题：UI-002 仍需在一条可继续的真实运行上验证完整启动、确认、停止调度和恢复；
  REP-002 overlay、第二真实案例、Windows shell 和正式公网/多人系统仍未完成。
- 提交：数据投影
  `66e8fb630c02652801cb44d31c9d826a6973ad6d`；界面、验证和文档提交以远端 `main`
  最终核对 SHA 为准。

## 2026-07-26 — UI-006 / ENG-011：结构、执行进度与筛选证据纠偏

- 状态：UI-004、ENG-010、UI-005、UI-006、ENG-011 均恢复或达到
  `smoke-validated`。
- 完成时间：2026-07-26T17:48:37+08:00
- 问题：第1/2步 Workbench 的 Mol* 背景偏黑；已完成 Stage 04 只显示终态
  `per_device`，因 GPU 已空闲而误呈现“没有设备分配”；第5步默认把科学停止放在首位，
  遮蔽了 21 个策略、Tier、初筛候选、正式指标和已有结构。
- 方案：第1/2/5/7步统一使用旧 Viewer 的 `#EEF1F6` 结构画布；增加 Stage 04/06
  `ExecutionProgressProjection`，实时消费结构化 SSE、终态从 manifest 声明的 task
  table/progress/events 重建历史；第5步按“策略/Tier → 扩展策略 → 12 个初筛候选 →
  10 个 Protenix 复核 → Stage 06 判断”默认展示。
- 数据修复：策略身份通过 Stage 03 strategy bundle 与 ArtifactRef 联接，不再拆字符串；
  九类策略指标保存有效/缺失样本数、均值、中位数和极值，缺失值不填零；12 个初筛候选
  均可打开 BoltzGen 原始/复折叠结构，其中 10 个在同一详情中增加 Protenix 结构切换。
- APOE 真实证据：Stage 04 恢复 GPU 0 的 11 个策略、440 个候选、14 attempts 与
  GPU 1 的 10 个策略、400 个候选、14 attempts；Stage 05 Tier A/B/C/D 为
  `1/1/5/14`，12/12 初筛候选有结构，10/10 有 Protenix 切换，最低观测 binder pose
  RMSD 为 18.004658 Å，但仍如实保留 `stopped-no-scale-winner`。
- 验证：`make check`；236 passed、8 个独立 PyMOL 环境测试按预期 skipped；dev8 wheel
  及 console script 通过；便携 Viewer 5/5；Workbench macOS Chromium 1440/1920 与
  Firefox 共 26 passed、1 skipped；Linux Chromium 功能验收通过。真实浏览器核对
  `#EEF1F6`、GPU 历史、12/10 候选层和三结构切换。
- 遇到的问题：服务器根分区无法写 pip/Playwright 临时数据，Linux 与 macOS 字体渲染
  又不适合共享像素基准。
- 解决：临时缓存和浏览器放入 `/root/autodl-tmp`，不删除用户数据；像素回归固定在
  macOS 1440/1920，Linux 跑相同交互和数据断言。浏览器配置允许显式跳过某一平台不具备
  的 Firefox 或跨平台像素用例，默认本地验收仍运行完整矩阵。
- 科学边界：没有修改 Stage 05 阈值、APOE 历史 manifest、科学停止结论或 Stage 06/07
  `not-reached`；UI 只重排和补全已存在证据。
- 提交：`daf833a5cc0d4650cd8db512ddd3bfaceb5b7fbd`
  （`fix(ui): surface evidence and historical execution`）；本条治理提交以远端 `main`
  最终核对 SHA 为准。

## 2026-07-26 — UI-007 / ENG-012：非线性新建设计与文件接收状态

- 状态：`smoke-validated`。
- 完成时间：2026-07-26T22:21:15+08:00
- 问题：新建设计把五项画成步骤轨道，却只有第一项可见，使用者必须先猜完目标输入才能
  阅读后续设计意图、区域策略和预算；浏览器选中文件后又只显示本地文件名，没有告诉
  使用者后端是否真正收到，草稿、环境检查和真实启动的禁用原因也不清楚。
- 方案：改为五项可任意切换的非线性向导，每项显示待填写、正在接收、已填写、已设置或
  检查通过；完整性集中在第五项解释。文件选择立即调用 localhost upload API，后端原子
  写入受控 token 目录并返回 basename、大小和 SHA-256；只有 receipt 成功才把输入标记
  为可用，草稿创建后单次消费 token 并冻结输入。
- 产品证据：使用者可以在没有目标文件时直接查看第2、3、4、5项；选择 PSE、PDB/mmCIF
  或 FASTA 后能看到正在接收、成功或失败，且标准 YAML 立即显示
  `inputs/<filename>`。草稿、配置/环境检查、真实启动按 `未开放 → 可用` 顺序变化，
  每个未开放状态都提供中文原因和返回对应项目的入口。
- 验证：Python 3.11 repository check、237 passed/8 skipped、dev9 wheel/console
  script/package data 均通过；Workbench 在 1440×900 和 1920×1080 Chromium 共
  20/20 通过，其中真实 File API 用例覆盖自由切换、上传 receipt、草稿、preflight 和
  启动按钮解锁。后端单元测试覆盖 SHA-256、原文件名复制、token 单次消费及空文件拒绝。
- 遇到的问题：首次尝试在 Proteindigger1 直接调用 `/usr/bin/chromium-browser` 时命中
  失效的 Snap wrapper；这不是页面失败，也没有用它冒充 Linux 浏览器通过。
- 解决：产品交互和双尺寸浏览器回归使用仓库固定的 Playwright Chromium；Python gateway、
  完整构建和 wheel 在 Proteindigger1 的 Python 3.11 环境独立复验，并保留 Linux
  浏览器路径为运行环境问题。
- 遗留问题：UI-002 仍需在下一条可继续的真实科学 run 上验证长任务启动、确认、drain
  和 resume；当前任务只完成向导和输入接收，不把模拟 preflight 视作长任务 smoke。
- 提交：`0e116db9c6b125d4dc6661ccd4e7a9d4189a2ab8`
  （`fix(ui): make project setup non-linear and stateful`）；本条治理提交以远端 `main`
  最终核对 SHA 为准。

## 2026-07-27 — DATA-004 / UX-005：APOE 合作者只读证据包

- 状态：`smoke-validated`。
- 完成时间：2026-07-27T00:39:20+08:00
- 问题：完整 APOE Stage 05 run 约 1.1 GB、20,955 个文件，其中约 970 MB 是 BoltzGen
  backend 中间目录；直接提交既违反 `runs/` 治理，也会让协作者难以校验哪些文件属于
  当前科学证据。仅提交截图又会丢失 21 个策略、840/100/12/10 各层指标、结构和 GPU
  历史。
- 方案：新增通用 `reporting.evidence_bundle`，先验证当前 RunManifest、StageManifest
  和全部 ArtifactRef，再复制正式 manifest 闭包与 12 个初筛候选、10 个 Protenix 候选
  所需结构；排除未被正式引用的 tasks/work/runtime，并生成逐文件大小与 SHA-256 清单。
- 共享结果：`examples/apoe-ui-demo` 为约 65 MiB，包含 307 个清单文件；保留 Stage
  01–05、21 个策略、840 个小规模候选、100 个扩展候选、12 个初筛通过候选、10 个
  Protenix 复核结果，以及 GPU 0 的 11/440 和 GPU 1 的 10/400 历史分配。
- 使用入口：`python scripts/serve_ui_evidence_bundle.py examples/apoe-ui-demo
  --port 8765` 会先完成 bundle 与科学 manifest 双重校验，再绑定 `127.0.0.1` 启动工作台。
- 验证：真实 bundle 校验通过；真实 FastAPI 投影复核 21/840/100/12/10 和双 GPU 历史；
  12 个初筛候选均有原始/复折叠结构，10 个还可切换 Protenix；`make check`、239
  passed/8 个 PyMOL 环境测试按预期 skipped、strict mypy、ruff 和 dev10 wheel/
  console-script/package-data 验证通过；localhost 服务启动 smoke 通过。
- 遇到的问题：服务器没有 pnpm，且根分区 pip cache 空间不足；科学结构文件中的合法
  固定宽度尾随空格也会触发通用文本 diff 检查。
- 解决办法：使用仓库锁定依赖配合本机 Node/pnpm 构建前端，在
  `/root/autodl-tmp/easydesign-build-cache` 完成 wheel 缓存；evidence-runs 以 exact-byte
  Git 属性保存并通过 bundle SHA-256 审计，不修改不可变结构文件。
- 遗留边界：该包不能恢复 BoltzGen 任务或重算筛选；历史配置保留服务器 provenance
  路径；APOE 私有资产只获准在当前仓库与合作者共享，公开 release 前必须重新审查。
- 提交：`980a8eae30e79e4ba0a59bab105f6da6beb1d48f`
  （`feat(reporting): share verified APOE UI evidence`）。

## 2026-07-27 — ENG-013：SSH whole-run 远程执行

- 状态：`smoke-validated`；APOE 50k 科学运行本身继续由 `S06-002` 在 Now 跟踪。
- 完成时间：2026-07-27T11:40:31+08:00
- 问题：Stage 04–06 只能在控制端本机运行；手工 SSH 复制 YAML 会丢失 source manifest、
  配置身份、systemd 持久性和 Stage 06 恢复证据。Continuation preflight 还会错误要求
  已完成 Stage 01/05 的 PyMOL 与 Protenix。
- 方案：建立 runtime-profile 驱动的 whole-run SSH control plane，严格验证 dedicated
  identity、known-host、EasyDesign 版本、GPU、磁盘、source RunManifest 和配置 hash，
  rsync 完整 continuation source 后由远端 systemd worker 调用同一 local multi-GPU
  executor；preflight 从 source 的最高连续 Stage 计算真正后续 backend。
- 验证证据：Suzhou2 报告 8×A100、约 6.5 TiB 可用空间、EasyDesign
  `0.1.0.dev11`、BoltzGen `0.3.2` 和固定 commit
  `a3149cf18eeb58648d1abbb27539bd73f746cdda`。真实 unit
  `easydesign-apoe-tier-a-50k-20260727` 为 `active/running`，首批八个 shard 分别在
  GPU 0–7 达到约 95–97% utilization，并开始产生设计文件。
- 遇到的问题：提交前 GPU 0 短暂存在两条 BindCraft；远端只配置 BoltzGen 时又暴露了
  continuation preflight 过度探测旧 Stage backend 的缺陷。
- 解决办法：未终止既有任务，等待八卡真正空闲后再通过资源门；将后端需求按
  `start_stage..stop_after_stage` 求交，只在 Stage 06 continuation 探测 BoltzGen。
- 遗留边界：SSH 首版依赖 OpenSSH、rsync 与 systemd，尚未实现 Slurm/SMART 或单 run
  跨节点；远端 50k 未完成前不能宣称 Stage 06 succeeded 或生成 ScaleBundle。
- 提交：
  `23c91988d5c623d08e1fb35e621b837f2d8c6503`
  （SSH executor 与人工 scale authority）；
  `f3562aef74b9d34a451db93cae92f4e3c879ec02`
  （continuation backend preflight）。

## 2026-07-27 — ENG-014 / UI-008：远程协作查看、同步与恢复

- 状态：`smoke-validated`；Stage 06 科学生成仍由 `S06-002` 在 Now 跟踪。
- 完成时间：2026-07-27T12:53:23+08:00
- 问题：首版 SSH 只能提交和查 systemd 状态，不能连续读取科学进度、同步结果或从 UI
  选择执行位置；旧 worker 长任务期间也没有结构化存活心跳。
- 方案：增加版本化 job record、远端 watch/resume、manifest 驱动的 metadata/complete
  rsync 和 task heartbeat；Workbench 通过 localhost API 选择远端、查看状态、同步镜像
  和恢复，不向浏览器暴露 SSH 配置。
- 验证：真实 Suzhou2 任务读取到 `active/running`、8 running/12 pending；控制端同步
  246 文件和 59,263,753 bytes 并验证 RunManifest SHA-256。全仓 249 passed/8 skipped，
  wheel 检查通过，Chromium 双尺寸 18/18 通过。
- 遇到的问题：当前 50k 由 dev11 启动，无法安全热替换为带 heartbeat 的进程；服务器
  Playwright 默认查找了未安装的 1234 浏览器 revision。
- 解决：不停止、不附加和不改写旧 worker；dev12 对旧 ProgressSnapshot 向后兼容，新
  任务/合法 resume 才记录 heartbeat。浏览器验收使用服务器已安装的固定 Chromium
  revision 1228，不下载临时浏览器。
- 遗留边界：当前 metadata 镜像只用于协作查看；50k 终态后再执行 complete 同步和候选
  闭包验收。SSH 首版仍要求 OpenSSH、rsync、systemd，Slurm/SMART 保留后续。
- 实现提交：`1e3c4ae7742919cca5f909200d8ffa7bad7813d5`。

## 2026-07-27 — UI-009 / ENG-015 / ENG-016 / REP-004 / S02-009 / VAL-004

- 状态：`smoke-validated`；真实后端微型自检继续由 `VAL-005` 跟踪。
- 完成时间：2026-07-27T19:21:46+08:00
- 完成内容：普通项目目录只保留 `apoe-s02-006-pse` 与 `apoe-fasta`；17 个非主项目
  进入可恢复归档。全流程、按步骤和开发者自检三条路线完成；Stage 02 交互式区域编辑
  可建立不可变 continuation 分支。
- APOE FASTA 证据：
  `runs/apoe-fasta/20260727-002-stage01-protenix` 真实消费 143 aa FASTA、609-depth
  A3M（SHA-256 `12d913001bd955c05544b084f396f6b17bc0086ae69cfca5cd376ab722f72716`）
  和 Protenix-v2 2.0.0，发布 Target Bundle 0.4 与 Viewer。
- APOE PSE 证据：
  `runs/apoe-s02-006-pse/20260727-003-stage02-reselection-lineage` 保存 A/B/C
  `9/14/14` 的 `manual-residue-list`，RunManifest revision 3 停在
  `awaiting-human-approval`；DesignSession 记录稳定 run key
  `c63204b57808e88a26efb0cf`。
- Mol* 证据：真实 APOE FASTA 与 PSE 页面均建立 structure/representation 和相机取景；
  FASTA 页面非背景像素比例约 5.2%，PSE 页面显示来源红蓝黄与独立编辑层，不再把空
  canvas 误报为就绪。
- 自检证据：`selftest-20260727t104835z-f73dfb` 在
  `runs/_selftests/selftest-20260727t104835z-f73dfb/synthetic-7b3b6c1c7288`
  确定性完成 Stage 01–07，并通过 `developer-smoke-run` 分类从普通项目隔离。
- 遇到的问题：Stage 01 决策恢复丢失 precomputed MSA；legacy-0 归档没有 manifest；
  Mol* WASM data URL 被 CSP 阻止；Stage 01-only run 默认误跳 Stage 05；continuation
  引用旧项目相对输入；UI 深链接依赖先访问项目列表；worker 未写回 session lineage。
- 解决办法：恢复 resolved config 中的 precomputed MSA；legacy run 使用字节级清单保持
  可恢复；CSP 明确允许 self/data/blob；运行页默认选择最高已达 Stage；冻结输入按
  SHA-256 原子复制并重写相对路径；服务启动注册 run-index；worker 写回 run key、stage
  和终态。
- 验证：真实 run `runs show` 完整性通过；源 APOE 审计 run 的 `LATEST` 保持
  `run-manifest.v0004.json`；全仓 259 passed、8 个显式 PyMOL 环境集成测试按预期
  skipped；Workbench Chromium 双尺寸 26/26，Target Viewer 3 passed/2 skipped；
  dev13 wheel、console script 与 package data 校验通过。
- 遗留边界：真实后端微型自检尚未执行；交互区域是用户证据，不等于科学验证；新的
  Stage 02 分支在人工批准前不能进入 Stage 03。
- 提交：初始实现为 `e7c21ded2de4a12f4e23f1c4f3b9bb63ba4d4bcd`；
  MSA 决策恢复为 `f82e315757b70c7053a473865646e19dbe9d616f`；
  legacy 归档为 `d8b281fe67599193ff24fd23232a0b1e523b9379`；最终运行修复与文档
  为 `627b36dbd7d67662eb6b5ea080cebc069417ff1d`；本记录文档 SHA 以所在提交
  和远端 `main` 为准。

## 2026-07-27 — UI-010：显式选择项目主展示运行

- 状态：`smoke-validated`。
- 完成时间：2026-07-27T20:56:19+08:00
- 问题：项目卡片原先永远选择最近更新的 run，导致 APOE PSE 新建的 Stage 02 重选
  分支覆盖了已经完成 Stage 01–05 的主要结果；简单改成“自动选择阶段最深”又会错误
  改变其他项目的展示规则。
- 方案：在可再生 `run-index.json` 中增加项目级唯一
  `is_project_primary`，通过 `projects select-primary` 显式选择。首页只对该项目采用
  指定 run；所有其他项目、历史分支、远程运行和科学文件保持原状。
- 验证：契约测试证明较新的同项目分支仍位于历史列表首位，但首页继续展示显式指定的
  较早 run；同时证明选择一个项目不会改变另一项目的主展示设置。Proteindigger1
  真实索引指定 `apoe-s02-006-pse/20260726-004-stage05-pilot-filter` 后，API 返回
  Stage 01–04 `succeeded`、Stage 05 `scientific-stop`，而 `apoe-fasta` 仍展示
  `20260727-002-stage01-protenix`。
- 遇到的问题：项目首页的旧字段名是 `latest_run`，但产品语义已经是“首页主展示
  运行”。
- 解决办法：保留旧 API 字段以避免前端和证据包兼容性中断；选择逻辑只在后端投影层
  读取显式索引标记，未标记项目保持原先最近运行行为。
- 遗留边界：当前通过 CLI 选择；未来如需让普通用户切换，可在“历史运行”页面为同一
  API 增加“设为项目首页”按钮。
- 实现提交：本记录对应的 `fix(ui): pin the APOE PSE stage05 project result`；完整 SHA
  在推送后由远端 `main` 核对。

## 2026-07-28 — ENG-017：统一 Run 目录与同 Run 阶段延续

- 状态：`smoke-validated`。
- 完成时间：2026-07-28T00:31:59+08:00
- 问题：旧产品 continuation 会为每个下一 Stage 新建 run，并复制全部上游目录；run
  初始化又提前创建七个 Stage 空目录。这使一次实验被拆成多个 checkpoint run、重复占用
  磁盘，也让 `runs/` 顶层残留 17 个已归档项目空壳。
- 方案：新增 `docs/architecture/RUN_LAYOUT.md`，固定 Project/Run/Stage/Attempt 与
  branch 语义。正常下一 Stage 通过新的 config/RunManifest revision 继续同一 run；
  重新选区、换 target 或改写已完成 Stage 才建立分支。Stage 目录改为首次执行时惰性
  创建；`PROJECT.json`/`PRIMARY` 作为可再生导航，manifest 继续是科学事实来源。
- 安全边界：成功终态的旧 RunManifest 不被修改，新 revision 保存前驱 hash、新配置、
  新代码/profile 身份；同 run 续跑会拒绝输入 hash 或已完成 Stage 配置变化。历史
  Stage 02/03/04 checkpoint runs 暂不合并或重写，后续由 ENG-018 先做逐 run 依赖报告。
- 真实目录治理：Proteindigger1 为两个 APOE 项目生成项目导航并固定主 run；只删除
  run-index 已确认归档且内容为空的 17 个一级项目壳。APOE PSE 原文件仍为 397,738
  bytes，SHA-256 仍是
  `7d382a2fd158bd4664ef3d17296591e380ff01232926ed5bc86a9bcd7a813651`；
  Stage 05 主 run 的 Stage 01 `target.cif` 仍存在。
- 验证：`make check` 通过；全仓 263 passed、8 个独立 PyMOL 环境集成测试按设计
  skipped；新增 30 项定向契约回归通过；dev14 wheel、console script/package data
  通过。Target Viewer 3 passed/2 个真实可选案例 skipped；Workbench 固定 Chromium
  双尺寸 26/26 passed。
- 遇到的问题：Proteindigger1 默认 shell 的 Node 18 不能执行 pnpm 11，且首次给
  Playwright 的 Chromium 路径使用了旧 `chrome-linux` 目录名。
- 解决办法：显式使用 `easydesign-reporting-web` 的 Node 22、固定 pnpm 和服务器已安装
  的 `chromium-1228/chrome-linux64/chrome`，不下载临时浏览器或改变科学环境。
- 遗留问题：dev14 之前的 checkpoint runs 保持可读；逐 run 可恢复归档和内容寻址去重
  分别进入 ENG-018 与后续 ADR，不在本次偷偷移动仍可能被引用的历史证据。
- 实现提交：`ef8847ad47c1eb593f42a071b36722a3740a957f`
  （`refactor(core): unify staged run layout`）。

## 2026-07-28 — UI-011 / ENG-019：按步骤 Stage 01 单页运行

- 状态：`smoke-validated`。
- 完成时间：2026-07-28T00:58:17+08:00
- 问题：浏览器在发送上传请求前先用 `FileReader` 为整个文件生成 Base64；用户选择
  APOE PSE 后请求没有到达 localhost gateway，界面又没有超时，因而永久停在“正在接收
  文件”。按步骤设计还错误复用全流程的第5项启动页，让用户手动经历草稿、环境检查和
  真实启动三层工程操作。
- 方案：新增 64 MiB 有界的原始字节流上传接口，边接收边计算 SHA-256，浏览器设置
  120 秒超时并保证成功/失败终态。按步骤 PSE receipt 成功后，在同一页面依次执行配置
  生成、preflight、Stage 01 job 和结构化状态轮询；完成后凭 `run_key` 直接进入第1步
  结构审查。全流程设计的显式第5项保持不变。
- 工程修复：localhost job 现在使用 UI 实际配置的 `runs_root`，并携带 session ID 与
  Stage 编号；worker 成功后把 run key 写入 DesignSession lineage。旧 JSON/Base64
  上传端点只为兼容保留，新的 Workbench 不再调用。
- 真实验证：`runs/_validation/ui011-pC8Ldb` 对 397,738-byte `apoe_abc.pse`
  （SHA-256
  `7d382a2fd158bd4664ef3d17296591e380ff01232926ed5bc86a9bcd7a813651`）
  完成 raw receipt、doctor 和 Stage 01；run
  `ui011-pse-smoke/20260727t165230z` 为 `succeeded`，目标 138 aa，Stage 01 发布
  15 个工作台可见正式输出。DesignSession 为 `succeeded`，lineage 包含 run key
  `74f21b1f3766a30e9df0e4e1`。
- 自动验证：`make check` 通过；全仓 264 passed、8 个独立 PyMOL 集成测试按配置
  skipped；Workbench Chromium 1440×900 与 1920×1080 共 26/26 passed；
  Target Viewer 3 passed/2 个真实可选案例 skipped；dev15 wheel、console script 和
  package data 校验通过。
- 遇到的问题：真实验收使用独立 runs root 时暴露出 UI job 没有把配置的 runs root
  传给 worker、且首次启动没有写回 DesignSession 的旧缺口。
- 解决办法：LaunchRequest 增加成对校验的 session/stage 身份，job controller 显式
  接收 registry runs root；新增单 job 查询接口供前端轮询，不扫描目录或解析终端文本。
- 遗留边界：PSE 等低成本本地导入可自动执行；FASTA/序列等可能触发预测的入口仍需在
  同一页面点击“开始准备结构”。本轮不改变任何 Stage 01 科学契约或 APOE 主项目结果。
- 实现提交：`df4d81167950a54c04ddd218eb2baf9536eb2921`
  （`fix(ui): streamline stepwise target preparation`）。
