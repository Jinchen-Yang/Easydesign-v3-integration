# EasyDesign 当前工作

## 七阶段实时摘要

下表由各 Stage `STATUS.md` 的“顶层摘要”自动生成；详细证据和任务仍以对应 STATUS 为准。

<!-- BEGIN AUTO-GENERATED STAGE ROLLUP -->
| Stage | 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新 | 详情 |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 01 | `smoke-validated` | 六类入口与 Target Bundle 0.4 已通过真实 APOE；REP-009 已把结构助手重构为完整 PML/Skill/SceneVersion 主循环，历史 typed 记录只读兼容。 | 冻结 Stage 01 科学边界；复验真实 provider 连续对话和双查看器投影。 | 无 Stage 01 1.0 工程阻塞；REP-009 的 live provider 浏览器矩阵待完成。 | 2026-07-31 | [STATUS](workflow/01-target-preparation/STATUS.md) |
| Stage 02 | `planned` | automatic、PSE/YAML、交互选区共享人工批准交接；REP-009 已用完整 PML `ed_region_A/B/C` 桥接替代模型 typed 区域协议。 | 复验完整 PML 区域往返，同时推进科学 benchmark 和 REP-002 独立 overlay。 | Stage 03 handoff 无工程阻塞；GPU、外部证据和 VHH–抗原科学验证仍是后续工作。 | 2026-07-31 | [STATUS](workflow/02-hotspot-discovery/STATUS.md) |
| Stage 03 | `smoke-validated` | S03-001 已完成通用基础编译器；APOE 3×7 共 21 个 YAML 全部通过固定 BoltzGen 0.3.2 官方校验。 | 冻结 1.0 基础模板，把开发重心移交 Stage 04 可恢复 pilot generation。 | 无 Stage 03 工程阻塞。 | 2026-07-26 | [STATUS](workflow/03-boltzgen-configuration/STATUS.md) |
| Stage 04 | `smoke-validated` | APOE 21×40 真实生成保持通过；dev32 已实现本机自动 GPU 租约与 Suzhou2 受管中央队列。 | 完成 VAL-008 的本机极小任务和 Suzhou2 极小 Stage 04 真实探针。 | 新受管执行尚未在 Suzhou2 完成真实 worker/GPU 验收；旧 APOE 证据不受影响。 | 2026-08-01 | [STATUS](workflow/04-pilot-generation/STATUS.md) |
| Stage 05 | `smoke-validated` | v1.5 APOE 结论保持冻结；v1.6 晋级与诊断 warning 保持不变，Stage 04→05 已支持 Suzhou2 原地连续。 | 在第二真实案例验证 2–3 个 Tier A 晋级；启动 VAL-003 受控 full-target benchmark。 | Suzhou2 新 worker 真实 Stage 04→05 极小任务待 VAL-008。 | 2026-08-01 | [STATUS](workflow/05-pilot-filtering/STATUS.md) |
| Stage 06 | `smoke-validated` | APOE 历史单策略 50k 证据保持；dev32 已实现本机自动 GPU 租约、Suzhou2 受管分片与 6→7 原地执行。 | 在 Suzhou2 完成 Stage 06 单 shard 真实探针和 Stage 07 adapter probe。 | 新 worker 真实探针尚未执行；旧 50k 不重跑。 | 2026-08-01 | [STATUS](workflow/06-scale-generation-and-refolding/STATUS.md) |
| Stage 07 | `implemented` | S07-002 多策略筛选保持；dev32 已将受管 Stage 06→07 原地运行与 review 同步固化为执行契约。 | 完成 Suzhou2 Stage 07 后端 probe，再对已验证历史 50k 原地运行。 | Suzhou2 缺少 Protenix/TNP 登记，GPU 当前全部繁忙。 | 2026-08-01 | [STATUS](workflow/07-final-filtering-and-selection/STATUS.md) |
<!-- END AUTO-GENERATED STAGE ROLLUP -->

## Now

- `[VAL-008]` 在审核 Suzhou2 systemd unit 和专用 SSH 配对后，完成本机极小
  Stage 04、Suzhou2 极小 Stage 04 及 Stage 06 单 shard 真实探针；Stage 04→05、
  Stage 06→07 必须原地连续，不重跑或改写历史 APOE 50k。

