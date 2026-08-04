# 2026-08 项目历史

本文件归档跨阶段工作；各 Stage 的详细证据仍以对应
`workflow/*/history/2026-08.md` 为准。

## 2026-08-01 — ENG-030 / ENG-031 / UX-008 / UI-022：双执行与 Suzhou2 统一队列

- 状态：`implemented`。
- 完成时间：2026-08-01T03:39:51+08:00
- 问题：Stage 04/06 既要在当前 GPU 机器自动分配，又要使已获授权的无本地算力用户通过 Suzhou2 运行；旧 SSH 路径缺少统一队列、一卡一租约和大数据原地交接。
- 方案：引入非科学 `ExecutionTarget`、本机 GPU 发现/租约、Suzhou2 `RemoteJobBundle`/Managed Worker、独立 SSH key 与 host fingerprint 配对、逻辑解绑、结构化观察及 metadata/review/complete 同步。
- 安全边界：新 worker 只能写 `/data/easydesign/managed-worker`；旧 `/data/easydesign`、APOE 50k、旧环境和 `/root/Easydesign/Easycontrol` 均保持原样。本任务没有执行删除、移动、覆盖、进程终止或系统代理修改。
- 验证：386 passed/8 skipped；Ruff 通过；149 个源文件 mypy 通过；Workbench 非视觉 60/60；Target Viewer 3 passed/2 skipped；dev32 wheel SHA-256 `50a9a1369ddce8106fbbec3cda7e51b4407493403b83e518a6d89f207480855b` 且资产/console script smoke 通过。
- 遗留边界：本轮达到工程 `implemented`，不伪装 Suzhou2 已部署。`VAL-008` 继续负责 systemd unit 人工审阅、专用 key 配对、本机极小 Stage 04、Suzhou2 极小 Stage 04、Stage 06 单 shard 和 Stage 07 adapter probe。
- 实现提交：`bede8e13f161987d5ce77658c73121ba0aeac5b5`。

## 2026-08-01 — UI-023：精简设置与自动就绪检查

- 状态：`smoke-validated`。
- 完成时间：2026-08-01T09:49:56+08:00
- 问题：旧设置页将环境、模型资产、安装任务、公共算力、项目 preflight、自检、存档和技术元数据堆在一个长页面，普通使用者难以快速判断“当前机器能否运行”、“如何连接 Suzhou2”和“如何找回存档”。
- 方案：将设置重构为“当前设备 / 公共算力 / 项目存档”三个可切换页面。当前设备自动投影工作区 setup plan 和注册表，区分基础环境与按需科学后端，仅对缺失组件提供安装操作；Suzhou2 配对和存档恢复各自进入独立上下文。
- 自动行为：进入页面、窗口重新获得焦点、页面恢复可见和安装任务运行期间都会自动更新状态；不再要求用户点击“刷新状态”。工作区绝对路径、environment/asset ID、安装任务、隔离区和结构助手状态统一收进默认折叠的“技术详情”。
- 验证：`make check` 通过，157 个 Python 源文件通过 mypy；386 passed / 8 skipped；Workbench 65 passed / 1 skipped，包含 1440×900、1920×1080 和 Firefox smoke；Target Viewer 3 passed / 2 skipped；dev33 wheel SHA-256 `76a9705d91a5bdddb93658652911d02a663ab76d6ba7ce83cad8567b63626711`，静态资产与 console script 验证通过。
- 安全边界：本任务没有执行删除、移动、清理、环境覆盖或系统配置修改；Stage 01/02 协作者历史和无关静态文件未纳入提交。
- 遗留边界：环境页只显示已有 setup plan 中的组件；真实 Suzhou2 配对和缺失科学后端安装继续由 `VAL-008` 与环境资产许可验收负责。
- 实现提交：`47cf194879264110d3ac353c7954221ccbe25b26`。

## 2026-08-01 — UX-008：Suzhou2 主机身份稳定配对

