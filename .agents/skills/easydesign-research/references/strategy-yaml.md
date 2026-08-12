# Approved site → 可归因首轮 VHH pilot

本章是 `strategize` phase 核心，也是首轮 baseline 产品 policy 的唯一人类可读权威。它指导 Agent 从已批准 site 构造 scientific pilot matrix 与可验证 `ResearchStrategy`，而不是机械填 YAML。

## 目录

1. 输入与完成标准
2. 首轮唯一产品 policy
3. 冻结前 foundation 检查
4. Site 与 hotspot 的区别
5. Geometry、scaffold、CDR 与 crop
6. Experiment contract
7. Pilot matrix 设计
8. Candidate allocation
9. ResearchStrategy 1.1 模板
10. 编译、校验与冻结
11. 正例、反例与停止条件
12. Scientific pilot matrix 输出模板

## 1. 输入与完成标准

### 1.1 必需输入

- current project status 与 current approved foundation；
- approved target/site artifact、revision 与 checksum；
- `label_seq_id` mapping；
- design goal、mechanism、assay/readout；
- primary/backup/avoid site 与 evidence refs；
- target full/crop/context representations；
- backend/profile/scaffold registry identity；
- pilot budget 与环境预检信息。

### 1.2 完成标准

冻结前必须同时交付：

1. 每个 experiment group 的假设、只改变因素、保持因素与反证；
2. 首轮 baseline policy 合规证明；
3. hotspot、scaffold、CDR、crop/context 的 target-specific 理由；
4. 计划 candidate denominator 与展开方式；
5. 可由当前 schema 解析、由 compiler 编译、由 backend check 的配置；
6. freeze/run 两个独立审批边界。

### 1.3 Strategize decision kernel

按以下顺序执行；前一步未通过时不要跳到后一步补 YAML：

1. 锁定 approved foundation、target/site/mapping 与 current artifact identity；
2. 写出 primary mechanism、至少一个 competing hypothesis 与各自 falsifier；
3. 从 approved site 选择有三维证据的 hotspot topology；没有坐标则停止方向性命名；
4. 建立 `PI-FIRST-PILOT-001` 七 scaffold baseline；
5. 只为最大的不确定性增加少量 matched diagnostic；
6. 为每组声明 comparator、changed/held factors 与 generalization scope；
7. 逐 scaffold 核验 asset/CDR override，逐 representation 核验 crop/context；
8. 计算 expanded denominator，生成 config draft；
9. 分别记录 parse/schema/project/backend validation receipt；
10. 展示 exact revision 与风险，等待 freeze；run 仍需独立批准。

## 2. 首轮唯一产品 policy

### `PI-FIRST-PILOT-001`

`knowledge_class: product_invariant`

适用范围：当前 project 尚无任何 internal stage 05 pilot 时的首轮标准 VHH baseline。

规则：

1. baseline 必须覆盖 `official-vhh7-v1` 的全部七个且不重复 scaffold：
   - `7eow`
   - `7xl0`
   - `8coh`
   - `8z8v`
   - `gontivimab`
   - `isecarosmab`
   - `sonelokimab`
2. 每个展开后的 experiment group / strategy 必须计划 `40` 个 candidates；
3. baseline 计划总量不得低于 `7 × 40 = 280` candidates；
4. baseline 不得根据药物来源、单次先验、预测稳定性或个人偏好预筛 scaffold；
5. diagnostic/integrated-alternative 可以增加，但不能替代上述 baseline coverage；
6. 当前 repository 的 `ResearchStrategy` validator 是执行层。文档与 validator 不一致时停止并报告 `policy_drift`，不得自行选择一方继续。

这些数值是产品 policy，不是 VHH 普适科学规律。其他文档只引用 `PI-FIRST-PILOT-001`，不得复制成第二份权威定义。

## 3. 冻结前 foundation 检查

### 3.1 决策问题

当前 strategy 是否建立在同一个已批准 target/site revision 上？

### 3.2 必需证据

- `project_id`；
- approved target/site artifact path 与 SHA-256；
- current `SITE_CURRENT`；
- target structure/bundle checksum；
- hotspot sets 与 target mapping；
- design goal/mechanism/assay；
- current backend/profile identity。

### 3.3 条件分支

- 新 structure 只改善 representation、不改 identity/site：创建新的 strategy revision并保留关联；
- mapping、site residue、state 或 construct改变：返回 prepare 并重新 site approval；
- current pointer 与 dossier 不一致：停止写配置；
- project 尚无 approved foundation：可以起草 scientific matrix，不能 validate/freeze。

### 3.4 正例