- `[REP-009]` 已将 Stage 01/02 新结构助手从 typed proposal 混合协议重构为 ChatPyMol
  原生完整 PML 主循环：`safe-pml + 最多两个动态 Skill + 当前完整 PML + metadata +
  最近十轮对话` 进入平台模型，四字段完整 PML 返回后形成不可变 SceneVersion；Mol*
  只作兼容投影，Stage 02 区域仍须确定性映射和人工批准。dev31 已修复未限定数字误按
  author 解释、助手文字与草稿脱节、全局灰色覆盖 A/B/C 以及原生 `deselect` 循环创建版本。
  真实平台 provider 已将规范编号 32–36 准确写入 A 区，APOE 9/14/14 恢复、空闲不增版本
  及多次 PyMOL/Mol* 切换均通过；下一门槛是第二真实 target 和 Edge/触摸矩阵。
- `[VAL-007/S07-002]` APOE v1.6 policy reevaluation 与 Suzhou2 50,000-candidate
  evidence adoption 已发布：旧 v1.5 bundle、manifest 和
  `stopped-no-scale-winner` 保持不可变；新投影显示 Stage 05 一组 Tier A 晋级与
  Stage 06 20/20 分片、50,000/50,000 完成。当前工作转为 Suzhou2 的
  Protenix/TNP/模型探针和 Stage 07 原地运行。
- `[REP-008]` 修复协作引入的浏览器 PyMOL 生命周期回归：同页 pane 持续挂载，但每个
  新 PyMOL canvas 使用独立 Pyodide/PyMOL 运行时，禁止把绑定旧 Emscripten WebGL
  context 的全局运行时改绑到新 canvas；显示 revision 不重建结构，framebuffer 只作
  诊断。真实 APOE 已完成 Stage 01、Stage 02、`PyMOL → Mol* → PyMOL` 与跨 Stage
  往返，结构和 9/14/14 区域均保持可见。
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

- `[S06-002]` APOE 唯一已扩展 Tier A 的探索性 `production-50000` 已在 Suzhou2
  完成 20 个 2500-candidate shard 和 50,000 候选。源运行仍属于 v1.5 科学停止后的
  manual override；v1.6 只通过独立采用记录引用，未改写源运行。

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
- `[S06-004]` 在第二条独立真实案例验证 2–3 个 Tier A 的共享总预算、尾部分片、恢复、
  全局无重复和无缺口；50,000 是全部晋级策略共享总数，不能解释成每组 50,000。
- `[S07-002]` 在 Suzhou2 完成远程 Protenix/TNP 与模型 probe 后，原地消费已经通过
  VAL-007 采用记录授权的 50,000 候选并运行全局 Stage 07；本地只同步 manifest、
  进度和最终候选证据。
- `[S05/S06/S07]` 分别接入 pilot go/no-go、高成本预算和 Top N 候选包 gate；
  `required_reviews: [biosafety]` 不能被 unattended 绕过，真实下单始终是人工动作。
- `[REP-002]` 在不改变 Stage 02 科学输出的前提下增加 SASA/ScanNet 独立 overlay；
  可视化层不得融合 PSE、SASA 和 ScanNet。
- `[REP-006/REP-008/REP-009/ENG-028/UI-017/UI-020]` 离线浏览器 PyMOL、Mol* 与平台结构助手
  已通过 dev28 真实 APOE Stage 01/02 多轮 smoke；`PyMOL → Mol* → PyMOL` 不再丢失
  WASM 画布或因空 framebuffer 误报失败。REP-009 已把后续新会话迁移为完整 PML
  SceneVersion，旧 typed/ViewState 记录只读兼容。普通使用者不选择 provider 或填写
  API key；下一步由部署者补充受控 live 连通、连续多轮、预算、限流和用量监控，平台
  助手未启用不阻塞无 Agent 的 Stage 01/02 主线。
- `[ENG-003]` 部署自建 ColabFold/MMseqs2，并建立 CI 平台矩阵；sequence-hash cache
  与 precomputed A3M 已由 S01-009 完成。
- `[S02]` 将 ScanNet GPU 兼容性和性能优化作为后续 benchmark，不改变 CPU 主线。

## Blocked

- `[VAL-007]` Suzhou2 当前没有已登记可用的 Protenix/TNP 环境和模型资产，且 8 张 GPU
  正被其他任务占用。Stage 07 真实运行必须等待资源自然释放并完成显式后端探针；禁止
  终止非 EasyDesign 进程或把缺失环境报告为科学停止。
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
