# Stage 02 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态状态、验证证据和阶段历史。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `planned` | schema 0.4 已消费 Stage 01 冻结 UniProt 证据并支持 unattended 单方法交接；APOE 双方法仍等待人工批准。 | 用户从 SASA 或 ScanNet 中批准 2–3 个完整区域，再启动 Stage 03。 | 自动流程无 runtime 阻塞；Stage 03 等待真实人工区域批准，GPU 仅是后续优化。 | 2026-07-25 |

## 当前结论

- 阶段总体状态：`planned`；manual、PSE annotation、外部 annotation 和科学 benchmark
  尚未完成。
- automatic 方法可按 YAML 选择 SASA、ScanNet 或二者；代码状态：`implemented`。
- SASA 已支持 Target Bundle coordinate ensemble：逐模型 SASA/图、70% presence/exposure/
  edge/region 完整度、中位数指标和最坏情况区域分离均通过工程测试；单模型回归保持一致。
- ScanNet 多模型仍未定义科学策略，配置选择时明确返回 `unsupported_ensemble`。
- 可选 UniProt accession 已支持 `off/if_available/required`、确定性序列映射、功能/PTM/
  topology feature 和 N-X-S/T warning；annotation 不改变两种方法排名。
- 自动阶段成功后 RunManifest 进入 `awaiting-human-approval`；`hotspots export/approve`
  只允许同一种方法的 2–3 个完整区域，并以 `attempt-0002` 发布唯一 `hotspots.yaml`。
- SASA/geometry 在 138-aa APOE 上状态为 `smoke-validated`。
- ScanNet epitope no-MSA 的 CPU 路径已通过官方 1BRS 和 138-aa APOE 真实 smoke；
  CPU 是当前正式主线，不是 GPU 失败后的静默 fallback。
- APOE CPU 双方法正式 run 状态为 `smoke-validated`；Stage/Attempt/Run manifest 均成功，
  输出两套 Top 3、完整 `3 × 3` comparison，且没有融合分数或默认赢家。
- schema `0.3` 新流程已在真实 APOE PSE 上重新验证：RunManifest `1.2` 正确停在
  `running / awaiting-human-approval`，Target Bundle `0.3` 声明单模型 `1`，无 accession
  时 annotation 为 `not_requested / structural_only`，Viewer 与审批模板均成功生成。
- GPU 是后续性能优化：小型 GPU probe 通过，但官方模型和 APOE 均在 RTX 4080 的
  cuBLAS GEMM 执行时失败，不再阻塞 1.0 的 Stage 02 主线。
- SASA/geometry 与 ScanNet probability 在类型、文件和排名路径上完全分离。
- adapter 要求显式选择 `cpu` 或 `gpu`，默认 `cpu`；禁止执行期间在设备之间静默 fallback。
- 人工选择前不会向 Stage 03 发布默认赢家；structural-only 审批必须确认科学证据限制。
- Developer Preview CLI 已通过同一 orchestration API 调用正式 Stage 02，并从 YAML
  读取独立方法参数、从 runtime profile 读取 ScanNet CPU；这不改变本阶段科学状态。
- schema 0.4 新 Bundle 优先消费 Stage 01 冻结的 UniProt response，不在 Stage 02
  重新获取漂移记录；旧 Bundle 仍保留兼容联网路径。
- `unattended` 只允许单一 SASA 或 ScanNet 方法，按
  `stage02-single-method-top-regions-v1` 发布完整 Top 2–3 与 policy 证据；双方法比较仍
  只能走 `review-gated`，不产生融合结果。

## 功能矩阵

| 能力 | 状态 | 当前证据 |
| --- | --- | --- |
| Stage 01 Target Bundle/编号读取 | `smoke-validated` | APOE 单模型 checksum/双编号真实读取；多模型 ID、缺失和类型冲突通过工程测试 |
| SASA/表面几何候选池 | `smoke-validated` | APOE 独立 evidence、51 个候选、Top 3 和 PyMOL 脚本 |
| SASA 多模型共识 | `implemented` | 7/10 与 6/10 阈值、边共识、中位数、缺失坐标和最坏情况分离测试 |
| ScanNet epitope no-MSA CPU adapter | `smoke-validated` | 官方 1BRS 与 APOE 138-aa 均真实运行，逐残基 CSV 完整回映射 |
| ScanNet 多模型 | `planned` | 当前明确 `unsupported_ensemble`；不选代表模型、不回退 |
| ScanNet epitope no-MSA GPU 优化 | `planned` | probe 通过；RTX 4080 真实模型 GEMM 失败，不阻塞 CPU 主线 |
| 两方法 `3 × 3` 重叠报告 | `implemented` | Jaccard、覆盖率、距离、最佳匹配；无融合字段 |
| APOE 138-aa 真实双方法 run | `smoke-validated` | schema 0.3 validation run；双方法、comparison、Viewer 和等待审批状态全部成功 |
| PSE 染色区域导入 | `planned` | 只有明确失败的 provider 接口 |
| 人工区域上传 | `planned` | 只有明确失败的 provider 接口 |
| 显式 UniProt 功能位点/PTM/topology | `implemented` | 三种策略、确定性映射、零 accession 零网络请求和失败语义测试 |
| 天然界面/文献/疾病突变 annotation | `planned` | 未实现 |
| 人工批准与 `hotspots.yaml` | `implemented` | revision/hash/完整区域/理由/structural-only acknowledgement 契约测试 |
| unattended 单方法 handoff | `implemented` | policy ID、完整 Top 2–3、structural-only 显式许可；无跨方法融合 |
| SASA MAX_ASA 来源/归一化 benchmark | `planned` | 当前常数已落盘，但来源登记和替代表对照未完成 |
| ScanNet PPBS/interface no-MSA | `planned` | 未安装、未测试 |
| ScanNet 带 MSA 模型 | `planned` | 未安装、未测试 |
| PeSTo | `planned` | 未安装、未测试；非商业许可证，产品接入前需授权审查 |
| GraphPPIS/MaSIF-site/DiscoTope | `planned` | 未安装、未测试；分别做技术和许可证审查 |
| VHH–抗原真实 benchmark | `planned` | 无科学验证 |

