---
name: easydesign-result-review
description: 为 EasyDesign VHH/nanobody 研究生成和解释只读、可审计的结果网页，包括 Pilot 小批量实验组比较、hard-gate/missingness/代表成功与失败结构审阅，以及 Scale/Select 候选池、聚类、Pareto 与实验 panel 呈现。适用于“网页展示结果”“小批量筛选复盘”“pilot dashboard”“大批量筛选结果”“候选选择报告”；不用于 prepare/site 选点、重算筛选、修改 scientific artifact、自动 promotion/scale/select 或启动 GPU。
---

# EasyDesign 结果审阅

把网页当作证据索引和比较工具，不当作新的科学计算阶段。只从 current run 的
manifest/checksum 验证 artifact 构建报告；不扫描目录猜输入，不修改上游文件，不把展示排序提升为
新的 filter、affinity 或 approval。

## 1. 先恢复身份

1. 运行 `easydesign project status PROJECT --json`，取得 current phase 与 run identity。
2. 用户指定 run 时使用该精确 run；未指定时不得在多个 plausible run 中猜选。
3. Pilot review 只接受完成内部过滤阶段且包含 checksum-verified `strategy-bundle`、
   `candidate-index`、`pilot-filter-report` 的 run。
4. Scale/Select 只有相应 manifest/report 合同已实现并验证后才能生成；当前缺少时报告
   `capability_gap`，不得用 Pilot 字段伪装。

## 2. 选择模式

### `pilot-review`

读取 [references/pilot-review.md](references/pilot-review.md)，然后运行：

```bash
python .agents/skills/easydesign-result-review/scripts/build_result_review.py \
  --run-root RUN_ROOT \
  --output-root runtime/tmp/result-reviews/REVIEW_ID \
  --mode pilot-review
```

脚本只向全新输出目录原子发布派生报告。交付 `index.html`、`review-data.json`、
`review-manifest.json`、固定校验和的本地 Mol* viewer 与已验证的 shortlisted CIF 副本。展示完整
denominator、实验组合同、hard-gate failure、missingness、代表性成功和代表性失败；不能只展示
Top-N。

### `scale-selection-review`

读取 [references/scale-selection-review.md](references/scale-selection-review.md)。该模式必须以当前
Stage 06/07 manifest、cluster 和 selection artifact 为输入。若生成器声明暂不支持，输出输入缺口与
拟展示合同，停止执行；不得自行遍历数万结构或生成不可审计的临时排名。

## 3. 解释边界

- 分布、箱线图、pass rate 和 failure counts 只描述 frozen artifact；不重算 hard gate。
- missing 与 `0`、`not_applicable` 分开；不同 source/profile/version 不静默合并。
- 代表成功用于查看“合格例子”，代表失败用于诊断失败模式；都不自动代表整个实验组。
- 同一 baseline variant 的七个 scaffold 是一个 blocked comparison；diagnostic 必须对照 matched
  baseline，sentinel 结果不宣称 scaffold-general。
- 结构 viewer 只读取报告 manifest 中带 SHA-256 的本地 CIF；页面没有上传、编辑、审批或运行入口。
- 报告生成失败属于 reporting failure，不改变 scientific run、promotion eligibility 或 selection。

## 4. 与研究 Skill 协作

网页生成后使用 `$easydesign-research` 的 `pilot-diagnosis.md` 或
`scale-and-selection.md` 解释结果。Agent 的结构化诊断至少包含：

```yaml
observed_pattern: []
competing_explanations: []
evidence_for: []
evidence_against: []
minimum_discriminating_experiment: []
recommended_next_round: []
approval_required: []
```

不要把 Agent 解释回写进 immutable report；需要保留时作为新的项目 decision/dossier，由研究者按
现有审批协议处理。

## 5. 完成条件

结束前确认：

- source run、profile、artifact SHA 与生成器版本都在 `review-manifest.json`；
- report 中 planned/generated/evaluable/passed/missing denominator 没有被 Top-N 隐藏；
- 每个结构副本的 SHA 与来源 ArtifactRef 一致；
- HTML/JSON 没有外部 CDN、绝对服务器路径或 mutation/approval 控件；
- 输出路径位于 current clone 的 `runtime/` 或 `workspace/`；
- 页面只给出可观察证据，不声称实验 affinity、机制证明或自动决策。
