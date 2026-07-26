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
- 验证证据：Python UI unit、ruff、mypy、TypeScript/Vite build 和 Chromium 1440
  产品测试通过；1440 项目页和第5步页面形成稳定视觉基线。最终 Python 3.11 全量测试、
  wheel、双尺寸/多浏览器和 Proteindigger1 真实 APOE 投影证据记录在本任务交付。
- 科学边界：没有改变 Stage 05 阈值、APOE `stopped-no-scale-winner`、Stage 06/07
  `not-reached` 或任何历史 manifest；VAL-003 继续作为独立受控实验。
- 遗留问题：UI-002 仍需在一条可继续的真实运行上验证完整启动、确认、停止调度和恢复；
  REP-002 overlay、第二真实案例、Windows shell 和正式公网/多人系统仍未完成。
- 提交：数据投影
  `66e8fb630c02652801cb44d31c9d826a6973ad6d`；界面、验证和文档提交以远端 `main`
  最终核对 SHA 为准。
