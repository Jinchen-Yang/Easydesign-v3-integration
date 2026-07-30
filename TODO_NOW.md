# EasyDesign 当前工作

## 七阶段实时摘要

下表由各 Stage `STATUS.md` 的“顶层摘要”自动生成；详细证据和任务仍以对应 STATUS 为准。

<!-- BEGIN AUTO-GENERATED STAGE ROLLUP -->
| Stage | 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新 | 详情 |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 01 | `smoke-validated` | 六类入口与 Target Bundle 0.4 已通过真实 APOE；Workbench 浏览器 PyMOL 严格首帧状态机已在 dev25 复验 138-aa 结构和 9/14/14 来源区域。 | 冻结 Stage 01 科学边界；在第二真实案例继续验证双查看器。 | 无 Stage 01 1.0 工程阻塞；PyMOL、Mol* 与便携报告均可用。 | 2026-07-30 | [STATUS](workflow/01-target-preparation/STATUS.md) |
| Stage 02 | `planned` | automatic、PSE/YAML、交互选区与自然语言明确残基操作共享人工批准交接；运行链递进冻结及查看器中立区域显示已通过真实 APOE 页面复验。 | 推进区域科学 benchmark 和 REP-002 独立 overlay。 | Stage 03 handoff 无工程阻塞；GPU、外部证据和 VHH–抗原科学验证仍是后续工作。 | 2026-07-30 | [STATUS](workflow/02-hotspot-discovery/STATUS.md) |
| Stage 03 | `smoke-validated` | S03-001 已完成通用基础编译器；APOE 3×7 共 21 个 YAML 全部通过固定 BoltzGen 0.3.2 官方校验。 | 冻结 1.0 基础模板，把开发重心移交 Stage 04 可恢复 pilot generation。 | 无 Stage 03 工程阻塞。 | 2026-07-26 | [STATUS](workflow/03-boltzgen-configuration/STATUS.md) |
| Stage 04 | `smoke-validated` | APOE 21×40 共 840 个完整候选已由双 GPU 可恢复执行器收集，RunManifest 与全部交接产物完整性验证通过。 | 冻结 Stage 04 交接，把 840 个候选交给 Stage 05 v1.5 逐规则筛选。 | 无 Stage 04 工程阻塞；科学通过率由 Stage 05 判定。 | 2026-07-26 | [STATUS](workflow/04-pilot-generation/STATUS.md) |
| Stage 05 | `smoke-validated` | APOE 840 个 pilot 已完成 v1.5 审计；唯一 Tier A 扩展到 100 后，10/10 full-target Protenix 因 binder pose 不稳定而合法停止。 | 冻结 `stopped-no-scale-winner` 负结果，不启动本轮 APOE Stage 06/07。 | 无 operational failure；APOE 本轮没有通过科学规模化门。 | 2026-07-26 | [STATUS](workflow/05-pilot-filtering/STATUS.md) |
| Stage 06 | `implemented` | S06-003 已补齐远程 watch、心跳、恢复、manifest 同步和 UI 服务器选择；APOE 50k 继续运行。 | 跟踪 Suzhou2 20×2500，并用控制端只读镜像让合作者查看相同运行记录。 | 无代码阻塞；当前 dev11 worker 没有心跳字段，新提交/恢复的 dev12 任务才产生心跳。 | 2026-07-27 | [STATUS](workflow/06-scale-generation-and-refolding/STATUS.md) |
| Stage 07 | `implemented` | S07-001 已实现 v1.5 预筛、Protenix 三 seed、一致性、TNP 证据和确定性主备候选包，固定 TNP batch smoke 已通过。 | 保持通用能力冻结；APOE 在 Stage 05 科学停止，本轮不生成 Stage 07 候选包。 | 无代码阻塞；APOE 没有合法 Stage 06 ScaleBundle，50k 未授权。 | 2026-07-26 | [STATUS](workflow/07-final-filtering-and-selection/STATUS.md) |
<!-- END AUTO-GENERATED STAGE ROLLUP -->

## Now

- `[ENG-024]` 将 ENG-023 已验证提交链收敛到唯一 `main`，禁止继续创建任何开发分支或
  Git worktree。现有 `easydesign-eng023/runtime` 作为只读迁移来源完整保留；正式环境
  与模型必须落在稳定的 `easydesign-clean/runtime`，不得直接移动带绝对 prefix 的
  Conda 环境。
