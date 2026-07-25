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
