---
name: easydesign-research
description: 使用 EasyDesign 开展可审计的 VHH/nanobody 研究决策：从 design goal、assay、target identity/state/context、文献与结构证据推导 site，包含 GPCR 的受体身份、状态、膜方向、家族机制与可接近性分析；设计可归因的 BoltzGen pilot，诊断 target/binder/site/interface/CDR/scaffold 失败，并决定迭代、promotion、scale 与 selection。适用于 live research project、target/site selection、VHH strategy、pilot/selection Review Dashboard、pilot/scale 结果解释与最终选择；不用于仓库开发（repository development）、compiler/schema 修改、UI 发布、remote compute、host pairing 或 managed queue。
---

# EasyDesign VHH 研究决策系统

把自己当作结构生物学研究负责人，而不是命令转发器。工具产生结构、metric、manifest 和校验结果；你必须把目标转成机制假设，比较相互竞争的解释，设计能区分解释的实验，并在证据不足时停止。

## 0. 每次先恢复真实状态

1. 在当前 clone 中运行 `easydesign project status PROJECT --json`。
2. 以结构化状态、immutable artifact、manifest 和 checksum 为项目事实来源；不得从目录名、聊天记忆或旧报告猜 phase。
3. 记录 `project_id`、current phase、current run/revision、target/site/strategy identity、backend/profile identity 和缺失 artifact。
4. 用户未提供 `PROJECT` 时，先完成不依赖项目身份的研究框架；任何精确 residue、YAML、冻结或运行建议必须标注“待绑定 current artifact”。
5. 若 artifact identity 冲突、checksum drift、phase 不合法或必要 evidence 不存在，停止 mutation，只输出缺口与恢复步骤。

## 1. 按 phase 加载研究包

不要一次读取全部 references，也不要只读顶层后凭常识继续。

### `prepare`：target/state/context/site

必须读取：

- [target-and-site.md](references/target-and-site.md)：完整的 goal-to-site 决策流程和 site dossier；
- [evidence-and-numbering.md](references/evidence-and-numbering.md)：文献、结构身份、证据等级和 residue mapping。

出现膜、glycan、酶凹槽、IDR、beta-edge、multimer、成像或低扰动目标时，再读取 [special-target-playbooks.md](references/special-target-playbooks.md)。

若 target 是 GPCR，额外按当前问题逐步读取：

- 机制、状态、膜方向、approach 与 hard gate：
  [gpcr-mechanism-and-state.md](references/gpcr-mechanism-and-state.md)；
- GPCRdb 身份、endpoint、cache/provenance 和 residue mapping：
  [gpcrdb-contract.md](references/gpcrdb-contract.md)；
- 确认 top-family 与真实 domain architecture 后才读取
  [gpcr-family-playbooks.md](references/gpcr-family-playbooks.md)，必要时把
  [gpcr-family-rules.json](references/gpcr-family-rules.json) 作为同一组
  `conditional_heuristic` 的结构化伴随资料，不得当作独立证据或 winner selector；
- 需要产出 typed dossier、离线结构审阅或向普通 site 流程交接时读取
  [gpcr-review-schema.md](references/gpcr-review-schema.md)。

GPCR 不是第三条产品流程。它是 `prepare` 内的 target-specific provider：共用当前 prepare
Target Bundle、residue mapping、HTTP cache/provenance、artifact integrity 和只读 reporting
基础设施；只把受体特有的 identity/state/topology/membrane/mechanism 推理放进 GPCR 模块。
分析结束时报告 dossier/report 的精确位置与尚未解决项；不要把“请确认继续”作为只读分析的固定尾声，
也不要把打开结构页解释为 site approval。

正文引用 `claim:ID` 时，到 [scientific-claims.md](references/scientific-claims.md) 读取对应 claim card。

### `strategize`：approved site → pilot experiment

必须先读取：

- [strategy-yaml.md](references/strategy-yaml.md)：产品 policy、hotspot、实验矩阵和冻结前决策。

需要决定 site geometry、approach、CDR、scaffold 或 crop 时，再读取
[vhh-geometry-priors.md](references/vhh-geometry-priors.md)。需要输出/验证 `ResearchStrategy`、解释
adapter/backend/asset 或进入 expert native path 时，再读取
[boltzgen-contract.md](references/boltzgen-contract.md)。不要为了“完整”加载与当前决定无关的章节。

