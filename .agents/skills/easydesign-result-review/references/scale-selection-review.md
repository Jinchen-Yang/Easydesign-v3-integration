# Scale / Select 大批量结果网页合同

当前第一版生成器以 Pilot 模式为实现目标。本章锁定后续模式，防止直接把 Pilot Top-N 页面放大到
数万候选。

## 必须回答的问题

- 全部候选经过 identity、hard gate、去重、sequence/pose cluster 后各剩多少；
- strategy/scaffold lineage 是否过度集中；
- Pareto front 覆盖哪些 mechanism、pose、sequence 与 developability tradeoff；
- proposed panel 的 lead/control slots、cluster cap 和总数是否算术可行；
- shortlist 的代表、runner-up、异常点和风险 control 结构如何比较；
- desired effect 与 forbidden effect 有哪些实验验证。

## 性能与数据边界

- HTML 不嵌入全部结构；只嵌入汇总索引和已批准 shortlist 的本地结构副本；
- 聚类与 filter 必须来自正式 artifact，不在浏览器中临时重算；
- 页面筛选只改变视图，不改变候选状态或 selection receipt；
- hard-gate failure 不得显示为 lead；control 必须有显式 role/risk；
- `panel_total`、`lead_slots`、`control_slots`、`controls_inside_total`、`cluster_cap` 与
  `cluster_cap_applies_to` 必须明确且可行。

## 上线前置条件

实现前必须确认 Stage 06/07 的正式 candidate index、cluster artifact、selection report、结构引用和
profile identity；为它们建立独立 fixture 和浏览器测试。缺任一合同只交付 capability gap，不扫描
目录构造替代数据。