策略明确记录 target checksum、site revision、hotspot set ID，并能追到批准 receipt；任何 binding residue 都是 approved hotspots 的子集。

### 3.5 反例/误判

从聊天中的 residue 列表创建 YAML，而 project current foundation 已更新。

### 3.6 停止条件

- checksum drift；
- site revision不唯一；
- binding residue不在 approved set；
- target sequence length 与 crop/mapping冲突。

### 3.7 输出字段

`foundation`, `site_revision`, `target_sha256`, `hotspots_sha256`, `mapping_artifact`, `foundation_status`。

## 4. Site 与 hotspot 的区别

### 4.1 核心定义

- `site`：机制相关、较大的允许/研究区域；
- `hotspot_set` / `binding_label_seq_ids`：本 experiment 用来条件化 approach 的少量、空间连贯、可解释 residue；
- `avoid`：不应被误用为 current standard adapter 的负 binding 字段；作为科学/分析约束保留。

### 4.2 决策问题

哪些 approved residues 最能规定预期 orientation、mechanism anchor 与空间覆盖，同时不把搜索过度锁死？

### 4.3 必需证据

- site 3D geometry 与 full-context accessibility；
- direct interface/mutagenesis/ligand/partner evidence；
- desired approach 与 forbidden volumes；
- residue mapping confidence；
- hotspot set 间的可判别性。

### 4.4 条件分支

- PPI blocking：优先 causal footprint anchor + directional edge；
- pocket：选择入口/机制 anchor，不把整个 floor全标；
- flat site：使用空间分散但单个 paratope可同时触达的 anchors；
- state-specific：优先 state-defining差异表面；
- imaging：避开 functional/partner interface，即使其 scan score 更高；
- scan 与 literature冲突：分别建立可比较的 evidence-linked hypotheses。

### 4.5 正例

approved site 含 18 residues。baseline hotspot 选 4 个覆盖界面中心与方向边；diagnostic 选另一个仍属于 approved site 的 4-residue set，测试 adjacent steric hypothesis。

### 4.6 反例/误判

- 将全部 18 residues 原样作为 binding；
- 选择空间相隔过远、单个 VHH 无法覆盖的 residue；
- 挑 mutation effect 最大的 residue，但 mutation 同时破坏 target fold；
- 用 `not_binding` 表达 avoid，尽管标准 adapter 不支持。

### 4.7 反证或停止条件

- hotspot 不形成单一可接近 3D patch；
- hotspot 位于 crop 之外或 artificial edge；
- mapping有歧义；
- hotspot无法对应任何可测机制预测。

### 4.8 输出字段

`hotspot_set_id`, `binding_label_seq_ids`, `source_site_id`, `geometry_role`, `mechanism_role`, `approach_prediction`, `avoid_contacts_for_analysis`。

## 5. Geometry、scaffold、CDR 与 crop

详细科学先验见 [vhh-geometry-priors.md](vhh-geometry-priors.md)，技术可表达性见 [boltzgen-contract.md](boltzgen-contract.md)。本阶段必须显式完成以下五个决定。

### 5.1 Hotspot topology

**问题**：hotspot 是否定义一个合理 paratope approach？

**证据**：3D 连贯性、表面法向、partner/ligand footprint、full-body clearance。

**分支**：需要不同 approach 时建立不同 group，而不是把互斥 residue 合并。

**正例**：PPI footprint 有两个可能 blocking orientation，形成 H_center 与 H_edge 两组。

**反例**：为“覆盖空间大”而把两个蛋白面合入一个 group。

**反证**：生成 pose反复 off-site或只能满足一部分远距离 hotspot。

**输出**：`hotspot_topology`, `approach_axis`, `expected_contact_pattern`。

### 5.2 Scaffold coverage

**问题**：怎样既满足 baseline policy又能观察 scaffold×geometry？

**证据**：`PI-FIRST-PILOT-001`、registry identity、current asset validation。

**分支**：首轮 baseline 全 registry。diagnostic 默认使用与 baseline 有 matched comparator 的一个
`sentinel scaffold`；需要检验 scaffold generalizability 时，才按有说明的 geometry/asset strata 选择
2–3 个 scaffold。只有科学问题明确是 scaffold interaction、且预算与审批允许时，diagnostic 才扩展
到全 registry。预算不足不能静默删 baseline，必须回到用户调整 scope/policy。

**正例**：一个 baseline variant列出全部 registry scaffold，compiler本地展开；一个 CDR3 reach
diagnostic 先在具备同 scaffold baseline 对照且 asset 已核验的 sentinel 上测试，成功后再确认迁移性。