## Now

### S02-005：APOE 真实人工批准

- 状态：`planned`；schema 0.3 自动流程已经真实重跑，不替用户编造生物学判断。
- 当前待用户比较已经生成的 SASA 与 ScanNet Top 3，并选择一种方法。
- 人工比较后从一种方法批准 2–3 个完整区域，形成真实 `attempt-0002/hotspots.yaml`。
- 完成门槛：RunManifest 从 `awaiting-human-approval` 转为终态，Stage 03 handoff 的
  target/method/mapping/evidence/hash 全部可验证。

## Next

- 按 S02-005 完成真实 APOE 人工选择；不得把合成审批测试或自动 Top 3 当真实科学批准。
- 将 GPU 兼容优化作为独立 benchmark：评估兼容旧 CUDA 的硬件/容器，或经科学和
  许可证评审的现代化模型路径；不得修改当前 CPU 主线的模型 commit 或权重。
- 扩展天然复合物界面、文献、疾病突变和自动身份发现；均先作为证据/warning。
- 登记 SASA MAX_ASA 常数来源，比较替代归一化表，并为阈值/权重建立 binder-specific
  benchmark；验证前保持当前 v0.1 参数不变。
- 设计 VHH–抗原 patch benchmark，比较 SASA、ScanNet PPBS、PeSTo 等方法。
- 实现 PSE annotation 与 manual provider，不改变 automatic 方法结果。

## Blocked

- Stage 02 CPU 自动选区主线当前没有外部 runtime 阻塞。
- schema 0.3 真实 APOE 自动 run 已完成；只有用户的科学区域选择尚未执行。
- GPU 优化在当前服务器阻塞，但它是后续性能待办，不再阻塞 CPU 主线：
- 环境已精确建立：Python 3.6.12、TensorFlow GPU 1.14.0、CUDA Toolkit 10.0、
  cuDNN 7.6.5、ScanNet commit
  `a61623cd98d243c2ff4cd03fc3619d2d22ec50e7`。
- RTX 4080 GPU probe 能完成一个显式 `/device:GPU:0` 矩阵乘法；但官方
  `1brs_A --mode epitope --noMSA` 在实际模型推理中报
  `CUBLAS_STATUS_EXECUTION_FAILED` 和 `CPU->GPU Memcpy failed`。
- APOE 推理复现为 `Blas GEMM launch failed`，矩阵
  `a=(138,20), b=(20,32)`；不是输入编号或 CSV 回映射问题。
- 历史 `20260724-003-stage02-auto` attempt 按当时 GPU-only 契约失败且保持不可变；
  CPU 主线必须创建新 run，不能改写该失败证据。

## 验证证据

- `make check` 通过：ruff、strict mypy、compile 和仓库结构检查全部成功。
- 159 个 pytest 中 151 passed；8 个需要显式 PyMOL 环境变量的集成测试按设计跳过；
  显式设置真实 PyMOL interpreter 后这 8 项集成测试全部通过，真实 CLI run 也实际调用
  了独立 PyMOL 环境。
- 单元测试验证：
  - SASA evidence 不包含 ScanNet probability；
  - ScanNet evidence 不包含 raw SASA/rSASA；
  - comparison 的 `fused_score`/`winner` 固定为 `null`；
  - ScanNet residue 缺失和 CPU-only probe 明确失败；
  - PSE/manual provider 不会回退 automatic。
  - 10 模型中 7/10 支持通过、6/10 失败，边共识使用 `ceil(N×0.70)`；
  - 多模型最坏情况中心距离/shell/重原子距离与 ScanNet 明确拒绝；
  - UniProt 缺 accession 不调用网络，显式 accession feature 映射和低 identity review；
  - structural-only 审批必须 acknowledge，跨方法/旧 revision/改成员明确失败。
- 服务器：2 × RTX 4080，compute capability 8.9，driver `580.105.08`，CUDA driver 13.0。
- 隔离环境：`/root/autodl-tmp/conda_envs/scannet-epitope-gpu`；官方源码/权重为 runtime
  only，commit 如上。
