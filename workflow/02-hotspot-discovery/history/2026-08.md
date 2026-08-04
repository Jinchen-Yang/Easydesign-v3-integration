# 2026-08 历史

## UI-027：逐步骤区域提交与归档投影收敛

- 状态：`implemented`
- 完成时间：2026-08-02T20:41:37+08:00

### 遇到的问题

- 归档 run 后保留的项目配置被默认项目列表误投影成“草稿·尚未运行”；逐步骤 Stage 02
  仍要求填写未认证批准人、重复确认证据限制并选择后续运行方式。

### 解决办法

- 使用 run index 的 active/archive category 约束项目和草稿投影；将逐步骤 Stage 02
  收敛为固定 `review-gated` 的单次交互式人工提交，同时保持底层科学合法性检查。

### 完成内容

- 逐步骤 Stage 02 手工选区移除批准人文本框、重复证据限制勾选和后续运行方式选择；
  “保存并完成第2步”作为一次明确的交互式人工提交，固定使用 `review-gated`。
- 本机工作台只记录 `human:local-workbench` 这一真实交互渠道，不伪造具体人员身份，
  仍生成“无独立生物学证据、未自动结构优选”的保守 typed record，并继续验证残基存在、
  编号映射和 A/B/C 不重叠。
- 自动选区分支同样不再提供连续运行选择；逐步骤会话始终在本步后暂停。初始 YAML、CLI
  和非交互 unattended 输入的真实审批人、逐区理由及 acknowledgement 契约保持不变。
- 项目列表以 `run-index.json` 的 active/archive category 为准；只有归档运行的项目即使
  保留 `projects/<id>/` 配置，也不会重新投影成草稿，恢复后重新可见。

### 验证证据

- `make check` 通过：Ruff 和 156 个 Python 源文件 mypy 均通过。
- Python 全量 `426 passed / 8 skipped`；归档→隐藏→恢复和无运行索引草稿边界均有
  FastAPI 回归。
- Workbench Chromium 1440、Chromium 1920、Firefox 非视觉矩阵 `75/75` 通过；本任务
  定向的归档、Stage 02 手工/自动和 Stage 03/04 连通为 `10/10`。
- Target Viewer `3 passed / 2 skipped`；dev40 wheel 资产与 console script 校验通过，
  SHA-256 为 `ccd715fab5405c1df12e0087948752fc8cf1aaec3a0a11f9fc3bf6e440e39cf4`。

### 安全边界

- 没有移动、删除或改写真实项目、归档 run、模型、环境或 Suzhou2 Manager；归档测试只在
  pytest 临时工作区执行。既有初始 YAML/CLI 科学批准门没有被放宽。

### 遗留问题

- 本任务不改变 automatic 方法的科学 benchmark 状态；S02-008 继续负责外部证据和
  VHH–抗原验证。

## REP-010/UI-028：Stage 02 managed-region cartoon-only 与左栏收敛

- 状态：`smoke-validated`
- 完成时间：2026-08-04T10:57:24+08:00

### 遇到的问题

- 新旧 Stage 02 场景会自动对 `ed_region_A/B/C` 显示 sticks，突出侧链干扰 cartoon
  阅读；只读和编辑左栏又展示整串规范编号及内部来源，使用户容易把设计输入误解为
  已验证结合位点。

### 解决办法

- 新 PML 和前端 overlay 不再生成 managed-region sticks；旧不可变 SceneVersion 只在
  PyMOL 显示投影时过滤精确的三条历史自动命令，不改写 canonical PML，也不影响其他
  selection 的用户或助手自定义 sticks。
- Stage 02 主左栏只显示 A/B/C、成员数和“用户确认设计输入不等于实验验证位点”的提示；
  单残基格、结构点击与反馈继续显示规范编号。来源、渠道、批准记录和完整成员仍进入
  正式 artifact 与技术记录。

### 完成内容

- A/B/C selection 与红、蓝、黄 cartoon 保持；Mol* 投影不变。
- Stage 02 schema、成员、`hotspots.yaml` 和 Stage 3 下游输入完全不变。
- 显示过滤逻辑抽成纯 TypeScript helper，并覆盖新旧 managed-region 命令和非 managed
  自定义 sticks 的正反回归。

### 验证证据

- `make check`、Python `439 passed / 8 skipped`、Target Viewer `3 passed / 2 skipped`、
  Workbench `86 passed / 1 skipped` 和 `make build` 全部通过。
- dev46 wheel 隔离安装和 localhost UI health 通过；wheel SHA-256 为
  `11f2e1d558b1b7141027f9ee9339df08e33aa818d4cbabe43f757feb4f7b109d`。

### 安全边界

- 未修改历史 SceneVersion、区域科学成员、审批证据或下游契约；未移动、删除或覆盖
  项目、run、环境、模型和密钥。

### 遗留问题

- S02-008 的 VHH–抗原科学 benchmark 与 REP-002 独立 overlay 仍按原计划推进；本次
  显示收敛不宣称区域已获得实验验证。
