# Stage 01 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态开发状态、验证证据和历史索引。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `smoke-validated` | 六类入口与 Target Bundle 0.4 已通过真实 APOE；REP-009 已把结构助手重构为完整 PML/Skill/SceneVersion 主循环，历史 typed 记录只读兼容。 | 冻结 Stage 01 科学边界；复验真实 provider 连续对话和双查看器投影。 | 无 Stage 01 1.0 工程阻塞；REP-009 的 live provider 浏览器矩阵待完成。 | 2026-07-31 |

## 当前结论

- 阶段总体状态：`smoke-validated`；六类 source、三种 required-MSA 来源、Viewer 和
  Stage 02 只读交接已在 Proteindigger1 完成真实矩阵。该状态不代表结构选择、预测或
  binder 设计达到科学验证。
- sequence/FASTA → remote MSA → Protenix-v2 → Target Bundle 纵向切片状态：
  `smoke-validated`。
- 单 Target PyMOL PSE → imported Target Bundle 纵向切片状态：`smoke-validated`。
- Stage 01 Target Bundle → 自包含 Mol* 5.11.0 Viewer 状态：`smoke-validated`。
- Stage 01 Target Bundle → Workbench 浏览器 PyMOL 2.6.0a0 / Mol* 双查看器状态：
  `smoke-validated`。两个查看器读取同一份 checksum 正确的 `target.cif`；显示会话不进入
  StageManifest，也不改变 Target Bundle。
- 同一 Workbench 结构页不再在切换时卸载浏览器 PyMOL canvas；返回 PyMOL 时在两个
  浏览器帧后同步 backing size、reshape、OpenGL viewport 和 redraw。静态 Pyodide/
  PyMOL 资产由浏览器缓存，但每个新挂载的 PyMOL canvas 使用独立运行时，禁止复用仍
  绑定旧 Emscripten WebGL context 的全局运行时。真实 APOE Stage 01/02 已完成
  `PyMOL → Mol* → PyMOL` 与跨 Stage 往返可见结构回归。
- dev28 再次收紧生命周期：隐藏 pane 不再使用 `visibility:hidden`，显示 revision 只重放
  最新 ViewState/PML，不累积全部历史命令；framebuffer `readPixels` 仅作诊断，不替代
  PyMOL 对象、原子和可见表示的严格 ready 门。
- REP-009 将新助手会话升级为 `StructureInteractionSession 0.4`：当前完整 PML、结构/
  场景 metadata、最近十轮对话和 `safe-pml + 最多两个动态 Skill` 进入模型；只接受
  `assistantMessage/summary/conversationTitle/pml` 四字段响应。安全追加增量执行，旧内容
  变化、历史恢复或增量失败时从已校验结构完整重放。Mol* 只投影支持的命令，不再限制
  PyMOL 原生场景；旧 typed proposal/ViewState 只读兼容。
- dev31 修正了 live 会话暴露的场景同步回归：重放/验证命令不再进入原生日志，
  瞬时 `deselect` 和重复命令不创建 SceneVersion，A/B/C overlay 放在全局配色之后。
  真实 APOE 空闲稳定性、9/14/14 配色和三轮双查看器往返均已通过。
- 通用 Target Bundle schema `0.4` 已声明 coordinate model count/IDs、代表 model、共享
  label identity 和 identity/scope/candidate/context evidence；兼容读取 0.1–0.3。
  PSE 与 Protenix 当前仍各发布单模型，这是 adapter
  限制而非全局结构限制。
- Viewer data `0.2` 显示 model 数量和代表 model；现有单模型 APOE 页面行为保持不变。
- 用户 YAML schema `0.6` 固定展示 `stage01`–`stage07`，旧 0.3–0.5 可兼容读取并显式
  迁移，run 内 `resolved-config.json` 统一保存 0.6。
- FASTA/UniProt 使用官方 RCSB sequence/data API 先查严格合格实验结构；本地结构、
  PDB ID、PSE 和 Target Bundle 均走同一 chain A、mapping、QC、manifest 与 Viewer 交接。