**反例**：因为 target 是 GPCR而只选长 CDR3 insertion上限较大的两个 scaffold。

**反证**：registry/hash/backend drift，停止并报告。

**输出**：`scaffold_ids`, `registry`, `coverage_check`, `scaffold_scope`,
`sentinel_selection_rationale`, `generalization_scope`。

### 5.3 CDR design

**问题**：asset default 是否足以测试第一假设，是否需要某条 CDR 的 matched override？

**证据**：surface geometry、reach、asset ranges、backend validation、历史 pilot（若有）。

**分支**：

- baseline：asset defaults；
- single-CDR diagnostic：只覆盖一条 CDR；
- multiple-CDR integrated alternative：允许探索，但标 `role=integrated-alternative`，不承担单因素归因；
- long CDR3：只有 geometry/机制证据并有 matched control 时测试。

**正例**：deep cleft另设只改 CDR3 insertion的 diagnostic，prediction 是 hotspot coverage/reach上升而clash不恶化。

**反例**：将口语“CDR3 15–50”直接填入 `design_res_index` 或 insertion字段。

**反证**：asset diff改变错误 CDR；backend check失败；pose并未进入cleft。

**输出**：`cdr_overrides`, `asset_default_control`, `expected_geometry`, `falsifier`。

### 5.4 Target crop

**问题**：full target是否必要，crop是否保留真实 site/context？

**证据**：domain boundary、site-edge距离、assembly/membrane/glycan/partner、full-vs-crop validation。

**分支**：默认 full；只有独立稳定域且上下文可转移时设 crop diagnostic；若 crop用于主要生成，必须计划full-target confirmatory validation。

**正例**：大多域 enzyme 的独立 catalytic domain有实验 construct，site远离边界；保留 full representation用于复核。

**反例**：删掉遮挡site的native domain以提高可设计性。

**反证**：crop edge contact、full target pose drift、state/assembly丢失。

**输出**：`target_crop`, `boundary_evidence`, `artificial_surface_mask`, `full_target_validation`。

### 5.5 Context

**问题**：设计结构应包含哪些 ligand/partner/glycan/membrane/assembly？

**证据**：design goal、state、approach与assay material。

**分支**：blocking时保留/移除partner取决于要表达的机制，但必须用另一个context做steric review；state selection保留state-defining ligand/partner；imaging保留真实可达性context。

**反例**：为了简单一律使用apo monomer。

**停止**：当前 adapter无法表达必要context且native expert path也未验证；记录code capability gap。

## 6. Experiment contract

schema `1.1` 的每个 variant 必须形成完整科学合同：

- `hypothesis_id`：稳定、唯一、可追踪；
- `role`：`baseline`, `diagnostic`, `integrated-alternative`, `confirmatory`；
- `evidence_refs`：site dossier、claim、artifact、run；
- `changed_factors`：本组相对明确 comparator 改了什么；
- `held_constant`：为因果解释保持了什么；
- `rationale`：为什么这个改变能回答问题；
- `expected_result`：若假设成立，哪些可观测量怎样变化；
- `failure_interpretation`：若不成立，哪些解释被削弱、哪些仍保留。

### 6.1 因果可比性

`diagnostic` 最好只改变一个主要因素。若不可避免改变多个，必须拆分或降为 `integrated-alternative`。

候选数量相同不等于可比：site、scaffold、CDR、crop、context、backend/profile、filter、missingness和sampling都属于 comparator。

### 6.2 正例

`H_cdr3_reach` 组在一个 asset 已核验的 sentinel scaffold 上只改变 CDR3 insertion；其 matched
comparator 是 baseline 中同一 scaffold，held constant 包含 site/hotspot/scaffold/full target/count/
backend/profile。结果只支持该 scaffold 上的 reach 解释；跨 scaffold 结论需要后续 confirmation。

### 6.3 反例/误判

“尝试更激进参数，看看会不会好”没有可证伪预测，也没有 comparator。

## 7. Pilot matrix 设计

### 7.1 最小高信息矩阵

在 `PI-FIRST-PILOT-001` baseline 之外，根据 target最多优先加入能区分最大不确定性的少量组：

- `baseline-primary`：primary hotspot、asset default、full/主要 context、全 registry；
- `diagnostic-site`：primary vs backup site，只改变 site/hotspot；
- `diagnostic-hotspot`：同 site 不同 anchor/orientation；
- `diagnostic-cdr3`：只有 reach hypothesis时只改CDR3；
- `diagnostic-crop`：full vs evidence-backed crop；
- `diagnostic-context`：state/ligand/assembly representation；
- `integrated-best-alternative`：Agent认为最优的联合策略，但不用于单因素因果归因。

