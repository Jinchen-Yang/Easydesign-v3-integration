# 当前 BoltzGen / EasyDesign strategy 技术合同

本章只描述当前 clone 已核验的 schema、compiler、asset 与 backend 边界，防止科学构想被翻译成不存在的字段。科学决策在 [strategy-yaml.md](strategy-yaml.md)；这里不重复首轮 policy 数字。

## 目录

1. 固定 identity
2. 两层 schema
3. Standard explicit path
4. Compiler 生成的 native YAML
5. Hotspot 与 residue 合同
6. Crop 与 CDR override
7. Scaffold registry 与 asset
8. Unsupported / not automatic
9. Native expert path
10. Validation 与 provenance
11. Contract failure 输出

## 1. 版本化 identity snapshot

`knowledge_class: version_specific_tool_fact`

- EasyDesign：`0.1.0.dev1`
- BoltzGen：`0.3.2`
- BoltzGen commit：`a3149cf18eeb58648d1abbb27539bd73f746cdda`
- pinned source-tree SHA-256：`1f9e0b2405e89ac7778ea5b98d5ce4eddf739be0f3ac4c6432378a8811fe7590`
- strategy profile：`boltzgen-vhh-basic-v1`
- scaffold registry：`official-vhh7-v1`
- Stage 05 默认filter：`nanobody-filter-standard-v1.6`
- Stage 05 默认full-target backend：`protenix-v2`
- Stage 07 默认final filter：`nanobody-final-v1.5`
- external research schema：新写 `ResearchStrategy` `1.3`；历史 `1.0/1.1/1.2` 可读
- internal compiled `StrategyBundle`：`0.3`
- random seed status：`unsupported-by-boltzgen-0.3.2`

以上是 Skill authoring 时核验的 repository default，角色是 `documentation_snapshot`，不是任意
current project/run 的自动事实。使用精确字段、asset range、backend/profile 或 threshold 前，必须
读取 current frozen config/manifest/receipt 并输出 identity diff。无法读取时可以条件性描述默认
合同，但不得声称 current artifact 已绑定或已验证。

`nanobody-filter-standard-v1.7`只与显式选择且已安装、已验证的`openfold3-af3-jax`配对；它不是 v1.6 的静默升级、fallback 或“当前最新所以自动使用”的路径。

任何 backend probe、manifest、frozen config 或 source 返回不同 identity 时停止，输出 diff；不要猜兼容性，也不要把 strategy compile成功误写成 Stage 05 backend/profile 已验证。

## 2. 两层 schema

### 2.1 External `ResearchStrategy` 1.3

研究者/Agent编写的project config：

```yaml
schema_version: "1.3"
foundation: current
protocol_kind: first-pilot
prior_research_event_ids: []
variants: []
```

一个 standard variant 的真实字段：

- `id`
- `hotspot_set_id` 或 `binding_label_seq_ids`
- `scaffold_ids`
- `avoid_label_seq_ids`
- `target_crop`
- `cdr_overrides`
- `candidates`
- `hypothesis_id`
- `role`
- `evidence_refs`
- `changed_factors`
- `held_constant`
- `hypothesis_statement`（optional）
- `hypothesis_basis`（optional）
- `rationale`
- `expected_result`
- `failure_interpretation`

一个 native variant 另使用：

- `native_boltzgen_yaml`
- `native_boltzgen_sha256`

schema `1.3` 要求每个 variant 的 experiment metadata完整并显式区分 first-pilot/follow-up；
follow-up 必须引用连通的 Hypothesis→Observation→Interpretation Research Graph events。历史 schema
不被原地改写。

### 2.2 Internal compiler models

compiler 将 external variant 转成 `ExplicitStrategyVariant` 或 `NativeStrategyVariant`，再展开为每个 scaffold 的 `StrategyRecord` 与 immutable `StrategyBundle`。内部字段名可能为 `variant_id`、`candidates_per_strategy`，不应照抄回 external YAML。