- `review-gated` 在 identity/chain/structure gate 暂停，审批后同一 run 新建 attempt；
  `unattended` 只按确定性规则运行，没有唯一实验结构时显式预测。
- sequence 和 PSE 成功路径都在正式 Stage/Run manifest 发布后自动生成 Viewer report；
  reporting failure 与科学状态分离，不阻塞 Stage 02 handoff。
- 报告只沿 manifest 声明读取并验证 artifact，复制 mmCIF、FASTA 和 mapping，页面不访问
  CDN；服务固定绑定 `127.0.0.1`，不暴露整个 run。
- PSE Viewer 用 label 编号映射恢复 101/9/14/14 来源颜色，页面明确标为
  `uninterpreted annotation`；Protenix Viewer 写 `not_applicable`，不显示颜色开关。
- PSE 真实 smoke 保留 138-aa imported 坐标和 101/9/14/14 的 CA 颜色分组；颜色没有被
  解释为 hotspot，也没有启动 Protenix、MSA 或结构预测。
- no-MSA 仅保留内部 adapter 回归；正式用户路径严格要求 remote、显式 cache 或
  precomputed A3M，任何失败都不得降级为 no-MSA。
- APOE 143-aa 序列本身没有阻止 MSA：显式使用
  `MMSEQS_SERVICE_HOST_URL=https://api.colabfold.com` 和
  `--msa_server_mode colabfold` 后，Protenix 官方 CLI 得到 609 条 unpaired MSA，并完成
  `use_msa=true`、`use_template=false` 的低预算 GPU 预测。
- sequence/FASTA schema `0.6` 已把 MSA 设为硬性正式路径：默认 provider 是
  `colabfold-public`，preset 固定解析到 `https://api.colabfold.com` 和
  `--msa_server_mode colabfold`；用户 YAML 禁止 no-MSA fallback。
- YAML 可按顺序声明 provider、timeout、最大 attempt 数和 retry backoff；解析后的实际
  endpoint/mode/预算进入 `resolved-config.json` schema `0.6`。adapter 已将 endpoint
  放入 MSA invocation 环境并设置 wall-clock timeout。
- 公共 ColabFold 不能被描述成永久稳定或具有 SLA。默认不把当前异常的
  `protenix-official` 放入 fallback；sequence-hash cache 和 precomputed A3M 已提供显式
  离线路径，自建 `custom-colabfold` 仍是商业部署待办。
- 正式 sequence executor 已实现：每次 MSA 重试/切换建立新 attempt，校验 A3M query、
  depth 和当前 attempt 路径，运行单 seed/单 sample Protenix，再发布与 PSE 对齐的
  `target.cif`/mapping/quality/provenance/Target Bundle/manifest 链。
- 正式 APOE run `runs/apoe/20260724-006-stage01-msa` 已用 commit `4ca3d8f` 成功完成：
  143-aa query、609-depth ColabFold MSA、`use_msa=true`、`use_template=false`、
  模型默认 10 recycle/200 diffusion steps，输出 143 个可映射残基的 mmCIF。
- Stage 02 的正式 `load_structure_context()` 已直接消费该 Target Bundle，校验结构
  artifact SHA-256 后读出单链 143 个残基；下游不需要扫描 Protenix 私有目录。
- “与 PSE 对齐”指交接契约一致，不指结构或残基编号强行相同：PSE run 是 138-aa
  imported 结构，保留 author chain A / residue 23–162；sequence run 是 143-aa predicted
  结构，编号为 1–143。二者均发布 `target.cif`（mmCIF）和显式 residue mapping。
- 先前所谓“ColabFold attempt”只记录了解析模式，没有保存 resolved endpoint 或 ticket，
  因此不能证明它真的请求了 ColabFold；该结论已在历史中追加更正。
- 旧仓在 Proteindigger1 没有保存 APOE MSA；文档提到的 SMART target feature cache
  尚未取回，但不再阻塞新建 MSA；不能用单序列 FASTA/AF3 JSON 冒充旧 MSA 测试。
