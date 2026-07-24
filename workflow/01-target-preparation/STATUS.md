# Stage 01 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态开发状态、验证证据和历史索引。

## 当前结论

- 阶段总体状态：`planned`；六类入口尚未全部实现。
- sequence/FASTA → Protenix-v2 → Target Bundle 纵向切片状态：`implemented`。
- no-MSA 工程 smoke、真实输出解析和 Target Bundle 发布已通过。
- remote-MSA/no-template 的两个外部服务 attempt 均超时失败，未通过前不能把纵向切片标成
  `smoke-validated`。
- 旧仓在 Proteindigger1 没有保存 APOE MSA；文档提到的 SMART target feature cache
  尚未取回，不能用单序列 FASTA/AF3 JSON 冒充旧 MSA 测试。
- APOE fixture 是旧仓工程案例的 143-aa 片段，科学身份尚待 UniProt 路径独立复核。

## 功能矩阵

| 输入或能力 | 状态 | 当前证据 |
| --- | --- | --- |
| 裸氨基酸序列 | `implemented` | 严格规范化、标准氨基酸校验和 identity 测试 |
| FASTA 文件 | `implemented` | 单记录解析；与同序列裸输入产生同一 SHA-256 |
| EasyDesign YAML 与自动识别 | `implemented` | 用户 YAML 严格校验；FASTA/序列识别和无 fallback 测试 |
| Run Workspace | `implemented` | 一次实验一个目录、七 Stage 同级、snapshot、索引和浅层 attempt |
| 本地 PDB/mmCIF | `planned` | 无 |
| RCSB PDB ID | `planned` | 无 |
| UniProt accession/名称 | `planned` | 无 |
| PyMOL PSE | `planned` | 无 |
| 标准 Target Bundle | `planned` | 目前能生成，尚不能作为输入导入 |
| 通用结构预测契约 | `implemented` | request/invocation/product 契约和测试 |
| Protenix-v2 adapter | `smoke-validated` | 真实 no-MSA CIF/confidence 收集成功 |
| 预测 Target Bundle 发布 | `smoke-validated` | 真实 143 残基 CIF 逐位映射并发布 6 个 artifact |
| remote-MSA/no-template | `implemented` | 两个显式服务 attempt 均因持续 `PENDING` 超时失败 |
| 预计算 MSA 复用 | `planned` | 枚举与 provenance 契约已预留；没有可用 APOE MSA artifact |

## Now

### S01-002：APOE MSA-backed Protenix-v2 验证

- 状态：`blocked`；等待公共服务恢复，或从 SMART 取回旧 target feature cache。
- 目标：用与当前 143-aa APOE 查询严格匹配、来源可追溯的 MSA 运行 Protenix-v2，
  显式关闭 template，并发布带 MSA provenance 的 Target Bundle。
- 旧仓本地 `data/apoe/msa/` 目录只有 FASTA 和单序列 AF3 JSON；数据盘现有 113 个
  alignment 文件也都不匹配当前查询，因此目前没有可安全复用的旧 MSA。
- 远程 MSA 失败或超时不得静默降级为 no-MSA，也不得把单序列输入命名为 MSA。

完成门槛：

1. MSA query 与规范序列 SHA-256 `7cfb40e9...115a` 严格一致：**无 MSA，未通过**；
2. MSA 来源、生成方式、文件 SHA-256 和实际深度写入 attempt：**未通过**；
3. Protenix-v2 `use_msa=true`、`use_template=false` 真实预测：**未通过**；
4. 同一 adapter 发布含 `msa_input_sha256` 的 Target Bundle：**未通过**；
5. 失败、重试和禁止 fallback 的契约测试：**已通过**。

## Next

- 优先从原 SMART workspace 取回已记录的 APOE
  `target_feature_cache/<target_sha256>/target_data.json`；取回后先做来源和序列审计，
  再提取为 Protenix 可消费的预计算 MSA attempt。
- 如果旧缓存不可获得，公共 MSA 服务恢复后建立新 attempt；不能覆盖已有失败 attempt。
- MSA 获得后，以模型默认 `10 recycle / 200 diffusion steps`、1 seed、1 sample
  运行无模板 APOE 预测，并用同一 adapter 发布正式 Target Bundle。
- 实现本地 PDB/mmCIF 与标准 Target Bundle 两条无网络入口。
- 实现 RCSB PDB ID、UniProt 和 PSE adapter。
- 增加本地 MSA 或预计算 MSA profile，支持不依赖公共队列的离线复现。

## Blocked

- Protenix 官方远程 MSA attempt 持续 `PENDING` 30 分钟后按工程超时终止。
- 显式创建的 ColabFold remote-MSA attempt 持续 `PENDING` 20 分钟后按工程超时终止。
- 两条 attempt 均为 `failed`、`retryable=true`；需要上游队列恢复后建立新 attempt。
- 旧仓文档提到的 APOE MSA/template cache 位于 SMART 运行目录，但没有同步到
  Proteindigger1；当前仓和旧仓本地文件都不包含该 asset。
- 这只阻塞 remote-MSA 验证，不阻塞已完成的本地契约、no-MSA smoke 和后续无网络入口开发。

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

### remote-MSA attempts

- 目录：`runs/_development/msa-services/apoe-remote-no-template-20260724`。
- `attempt-0001`：Protenix MSA 服务，`2026-07-23T18:59:06Z` 开始，持续
  `PENDING` 超过 30 分钟，终态 `failed` / `remote-msa-timeout` / retryable。
- `attempt-0002`：ColabFold MSA 服务，`2026-07-23T19:14:36Z` 开始，持续
  `PENDING` 超过 20 分钟，终态 `failed` / `remote-msa-timeout` / retryable。
- 两条均未生成 MSA artifact，因此没有启动假定存在 MSA 的正式预测，也没有降级为 no-MSA。

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

## 历史索引

- [2026-07：S01-001 sequence/FASTA 与 no-MSA 纵向切片](history/2026-07.md)
