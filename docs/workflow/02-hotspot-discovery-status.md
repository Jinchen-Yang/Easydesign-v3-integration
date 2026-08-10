# Stage 02 状态

稳定职责见 [`02-hotspot-discovery.md`](02-hotspot-discovery.md)。本文件只记录当前能力和仍
有效的验证事实，不保留旧工作台、结构助手或服务器操作说明。

| 总体状态 | 当前结论 | 更新时间 |
| --- | --- | --- |
| `implemented` | SASA、ScanNet、PSE/YAML 人工区域和显式批准契约已实现；完整科学 benchmark 尚未完成。 | 2026-08-10 |

## 当前能力

- 所有输入都从成功的 Stage 01 Target Bundle 和 manifest 读取并验证 checksum。
- `automatic` 可明确选择 SASA、ScanNet 或二者；两种方法的分数、排名和证据独立，
  不融合，也不自动选择赢家。
- SASA 支持多模型 coordinate ensemble；ScanNet 多模型策略尚未定义，必须明确失败。
- 人工区域支持 PSE 固定红/蓝/黄和 YAML 的 sequence/label/auth/UniProt 编号；成员只做
  映射、互斥和坐标校验，不自动扩展、删除或重新排名。
- `review-gated` 在候选生成后等待 2–3 个完整区域的显式人工批准；`unattended` 仅允许
  单一确定性方法和已满足契约的输入。
- 区域修改通过 Agent 生成可审阅的输入文件，再由 `site propose`、`site scan` 和带
  `--confirm` 的 `site approve` 执行；只读 Viewer 不承担编辑或批准。

## 外部服务边界

- 可选 UniProt annotation 只补充身份、功能、PTM 和 topology 证据，不参与方法排名。
- ScanNet、SASA 和批准流程在当前 clone 所在主机运行；没有公共算力、跨主机 job 或
  浏览器模型助手入口。

## 仍有效的验证事实

- 138-aa APOE 上 SASA/geometry 已完成真实 smoke。
- ScanNet epitope no-MSA 的显式 CPU 路径已在官方 1BRS 和 APOE 上完成 smoke；GPU
  兼容问题不触发静默 CPU fallback。
- APOE 的 PSE 颜色与 YAML auth 列表都得到 A/B/C=`9/14/14` 的同一规范成员，且分别
  保留不同 provenance。

## 待完成

- 增加独立 VHH–抗原正对照和预注册 benchmark，校准科学表现而非只验证工程闭环。
- 为多模型 ScanNet 定义并评审科学策略；在此之前继续 fail closed。
- required annotation、编号歧义、区域重叠或 checksum 不一致必须保持显式失败。