- APOE fixture 是旧仓工程案例的 143-aa 片段，科学身份尚待 UniProt 路径独立复核。

## 功能矩阵

| 输入或能力 | 状态 | 当前证据 |
| --- | --- | --- |
| 裸氨基酸序列 | `implemented` | 严格规范化、标准氨基酸校验和 identity 测试 |
| FASTA 文件 | `smoke-validated` | APOE 143-aa 通过 remote、offline cache、precomputed 三条 required-MSA 真实预测 |
| EasyDesign YAML 与自动识别 | `smoke-validated` | canonical 0.5、六种 source union、双执行模式与 0.3/0.4 兼容迁移 |
| Run Workspace | `implemented` | 一次实验一个目录、七 Stage 同级、snapshot、索引和浅层 attempt |
| 本地 PDB/mmCIF | `smoke-validated` | 1UBQ PDB 与 1D3Z 10-model mmCIF 均规范为 chain A，Bundle/Viewer/Stage 02 读取通过 |
| RCSB PDB ID | `smoke-validated` | 1UBQ chain A live run，76 aa、1.8 Å X-ray、Target Bundle 0.4/Viewer 成功 |
| UniProt accession/名称 | `smoke-validated` | P0CG48 与 UBC/taxon 9606 均解析 canonical identity，批准 1UBQ 后 attempt-0002 成功 |
| PyMOL PSE | `smoke-validated` | 独立 PyMOL 3.1.0 环境；合成边界测试和旧 APOE PSE 真实 run |
| 标准 Target Bundle | `smoke-validated` | 1UBQ Bundle 真实重导入，全部 evidence/context/retrieval checksum 与 Stage 02 交接通过 |
| Target Bundle coordinate ensemble | `smoke-validated` | 1D3Z 10-model ensemble 保留 model/mapping 并被 Viewer 与多模型 Stage 02 读取 |
| 通用结构预测契约 | `implemented` | request/invocation/product 契约和测试 |
| Protenix-v2 adapter | `smoke-validated` | 真实 no-MSA CIF/confidence 收集成功 |
| 预测 Target Bundle 发布 | `smoke-validated` | 真实 143 残基 CIF 逐位映射并发布 6 个 artifact |
| ColabFold remote MSA backend | `smoke-validated` | 显式 endpoint 生成 609-depth APOE MSA；Protenix `use_msa=true` 预测成功 |
| MSA provider/endpoint/cache policy | `smoke-validated` | 默认 ColabFold、online refresh、offline cache hit、precomputed A3M 与显式失败契约 |
| MSA-backed Target Bundle 发布 | `smoke-validated` | APOE 正式 run 发布 609-depth MSA、统一 mmCIF Bundle 和完整 manifest；Stage 02 真实读取器通过 |
| 预计算 MSA 复用 | `smoke-validated` | 609-depth APOE A3M 经 query/hash/depth 校验后真实 `use_msa=true` 预测 |
| 便携式 Mol* Target Viewer | `smoke-validated` | Mol* 5.11.0 本地资产、不可变报告 revision、localhost 服务、Chromium 与两条 APOE 报告 |
| Workbench PyMOL/Mol* 双查看器 | `smoke-validated` | 离线 Pyodide/PyMOL WASM 资产、真实 APOE 138-aa/PSE 颜色、双向反复切换及结构 SHA 不变 |
| ChatPyMol 完整 PML 结构助手 | `implemented` | 四字段响应、动态 Skill、最近十轮对话、SceneVersion 0.4、乐观并发、增量/完整重放和 Mol* 兼容投影工程测试通过；live provider/APOE 连续对话待复验 |

## Now

- REP-009 工程实现已完成；下一门槛是以仓库平台 provider 对真实 APOE 连续执行完整 PML
  编辑、历史恢复和 PyMOL/Mol* 多轮切换。Stage 01 科学边界仍冻结为 canonical
  UniProt、单 Target/单 state PSE、单 seed/单 sample Protenix 和显式 required-MSA。

## Next