- GPU probe：TensorFlow `1.14.0`、Keras `2.2.5`，GPU available、device name 和测试
  op 均为 `/device:GPU:0`。
- 官方 no-MSA smoke：真实模型失败，错误如 Blocked；因此不能把 probe 通过称为
  ScanNet smoke 成功。
- CPU 官方 no-MSA smoke：
  `runs/_validation/scannet-official-no-msa-cpu-20260724-001`；官方 1BRS 五模型
  ensemble 成功，约 33 秒。
- CPU APOE smoke：
  `runs/_validation/scannet-apoe-no-msa-cpu-20260724-001`；138 个残基全部输出并严格
  回映射，约 34 秒，已生成三个 10-residue 推荐区。
- CPU 双方法正式 run：`runs/apoe/20260724-005-stage02-cpu`；runtime probe 明确为
  `/device:CPU:0`，SASA 区域大小为 `12/12/12`，ScanNet 为 `10/10/10`，
  `method-comparison.json` 含 9 组比较；Attempt、StageManifest 与 RunManifest revision 3
  均为 `succeeded`，handoff 为 `awaiting_region_selection`。
- schema 0.3 真实回归位于 runtime-only validation
  `/root/autodl-tmp/Protein_design/easydesign-clean-validation.lDkLYp/`：
  `20260725-001-v03-pse` 从原始 397,738-byte APOE PSE 一条命令完成 Stage 01、Viewer、
  SASA 和 ScanNet CPU。RunManifest `1.2` revision 3 为
  `running / awaiting-human-approval`，代码版本为 `0.1.0.dev2`；annotation 明确记录
  `not_requested / structural_only`，`hotspots export --method sasa` 成功输出带源
  StageManifest/region artifact SHA-256 的审批模板。
- 操作失败证据：`runs/apoe/20260724-004-stage02-cpu` 因传入错误 ScanNet repository
  路径明确失败，错误码 `scannet-repository-missing`；没有覆盖，随后以新 run 重试。
- APOE 证据 run：
  `runs/apoe/20260724-003-stage02-auto/02-hotspot-discovery/attempt-0001/`。
  Attempt 与 StageManifest 均为 `failed`，RunManifest 为 revision 3/running；
  Stage 02 没有发布正式 output。
- 该 attempt 保留 SASA 诊断产物：51 个候选和三个 12-residue 推荐区；auth 编号分别为
  `126–129,131–132,135–136,139–140,142–143`，
  `86–89,91–92,95–96,98–99,102,158`，
  `49,52–55,58–59,61–62,65–66,69`。
- 几何距离缓存后，同一 APOE SASA 结果保持不变，耗时由约 255 秒降至 2.5 秒。

## 工作日志

### 2026-07-24

- 审计旧仓：旧自动区域是 Biopython Shrake–Rupley + 自定义三维图/集合选择，没有
  ScanNet、PeSTo 或 MaSIF。
- 明确 Stage 02 输出语义为候选表面区域，而非真实 binding site。
- 选择 SASA 与 ScanNet epitope no-MSA 两条独立方法；不融合评分。
- 固定 ScanNet commit、GPU-only adapter、连续工具编号 PDB和严格回映射。
- 完成类型化 evidence/region/comparison/report、运行编排和 101 项测试。
- 建立隔离环境并完成 GPU probe；确认 probe 通过不足以代表真实模型可运行。
- 官方 1BRS 和 APOE真实模型均在 RTX 4080 上复现 cuBLAS GEMM 失败，按契约标记 blocked。
- APOE失败 attempt 正确保留 SASA 并拒绝发布比较结果；将 SASA 几何选区加速至 2.5 秒。
- 将 SASA v0.1 的结构预处理、MAX_ASA、图构建、Dijkstra patch、评分公式、分散选择和
  放宽顺序完整落盘；识别出 MAX_ASA 来源登记与 binder-specific 校准仍是 planned。
- 在不改变 ScanNet commit、权重、epitope/no-MSA 模式的前提下验证 CPU 执行；决定
  CPU 成为当前主线、GPU 转为后续性能优化，并保持显式设备与无 fallback 契约。
- 完成并归档 S02-002：CPU runtime probe、正式 APOE 双方法 run、完整 comparison 与
  顶层状态自动汇总；当前工作切换到 S02-003 人工批准交接。

### 2026-07-25

- 完成并归档 S02-003/S02-004：多模型 SASA 共识、可选 UniProt annotation、
  `awaiting-human-approval` 状态和不可变 `hotspots.yaml` 审批契约。
- 使用 canonical schema 0.3 对真实 APOE PSE 重跑 Stage 01/02；两种方法均成功，
  structural-only 审批模板已导出，真实区域决定保留给用户。
- 接入 schema 0.4 Stage 01 frozen UniProt snapshot 和 unattended 单方法确定性审批；
  review-gated 的 APOE 双方法人工决定保持不变。

## 历史索引

已完成部分见 [`history/2026-07.md`](history/2026-07.md)；当前未关闭项是 S02-005
真实人工区域批准。