### 2.3 反例

- external YAML 使用 `candidates_per_strategy`；
- 把`hypothesis_id`写入native BoltzGen YAML；
- 根据内部`region_id`拼出未经schema定义的field；
- 用schema `1.0`规避1.1实验合同。

## 3. Standard explicit path

### 3.1 可表达能力

standard adapter当前可表达：

- approved hotspot set 或其 approved residue 子集；
- 一个或多个 registry scaffold；
- target chain `A` 的连续闭区间 crop；
- 经明确批准、mapping 有坐标的 avoid residue → `not_binding`；
- 每条CDR至多一个design range与insertion range override；
- 每展开strategy的candidate count；
- 完整scientific experiment metadata。

### 3.2 编译语义

- variant按声明的scaffold局部展开，不执行隐式全笛卡尔积；
- `candidates`解释为每个展开后的strategy数量；
- target/scaffold asset复制到immutable run attempt；
- strategy ID包含variant/scaffold；
- scaffold override生成variant-local `scaffold.yaml`；
- compiler保留checksum、evidence与experiment metadata；
- native design YAML仅包含backend需要的技术字段。

### 3.3 不代表什么

配置能parse不代表：site科学合理、CDR range合理、target context完整、backend可运行、会产生binder或会有实验affinity。

## 4. Compiler 生成的 native YAML

普通 explicit variant 当前只生成以下已验证结构：

```yaml
entities:
  - file:
      path: ../../assets/target.cif
      include:
        - chain:
            id: A
            # 仅 target_crop 存在时加入：
            res_index: 10..200
      binding_types:
        - chain:
            id: A
            binding: 50,54,58
  - file:
      path: ../../assets/scaffolds/7eow.yaml
```

使用variant-local scaffold override时，第二个path为`scaffold.yaml`。

### 4.1 固定语义

- target chain固定为`A`；
- `binding`使用current target的`label_seq_id`；
- binding列表升序、唯一、正整数；
- 未选target residues保持`unmarked`；
- 只有显式 `avoid_label_seq_ids` 才生成 `not_binding`；其余 non-hotspot residue 保持 neutral；
- target file/scaffold path由compiler管理；
- scientific metadata不进入native YAML，而进入manifest/record。

### 4.2 反例

手工修改compiled YAML后继续使用原manifest/checksum；这会破坏immutable identity，应创建新的config/revision。

## 5. Hotspot 与 residue 合同

### 5.1 Standard constraints

- `hotspot_set_id`必须存在于current approved hotspots；
- 或`binding_label_seq_ids`必须是所有approved hotspot residues的非空子集；
- residue必须升序、唯一、为正整数；
- crop存在时必须覆盖全部binding residues；
- target structure SHA-256必须与hotspots绑定的target一致。

### 5.2 科学/技术边界

adapter只验证“合法且已批准”，不验证：

- 这些residues是否空间连贯；
- 整体VHH approach是否可行；
- 是否命中desired mechanism；
- 是否过宽/过窄；
- 是否被glycan/膜/partner遮挡。

这些由strategy phase完成并记录。

## 6. Crop 与 CDR override

### 6.1 Target crop

```yaml
target_crop:
  start: 10
  end: 200
```

语义：正整数、闭区间、`end >= start`、不超过Target Bundle `sequence_length`，并覆盖全部binding residues。standard adapter只支持一个连续区间。

它不表达：多段crop、保留非连续partner、膜、glycan、negative mask或assembly选择。若科学上必须表达这些，standard path能力不足。

### 6.2 CDR override

```yaml
cdr_overrides:
  - cdr: 3
    design_res_index: 98..116
    insertion_num_residues: 3..12
```

真实语义：

- `cdr`只能是`1|2|3`；
- 每条CDR最多一次；
- `design_res_index`替换该scaffold YAML中对应的design range；
- `insertion_num_residues`替换对应insertion range；
- override会为每个展开scaffold读取原始asset、修改相应项并生成local scaffold YAML。