- 状态：`implemented`。
- 完成时间：2026-08-01T11:45:37+08:00
- 问题：同一台 Suzhou2 同时公布 Ed25519、ECDSA 和 RSA 主机密钥；旧逻辑只使用 `ssh-keyscan` 输出第一行，两次扫描顺序变化时会将同一服务器误报为 fingerprint 不一致。
- 方案：解析并去重全部主机密钥，以 Ed25519、ECDSA、RSA 稳定排序供界面展示，配对时在完整集合中查找用户已确认的 fingerprint；SSH 执行器增加 `IdentitiesOnly=yes`，只提交 EasyDesign 工作区专用密钥。
- 用户边界：配对页明确说明需通过 Suzhou2 控制台或管理员核对服务器身份；EasyDesign 不读取、替换或修改 `~/.ssh` 中的个人密钥。
- 验证：`make check` 通过；388 passed / 8 skipped；Workbench Chromium 非视觉流程 21/21 通过，含公共算力设置回归；真实 Suzhou2 扫描已确认三种主机密钥可同时观测。
- 安全边界：未修改个人 SSH、系统代理、shell 或 Git 全局配置；未删除、移动或覆盖环境、模型、run 或历史证据。
- 遗留边界：完成真实免密 worker 探针及极小 Stage 04/06 任务后，由 `VAL-008` 决定是否升级为 `smoke-validated`。
- 实现提交：`2bae835678a72a574d40377901966970744fcaef`。

## 2026-08-01 — UX-008 / UI-022：一次性密码配对与工作区密钥复用

- 状态：`implemented`；真实 Suzhou2 worker/GPU 验收继续由 `VAL-008` 承担。
- 完成时间：2026-08-01T14:25:41+08:00
- 问题：配对向导只能展示手动 `authorized_keys` 命令，而且重复进入时没有在列表阶段明确
  告知工作区密钥已经存在；使用者容易误以为每次都要重新生成密钥。
- 方案：配对前检查 `runtime/secrets/ssh/<executor>/id_ed25519{,.pub}`，完整时复用，
  只有一半时拒绝覆盖。第三步新增一次性密码输入，通过严格 known-host 的 OpenSSH PTY
  幂等安装公钥，再立即使用工作区专用私钥探测 managed worker；手动安装继续保留。
- 安全边界：密码使用 `SecretStr` 接收，只写入单次 PTY，不进入 argv、环境、配置、
  registry、日志、异常文本或磁盘；失败输出会执行密码脱敏。没有读取或修改个人
  `~/.ssh`，没有删除、覆盖或清理历史 key、run、环境和模型。
- 验证：Ruff 通过，157 个源文件 mypy 通过；密码/脱敏/密钥复用/API 定向测试 9/9；
  Python 全量 390 passed、8 skipped，唯一失败来自既有 repository history/Markdown
  治理检查；Workbench 使用系统 Chrome 完成 1440/1920 非视觉 44/44。dev34 wheel
  SHA-256 为 `34f6bdd8035948995d7d66e4085f6ca7aebeeef77a49e28a7afa4654e2b08525`。
- 遗留问题：Playwright 官方浏览器下载被服务器自签名代理证书链阻止；未关闭 TLS 校验，
  Firefox 本轮未重装。真实 Suzhou2 一次性密码和 worker 探针需由有凭据的使用者在 UI
  中完成，密码不得交给日志或自动化记录。
- 实现提交：`7617022cc5b804408af3be9166eefeef47b34148`。

## 2026-08-02 — VAL-008 / S06-005 / S07-002：APOE 8 条受管 Stage 06→07 smoke

- 状态：`smoke-validated`。
- 完成时间：2026-08-02T10:31:17+08:00
- 问题：dev35 的精确 Stage 06 数量和 Suzhou2 `(6,7)` 受管链已实现，但仍缺少真实
  APOE 极小单 GPU 作业证明源闭包、中央租约、原地交接和 review-only 回传能够连续完成。
- 方案：复用冻结 APOE Stage 05 的唯一 Tier A 策略，以用户明确授权的精确 8 条预算、
  1 GPU、单 shard 和 `(6,7)` 连续范围提交 Manager。旧 run 缺失的 manifest 闭包只从
  Suzhou2 历史只读来源复制到全新 staging assembly，完成 SHA/闭包校验后再入队。
- 验证：作业 `val008-apoe-0607-smoke-20260802t0214z` 在 GPU 6 生成 8/8、无缺口且
  ID 唯一；Manager 队列终态 `succeeded` 并释放 lease。Stage 07 将 8/8 候选正常处置，
  全部因 BoltzGen `pass_filters` 为 false 发布 `stopped-no-final-candidate` 和空 review
  package；本作业没有调用 Protenix/TNP。最终 RunManifest SHA-256 为
  `bb54dd54592907bd43edcf1af156cf36ccd2878f955dd24a6e9528f5f7c90747`。
- 安全边界：旧 `easydesign-core`、`easydesign-core-dev12`、APOE 50k run 和
  `/root/Easydesign/Easycontrol` 的 inode、mtime、字节数和文件数在运行前后完全一致；
  没有移动、覆盖、删除历史数据，也没有终止外部 GPU 进程。
