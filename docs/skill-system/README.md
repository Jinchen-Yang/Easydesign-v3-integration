# EasyDesign Skills

本目录只用于说明当前有哪些 Skill、各自解决什么问题。Skill 的真实内容以对应 `SKILL.md` 和其 `references/` 为准；这里不保存版本迁移对比、coverage、claim/source ledger 或阶段性评测报告。

## 当前 Skill

| Skill | 状态 | 用途 | 不用于 | 权威入口 |
|---|---|---|---|---|
| `easydesign-development` | live | EasyDesign 仓库工程：代码、测试、开发文档、developer policy、Skill、runtime configuration、local worker 和 Viewer | 蛋白结合物研究执行，创建科学 run/job/attempt | `.agents/skills/easydesign-development/SKILL.md` |
| `easydesign-research` | live（v0.3） | VHH/nanobody 研究：从 design goal、target/state/context 和文献证据推导 site，设计 pilot，通过 Stage 5/7 核心 Review Dashboard 诊断结果，并决定迭代、promotion、scale 和 selection | 仓库开发、UI 发布、remote compute、host pairing、managed queue | `.agents/skills/easydesign-research/SKILL.md` |

`easydesign-research` 按研究 phase 渐进加载：

- `prepare`：目标身份、机制、文献与结构证据、site 比较和审批；
- `strategize`：hotspot、scaffold、CDR、crop/context、可归因 pilot matrix 和 BoltzGen 配置；
- `pilot`：数据可比性、target/binder/site/interface/CDR/scaffold 分层诊断和下一轮实验；
- `scale/select`：promotion、规模化、候选多样性、选择和实验验证。

当前 v0.3 已部署为 live Skill；匿名 A/B 评测产物只进入 `runtime/tmp/skill-evals/`，不作为长期文档提交。

## 如何使用

- 仓库开发任务使用 `$easydesign-development`。
- VHH 研究任务使用 `$easydesign-research`。
- Stage 5/7 网页由核心 reporting 基础设施生成，结果呈现与解释统一由 `$easydesign-research` 按 `pilot` 或 `scale/select` phase 处理，不再维护独立结果 Skill。
- 正常情况下 Codex 可根据 Skill `description` 隐式选择；需要明确限定角色时再显式写出 Skill 名称。
- 根 `AGENTS.md` 只规定研究 Agent 的全局边界；仓库开发流程由 `easydesign-development` 管理。

## 文档维护规则

- 本目录根层只保留本 `README.md`。
- Skill 的科学知识、工具合同、例子和审批边界放在对应 Skill 的 `references/`。
- draft 只放在 `drafts/<skill-version>/`。
- 临时coverage、版本对比和评测过程不作为长期文档保留；需要时由 Git/history 或当次任务报告追踪。