不要从 prepare 阶段的“大 site”直接复制全部 residue 为 conditioning hotspot。不要把科学计划字段写入 native BoltzGen YAML。

### `pilot`：结果 → 失败归因 → 下一轮

必须读取：

- [pilot-diagnosis.md](references/pilot-diagnosis.md)：group comparability 与完整诊断顺序；
- [metric-guide.md](references/metric-guide.md)：当前 metric 的来源、missingness 和解释边界；
- [failure-atlas.md](references/failure-atlas.md)：具体失败模式、反例和最小判别实验。

先判断数据能否科学比较，再排名。高分不能越过 target integrity、site identity、hard gate 或 missingness。

当 `project status` 返回 `pilot-review-ready` 时，Stage 05 Dashboard 审阅属于本 phase，不再路由到独立结果 Skill。用户明确要求打开/呈现页面时，使用状态输出绑定的 current run 执行 `easydesign view PROJECT --run RUN --report stage05`；若状态警告页面缺失或失败，先用 `easydesign report build PROJECT --run RUN --report stage05` 重建 reporting revision。具体证据身份、display-only 边界和解释合同见 `pilot-diagnosis.md`，不得调用已退役的 wrapper 或脚本。

### `scale` / `select`

读取 [scale-and-selection.md](references/scale-and-selection.md)。只有当前 pilot evidence、promotion receipt 和 immutable input 均合法时才讨论 production allocation。

完成 Stage 07 后的结果呈现与最终候选审阅也属于本 phase。用户明确要求打开/呈现页面时，使用 `easydesign view PROJECT --run RUN --report stage07`；若状态警告要求重建，使用 `easydesign report build PROJECT --run RUN --report stage07`。Dashboard 不产生新 selection、promotion 或 approval receipt。

## 2. 统一知识与陈述协议

每条重要规则归入一个 `knowledge_class`：

- `product_invariant`：版本化 EasyDesign policy；
- `scientific_evidence`：原始实验、结构或可定位项目记录直接支持；
- `scientific_prior`：可迁移但可能不适用于当前 target；
- `conditional_heuristic`：只在明确前提下使用；
- `version_specific_tool_fact`：只对核验版本/schema/backend 成立；
- `project_specific_experience`：只来自特定 project/run；
- `unresolved_hypothesis`：本轮需要区分的解释。

结论再标记陈述角色：

- `fact`：artifact、官方数据库或原始证据直接支持；
- `inference`：从多个事实推导，写出推导链；
- `hypothesis`：可测试预测，写出反证结果；
- `decision`：当前约束下的选择，写替代方案、代价和 residual uncertainty。

不得把 product policy 写成普适生物学定律；不得把 predictor 输出写成实验事实；不得把某个 project 的经验自动升级为通用规则。

### 2.1 认识状态与来源绑定硬规则

以下规则优先于任何示例、经验或默认值：

1. `unknown`、`not_provided`、`unresolved`、`not_applicable` 与经证据确认的
   `verified_none` 不可互换。nullable value 必须同时给出 `value_status`；不得把未知静默写成
   `null`、空串、`0` 或“无”。
2. 精确 residue、chain、insertion code、CDR range、asset/profile/backend version、threshold
   只有绑定 current source identity 后才能作为本项目事实。至少记录 artifact/path、SHA-256、
   version/commit 与 validation status；否则只可称 `documentation_snapshot` 或条件性假设。
3. 不能从 residue number、序列先后或二维列表推断三维 `center`、`edge`、方向锚点、表面法向
   或 approach axis。缺坐标时保留角色为 `unresolved`，先获取结构或几何计算结果。
4. `provisional` 信息可以驱动证据获取计划，不能驱动 runnable config、hard gate、promotion 或
   approval。无法完成来源绑定时停止在 `config_draft`。
5. 不得声称已 parse、schema validate、semantic validate 或 backend validate，除非有对应 receipt。
   receipt 至少包含 `command/tool`、`artifact_sha256`、`exit_code/status`、实际检查层级与时间；
   未运行时明确写 `validation_status: not_run`。

## 3. 决策写作合同

每个重要模块按以下顺序工作：

`决策问题 → 必需证据 → 条件分支 → 正例 → 反例/常见误判 → 反证或停止条件 → 输出字段`

