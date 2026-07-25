# EasyDesign 项目宪章与开发规则

本文档是项目战略、1.0 边界和开发制度的统一事实来源。发布阶段再拆分英文 README、
CONTRIBUTING、CHANGELOG、LICENSE、CITATION 和第三方声明。

## 1. 使命

EasyDesign 要把多类 binder 的设计研究流程变成容易使用、可追溯、可复现、可扩展并能够
产品化的系统。用户最终只需提供 target 与必要设计约束，平台负责组织真实后端、保存中间
证据、解释失败并生成可人工批准的候选包。项目同时推进三条路线：

- **科研：** 保存方法、基准、负结果和 claim-to-evidence 链接，支撑正刊论文。
- **软件：** 先让稳定 Python API 与薄 Developer Preview CLI 共同收敛，再做调用同一
  API 的正式 CLI 和 UI。
- **商业：** 保护知识产权和资产权利，支持私有部署及未来商业产品。

开发速度来自清楚的契约、证据和模块边界，不来自隐藏失败或堆叠临时脚本。

## 2. EasyDesign 1.0

1.0 实现完整七阶段 VHH 主线，可以使用小规模预算和基线模型，不承诺 binder
准确率。发布门槛是：

1. 七个阶段均调用真实工具，不使用伪造科学结果通过验收；
2. 一条实验结构输入的端到端基准通过；
3. 一条无合适现成结构的 sequence/UniProt 端到端基准通过；
4. Stage 01 六类输入入口分别通过集成测试；
5. 运行可安全恢复，保留溯源且不覆盖已完成产物；
6. 软件成功与科学筛选结果分别报告。

VHH 是 1.0 的首个参考实现，不是 EasyDesign 的永久产品边界。其他 binder 类型在 1.0
只保留 adapter/profile 扩展边界，不列入实现承诺。

1.0 的流程判断必须来自版本化算法、规则和模板，不依赖本地或远程 LLM/Agent 才能运行。
Protenix、ScanNet、BoltzGen 等确定用途的科学模型不属于这一限制。1.0 以后可以增加可选
Agent 建议层，但其建议必须转成类型化配置，经过确定性校验和明确人工批准；关闭 Agent
时七阶段仍须完整运行，Agent 不得成为隐藏 fallback 或事实来源。

## 3. 长期 binder 范围与“一键式”边界

长期计划支持但不限于：

- VHH/nanobody 和后续经过评审的其他抗体片段；
- de novo 或 scaffold-based 蛋白 binder；
- 线性肽、环肽等具有明确表示和约束契约的肽 binder；
- 未来经过科学验证、许可证审查和产品评审的其他 binder 类型。

七阶段的运行、manifest、溯源、恢复和报告机制保持共用；binder 特异差异必须通过可替换
profile/adapter 表达，包括：

- 分子表示、长度、组成和结构约束；
- scaffold 或生成起点；
- 生成后端及其参数能力；
- 序列、结构、界面和可制造性筛选规则；
- 最终实验或下单候选包格式。

不得为每种 binder 复制一套七阶段 pipeline。Stage 01–02 尽可能保持 target 侧通用，
Stage 03–07 通过 binder-specific profile、backend 和 filter 扩展。

“一键式”表示一个用户配置和一个稳定入口能够编排完整流程，而不是取消科学透明度。
系统仍必须显式报告模型选择、经允许的 fallback、人工批准点、负结果和未实现能力；其中
静默 fallback 始终禁止。

1.0 提供两种共享同一科学实现的执行策略：

- `review-gated` 为默认模式，在身份、结构、区域、设计策略和高成本预算等科学选择点暂停，
  保存候选与证据，等待类型化人工批准后以新 attempt 继续；
- `unattended` 只按版本化硬规则和模板自动运行，任何歧义、证据不足或未授权 fallback
  都明确失败，最多生成候选下单包。

两种模式都不能自动向供应商下单。`required_reviews` 中的 biosafety 等审查无论模式如何
都必须完成，否则最终只能生成 `draft-order-package`。

## 4. 不可妥协的工程规则