- 实现非 canonical isoform 选择和服务端 ticket/status 采集。
- 为多 state PSE 和 Protenix 多 seed/sample 分别设计显式 ensemble 策略；不得自动
  选择或平均输出。
- 扩展 PSE 到复合物、receptor/ligand、多聚体或人工 object/chain/state 选择前，先新增
  独立契约；当前严格单 Target adapter 不做隐式放宽。
- 部署并验证自建 ColabFold/MMseqs2 服务，用于商业或敏感序列。
- REP-002/REP-003 在 Stage 02 单独实现 SASA/ScanNet overlay 与人工批准；Stage 01 Viewer
  继续保持只读，不保存 hotspot。

## Blocked

- Protenix 官方 MSA endpoint 在本轮新提交的同一 APOE 查询上仍持续 `PENDING`，而实际
  ColabFold endpoint 约 30 秒完成；官方 endpoint 当前不能作为可靠主线。
- `colabfold-public` 真实 smoke 已通过，但这是第三方公共服务且没有 EasyDesign 可承诺的
  SLA；未显式准备 cache/precomputed A3M 的在线 run 在上游停机时会按契约失败。
- 公共 provider 会向第三方提交 target 序列；当前仅批准内部研究 runtime。商业或敏感
  序列在条款/隐私审查和自建 provider 完成前仍受阻。
- 旧失败 attempt 没有保存 resolved endpoint 和 ticket，无法审计“ColabFold attempt”
  实际请求了哪台服务；不能事后把它当成 ColabFold 服务失败证据。
- 旧 SMART cache 未同步到 Proteindigger1；它只影响历史复现，不阻塞 1.0 主线。

## 验证证据

### 服务器与环境

- Proteindigger1：2 × RTX 4080，每卡 32,760 MiB；driver `580.105.08`，compute capability
  `8.9`；`/root/autodl-tmp` 审计时可用约 77 GiB。
- Conda 环境：`/root/autodl-tmp/conda_envs/protenix-v2`，Python `3.11.15`，
  `protenix 2.0.0`，PyTorch `2.7.1+cu126`；`pip check` 通过，两张 GPU 可见。
- 独立环境包含 `cuda-nvcc 12.6.85` 和 `cuda-libraries-dev 12.6.3`；LayerNorm CUDA
  扩展已在该环境编译。
- checkpoint：
  `models/protenix/checkpoint/protenix-v2.pt`，1,859,785,497 bytes，
  SHA-256 `8f931f9774a396b67033d0e58628e1834f4a1448165e04254b40a780b0c0d599`；
  CPU 反序列化得到 4,174 个 model tensors。
- 2.0.0 包内官方 checkpoint URL 在 2026-07-24 返回 HTTP 403；实际从社区备份恢复，
  只有在公开 LFS SHA-256 完全匹配且 PyTorch 完整加载后才接受，具体来源已登记；因缺少
  可访问的官方 checksum，目前只批准内部 runtime 使用，公开 release 前必须再做官方核验。

### no-MSA 工程 smoke

- run：`runs/_development/protenix-v2/apoe-no-msa-smoke-20260724/attempt-0002`。
- 配置：`protenix-v2`、seed `101`、1 recycle、5 diffusion steps、1 sample、
  `use_msa=false`、`use_template=false`。
- 结果：前向 6.57 s；CIF SHA-256
  `e056cdab5b9a602fc51187aad2cb9dab6f231e8d788ec9bedc35d7c19cd70964`；
  confidence SHA-256
  `88a0655909afc6b32a06853863fee5a2ef8f516432735e56a146883c5efcba80`。
- smoke 输出 `pLDDT=80.90`、`pTM=0.143`；这些低预算数值不作为科学质量结论。

### EasyDesign adapter 与 Target Bundle

- adapter 实际读取上述 Protenix 2.0.0 目录协议，未扫描或猜测其他文件。
- run：`runs/apoe/20260724-001-stage01-no-msa`，`attempt-0001`；这是只整体迁移的
  `legacy-0` 布局，内部旧 `attempts/` 层保持不变。