不是每个项目都需要全部组。选择原则是最大化“一个 pilot 后可排除多少竞争解释”，而不是最大化 YAML 数量。

`PI-FIRST-PILOT-001` 的全 registry 要求只约束 mandatory baseline，不自动复制到每个 diagnostic。
diagnostic 必须拥有 matched baseline comparator；sentinel 结果不得宣称 scaffold-general。若选择
2–3 个 scaffold，说明 strata 与仍未覆盖的范围；全 registry diagnostic 需要独立预算理由和审批。

### 7.2 覆盖空间与优先级

优先级顺序：

1. 会让整个 site 失效的 identity/state/context不确定性；
2. primary vs backup mechanism；
3. approach/hotspot topology；
4. scaffold×geometry；
5. CDR/crop search细化；
6. 次要数值微调。

### 7.3 正例

多域 enzyme 深凹槽：baseline-primary(full/default)；diagnostic-site(rim)；diagnostic-cdr3(same primary, only CDR3); diagnostic-crop(same baseline, validated domain crop)。这四组可分别检查 site、reach与crop。

### 7.4 反例/误判

一次列出数十个微小 hotspot 变体，却没有 backup mechanism或full/crop control；看似覆盖大，实际无法解释。

## 8. Candidate allocation

### 8.1 Policy floor

首轮所有展开 group按 `PI-FIRST-PILOT-001` 使用规定 candidates。不得给“更看好的”scaffold额外数量、给其他 scaffold减少数量后仍称 matched baseline。

### 8.2 超出 baseline 的预算权衡

- 优先给能区分高层不确定性的 diagnostic；
- 对 matched comparator保持相同 candidate数；
- integrated alternative只在baseline与关键diagnostic已覆盖后加入；
- 记录 `planned_candidates = sum(variant candidates × expanded scaffold count)`；
- 展示GPU、disk和estimated runtime，但不得自动run。

### 8.3 不允许

- 因预期某组差而减少其 denominator；
- 运行后删除 failed/duplicate/missing candidate改变planned denominator；
- 将 native expert variant混入baseline却不给独立provenance；
- 用候选数量弥补错误site/context。

## 9. ResearchStrategy 1.1 模板

以下是科学计划输入，不是 native BoltzGen YAML。示例中的 residue/范围是占位符，必须绑定 current approved artifact。

```yaml
schema_version: "1.1"
foundation: current
variants:
  - id: baseline-primary
    hypothesis_id: h-primary-site-default-vhh7
    role: baseline
    hotspot_set_id: hs-primary
    binding_label_seq_ids: null
    scaffold_ids:
      - 7eow
      - 7xl0
      - 8coh
      - 8z8v
      - gontivimab
      - isecarosmab
      - sonelokimab
    target_crop: null
    cdr_overrides: []
    candidates: 40
    evidence_refs:
      - site:site-primary@REVISION
      - claim:MECHANISM-ID
      - artifact:target-bundle@SHA256
    changed_factors:
      - scaffold_id
    held_constant:
      - target_state
      - target_context
      - approved_site
      - hotspot_set
      - target_crop
      - cdr_design
      - candidates_per_strategy
      - backend_and_filter_profile
    rationale: >-
      以 primary mechanism hotspot 和 asset defaults 建立首轮全 registry baseline。
    expected_result: >-
      若 site 与 representation 可设计，多个 scaffold 应产生 target integrity 合格、
      命中 hotspot 且不过度 framework-driven 的候选；scaffold 差异可后续复核。
    failure_interpretation: >-
      全组共同失败优先削弱 shared site/context/hotspot 或 pipeline 合同，
      不证明七个 scaffold 各自都不适合所有后续策略。
    native_boltzgen_yaml: null
    native_boltzgen_sha256: null
```

### 9.1 模板注意

- `id` 使用 external `ResearchStrategy` 字段；内部 compiler 会生成每 scaffold strategy；
- `hotspot_set_id` 与 `binding_label_seq_ids` 二选一；
- `binding_label_seq_ids` 只能是 approved hotspots 的非空子集，升序、唯一、正整数；
- 不同 scaffold的native CDR range不同。若一个override字符串对各asset不科学，拆成多个仍可比较的variant，不要假装统一；
- native expert variant合同见 [boltzgen-contract.md](boltzgen-contract.md)；
- 科学 metadata不得写入生成的native design YAML。
- 上述 canonical baseline 与产品生成的初始 draft 对齐。CDR/crop/context diagnostic 不提供可复制的
  通用数值模板：先绑定 current asset/representation，再创建只改变一个主要因素的独立 variant。

