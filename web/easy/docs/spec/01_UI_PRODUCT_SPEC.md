# 01 — EasyDesign Workbench UI Product Spec

## 1. 产品目标

第一版不是“科学系统完成版”，而是一个真正可运行的蛋白设计 Agent 工作台原型。

用户打开页面后，不需要知道 repository、CLI、manifest 或 checksum。
他只需要：

1. 输入一个设计目标；
2. 看见 EasyDesign 把任务拆成 Target / Site / Design / Pilot / Scale / Candidates；
3. 在中间与 Design Scientist 对话；
4. 在右侧看到当前科学对象；
5. 在关键节点点击 Approve / Edit / Compare；
6. 最终得到一组 candidate cards。

## 2. 首屏

参考 Latent-Y 的极简 landing：

- 白色或近白背景；
- EasyDesign wordmark 居中；
- 中央单一自然语言输入框；
- 不展示复杂 dashboard；
- 可有 2–3 个很淡的 example prompts；
- 输入后切换到 Workbench，不另开页面。

推荐默认 prompt：

`Design a VHH binder against hen egg-white lysozyme and prioritize a compact accessible epitope.`

## 3. Workbench 总体布局

桌面端 1440 px 左右时：

- App rail：52–60 px
- Workflow：220–250 px
- Conversation：flex，建议不小于 520 px
- Scientific Context：380–480 px
- Decision bar：底部跨 Conversation + Context，必要时 sticky

示意：

┌────┬──────────────┬──────────────────────────┬───────────────────────┐
│ ED │ WORKFLOW     │ DESIGN SCIENTIST         │ SCIENTIFIC CONTEXT    │
│    │ ✓ Goal       │                          │                       │
│ +  │ ✓ Target     │ User                     │ 3D structure          │
│    │ ● Site       │ ...                      │ hotspot / sequence    │
│    │ ○ Design     │                          │ metrics / evidence    │
│    │ ○ Pilot      │ EasyDesign               │                       │
│    │ ○ Scale      │ ...                      │                       │
│    │ ○ Candidates │                          │                       │
└────┴──────────────┴──────────────────────────┴───────────────────────┘

## 4. 左栏：Workflow / Agent Tasks

一级步骤固定为：

1. Goal
2. Target
3. Site
4. Design
5. Pilot
6. Scale
7. Candidates

状态只有：

- complete
- current
- locked
- approval

不要暴露内部工程术语 `prepare / strategize / select` 作为主标签。

当前步骤下方显示 3–5 个 subtasks，例如 Site：

- ✓ Literature context
- ✓ Structure identity
- ✓ Residue mapping
- ● Compare candidate sites
- ○ Approve hotspot

左栏不是导航树，也不是日志树。只用于让用户一眼知道“EasyDesign 现在做到哪里”。

## 5. 中栏：Conversation + Research Trace

中栏不是 raw chain-of-thought。

允许展示：

- 用户消息；
- Design Scientist 对用户可解释的阶段总结；
- specialist 状态；
- tool result cards；
- search / structure / generation / evaluation events；
- high-level rationale；
- warning / retry / completed 状态。

不要展示：

- 隐藏推理链；
- 巨量 stdout；
- SHA/checksum；
- 原始 JSON 默认展开；
- 冗长系统提示词。

Tool card 示例：

Structure search                         Completed
3 candidate structures inspected
PDB · UniProt · literature
                                      View details >

Subagent 示例：

Structure Analyst     Completed
Site Strategist       Running
Evidence Judge        Waiting

Tool card 默认折叠，点击后才展开细节。

## 6. 右栏：Scientific Context

右栏必须随 phase 改变，不是固定 Mol*。

### Goal
- Goal summary
- binder type
- design constraints
- uploaded source placeholders

### Target
- 3D structure
- target identity
- chain
- PDB / UniProt
- compact sequence strip
- small metadata

### Site
- 3D structure with A/B/C site overlays
- site selector A/B/C
- residue list
- accessibility / geometry / evidence mock metrics
- selected site highlighted

### Design
- approved site
- VHH scaffold
- 2 design arms
- candidate budget
- concise configuration summary
- no raw YAML by default

### Pilot
- 8 candidate cards
- status summary
- pass/fail mini chart
- 3–4 compact metrics
- selected candidate structure

### Scale
- 24 simulated candidates
- progress line / batch list
- pass count
- no GPU jargon unless expanded

### Candidates
- 6 finalist cards
- structure carousel
- sequence strip
- compact metric table
- final selection state

## 7. Bottom Decision Bar

只在真正的决策点出现：

- Approve target
- Approve Site B
- Approve design
- Promote pilot
- Finalize candidate panel

按钮文案使用人的语言，不使用：

`freeze strategy`, `consume receipt`, `approve artifact`.

标准按钮：

- Compare
- Edit
- Approve
- Continue

主按钮使用品牌紫色。

## 8. Latent-Y 风格视觉语言

目标是“白色、清爽、克制、科研产品”，不是传统 dashboard。

### Tokens

- page: #FAFAFC / #FFFFFF
- surface: #FFFFFF
- border: #E8E8EE
- primary text: #18181D
- secondary text: #70707A
- muted text: #9A9AA3
- brand purple: #6657E8 左右
- brand purple hover: 稍深
- success: 低饱和绿
- warning: 低饱和黄
- error: 低饱和红

### 视觉规则

- 大量留白；
- 1 px 浅灰边框；
- card shadow 极弱或无；
- 圆角 10–14 px；
- 不做玻璃态；
- 不做渐变背景；
- 不用荧光色；
- 不用夸张大标题；
- 不要“AI dashboard”式彩色卡片墙；
- 不复制 Latent-Y logo、品牌文案或专有资产；
- EasyDesign 使用自己的 ED / EasyDesign 品牌。

## 9. 结构交互

至少实现：

- viewer load；
- chain / selection 切换；
- Site A/B/C 选择时改变高亮；
- Candidates 阶段可显示 target + binder complex；
- 右侧 site/candidate card 点击后 viewer 联动。

若 Mol* 接入时间过长，第一版允许先用现有 EasyDesign viewer iframe / RCSB-compatible viewer adapter，
但组件接口必须保留，不能把 viewer 逻辑散落到页面里。

## 10. Responsive

第一版只保证：
- 1366×768
- 1440×900
- 1728×1117

小屏可把 Scientific Context 做成右侧 drawer。
手机端不是第一优先级。

## 11. 文案风格

自然、克制、像科研软件。

不要：
- “Your revolutionary AI scientist is thinking...”
- “Unlock the future of protein design”
- 大量感叹号

可以：
- “Three candidate sites are ready for comparison.”
- “Site B gives the clearest accessible surface in this demo.”
- “The pilot produced 6/8 passing candidates.”