- 143 个结构残基与规范输入逐位一致；Target Bundle SHA-256
  `1417adfc60cd9ab6f6778e2712c2fdb90accdaaaa888a7c6820e2bb1b5ed7c08`。
- `make check` 和 63 个 pytest 全部通过；严格 mypy 和 ruff 通过。

### PyMOL PSE import

- 环境：`/root/autodl-tmp/conda_envs/pymol-pse`，Python `3.11.15`，
  `pymol-open-source 3.1.0`；core 环境没有安装或导入 PyMOL。
- 合成 session 覆盖成功导入，以及零蛋白、多 object、多 chain、多 state、配体、
  非标准残基和损坏 PSE 的明确失败；adapter 另有版本、timeout、非零退出和缺失输出测试。
- runtime-only fixture：397,738 bytes，SHA-256
  `7d382a2fd158bd4664ef3d17296591e380ff01232926ed5bc86a9bcd7a813651`。
- 正式 run：`runs/apoe/20260724-002-stage01-pse`，object `1B68`、chain `A`、state 1、
  138 个标准残基；sequence SHA-256
  `f805c6ca91a7d925814212be97c34f0de339067c8a7ade2826dd5168da6bd2af`。
- CA 颜色计数：index 26 / `#33FF33` 101，red 9，blue 14，yellow 14；
  `source-annotations.json` 标记为 `uninterpreted`。run 内没有 Protenix input、MSA 或预测。
- Target Bundle 0.2、Attempt、StageManifest、RunManifest revision 2 和 `LATEST` 审计链
  全部发布；Target Bundle 0.1 兼容读取测试通过。

### remote-MSA attempts

- 目录：`runs/_development/msa-services/apoe-remote-no-template-20260724`。
- `attempt-0001`：Protenix MSA 服务，`2026-07-23T18:59:06Z` 开始，持续
  `PENDING` 超过 30 分钟，终态 `failed` / `remote-msa-timeout` / retryable。
- `attempt-0002`：配置了 `--msa_server_mode colabfold`，`2026-07-23T19:14:36Z`
  开始，持续 `PENDING` 超过 20 分钟，终态 `failed` /
  `remote-msa-timeout` / retryable；由于没有保存 resolved endpoint，不能证明它访问了
  `api.colabfold.com`。
- 两条均未生成 MSA artifact，因此没有启动假定存在 MSA 的正式预测，也没有降级为 no-MSA。

### APOE MSA 根因诊断与 backend smoke

- 对同一 143-aa 规范序列做串行 endpoint 对照：Protenix 官方
  `https://protenix-server.com/api/msa` 的新 ticket 在 120 秒内始终 `PENDING`，
  下载返回 HTTP 500；`https://api.colabfold.com` 在约 30 秒完成，下载 34,521-byte
  archive。两端 DNS、TLS 和基础 HTTP 均可达。
- Protenix 2.0.0 的 `--msa_server_mode colabfold` 只选择结果解析模式，不自动修改
  `MMSEQS_SERVICE_HOST_URL`；默认 host 仍是 Protenix 官方服务。因此 mode 与 endpoint
  必须成对显式配置和留痕。
- 验证目录：
  `runs/_validation/protenix-apoe-msa-backed-smoke-20260724-001`。
- Protenix 官方 CLI 生成 `non_pairing.a3m`：124,933 bytes、609 条序列、SHA-256
  `12d913001bd955c05544b084f396f6b17bc0086ae69cfca5cd376ab722f72716`；首条 query 与
  143-aa 输入完全相同。单体没有 `pairedMsaPath` 属于预期行为。
- 低预算 GPU smoke：seed 101、1 recycle、5 diffusion steps、1 sample、
  `use_msa=true`、`use_template=false`；模型实际特征 `N_msa=550`，前向 5.03 秒，
  生成 115,257-byte CIF，summary `pLDDT=84.35`、无 clash。该数值只证明工程链路，
  不代表科学质量或优于 no-MSA。

### APOE 正式 MSA-backed Stage 01 纵向切片

