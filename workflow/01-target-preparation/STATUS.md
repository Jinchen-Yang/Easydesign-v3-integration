# Stage 01 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态开发状态、验证证据和历史索引。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `planned` | sequence/FASTA MSA、单 Target PSE 与便携 Mol* Viewer 已真实跑通，其余四类入口待实现。 | 排期本地 PDB/mmCIF 与标准 Target Bundle 输入；Viewer 后续 overlay 留给 Stage 02。 | 公共 ColabFold 无 SLA；离线 MSA cache、自建服务与其余输入 adapter 未完成。 | 2026-07-24 |

## 当前结论

- 阶段总体状态：`planned`；六类入口尚未全部实现。
- sequence/FASTA → remote MSA → Protenix-v2 → Target Bundle 纵向切片状态：
  `smoke-validated`。
- 单 Target PyMOL PSE → imported Target Bundle 纵向切片状态：`smoke-validated`。
- Stage 01 Target Bundle → 自包含 Mol* 5.11.0 Viewer 状态：`smoke-validated`。
- sequence 和 PSE 成功路径都在正式 Stage/Run manifest 发布后自动生成 Viewer report；
  reporting failure 与科学状态分离，不阻塞 Stage 02 handoff。
- 报告只沿 manifest 声明读取并验证 artifact，复制 mmCIF、FASTA 和 mapping，页面不访问
  CDN；服务固定绑定 `127.0.0.1`，不暴露整个 run。
- PSE Viewer 用 label 编号映射恢复 101/9/14/14 来源颜色，页面明确标为
  `uninterpreted annotation`；Protenix Viewer 写 `not_applicable`，不显示颜色开关。
- PSE 真实 smoke 保留 138-aa imported 坐标和 101/9/14/14 的 CA 颜色分组；颜色没有被
  解释为 hotspot，也没有启动 Protenix、MSA 或结构预测。
- no-MSA 工程 smoke、真实输出解析和 Target Bundle 发布已通过。
- APOE 143-aa 序列本身没有阻止 MSA：显式使用
  `MMSEQS_SERVICE_HOST_URL=https://api.colabfold.com` 和
  `--msa_server_mode colabfold` 后，Protenix 官方 CLI 得到 609 条 unpaired MSA，并完成
  `use_msa=true`、`use_template=false` 的低预算 GPU 预测。
- sequence/FASTA schema `0.2` 已把 MSA 设为硬性正式路径：默认 provider 是
  `colabfold-public`，preset 固定解析到 `https://api.colabfold.com` 和
  `--msa_server_mode colabfold`；用户 YAML 禁止 no-MSA fallback。
- YAML 可按顺序声明 provider、timeout、最大 attempt 数和 retry backoff；解析后的实际
  endpoint/mode/预算进入 `resolved-config.json` schema `0.3`。adapter 已将 endpoint
  放入 MSA invocation 环境并设置 wall-clock timeout。
- 公共 ColabFold 不能被描述成永久稳定或具有 SLA。默认不把当前异常的
  `protenix-official` 放入 fallback；真正稳健的后续兜底是 sequence-hash MSA cache 和
  自建 `custom-colabfold` 服务。
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
| FASTA 文件 | `implemented` | 单记录解析；与同序列裸输入产生同一 SHA-256 |
| EasyDesign YAML 与自动识别 | `implemented` | schema 0.2 强制 MSA；provider 顺序、endpoint、timeout/retry 和禁止 no-MSA 测试 |
| Run Workspace | `implemented` | 一次实验一个目录、七 Stage 同级、snapshot、索引和浅层 attempt |
| 本地 PDB/mmCIF | `planned` | 无 |
| RCSB PDB ID | `planned` | 无 |
| UniProt accession/名称 | `planned` | 无 |
| PyMOL PSE | `smoke-validated` | 独立 PyMOL 3.1.0 环境；合成边界测试和旧 APOE PSE 真实 run |
| 标准 Target Bundle | `planned` | 目前能生成，尚不能作为输入导入 |
| 通用结构预测契约 | `implemented` | request/invocation/product 契约和测试 |
| Protenix-v2 adapter | `smoke-validated` | 真实 no-MSA CIF/confidence 收集成功 |
| 预测 Target Bundle 发布 | `smoke-validated` | 真实 143 残基 CIF 逐位映射并发布 6 个 artifact |
| ColabFold remote MSA backend | `smoke-validated` | 显式 endpoint 生成 609-depth APOE MSA；Protenix `use_msa=true` 预测成功 |
| MSA provider/endpoint policy | `implemented` | 默认 ColabFold preset、resolved plan、wall timeout 与显式 fallback 接口 |
| MSA-backed Target Bundle 发布 | `smoke-validated` | APOE 正式 run 发布 609-depth MSA、统一 mmCIF Bundle 和完整 manifest；Stage 02 真实读取器通过 |
| 预计算 MSA 复用 | `planned` | 枚举与 provenance 契约已预留；没有可用 APOE MSA artifact |
| 便携式 Mol* Target Viewer | `smoke-validated` | Mol* 5.11.0 本地资产、不可变报告 revision、localhost 服务、Chromium 与两条 APOE 报告 |

## Now

- 当前没有进行中的 Stage 01 工作项。REP-001 已关闭并归档；项目当前跨阶段重心是
  Stage 02 人工批准到 Stage 03 的交接。
- Stage 01 下一候选工作项是本地 PDB/mmCIF 输入 adapter，尚未开始，开始时必须另建任务
  编号和完成门槛。

## Next

- 将本地/预计算 MSA 作为可复现 profile；SMART 旧 cache 只作为可选历史审计来源，不再是
  当前主线的外部阻塞。
- 实现本地 PDB/mmCIF、RCSB PDB ID、UniProt 和标准 Target Bundle 输入 adapter。
- 扩展 PSE 到复合物、receptor/ligand、多聚体或人工 object/chain/state 选择前，先新增
  独立契约；当前严格单 Target adapter 不做隐式放宽。
- 增加本地 MSA 或预计算 MSA profile，支持不依赖公共队列的离线复现。
- REP-002/REP-003 在 Stage 02 单独实现 SASA/ScanNet overlay 与人工批准；Stage 01 Viewer
  继续保持只读，不保存 hotspot。

## Blocked

- Protenix 官方 MSA endpoint 在本轮新提交的同一 APOE 查询上仍持续 `PENDING`，而实际
  ColabFold endpoint 约 30 秒完成；官方 endpoint 当前不能作为可靠主线。
- `colabfold-public` 真实 smoke 已通过，但这是第三方公共服务且没有 EasyDesign 可承诺的
  SLA；在 cache/自建服务完成前，网络或上游停机仍会使正式 run 明确失败。
- 公共 provider 会向第三方提交 target 序列；当前仅批准内部研究 runtime。商业或敏感
  序列在条款/隐私审查和自建 provider 完成前仍受阻。
- 旧失败 attempt 没有保存 resolved endpoint 和 ticket，无法审计“ColabFold attempt”
  实际请求了哪台服务；不能事后把它当成 ColabFold 服务失败证据。
- 旧 SMART cache 未同步到 Proteindigger1；它只影响历史复现，不阻塞新 MSA 主线。

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

## 历史索引

- [2026-07：S01-001 至 S01-006](history/2026-07.md)
