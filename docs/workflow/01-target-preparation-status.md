# Stage 01 状态

稳定职责见 [`01-target-preparation.md`](01-target-preparation.md)。本文件只保留当前实现状态、
仍有效的科学验证结论和未完成门槛，不提供旧版本操作入口。

| 总体状态 | 当前结论 | 更新时间 |
| --- | --- | --- |
| `smoke-validated` | 六类输入、Target Bundle 0.4、required-MSA 路径和只读 Target Viewer 已有真实 smoke。 | 2026-08-10 |

## 当前能力

- 支持裸序列、FASTA、本地 PDB/mmCIF、PDB ID、UniProt、单 Target PSE 和既有
  Target Bundle；所有输入最终发布统一 mmCIF、residue mapping、provenance 和 manifest。
- sequence/FASTA 正式路径要求显式 MSA；支持在线 MSA、按序列 hash 的本地 cache 和
  precomputed A3M，失败时禁止静默降级为 no-MSA。
- PSE 只接受一个蛋白 molecule object、一条有效 protein chain 和一个 state；颜色只作为
  `uninterpreted annotation`，不得解释成 hotspot。
- `review-gated` 在身份、链或结构选择处暂停；批准后在同一项目的新 attempt 中继续。
- Target Viewer 是自包含、只读的 Mol* 报告，只读取 manifest 声明且 checksum 正确的
  artifact；服务只绑定当前主机 loopback，不修改 Target Bundle。

## 外部服务边界

- RCSB、UniProt 和在线 ColabFold/MMseqs2 只提供结构、身份或 MSA 数据；计算编排、GPU
  任务、run 和 runtime 始终留在当前 clone 所在主机。
- 公共 MSA 服务没有可承诺的 SLA，并会接收 target 序列。敏感或受限序列必须使用本地
  cache、precomputed A3M 或另行部署的自有 MSA 服务。
- Runtime 安装可以从已登记的 HTTPS 来源下载固定版本包、模型和数据，并在当前 clone 内
  校验 SHA-256；这不是远程执行入口。

## 仍有效的验证事实

- APOE 143-aa sequence 路径曾获得 609-depth MSA，并完成 `use_msa=true`、
  `use_template=false` 的 Protenix 低预算预测和 Stage 02 交接。
- APOE PSE 路径保留 138-aa imported 坐标及 101/9/14/14 的来源颜色分组，没有启动
  Protenix 或把颜色升级成科学结论。
- 1UBQ PDB、1D3Z 多模型 mmCIF、PDB ID、UniProt 和 Target Bundle 重导入均通过
  mapping、checksum、Viewer 与 Stage 02 读取 smoke。

## 待完成

- 非 canonical isoform、多 state PSE 和 Protenix 多 seed/sample 需要独立显式策略。
- 在线 MSA 的服务状态、隐私和条款仍需按部署场景复核；不得把历史成功当作 SLA。
- Target Viewer 的科学边界保持只读；区域选择和批准属于 Stage 02。