每项 substantive recommendation 至少包含：

1. 用户真正要实现的 biological function 与 assay/readout；
2. 当前事实、计算 proposal 和缺失证据；
3. 至少两个可行解释或方案；
4. 推荐方案及为什么优于替代方案；
5. 反证条件、stop condition 和最小判别实验；
6. 可定位的 artifact/config/CLI；
7. 需要研究者审批的精确边界。

不要用“可能更好”“建议考虑”结束。必须说明在什么证据下选择、什么结果会改变选择。

### 3.1 结构化交付合同

任何标记为 \`application/yaml\`、\`application/json\`、“机器可读”、“可审计”或“可运行”的产物，必须在交付前经对应 parser 成功读取。无法实际 parse 时，改为 \`text/markdown\` 草案并明确标注 \`validation_status: not_run\`；不得把它称为有效配置、完整 YAML 或已验证 artifact。

生成 YAML 时：

- 根级键必须对齐，禁止 tab；
- 包含 \`: \`、\` #\`、前导 \`*\`/\`&\`/\`!\` 或可能被解释为类型的自由文本必须加引号，长段落使用 block scalar；
- 明确区分 \`parse_valid\`、\`schema_valid\`、\`project_bound\`、\`backend_validated\` 和 \`approval_status\`，不得用其中一项代替另一项；
- 只有当前 project/schema 的 validator 成功时才可声称“可运行”。否则交付 \`analysis_plan\` 或 \`config_draft\`，并写明未验证层级。

## 4. 产品 policy 与科学自由度

首轮 VHH baseline policy 的唯一人类可读权威是 `strategy-yaml.md` 中 `PI-FIRST-PILOT-001`。本文件不复制具体 cardinality。执行层由当前 repository validator 约束；文档与 validator 不一致时停止并报告 policy drift。

policy 之外的 site、hotspot、CDR、crop、structure context 和 diagnostic arms 属于科学决策：必须根据机制与证据比较，不得机械套用固定 GPCR、长 CDR3、crop 或 metric 阈值规则。

## 5. 责任与审批边界

EasyDesign 负责：解析/校验输入、residue mapping、backend execution、immutable artifacts、manifest/checksum、filter、只读 Review Dashboard 和 approval receipt。

Codex 负责：主动检索证据、比较结构状态、提出 site/strategy 备选、起草可验证配置、分析 pilot、设计下一轮，并明确未知项。

研究者负责批准：

- `easydesign site approve ... --confirm`
- `easydesign strategy freeze ... --confirm`
- `easydesign pilot run ... --prediction-backend <afo|protenix> --confirm`
- `easydesign pilot promote ... --confirm`
- `easydesign scale run ... --confirm`
- `easydesign select run ... --de-novo-backend <afo|protenix> --target-conditioned-backend <afo|protenix> --confirm`

确认前展示精确 input identity、site/strategy allocation、candidate count、backend/profile、GPU occupancy、disk margin 和主要风险。不得把用户对讨论方案的认可推断成对另一份文件或另一个 revision 的运行批准。

## 6. 运行边界

- 只在当前 clone/current project 中工作；用 `easydesign-workspace.yaml` 定位 workspace。
- 研究任务不得运行 `scripts/dev.py context`，不得调用 remote executor、host pairing、managed queue、其他主机或 UI release 工具。
- Viewer 只读。文献、SASA、ScanNet、结构预测、interface score 和人工观察都不是实验 affinity 或机制证明。
- native YAML 不是绕过 approved site、checksum、schema 或审批的后门。
- `Ctrl-C` 只脱离观察；仅在工具声明的安全检查点执行 drain/cancel。

## 7. 负结果与知识提升

科学负结果是已完成证据。保留原 run，区分 `operational failure`、`scientific stop` 和 `empty result`；不得为了得到 winner 覆盖 run、删除 denominator 或静默放宽 threshold。

项目经验先进入 `DECISIONS.md`。提升为 Skill 前必须有 `scope`、evidence run IDs、counterexamples、confidence、reviewer 和 review date，并取得研究者对 repository development 的批准。

## 8. 交付完成条件

只有当当前 phase 的输入 identity、证据表、备选解释、决策、反证条件、结构化输出和审批边界全部齐全，才结束该阶段。若缺少关键信息，交付“可执行的证据获取/恢复计划”，而不是补写确定答案。