## 10. 编译、校验与冻结

### 10.1 顺序

1. 将 scientific matrix写成project内新strategy file；
2. 运行 `easydesign strategy validate PROJECT --config FILE`；
3. 检查 parser/schema；
4. 检查 approved foundation与residue subset；
5. 检查registry asset/checksum；
6. 检查每个compiled strategy的backend check；
7. 复核planned denominator、group expansion与experiment metadata；
8. 展示可读diff、风险和precision identity；
9. 等待用户执行/批准 `easydesign strategy freeze ... --confirm`；
10. freeze完成后，run仍需单独批准。

### 10.2 Validation receipt

每个 validation 层级分别记录，不得用笼统的“已验证”覆盖：

```yaml
validation_receipt:
  artifact_sha256: ""
  parser:
    status: not_run
    tool: null
    command: null
    exit_code: null
  schema:
    status: not_run
    validator: null
    exit_code: null
  project_binding:
    status: not_run
    project_id: null
    foundation_sha256: null
  backend:
    status: not_run
    backend_identity: null
    exit_code: null
  checked_at: null
```

只有对应 receipt 为 passed 才能声称该层通过。没有 command/tool receipt 时不得自行补 parser 名称或
版本；semantic review 必须列出实际规则与逐项结果。

### 10.3 Freeze 前检查表

- [ ] current project/phase合法；
- [ ] target/site revision与checksum匹配；
- [ ] design goal/assay仍未漂移；
- [ ] `PI-FIRST-PILOT-001`合规；
- [ ] 每组complete experiment contract；
- [ ] changed/held factors逻辑成立；
- [ ] hotspot 3D可达且mapping唯一；
- [ ] CDR override与每个asset核验；
- [ ] crop覆盖binding residues且无未处理artificial surface；
- [ ] backend version/commit/profile匹配；
- [ ] 所有compiled strategy backend validation通过；
- [ ] planned candidates、GPU、disk、runtime展示；
- [ ] freeze path/revision明确；
- [ ] 没有暗含run approval。

## 11. 正例、反例与停止条件

### 11.1 好策略的特征

- baseline满足产品policy；
- 最小组数覆盖最大机制/geometry不确定性；
- diagnostic尽量单因素；
- integrated方案显式降级因果解释；
- 每组都有可观察prediction和failure interpretation；
- 所有字段是当前schema真实字段。

### 11.2 常见失败

- 只生成一个“最优YAML”，没有备选假设；
- 把tool scan排名当site approval；
- 把site全部residues当hotspot；
- 根据target class预筛scaffold；
- 随意扩张CDR3范围；
- crop掉真实遮挡；
- 同时改变site、scaffold、CDR、crop后声称可归因；
- 将`not_binding`, `structure_groups`, seed当标准ResearchStrategy字段；
- validate通过即认为科学设计正确；
- freeze approval推断成run approval。

### 11.3 停止条件

- foundation/identity/checksum不一致；
- policy与validator drift；
- schema或backend identity不匹配；
- 必要科学意图无法由standard adapter表达，且native path未验证；
- group之间无有效comparator；
- crop/CDR override缺asset级验证；
- GPU/disk/候选总量未展示；
- 用户未看到exact freeze revision。

## 12. Scientific pilot matrix 输出模板

```yaml
pilot_plan:
  plan_id: pilot-plan-001
  project_id: ""
  foundation:
    target_sha256: ""
    site_revision: ""
    hotspots_sha256: ""
  design_goal_id: ""
  policy:
    id: PI-FIRST-PILOT-001
    compliance: pass|fail
    evidence: []
  backend_contract:
    easy_design_version: ""
    boltzgen_version: ""
    boltzgen_commit: ""
    strategy_profile: ""
    scaffold_registry: ""
    filter_profile: ""
  groups:
    - variant_id: ""
      hypothesis_id: ""
      role: baseline
      comparator: null
      site_or_hotspot: ""
      scaffolds: []
      cdr_policy: ""
      crop_context: ""
      candidates_per_expanded_strategy: 40
      changed_factors: []
      held_constant: []
      evidence_refs: []
      rationale: ""
      expected_result: ""
      failure_interpretation: ""
      primary_metrics: []
      structural_reviews: []
  planned_candidates: null
  config_path: ""
  validation:
    schema: pending
    foundation: pending
    backend: pending
    policy: pending
  unresolved_scientific_risks: []
  capability_gaps: []
  approvals:
    freeze: awaiting_user_approval
    run: not_requested
```