1. 一个概念只能有一个实现和一个事实来源。
2. 阶段只读取上游 manifest 声明的 artifact，并输出不可变 manifest。
3. 禁止静默 fallback、伪造成功、错误后端命名和吞掉异常。
4. 每次运行保存输入 hash、配置快照、代码版本、随机种子、后端/模型版本和环境。
5. CLI、UI、notebook 和 shell 脚本不得包含科学业务逻辑。
6. filter、scaffold、预测器和 executor 都必须是带能力声明的可替换 adapter。
7. 启发式必须明确标注；没有证据时不得描述成能量学或实验验证方法。
8. run 和 attempt 只追加不覆盖；恢复执行创建新 attempt。
9. 密钥、权重、缓存、大型运行结果和未经审查资产不得提交。
10. 第三方代码、模型、数据和 scaffold 引入前必须完成来源与权利审查。
11. 代码、测试、阶段说明和 TODO 状态必须在同一变更中保持一致。
12. 阶段契约、架构、证据标准和兼容性发生重大变化时记录 ADR。
13. 生物学身份只能来自显式输入或可审计解析；禁止根据 target 名称静默猜 accession。
14. 自动候选与人工批准分离；人工输入必须形成不可变 attempt 和类型化下游 artifact。
15. 联网检索必须保存请求/响应身份并区分“无候选”与“API 失败”；cache 与 fallback
    只能由配置显式允许。
16. unattended 决策必须记录 deterministic policy ID、参数和源 artifact hash；不得用
    Agent/LLM 或 CLI 隐藏参数替代版本化规则。

## 5. 状态与证据

项目只使用以下状态：

- `planned`：已经规范，尚未实现；
- `implemented`：代码存在并通过工程检查；
- `smoke-validated`：真实小规模运行完成；
- `scientifically-validated`：预定义科学基准通过；
- `production-ready`：运行、支持、安全和发布门槛全部通过。

高等级状态必须链接当前等级及所有更低等级的证据。一次完整运行没有候选通过
filter，是有效的科学负结果，不代表软件失败，也不能包装为 binder 成功。

## 6. 开发与评审流程

- 采用 trunk-based 开发；`main` 保持可验证，工作使用短期分支和 Conventional Commits。
- 修改前阅读相关阶段 `README.md`、`TODO.md` 和 `TODO_NOW.md`。
- 领域逻辑只放在 `src/easydesign/`；脚本只能调用 API。
- 按风险补充 unit、adapter integration 和 end-to-end 测试。
- 合并前运行 `make check`、`make test`；打包变更再运行 `make build`。
- 重型后端可以使用独立环境，不能在包导入时强制加载可选重型依赖。
- 核心逻辑不得硬编码 SMART、服务器路径、用户名或密钥。

评审必须拒绝重复逻辑、读取未声明文件、覆盖产物、隐藏 fallback、错误科学标签、
站点路径泄漏和来源不明资产。

## 7. 文档制度

- `README.md`：项目入口与当前状态。
- `PROJECT_CHARTER.md`：战略、1.0 边界和开发规则。
- `TODO.md`：短期、中期和长期宏观路线；除七阶段外还统一维护工程、CLI、报告、UI、
  验证、数据、发布、论文和商业板块。
- `TODO_NOW.md`：跨阶段的 Now/Next/Blocked、自动生成的七阶段实时摘要和项目历史索引，
  不复制阶段任务。
- 每个 workflow 阶段维护一个稳定的中文 `README.md`，同时承担说明和契约。
- 每个 workflow 阶段维护一个动态 `STATUS.md`，记录功能矩阵、Now/Next/Blocked、
  验证证据、只追加工作日志，以及供顶层自动汇总的一句话状态。
- 七阶段实时摘要只能由 `scripts/sync_status_rollup.py` 从各 Stage `STATUS.md` 生成；
  `make check` 必须拒绝过期的顶层摘要。
- 阶段历史每月归档到该阶段的 `history/YYYY-MM.md`；跨阶段历史归档到
  `docs/history/YYYY-MM/`。
- 每条已完成历史必须记录完成门槛满足时的 RFC 3339 秒级时间和 UTC offset，例如
  `2026-07-25T14:30:00+08:00`；Stage history 与从顶层 `TODO_NOW` 移出的完成事项使用
  同一格式，并由 `make check` 自动校验。
- Git commit 记录代码差异；历史文档只记录决策理由、验证证据、run/attempt 身份、
  失败和结论更正，不能复制流水账。
- 当前开发期只维护中文；公开发行前再建立英文发布文档并进行逐项校对。
- 每个实质性任务必须有板块 ID。Stage 使用 `S01–S07`，其他任务使用 `ENG`、`UX`、
  `REP`、`UI`、`VAL`、`DATA`、`REL`、`PAPER` 或 `BIZ` 前缀。
- 非 Stage 工作默认进入共享顶层月度 history；只有一个板块内容明显膨胀后才建立独立
  STATUS/history，避免重新产生文档碎片。

## 8. 知识产权与第三方资产

当前没有 `LICENSE` 是刻意选择，所有权利保留。当前只使用项目所有者批准的私有远程
托管；公开授权、公开 release 和论文引用信息必须经过明确的 IP/release 决策。第三方
资产使用前登记到
`resources/provenance/ASSET_REGISTER.tsv`，记录来源、不可变版本或 checksum、
许可证、用途、再分发权和审查结论。能够下载不代表拥有使用权。