- 代码：commit `4ca3d8f2743c206583453c03af352c906c586df8`；正式 run：
  `runs/apoe/20260724-006-stage01-msa`，`attempt-0001`，RunManifest 与 StageManifest
  均为 `succeeded`。
- remote MSA：provider `colabfold-public`、endpoint `https://api.colabfold.com`、
  609 条序列、124,933 bytes、SHA-256
  `12d913001bd955c05544b084f396f6b17bc0086ae69cfca5cd376ab722f72716`；
  首条 query 与 143-aa 规范输入完全一致。
- Protenix-v2：`use_msa=true`、`use_template=false`、seed 101、单 sample、
  `model-default` 解析为 10 recycle 和 200 diffusion steps；输出 `pLDDT=83.01`、
  `pTM=0.818`、无 clash。这些数值只作为运行证据，不是科学成功声明。
- 正式 `target.cif`：118,776 bytes、SHA-256
  `71b58bc6975173f2238d8ae64009299054781d08db6ba26d9058924917246a44`；
  residue mapping 含 A 链 143 个连续 label/auth 残基。
- Target Bundle schema 0.2 SHA-256
  `2365f03c9b00586abf1d7139a30bdca8a40ea2117e6b65e05987135a0b16809b`；
  Stage 02 `load_structure_context()` 已只通过 Bundle 声明的结构和 mapping 成功读出
  143 个残基，并复核结构 SHA-256。
- PSE 与 sequence 路径都输出 mmCIF `target.cif`、sequence、mapping、quality、
  provenance、Target Bundle 和 manifest 链；只有来源特有 artifact 不同：
  PSE 额外保存未解释颜色 annotation，sequence 额外保存 MSA。
- Developer Preview CLI 已通过同一 orchestration API 暴露 sequence/FASTA 与 PSE
  Stage 01；这属于 UX/工程验证，不改变 Stage 01 总体 `planned` 状态。

### S01-008 六入口与双运行模式

- schema 0.4 覆盖 `local-file`、`pdb-id`、`uniprot`、`uniprot-search` 和
  `target-bundle` union；local-file 再区分 sequence/FASTA、PDB/mmCIF 与 PSE。
- unit/contract 覆盖 0.3→0.4、远程 404/429/5xx/timeout/cache、单/多模型结构、label/auth
  chain、最高 occupancy altloc、Bundle evidence 重导入、Decision revision/hash 和
  批准后新 attempt 恢复。默认测试不依赖互联网。
- schema 0.4 新 PSE run 同样规范 target label/auth chain A，并把原 PSE chain/residue
  保留到 `source_*` mapping；旧 APOE `Axp` artifact 不重写。
- 远程 retry/error/timeout 每次尝试均保存 evidence；最终失败发布 failed
  Attempt/StageManifest/RunManifest，不再留下只有初始 running manifest 的半成品 run。
- 真实 PDB smoke：`1UBQ` chain A 发布 76-aa experimental Target Bundle 0.4、
  `target.cif`/兼容 PDB、identity/scope/candidate/retrieval/source-context、Viewer 和
  RunManifest revision 2。
- 真实 UniProt smoke：
  `/root/autodl-tmp/s01-008-uniprot.OBb7ZH/runs/project/uniprot-p0cg48-live`；
  P0CG48 scope 1–76 产生多个严格合格候选（含 1UBQ），先停在
  `structure-selection`，批准 1UBQ 后以 `attempt-0002` 发布 Bundle，RunManifest
  revision 3 与 Viewer 成功。
- FASTA 已改为 RCSB experimental-first；无唯一候选才进入 review gate 或 unattended
  Protenix。API failure 与零候选使用不同错误，不允许静默 cache/fallback。

### S01-009 六入口 1.0 真实 smoke 矩阵