- 遗留边界：本次证明受管小链和科学空结果，不证明非空 Protenix/TNP 深筛，更不授权
  历史 APOE 50k 的 Stage 07。下一步用第二真实目标验证非空深筛路径。
- 实现提交：以本记录所在 `main` 提交为准。

## 2026-08-02 — UI-024：公共算力解锁、重新配置与设置返回

- 状态：`smoke-validated`。
- 完成时间：2026-08-02T11:40:36+08:00
- 问题：设置页从 `/remote-executors` 正确显示 Suzhou2 已配对，但 Stage 04/06 从
  `/execution-targets` 读取不存在的 `pairing_state`，因此同一真实配对在项目页被误投影为
  “尚未配对”；设置入口也没有保留来源页面，逻辑解绑按钮的重新配置语义不够明确。
- 方案：所有配对投影同时发布兼容 `state` 和统一 `pairing_state`；Stage 04/06 继续只在
  `paired` 时解锁。设置页把动作明确为“解除绑定并重新配置”，解绑后立即回到主机指纹、
  工作区密钥和一次性密码向导；应用记住进入设置前的项目/页面并提供直接返回按钮。
- 安全边界：解绑继续追加 `unpaired` revision，不删除或覆盖工作区专用私钥、远端
  `authorized_keys` 公钥、known-host 和历史运行证据；重新连接会复用完整密钥对，半套
  密钥仍 fail closed。本任务没有修改 Suzhou2 Manager、队列、GPU 作业、模型或旧 run。
- 验证：`make check` 与 416 passed/8 skipped 的 Python 全量门通过；双尺寸 Chromium
  对“项目返回”、“配对→解绑→重新配置”和“Stage 03→04 后 Suzhou2 卡片已配对且可点击”
  完成 6/6 定向回归；Workbench Chromium/Firefox 非视觉矩阵 72/72 通过，设置页新返回
  按钮另完成 1440×900、1920×1080 视觉基线审阅。
- 实现提交：以本记录所在 `main` 提交为准。

## 2026-08-02 — UI-025：逐卡资源弹窗与连续阶段真实进度

- 状态：`smoke-validated`。
- 完成时间：2026-08-02T13:09:25+08:00
- 问题：Stage 04/06 只在执行卡片上显示总 GPU 文案，用户选择卡数前看不到真实空闲数或
  逐卡占用原因；运行后只有单调的无语义横条，无法区分受管 `4→5`、`6→7` 的阶段交接，
  也没有把已有结构化候选/任务进度投影出来。
- 方案：`ManagedWorkerProbe` 升至 schema 0.3，按与 admission 相同的阈值发布 8 张卡的
  型号、显存、利用率、compute process 数量、eligibility 原因与 lease 状态。Workbench
  在卡数输入前显示“空闲/总数”，逐卡信息只在按需弹窗打开；受管任务用真实
  `ProgressSnapshot.stage_id`、task/candidate 计数与 ETA 驱动两段阶段轨道和阶段内进度。
- 安全边界：probe 不返回 PID，不接受 shell 字段，也不把瞬时空闲数当作资源预留。
  Suzhou2 activation revision 9 只追加 Manager dev2/EasyDesign dev36 release；检测到既有
  `ui-9bce0dcb8bd94826` 正在 GPU 6/7 运行后，没有重启 systemd、终止子进程或触碰外部
  GPU 作业。daemon 仍以 dev1 进程自然服务当前作业，待队列空闲后再无中断重启。
- 验证：ProteinDigger `make check`、418 passed/8 skipped、dev36 wheel/package-data
  校验通过；Manager 28/28 与跨仓 golden JSON 通过。Workbench 去除既有设置页字体栅格
  基线项后的 Chromium 1440、Chromium 1920、Firefox 矩阵为 75/75；设置页原基线仅有
  约 1% 平台字体栅格差异，布局与内容一致且未重写基线。真实 18769 已报告 dev36，
  `/execution-targets` 返回本机 2/2、Suzhou2 0/8、8 条逐卡记录和 1 条运行中队列记录；
  0/8 与当时外部进程及有效租约一致。EasyDesign wheel SHA-256 为
  `d8ba14d59350d61fb5459ed4da27859633ca617627535f80a8ab3a2934593cbf`。
- 实现提交：`6a41546bf8e03b6d2a2e2ab907ab949c2189d1d2`；本记录提交为后续状态归档。

## 2026-08-02 — UI-027：归档隐藏与逐步骤 Stage 02 单次提交

- 状态：`implemented`。
- 完成时间：2026-08-02T20:41:37+08:00
- 问题：归档只移动 run，保留的项目配置随后被默认项目页错误解释成“草稿·尚未运行”；
  逐步骤 Stage 02 又要求填写未认证批准人、重复勾选证据限制并选择后续运行方式。