- `[ENG-023/UX-006]` 在 Proteindigger 的全新 clone 验证仓库内
  `runtime/profile.yaml`、setup 恢复、doctor 和一条命令 UI。当前锁的 core/web 已从
  仓库内 lock 重建；dev22 增加 `--component` 逐后端计划与安装，PyMOL 3.1.0 已在
  `runtime/envs/` 真实重建并通过探针，BoltzGen 0.3.2 环境也已通过当前 lock 探针；
  Protenix 当前 lock 正在按独立计划恢复。
  dev23 将远程长时安装统一为 `setup --detach` 持久任务；CLI 与 UI 共享不可变
  request/process/result，SSH 或浏览器断开不再中断安装或丢失终态。网络异常时允许
  为单个任务显式指定经过审计的 HTTPS pip 源，并把选择写入请求；禁止修改全局代理或
  自动切换镜像。
  `doctor --full` 继续把未就绪科学后端逐项判为失败。不得修改 base Conda、系统代理、
  Git 全局配置、shell profile 或仓库外用户数据。
- `[DATA-005]` 已完成七环境解析后的 linux-64 Conda/pip lock 与十五项资产来源、大小、
  SHA-256 和许可门；继续完成用户逐项确认后的下载发布验收。待许可必须保留
  `awaiting-approval`，不能静默跳过或把“环境可导入”报告成“完整后端可运行”。
- `[UI-016/VAL-006]` 完成安装中心浏览器验收，并在许可资产和后端就绪后逐步真实运行
  固定非 APOE 1UBQ 自检。Stage 05 科学停止允许；后端失败和科学停止必须分开显示。

- `[S06-002]` APOE 唯一已扩展 Tier A 已获探索性 `production-50000` 人工授权；保持
  Stage 05 `stopped-no-scale-winner` 不变；Suzhou2 首批 8 个 2500-candidate shard
  已在 8×A100 运行。`ENG-014/S06-003/UI-008` 已提供远程 watch、校验镜像、恢复与
  UI 服务器选择；继续跟踪 20 个分片直到完成或形成可恢复的 operational failure 证据。

## Next

- `[DATA-005]` 继续按 PyMOL、BoltzGen、Protenix、ScanNet、TNP 顺序逐组件验证解析锁；
  每次只按本组件环境、必需资产与最大单资产 staging 计算峰值，并在完成后读取真实剩余
  空间。完整全量计划仍保留自己的磁盘门；不得通过删除旧环境、缓存或运行规避门槛。
- `[UX-006]` 在 macOS/Windows 验证 core/UI minimal setup，并通过显式 SSH executor
  使用 Linux 科学后端；不得在桌面平台伪装重型后端可用。
- `[UI-015/ENG-021]` dev20 已完成连续七阶段工作区：Stage 02 不再覆盖式弹窗；
  Stage 03 显示真实 `3×7=21` 方案、每方案 40 和 840 候选预算；统一任务成功后定位
  下一 Stage。按步骤续跑现依据连续成功的 Stage 前缀，不再错误要求开放中的整个 run
  已终态成功；后续只在第二真实案例和真实长任务中继续做产品验收。
- `[ENG-018]` 对 `apoe-s02-006-pse` 中 dev14 之前的 Stage 02/03/04 checkpoint runs
  生成逐 run 依赖报告；只对终态、未被远程任务引用且 manifest 闭包完整的冗余 checkpoint
  提供可恢复单 run 归档。历史科学文件不合并、不重写；内容寻址去重另立 ADR。
- `[VAL-005]` 快速确定性七步自检已实现并与科研项目隔离；真实后端微型自检还必须使用
  固定非 APOE fixture 完成 Stage 01–05，并为 Stage 06/07 建立真实 adapter probe。
  当前“准备真实后端自检”只创建 `not-started` 记录，不能被报告为通过。
- `[UI-009/ENG-015/ENG-016/REP-004/S02-009/VAL-004]` 已完成 dev13 真实验收：
  普通项目只保留两个 APOE 主案例，FASTA 真实 Protenix Stage 01、PSE 交互选区新分支、
  DesignSession lineage、Mol* 可见结构和确定性七步自检均有运行证据。后续只处理新发现
  的回归，不再作为 Now 中的开发任务。
- `[UI-014/ENG-020/S02-009]` dev19 已修复 Stage 02 continuation 与人工提交反馈：
  两条路线只继承 checksum 正确的 Stage 01 成功前缀；批准人或证据限制确认缺失时逐项
  高亮并聚焦，条件满足后显示真实 job 进度，终态自动打开新分支。Mol* 与序列同区再次
  点击均可取消。