- Proteindigger1 固定 core Python 3.11、PyMOL 3.1.0、Protenix 2.0.0 与同一 runtime
  profile，使用 schema 0.5 完成：
  - 本地 `1UBQ.pdb`：76 aa、单模型、chain A；
  - 本地 `1D3Z.cif`：76 aa、10-model NMR ensemble；
  - PDB ID `1UBQ` chain A；
  - APOE 143-aa FASTA：ColabFold remote online refresh；
  - 同一 APOE FASTA：609-depth 预计算 A3M；
  - 同一 APOE FASTA：显式 offline sequence-hash cache hit；
  - UniProt accession `P0CG48` scope 1–76，批准 `1UBQ`；
  - UniProt name `UBC` / taxonomy 9606，唯一 canonical identity 后批准 `1UBQ`；
  - 旧 APOE 单 Target PSE：138 aa、来源颜色保留；
  - 1UBQ Target Bundle 真实再导入。
- 十条成功路径均发布统一的 target CIF、sequence、JSON/TSV mapping、quality、
  identity、scope、candidate、retrieval、provenance 和 Target Bundle；全部 ArtifactRef
  checksum、Viewer report 和 Stage 02 `load_structure_context()` 通过。
- 1D3Z 保留 10 个 model，Stage 02 读出 76 个共享残基；其他结构路径为单模型。
- remote/cache/precomputed 三条路径实际消费的 APOE A3M 都是 124,933 bytes、
  depth 609、SHA-256
  `12d913001bd955c05544b084f396f6b17bc0086ae69cfca5cd376ab722f72716`。
  provenance 分别记录
  `not-exposed-by-protenix-cli-2.0.0`、`cache-hit` 和 `precomputed`。
- schema 0.5 PDB ID `1UBQ` 继续运行 Stage 02 SASA 后达到
  `awaiting-human-approval`，证明正式 handoff 不依赖开发期扫描。
- live 验证发现本地 PDB 经 gemmi 重建 entity 时可能生成 label subchain `Axp`，与
  mapping 中的 chain A 不一致。修复为在序列化前显式设置 residue subchain A，并增加
  本地 PDB → Stage 02 回归；重跑后的本地 PDB 与 Bundle import 均通过。

### Target Bundle 0.3 与 canonical 配置回归

- runtime-only validation
  `/root/autodl-tmp/Protein_design/easydesign-clean-validation.lDkLYp/` 使用 schema `0.3`
  七阶段配置和原始 APOE PSE 完成真实 Stage 01。
- 发布的 Target Bundle schema `0.3` 声明 `model_count=1`、`model_ids=["1"]`、
  `representative_model_id="1"` 和 `shared-label-seq-id`；Stage 02 随后直接消费。
- Viewer data `0.2` 成功显示模型身份；Playwright 为 3 passed、2 skipped。完整 Python
  门禁为 151 passed、8 skipped；设置真实 PyMOL interpreter 后，8 项独立环境集成测试
  全部通过。wheel `0.1.0.dev2` 的 console script 与资产均通过。
- 当前证据只验证单模型 adapter 对新通用契约的兼容，不冒充真实多模型入口 smoke。

### REP-001 便携式 Mol* Target Viewer

- 固定 Mol* `5.11.0` 官方 npm tarball，npm integrity
  `sha512-Jv2oHkKoCpzrhqLmGlknepm0pfRsoTDebsGRkvXpbUFb6p+JIAkhLyM3uqV2twC6VR83ZbXtdswOtouPhozpuQ==`；
  vendored JS SHA-256
  `7fad5561c74bc900930fb57d6ab028d1aafdda82223a901bf932b1098e84f1f3`。
- Python 契约覆盖 running/succeeded run、失败 Stage、缺失/篡改 source、不可覆盖
  report revision、报告 checksum、失败不改科学 manifest、路径穿越和 symlink 边界。
- Playwright Chromium 通过真实 `127.0.0.1` 服务验证 Mol* canvas、无外部 HTTP 请求、
  representation/居中/下载、PSE 颜色开关、编号 mapping 和 WebGL 明确失败。
- 正式 APOE sequence report：
  `runs/apoe/20260724-006-stage01-msa/results/01-target-preparation/target-viewer/report-0002`；
  143 aa、predicted/Protenix-v2、MSA depth 609、annotation `not_applicable`。
