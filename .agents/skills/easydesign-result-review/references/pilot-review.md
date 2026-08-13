# Pilot 小批量结果网页合同

## 1. 页面回答的问题

Pilot dashboard 必须帮助研究者判断：

1. 每个 experiment group 的计划、生成、可评价、hard-pass、unique-pass 是否完整；
2. 哪些规则造成失败，missingness 是否集中在特定 strategy/scaffold；
3. 七 scaffold 是共同失败、单 scaffold 失败，还是存在 scaffold×geometry 差异；
4. diagnostic 相对 matched baseline 改变了什么，结论能推广到什么范围；
5. 哪些成功/失败结构值得人工查看，下一轮需要区分哪些解释。

## 2. 输入合同

只接受同一 succeeded run 的 manifest-declared、checksum-verified：

- Stage 03 `strategy-bundle`；
- Stage 04 `candidate-index`；
- Stage 05 `pilot-filter-report`；
- 可选 Stage 05 expansion/advisory artifacts；
- `CandidateRecord.refolded_structure`，仅为 shortlisted candidates 复制到报告。

不得扫描 backend output、cache 或未被 manifest 声明的结构补全数据。report/profile schema 不支持时
明确失败，不按字段相似性猜版本。

## 3. 固定页面结构

- 深蓝 header：run/profile/status 与“只读派生报告”；
- 左侧独立滚动 strategy 列表：role、scaffold、tier、pass/total；
- 右侧独立滚动内容：denominator、组间比较、failure/missingness、candidate table；
- 结构区：本地 Mol*，显示 target chain A、binder 其他链、hotspot；
- provenance：source ArtifactRef 与 SHA、generator identity、生成时间。

窄屏可堆叠，但 strategy 列表保持有界滚动。不要用装饰性卡片替代密集、可审计的表格。

## 4. 代表候选选择

每个 strategy 最多默认复制：

- `best-pass`：`eligible_unique_pass=true` 中 `score_screen` 最高者；
- `typical-pass`：通过候选中最接近组内 `score_screen` 中位数者；
- `representative-failure`：失败候选中失败规则组合最常见者，再按 `score_screen` 与稳定 ID 排序。

同一 candidate 命中多个角色时只复制一次并保留全部 role。页面必须仍展示完整候选表/计数，不能
让 shortlist 取代 denominator。

## 5. 指标呈现

优先显示 frozen report 已提供且在同 profile 内可比的字段：

- `score_screen`；
- `hotspot-coverage`；
- `target-ca-rmsd`；
- `design-to-target-iptm`；
- `min-design-to-target-pae`；
- `cdr-dominance` / `cdr-utilization`；
- `interface-bsa` 与 source/fallback；
- clash/contact proxies。

每个 metric 保留 `available`、`missing_reason`、`source`、`unit`、`definition_version`。网页不创建
新的 aggregate score，也不把不存在的 metric 画成 0。

## 6. 科学解释提醒

- 全 scaffold failure 优先检查 shared site/context/hotspot/tool contract；
- 单 scaffold failure 只能支持 target-specific incompatibility proposal；
- high interface + target drift 不得 promotion；
- high contact + low CDR dominance 需要 framework/crop-edge review；
- missingness 不平衡时组间 rank 标记 `not-comparable`；
- promotion eligibility 只能引用 frozen report，不由网页按钮产生。