- `[VAL-003]` 冻结当前 APOE 负结果，对相同候选、相同 MSA 和 seeds 101/202/303
  比较 no-template、target-template、target-template+hotspot constraint，并加入已知
  VHH–抗原正对照；未形成新 profile/ADR 前不得改变 Stage 05 默认 gate。
- `[UI-002]` 在下一条可继续的真实 run 上验收浏览器中的 doctor、启动、hotspot
  审批、drain 和 resume；当前 API/界面已实现，但不以只读 APOE scientific-stop
  冒充长任务交互 smoke。
- `[VAL-001]` 选择第二条独立真实 target，复用 frozen 1.0 主线；APOE 的
  binder-pose gate 只能通过预注册 benchmark 和新版本 profile 研究，不能事后调参。
- `[S06-001]` 通用 1000 smoke / 50000 production plan、25% 磁盘门、共享恢复和精确
  merge 已实现；正常主线仍要求 Stage 05 winner，人工 override 只用于明确记录的探索性
  运行。
- `[S07-001]` 通用深度筛选、Protenix 三 seed、TNP 和多样性候选包已实现，固定 TNP
  backend 单候选真实 smoke 已通过；APOE 因 Stage 05 科学停止而不会进入本轮 Stage 07。
- `[S05/S06/S07]` 分别接入 pilot go/no-go、高成本预算和 Top N 候选包 gate；
  `required_reviews: [biosafety]` 不能被 unattended 绕过，真实下单始终是人工动作。
- `[REP-002]` 在不改变 Stage 02 科学输出的前提下增加 SASA/ScanNet 独立 overlay；
  可视化层不得融合 PSE、SASA 和 ScanNet。
- `[REP-006/ENG-025/UI-017]` 离线浏览器 PyMOL、Mol* 和安全结构助手已通过真实 APOE
  Stage 01/02 smoke；下一步在带本机 Chromium/Edge 的环境补齐自动双尺寸与触摸矩阵，
  并在用户显式提供 API key 后分别验证 DeepSeek/智谱 GLM 连通。未配置模型不阻塞无
  Agent 的 Stage 01/02 主线。
- `[ENG-003]` 部署自建 ColabFold/MMseqs2，并建立 CI 平台矩阵；sequence-hash cache
  与 precomputed A3M 已由 S01-009 完成。
- `[S02]` 将 ScanNet GPU 兼容性和性能优化作为后续 benchmark，不改变 CPU 主线。

## Blocked

- `[DATA-005/VAL-006]` Protenix、BoltzGen、ScanNet 和验证 fixture 的受控资产在
  用户逐项确认相应许可前保持 `awaiting-approval`；真实后端逐步自检不能在资产缺失时
  标记通过。完整全量 setup 仍可能因峰值与安全余量拒绝，但逐后端安装已经开始且
  PyMOL 当前 lock 已可用；模型和数据资产仍等待精确许可确认。系统盘空间仍紧张，
  EasyDesign 不清理系统文件；环境、模型、缓存、临时文件和构建缓存均必须写入数据盘
  当前仓库的 `runtime/`。
- `[S01]` 默认 ColabFold endpoint 已成功验证，但公共服务没有 EasyDesign 可承诺的
  SLA；remote、显式 offline cache、precomputed A3M、真实 APOE run 和 Stage 02
  交接均已完成。Protenix 官方 endpoint 持续 `PENDING`，不进入
  默认 fallback；公共 endpoint 只批准内部研究序列，商业/敏感序列等待隐私、服务条款和
  自建 provider 审查。旧 SMART cache 缺失只影响历史复现。
- `[S02]` GPU 优化：TensorFlow 1.14 GPU probe 通过，但官方 1BRS 与 APOE 在 RTX 4080
  报 cuBLAS GEMM execution failure；这是后续性能待办，不阻塞 CPU 主线。
- `[REL-001]` 公开许可证、PyPI 和正式 release 等待 IP/release 决策。
- `[DATA-001]` 第三方 VHH scaffold 迁移等待来源与权利审查。

## 历史索引

- [2026-07 项目历史](docs/history/2026-07/TODO_NOW.md)

阶段内部历史从对应 `workflow/<stage>/STATUS.md` 进入。历史不得改写；原记录有误时追加更正。
任何事项从 `Now` 移出前，必须在对应 history 写入带 UTC offset 的 RFC 3339 秒级
`完成时间`；该规则由 `make check` 自动校验。