`design_res_index`、`insertion_num_residues`与final loop length不是同一概念。字符串正则合法不证明其与每个asset的anchor、structure或backend相容。

### 6.3 必做校验

- 对每个scaffold显示原值→新值diff；
- 验证只改目标CDR；
- 检查range与anchor/residue numbering；
- 检查structure_groups/exclude/design_insertions仍一致；
- 运行当前BoltzGen backend check；
- 在experiment contract记录改变与反证。

## 7. Scaffold registry 与 asset

`official-vhh7-v1`绑定七个本地reviewed scaffold asset。每个asset包括CIF、YAML、SHA-256、source repository与source commit；compiler会逐字节验证内置expected hash，再复制到run attempt。

source repository：`https://github.com/HannesStark/boltzgen`

source commit：`a3149cf18eeb58648d1abbb27539bd73f746cdda`

详细CDR range 的 authoring snapshot 见 [vhh-geometry-priors.md](vhh-geometry-priors.md)。current 精确
range 必须从 materialized asset/manifest 读取并绑定 path+SHA-256；不得仅引用 Skill 表格生成 runnable
override。不得从scaffold名称推断current target上的性能，也不得使用同名但checksum不同的外部asset
替换而仍称同一registry。

### 7.1 Current asset 解析顺序

1. 从 current frozen `StrategyBundle`/manifest 取得 registry、BoltzGen version/commit 与 scaffold asset
   path；尚未 materialize 时，从当前 clone 的 compiler registry 解析 package，不凭 Skill 表格猜路径；
2. 对实际 YAML/CIF 计算 SHA-256，并与 compiler 的 expected hash/manifest 对照；
3. 从实际 YAML 提取 `design.res_index` 与 `design_insertions.num_residues`；
4. 逐 scaffold 输出 extracted default 与 proposed override diff；
5. 保存 backend check receipt。任一步缺失都保持 `asset_binding.status != verified`。

## 8. Unsupported / not automatic

以下能力不得作为current standard `ResearchStrategy`普通事实：

| 构想/字段 | current standard path | 正确处理 |
|---|---|---|
| `not_binding` | pinned 0.3.2 source 已核实支持 | 只由显式 approved `avoid_label_seq_ids` 生成 |
| `structure_groups` | asset内部存在，但external strategy不开放 | 不在普通config伪造；expert path需核验backend语义 |
| explicit random seed | bundle标记unsupported | 不承诺seed reproducibility |
| 多段/non-contiguous target crop | 不支持 | 保留full或使用经审批native方案 |
| 自动 negative complement | 禁止 | 未选择 residue 保持 neutral，不把 non-hotspot 自动设 avoid |
| arbitrary chain/assembly selection | standard target chain固定A | 在Target Bundle准备或native expert path解决 |
| glycan/membrane semantic field | 不支持 | 必须在输入structure/context中真实体现 |
| arbitrary backend parameter | 未开放 | 先查当前CLI/schema并验证native |

### 8.1 关键细节

官方scaffold asset YAML内部确实有`structure_groups`。这证明BoltzGen asset使用该字段，不证明EasyDesign external strategy允许用户随意写它，也不证明旧文档中的任意用法兼容当前backend。

### 8.2 停止条件

如果desired scientific experiment必须依赖unsupported能力：

1. 不用近似standard field冒充；
2. 输出`capability_gap`；
3. 评估是否可由已验证native expert path表达；
4. 需要修改adapter/schema/compiler时，停止research mutation，另开repository development任务。

## 9. Native expert path

### 9.1 进入条件

仅当standard adapter无法表达必要科学实验，且研究者明确理解可验证边界时使用。native path不是“更高级默认模式”。

### 9.2 合同