- 方案：默认项目投影同时读取 active/archive index category，过滤只有归档运行的配置，
  恢复后重新显示。逐步骤 Stage 02 以保存按钮点击作为明确人工提交，固定
  `review-gated`；只记录真实交互渠道，不伪造人员身份或已验证结合位点。
- 验证：`make check`、426 passed/8 skipped、Workbench 三浏览器 75/75、Target Viewer
  3 passed/2 skipped、dev40 wheel/package-data 检查均通过。wheel SHA-256：
  `ccd715fab5405c1df12e0087948752fc8cf1aaec3a0a11f9fc3bf6e440e39cf4`。
- 安全边界：没有移动、删除或修改真实项目、归档、运行、环境、模型或 Suzhou2 Manager；
  初始 YAML/CLI 和非交互 unattended 的完整人工批准契约保持不变。
- 实现提交：以本记录所在 `main` 提交为准。

## 2026-08-03 — UI-028：刷新后恢复 continuation 并防止重复入队

- 状态：`smoke-validated`。
- 完成时间：2026-08-03T14:39:50+08:00
- 问题：Stage 04 远程任务已在 Suzhou2 运行，但接受记录缺少
  `accepted_run_key`，前端又只在 React 内存保存 managed job 指针；刷新后页面
  误显示“尚未开始”并重新开放提交。
- 方案：新增按 run/project/stage 的持久 continuation 查询，恢复本机 job ID 或
  Suzhou2 managed pointer 后继续轮询。旧活跃记录以 append-only revision 补写
  binding；终态旧记录不会误绑新 run。continuation POST 在服务端锁内二次
  查重，重复请求返回 `409 stage_locked`。
- 验证：`make check`、435 passed/8 skipped 的 Python 全量回归、Workbench
  83 passed/1 skipped、Target Viewer 3 passed/2 skipped 和 dev44 wheel/package-data 检查
  全部通过。wheel SHA-256 为 `41e55267cc5522de86c56a7e5f2d8c6d157600aaa32065dbd6ce20667817954d`。
  真实 18769 刷新后先恢复同一 `ui-5360583208ee4bdf`，页面无新启动按钮；
  随后同步 280/280 终态并进入 Stage 05 `scientific-stop`，控制台 0 error。
- 安全边界：未停止或重启 Suzhou2 Manager；`lyjsmoke1` 4→5 job 是在
  验收期间自然完成的。未移动、删除或覆盖 run、环境、模型和队列证据。
- 实现提交：以本记录所在 `main` 提交为准。

## 2026-08-03 — REL-002：dev44 Manager 同步与强制版本门

- 状态：`smoke-validated`。
- 完成时间：2026-08-03T16:12:29+08:00
- 完成：在 Suzhou2 队列 0/running 0 的窗口，将 ProteinDigger 构建的 dev44 wheel
  `41e55267cc5522de86c56a7e5f2d8c6d157600aaa32065dbd6ce20667817954d`
  安装到全新 immutable release，追加 activation revision 12，并只重启
  `easydesign-managed-worker.service`。Manager 自身保持 `0.1.0.dev2`。
- 验证：新 release 激活前 probe、激活后固定入口 probe、ProteinDigger 控制端兼容 probe
  和真实 18769 execution-target API 均通过；报告 EasyDesign dev44、8/8 GPU、三后端
  ready、`[(4,5),(6,7)]`、队列 0，systemd `NRestarts=0`。
- 规则：根 `AGENTS.md` 和架构契约现在要求任何改变本地 EasyDesign 版本或 wheel identity
  的更新，都必须在交付前把同一 SHA wheel 以新 release/activation 同步到所有已配对
  Manager；失败时 fail closed，不得显示为可用。
- 安全边界：未重装 BoltzGen/Protenix/TNP 环境，未复制模型，未覆盖旧 release/revision，
  未修改历史 run、队列或外部 GPU 进程。
- 实现提交：以本记录所在 `main` 提交为准。

## 2026-08-03 — UI-029：Stage 01 紧凑摘要与 PyMOL cartoon-only

- 状态：`smoke-validated`。
- 完成时间：2026-08-03T23:33:19+08:00
- 问题：Stage 01 左栏重复展示目标名、来源、结构模型数和缺失 CA，单个序列事实被拆成
  四张未对齐卡片；默认 PyMOL PML 又把来源 A/B/C 区域强制显示为 stick，形成 Mol*
  没有的突出侧链，容易被误解为结构异常。
