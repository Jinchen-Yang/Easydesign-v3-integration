# Stage 01 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态开发状态、验证证据和历史索引。

## 当前结论

- 阶段总体状态：`planned`；六类入口尚未全部实现。
- sequence/FASTA → Protenix-v2 → Target Bundle 纵向切片状态：`implemented`。
- no-MSA 工程 smoke、真实输出解析和 Target Bundle 发布已通过。
- remote-MSA/no-template 的两个外部服务 attempt 均超时失败，未通过前不能把纵向切片标成
  `smoke-validated`。
- APOE fixture 是旧仓工程案例的 143-aa 片段，科学身份尚待 UniProt 路径独立复核。

## 功能矩阵

| 输入或能力 | 状态 | 当前证据 |
| --- | --- | --- |
| 裸氨基酸序列 | `implemented` | 严格规范化、标准氨基酸校验和 identity 测试 |
| FASTA 文件 | `implemented` | 单记录解析；与同序列裸输入产生同一 SHA-256 |
| 本地 PDB/mmCIF | `planned` | 无 |
| RCSB PDB ID | `planned` | 无 |
| UniProt accession/名称 | `planned` | 无 |
| PyMOL PSE | `planned` | 无 |
| 标准 Target Bundle | `planned` | 目前能生成，尚不能作为输入导入 |
| 通用结构预测契约 | `implemented` | request/invocation/product 契约和测试 |
| Protenix-v2 adapter | `smoke-validated` | 真实 no-MSA CIF/confidence 收集成功 |
| 预测 Target Bundle 发布 | `smoke-validated` | 真实 143 残基 CIF 逐位映射并发布 6 个 artifact |
| remote-MSA/no-template | `implemented` | 两个显式服务 attempt 均因持续 `PENDING` 超时失败 |

## Now

### S01-001：APOE sequence/FASTA 纵向切片

- 状态：`implemented`，等待 remote-MSA/no-template 外部验证。
- `protenix==2.0.0` / `protenix-v2` 的 Python 3.11 独立环境和参数已经固定。
- sequence/FASTA、通用结构预测接口、Protenix-v2 adapter 和 Target Bundle 已实现。
- Protenix 官方 MSA 服务与其支持的 ColabFold 服务分别使用独立 attempt，均已保留失败
  manifest，禁止互相覆盖。
- 远程 MSA 失败或超时不得静默降级为 no-MSA。

完成门槛：

1. 裸序列与 FASTA 产生相同规范序列和 SHA-256：**通过**；
2. Protenix-v2 no-MSA smoke：**通过**；
3. APOE `remote MSA + template disabled` 真实预测：**外部 MSA 服务超时，未通过**；
4. `target.cif`、序列、残基映射、质量报告和 provenance：**no-MSA 路径通过**；
5. unit、adapter contract 和实际产物集成验证：**通过**。

## Next

- remote MSA 返回后，以模型默认 `10 recycle / 200 diffusion steps`、1 seed、1 sample
  运行无模板 APOE 预测，并用同一 adapter 发布正式 Target Bundle。
- 实现本地 PDB/mmCIF 与标准 Target Bundle 两条无网络入口。
- 实现 RCSB PDB ID、UniProt 和 PSE adapter。
- 增加本地 MSA 或预计算 MSA profile，支持不依赖公共队列的离线复现。

## Blocked

- Protenix 官方远程 MSA attempt 持续 `PENDING` 30 分钟后按工程超时终止。
- 显式创建的 ColabFold remote-MSA attempt 持续 `PENDING` 20 分钟后按工程超时终止。
- 两条 attempt 均为 `failed`、`retryable=true`；需要上游队列恢复后建立新 attempt。
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

- run：`runs/apoe-protenix-bootstrap/no-msa-smoke/attempt-0002`。
- 配置：`protenix-v2`、seed `101`、1 recycle、5 diffusion steps、1 sample、
  `use_msa=false`、`use_template=false`。
- 结果：前向 6.57 s；CIF SHA-256
  `e056cdab5b9a602fc51187aad2cb9dab6f231e8d788ec9bedc35d7c19cd70964`；
  confidence SHA-256
  `88a0655909afc6b32a06853863fee5a2ef8f516432735e56a146883c5efcba80`。
- smoke 输出 `pLDDT=80.90`、`pTM=0.143`；这些低预算数值不作为科学质量结论。

### EasyDesign adapter 与 Target Bundle

- adapter 实际读取上述 Protenix 2.0.0 目录协议，未扫描或猜测其他文件。
- run：`runs/apoe-stage01-adapter/run-20260724-no-msa`，`attempt-0001`。
- 143 个结构残基与规范输入逐位一致；Target Bundle SHA-256
  `1417adfc60cd9ab6f6778e2712c2fdb90accdaaaa888a7c6820e2bb1b5ed7c08`。
- `make check` 和 63 个 pytest 全部通过；严格 mypy 和 ruff 通过。

### remote-MSA attempts

- `attempt-0001`：Protenix MSA 服务，`2026-07-23T18:59:06Z` 开始，持续
  `PENDING` 超过 30 分钟，终态 `failed` / `remote-msa-timeout` / retryable。
- `attempt-0002`：ColabFold MSA 服务，`2026-07-23T19:14:36Z` 开始，持续
  `PENDING` 超过 20 分钟，终态 `failed` / `remote-msa-timeout` / retryable。
- 两条均未生成 MSA artifact，因此没有启动假定存在 MSA 的正式预测，也没有降级为 no-MSA。

## 工作日志

### 2026-07-24

- 固定 APOE 旧仓 fixture、文件 hash 和“尚待 UniProt 独立核对”的身份状态。
- 审计 GPU、CUDA、磁盘和已有环境；创建隔离的 Protenix-v2 Python 3.11 环境。
- 固定 `protenix==2.0.0`、CUDA 编译依赖和 `protenix-v2` checkpoint。
- no-MSA 首次 attempt 因官方 checkpoint URL 403 失败并保留；新 attempt 在校验参数后成功。
- 实现 sequence/FASTA 规范化、通用预测契约、Protenix-v2 adapter、确定性输出收集、
  CIF/序列逐残基校验和不可覆盖 Target Bundle 发布。
- Protenix 与 ColabFold 两个 remote-MSA 服务 attempt 均已显式提交并因持续 `PENDING`
  达到工程超时；终态和可重试错误已写入各自 attempt manifest。

## 历史索引

已结束日志按月移动到 `history/YYYY-MM.md`；当前工作尚未结束，不归档。