- 正式 APOE PSE report：
  `runs/apoe/20260724-002-stage01-pse/results/01-target-preparation/target-viewer/report-0002`；
  138 aa、label chain `Axp`、author chain `A` / residue 23–162、颜色 101/9/14/14。
- 两份 report 复制到 run 外后仍可经同一受限服务打开；原 Stage 01 artifact、
  StageManifest、RunManifest 和 SHA-256 均未改变。该结论只证明工程展示链路，不构成
  结构科学验证。

### 旧仓 MSA 审计

- `package/easydesign_competition/data/apoe/msa/apoe4_fragment.fasta` 是单序列 FASTA。
- 同目录 `apoe4_fragment_af3.json` 只有 143-aa protein sequence，不包含 MSA/template
  字段。
- 旧仓和 Proteindigger1 上没有匹配 APOE 查询的 `.a3m/.sto/.aln/.msa`；旧文档引用的
  SMART `target_data.json` 与原始 AF3 data JSON 均不在本服务器。
- 结论：旧 MSA 复用路径仍为**未通过**，目前不能执行用户提出的预计算 MSA 测试。

## 工作日志

### 2026-07-24

- 关闭并归档 S01-001；Stage 01 当前工作切换为 S01-002。
- 审计旧仓、归档包和 Proteindigger1 alignment 文件，确认本机没有 APOE MSA asset。
- 保留两个公共 MSA 服务失败 attempt；等待 SMART cache 或公共队列恢复。
- 完成 S01-003：用户 YAML、自动 target 识别、Protenix JSON 生成和统一 Run Workspace。
- 将历史 smoke、MSA 诊断和正式 APOE Target Bundle 整体迁移到分区目录；迁移前后
  fingerprint 一致，并生成 `runs/run-index.json` 和不可变迁移清单。
- 完成并归档 S01-004：独立 PyMOL 环境、严格单 Target PSE 导入、未解释颜色 annotation、
  Target Bundle 0.2 和 APOE 真实 smoke。
- 完成 S01-005 根因诊断：确认 APOE 序列可生成 MSA；旧失败源于官方 endpoint 持续
  `PENDING` 以及 adapter 未绑定/记录 endpoint。显式 ColabFold endpoint 已通过 MSA 和
  `use_msa=true` backend smoke；S01-002 转为正式 adapter/Bundle 收尾。
- 完成并归档 S01-006：sequence/FASTA 正式 YAML 强制 MSA，默认 ColabFold preset 同时绑定
  endpoint/mode，resolved config 保存 timeout/retry/provider 顺序，adapter 禁止环境变量
  覆盖和 no-MSA fallback。
- 实现 S01-002 正式 executor：有界 MSA attempt、A3M identity/depth 校验、MSA-backed
  Protenix 预测、统一 `target.cif` Target Bundle 与 Stage/Run manifest 发布。
- 完成并归档 S01-002：模型默认参数 APOE 正式 run 成功，609-depth MSA、143-aa mmCIF、
  Target Bundle 和完整 manifest 链发布；Stage 02 真实读取器直接消费通过。
- 完成并归档 REP-001：Stage 01 两条成功路径自动生成自包含 Mol* 5.11.0 报告，报告失败
  不影响科学状态；localhost Chromium 和两条真实 APOE report smoke 通过。

### 2026-07-25

- 完成并归档 S01-007：Target Bundle `0.3` 正式声明 coordinate ensemble，保留
  0.1/0.2 读取兼容；PSE 与 Protenix 的单模型限制下沉到各自 adapter。
- canonical schema 0.3 的 APOE PSE 真实回归成功发布单模型 descriptor、Viewer 和
  Stage 02 handoff；真实多模型入口仍是下一项工作。
- 完成 S01-008：canonical schema 0.4、六类 source、官方 UniProt/RCSB retrieval、
  strict experimental-first、本地多模型结构、Target Bundle 0.4、通用 Decision Gate 和
  双运行模式进入统一 API；1UBQ 与 P0CG48→1UBQ live smoke 成功。

## 历史索引

- [2026-07：S01-001 至 S01-008](history/2026-07.md)
