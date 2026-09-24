# EasyDesign Latent-style UI Prototype Pack

日期：2026-09-13

这个包只服务于一个目标：

> 先把 EasyDesign 的白色清爽 Workbench、完整演示流程和结构交互做通；暂时不要求科学流程真实执行，不跑真实 GPU 任务。

## 冻结目标

第一版必须能在浏览器中完整演示：

`Goal → Target → Site → Design → Pilot → Scale → Candidates`

界面采用三栏科研工作区：

- 左：Workflow / Agent Tasks
- 中：Design Scientist conversation + research trace / tool cards
- 右：Scientific Context（结构、hotspot、设计、pilot、scale、candidate）
- 底：关键阶段的 Decision bar

## Demo 原则

- 使用 deterministic fixture，不运行真实 BoltzGen、AFO、Protenix 或 GPU job。
- Pilot 只模拟 8 个 candidates。
- Scale 只模拟 24 个 candidates。
- Demo 必须总能顺利到达 Candidates。
- 所有模拟结果显著标记 `Demo fixture` 或 `Simulated for UI development`。
- 不展示模型隐藏 chain-of-thought；中栏只展示用户可解释的 research trace、tool events、high-level rationale。
- 第一版优先保证交互、审美和稳定重放，科学真实性后续再接。

## 推荐 demo target

Lysozyme + camelid VHH，PDB 1MEL。

1MEL 是公开的 camel single-domain VH–lysozyme complex。建议：
- Target / Site 阶段：只显示 lysozyme chain C（若 viewer chain 编号解析不同，以实际 mmCIF 为准）。
- Candidates 阶段：显示 VHH chain A + lysozyme target。
- 如果远程结构加载失败，UI 必须优雅降级，不能阻断流程。

## 目录

- `01_UI_PRODUCT_SPEC.md`：界面与交互冻结规范
- `02_DEMO_FLOW_SPEC.md`：完整 demo 状态机
- `03_ADAPTER_CONTRACT.md`：DemoAdapter / future DSHAdapter 边界
- `04_CODEX_PROMPT.md`：可直接发给 Codex 的主 prompt
- `05_ACCEPTANCE_CHECKLIST.md`：验收表
- `demo/demo-fixture.json`：建议 fixture
- `references/latent-y/`：用户提供的 Latent-Y UI 截图
- `references/current-easydesign/ui-plugin/`：当前发布版 EasyDesign 插件
- `references/current-easydesign/docs/`：当前架构与 workflow 参考
- `references/dsh-ui/`：与布局、conversation、tool、trajectory、theme、workspace、subagent 相关的已安装 DSH UI 包

## 开发边界

这次不要重构 scientific kernel，不要迁移 v3，不要重新设计审批科学语义。

尤其不要在已打包的 `ui-plugin/lib/client.js` 上继续堆大型新功能。它只作为历史 UI / DSH integration 参考。

应新建一个可维护的前端源码工程，并通过 adapter 把 UI 与数据源隔开。
