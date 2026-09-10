# Stage 01 状态

稳定职责见 [`01-target-preparation.md`](01-target-preparation.md)。本文件只保留当前实现状态、
仍有效的科学验证结论和未完成门槛，不提供旧版本操作入口。

| 总体状态 | 当前结论 | 更新时间 |
| --- | --- | --- |
| `smoke-validated` | 六类输入、历史 Target Bundle 0.4、required-MSA 路径和只读 Target Viewer 已有真实 smoke；Target Identity v2 / Bundle 0.5 已完成 contract test，尚无新增 backend smoke。 | 2026-09-04 |

## 当前能力

- 支持裸序列、FASTA、本地 PDB/mmCIF、PDB ID、UniProt、单 Target PSE 和既有
  Target Bundle；所有输入最终发布统一 mmCIF、residue mapping、provenance 和 manifest。
- sequence/FASTA 正式路径要求显式 MSA；支持在线 MSA、按序列 hash 的本地 cache 和
  precomputed A3M，失败时禁止静默降级为 no-MSA。
- 807-member GPCR v3 数据保留为只读 legacy library；主体只按 canonical sequence SHA-256
  解析、验证和冻结，不再暴露批量 Stockholm 转换/建库 CLI。新 release 使用
  `runtime/databases/gpcr-msa/<release-id>/entries/<sequence-sha256>.a3m` 和独立 receipt。
- 当前训练2 `easydesign-local` checkout 的 template 接口只有 `disabled/precomputed`；
  250/400 GB OpenFold/AF3 结构库的 `template_mode: database` 搜索尚未在该 checkout
  验证。远端正式 run 只能引用已物化、带 SHA-256 的 template JSON。
- PSE 只接受一个蛋白 molecule object、一条有效 protein chain 和一个 state；颜色只作为
  `uninterpreted annotation`，不得解释成 hotspot。
- `review-gated` 在身份、链或结构选择处暂停；批准后在同一项目的新 attempt 中继续。
- 新写 Target Bundle 0.5 区分 canonical、experimental construct、observed coordinates 与
  design scope；engineered/isoform/ortholog/chimera/ambiguous mapping 要求人工 review，显式
  PDB source 不再被报告成 canonical biological identity 已解析。旧 0.3/0.4 保持只读兼容并
  标记 identity detail 不足。
- 下游只消费 bundle 冻结且 checksum 验证通过的 residue mapping；mapping 改变会使旧
  foundation 与 plan-bound approval 失效。
- Target Viewer 是自包含、只读的 Mol* 报告，只读取 manifest 声明且 checksum 正确的
  artifact；服务只绑定当前主机 loopback，不修改 Target Bundle。

## 外部服务边界

- RCSB、UniProt 和在线 ColabFold/MMseqs2 只提供结构、身份或 MSA 数据；计算编排、GPU
  任务、run 和 runtime 始终留在当前 clone 所在主机。
- 公共 MSA 服务没有可承诺的 SLA，并会接收 target 序列。敏感或受限序列必须使用本地
  cache、precomputed A3M 或另行部署的自有 MSA 服务。
- AFO remote-MSA helper 在独立进程中运行，输出先写 staging，经 JSON 重载验证后原子发布；
  中断或失败会清理 staging，服务返回的 tar 使用 Python safe extraction filter。失败不会
  静默回退到 query-only 或 no-MSA；每次成功会冻结 provider、endpoint、输入/输出 hash、
  chain A3M identity、隐私提示和 `fallback_used=false` receipt。
- Runtime 安装可以从已登记的 HTTPS 来源下载固定版本包、模型和数据，并在当前 clone 内
  校验 SHA-256；这不是远程执行入口。

## 仍有效的验证事实

- APOE 143-aa sequence 路径曾获得 609-depth MSA，并完成 `use_msa=true`、
  `use_template=false` 的 Protenix 低预算预测和 Stage 02 交接。
- APOE PSE 路径保留 138-aa imported 坐标及 101/9/14/14 的来源颜色分组，没有启动
  Protenix 或把颜色升级成科学结论。
- 1UBQ PDB、1D3Z 多模型 mmCIF、PDB ID、UniProt 和 Target Bundle 重导入均通过
  mapping、checksum、Viewer 与 Stage 02 读取 smoke。
- 2026-08-21 在已安装的 AFO 3.1.4 runtime 中，预填 MSA 的 AF3 JSON v4 通过真实 helper、
  MSA artifact 写出、原子发布和 `folding_input` 重载验证，确认当前 EasyDesign/AFO API
  兼容。该 smoke 不访问公共 MSA 服务。
- 2026-08-20 使用公开的人泛素序列请求 `api.colabfold.com` 时，两次连接超时，随后六分钟
  内未完成；任务已中断且临时目录已清理。因此当前网络下的 AFO 公共 remote-MSA 路径仍
  不能标记为 live-smoke 通过，历史 Protenix 在线 MSA 成功也不能替代这项证据。

## 待完成

- 非 canonical isoform、多 state PSE 和 Protenix 多 seed/sample 需要独立显式策略。
- 在线 MSA 的服务状态、隐私和条款仍需按部署场景复核；AFO 公共 remote-MSA 需要在可用
  网络或显式代理下补一次成功的 live smoke，不得把历史成功当作 SLA。
- Target Viewer 的科学边界保持只读；区域选择和批准属于 Stage 02。
- GPCR schema 1.0 library contract/resolve/snapshot 仍需用一个正式新 release 做 ops smoke；
  当前 807-member v3 仅作为 schema 0.2 兼容数据保留。正式设计仍需 target identity/state
  和研究者 site/strategy approval。