1. source YAML位于current project内；
2. 记录原文字节SHA-256；
3. variant只声明一个provenance scaffold；
4. 不同时声明`hotspot_set_id`或`binding_label_seq_ids`；
5. 仍填写完整 schema 1.3 experiment metadata；单-scaffold native variant 不满足首轮
   `7 × 40 × X`，因此只能用于带前序 event refs 的 follow-up/expert实验；
6. Agent/研究者人工检查native YAML引用的target/scaffold/chain/residue；当前native compiler只验证mapping、identity与backend check，不自动证明这些科学语义；
7. 使用current BoltzGen version/commit运行backend check；
8. 在limitations中列出EasyDesign不能验证的科学语义；
9. native YAML、checksum与validation output一起冻结；
10. 仍遵守site/freeze/run approval，不能绕过foundation。

### 9.3 Native external示例骨架

```yaml
- id: expert-native-001
  hypothesis_id: h-native-capability
  role: diagnostic
  scaffold_ids: [7eow]
  native_boltzgen_yaml: configs/native-expert-001.yaml
  native_boltzgen_sha256: REPLACE_WITH_EXACT_SHA256
  # candidates 使用 strategy-yaml.md 中 PI-FIRST-PILOT-001 的当前值
  evidence_refs: []
  changed_factors: []
  held_constant: []
  rationale: ""
  expected_result: ""
  failure_interpretation: ""
```

示例只展示field placement，不表示该native file已科学或技术批准；真实配置必须显式填写`candidates`并从`PI-FIRST-PILOT-001`读取当前值。

## 10. Validation 与 provenance

### 10.1 Validation pipeline

`easydesign strategy validate PROJECT --config FILE`至少应验证：

- external schema；
- current approved foundation；
- hotspot/residue subset与target length；
- first-pilot validator；
- registry identity与asset hash；
- compiled YAML生成；
- current backend version/commit；
- 每个compiled strategy check结果；
- planned candidate count；
- experiment metadata与manifest checksum。

上述validation会在`runtime/tmp` staging中编译并运行BoltzGen check后清理；它证明当前schema/compiler/backend合同成立，不证明site、context、crop、CDR或机制在科学上合理。

### 10.2 应检查的 artifacts

- `strategy-manifest.json` / `StrategyBundle`；
- scaffold resolution与asset hashes；
- per-strategy `design.yaml`；
- variant-local `scaffold.yaml`及diff（若有）；
- validation report与stdout/stderr hashes；
- target/hotspot/source stage manifest hashes；
- `random_seed_status`。

### 10.3 Validation claim receipt

报告 parser/schema/project/backend 结论时，为每层保存 `tool_or_command`、`input_sha256`、
`status/exit_code`、实际检查项与时间。没有 receipt 的层级写 `not_run`；不得写“Ruby/Python 已解析”、
“semantic checks 已通过”或具体 validator 版本。Agent/研究者人工检查也必须列出规则和结果，不能
冒充 compiler 自动验证。

### 10.4 正例

所有strategy backend check通过，bundle identity匹配，planned denominator与scientific matrix一致；freeze前仍展示exact file/revision，等待用户批准。

### 10.5 反例/误判

- YAML parser能读就说validated；
- 一个strategy通过就推断全部通过；
- backend version不同但“看起来字段一样”就继续；
- candidate数只按variant计、不乘scaffold展开；
- validation通过就越过freeze/run审批。

## 11. Contract failure 输出

```yaml
contract_failure:
  stage: parse|foundation|compile|backend-check|policy|identity
  observed_identity:
    easy_design_version: ""
    boltzgen_version: ""
    boltzgen_commit: ""
    strategy_profile: ""
    scaffold_registry: ""
  expected_identity: {}
  config_path: ""
  config_sha256: ""
  failing_variant_or_strategy: ""
  unsupported_field_or_semantics: ""
  source_artifacts: []
  safe_next_action: ""
  requires_repository_development: false
  mutation_status: stopped
```