- 方案：只读 Stage 01 左栏改为单行“序列长度”，保留结果文件和后续配置动作；新建
  Stage 01 PML 不再生成区域 stick，前端对旧 Stage 01 会话也只过滤三条受管
  `show sticks, ed_region_A/B/C`，不修改 canonical PML。Stage 02 编辑态 stick、助手
  SceneVersion 和 Mol* 投影保持不变。
- 验证：`make check`、Python `436 passed / 8 skipped`、Workbench Chromium
  1440/1920 与 Firefox `83 passed / 1 skipped`、`make build` 全部通过。真实
  `apoe-s02-006-pse` 页面确认 Stage 01 只显示 `138 aa`、PyMOL 无突出 stick、Mol*
  正常，切换 Stage 02 后 stick 仍存在。dev45 wheel SHA-256 为
  `35c3cddadf24ed15251da3679804cde64d542eb12355b9f0f65d8f561e519e75`。
- Manager 同步：Suzhou2 Manager 保持 `0.1.0.dev2`。初次 activation revision 13
  暴露 release-local `worker.yaml` 仍声明 dev44，服务按精确版本门拒绝启动；随即追加
  revision 14 回退旧 release，再以修正后的全新 immutable release 追加 revision 15。
  最终 systemd `active/running`、`NRestarts=0`，固定入口和 ProteinDigger 控制端均探测
  dev45、三后端 ready、`[(4,5),(6,7)]`、queue/running 0。失败 release 与回退记录均
  保留为不可变证据，没有覆盖历史。
- 安全边界：没有重装 BoltzGen/Protenix/TNP 环境、复制模型、修改科学结果或终止外部
  GPU 进程；8 张 GPU 当时均有外部任务，因此控制端如实显示 `waiting-resource`。
- 实现提交：以本记录所在 `main` 提交为准。

## 2026-08-04 — ENG-033 / REL-003 / REP-010 / UI-028：dev46 可复现安装与 Stage 02 收敛

- 状态：`smoke-validated`。
- 完成时间：2026-08-04T10:57:24+08:00
- 问题：core/UI 缺少提交级依赖锁和紧凑的新用户安装路径；Stage 02 又会自动突出显示
  A/B/C 侧链并在主界面暴露整串规范编号和内部来源，既干扰结构阅读，也混淆设计输入与
  实验验证位点。
- 方案：提交 Python 3.11 与 `uv.lock`，由 uv 只管理 editable core/UI/dev `.venv`，五个
  科学后端继续使用独立 Conda lock 和资产许可门；重构中英文 README、环境文档、开发
  文档和轻量 CI。Stage 02 新场景不再生成 managed-region sticks，旧场景只在 PyMOL
  投影时过滤三条精确历史自动命令；左栏仅保留 A/B/C、成员数和证据限制提示，正式
  artifact、区域成员、schema、`hotspots.yaml` 与 Stage 03 输入保持不变。
- 验证：`make check`、`make test`（439 passed/8 skipped）、`make test-web`（Target
  Viewer 3 passed/2 skipped；Workbench 86 passed/1 skipped）与 `make build` 全部通过；
  官方 uv 0.12.1 的 frozen ui/dev 同步、干净 clone README smoke、wheel 隔离安装、CLI
  help、localhost-only UI health 和 Git diff 检查均通过。最终 wheel SHA-256 为
  `11f2e1d558b1b7141027f9ee9339df08e33aa818d4cbabe43f757feb4f7b109d`。
- Manager 同步：只在 queue/running 均为 0 后，以相同 SHA wheel 创建全新 immutable
  release，追加 activation revision 16 并重启 Manager 服务；Manager 保持
  `0.1.0.dev2`，固定入口和 ProteinDigger 控制端均报告 EasyDesign dev46、8 张 GPU、
  三后端 ready、`[(4,5),(6,7)]` 和 queue/running 0。registry 仍为 `paired`。
- 安全边界：没有重装科学环境、复制或移动模型、改写历史 run/release/revision，也没有
  终止外部 GPU 进程。部署前后审计 `audit-20260804T023716Z-0007.json` 与
  `audit-20260804T025724Z-0008.json` 证明六个受保护路径记录完全一致，前后均观察到
  8 个外部 GPU 进程。
- 遗留边界：Suzhou2 Manager 源码仓库保持干净 `main`，但私有 GitHub remote 仍缺可用
  deploy key，无法在 Suzhou2 上 fetch/push；该权限问题不影响已激活的不可变 release。
- 实现提交：`30f9e7e6589c974a91487ac9b2ef6ef8f9f859f2`；本记录提交负责最终状态归档。
