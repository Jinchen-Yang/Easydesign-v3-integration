# Stage 02 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态状态、验证证据和阶段历史。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `planned` | SASA 与 ScanNet CPU 已分别在 APOE 生成 Top 3，正式 CPU 双方法 run 正在固化。 | 以 CPU 跑通可发布比较并建立人工批准到 Stage 03 的交接。 | 人工批准契约尚未实现；GPU 在 RTX 4080 上不兼容旧运行栈。 | 2026-07-24 |

## 当前结论

- 阶段总体状态：`planned`；manual、PSE annotation、外部 annotation 和科学 benchmark
  尚未完成。
- automatic 双方法独立选区代码状态：`implemented`。
- SASA/geometry 在 138-aa APOE 上状态为 `smoke-validated`。
- ScanNet epitope no-MSA 的 CPU 路径已通过官方 1BRS 和 138-aa APOE 真实 smoke；
  CPU 是当前正式主线，不是 GPU 失败后的静默 fallback。
- GPU 是后续性能优化：小型 GPU probe 通过，但官方模型和 APOE 均在 RTX 4080 的
  cuBLAS GEMM 执行时失败，不再阻塞 1.0 的 Stage 02 主线。
- SASA/geometry 与 ScanNet probability 在类型、文件和排名路径上完全分离。
- adapter 要求显式选择 `cpu` 或 `gpu`，默认 `cpu`；禁止执行期间在设备之间静默 fallback。
- 人工选择前不会向 Stage 03 发布默认赢家。

## 功能矩阵

| 能力 | 状态 | 当前证据 |
| --- | --- | --- |
| Stage 01 Target Bundle/编号读取 | `smoke-validated` | APOE run 中 checksum、单链/单 model 和双编号强校验通过 |
| SASA/表面几何候选池 | `smoke-validated` | APOE 独立 evidence、51 个候选、Top 3 和 PyMOL 脚本 |
| ScanNet epitope no-MSA CPU adapter | `smoke-validated` | 官方 1BRS 与 APOE 138-aa 均真实运行，逐残基 CSV 完整回映射 |
| ScanNet epitope no-MSA GPU 优化 | `planned` | probe 通过；RTX 4080 真实模型 GEMM 失败，不阻塞 CPU 主线 |
| 两方法 `3 × 3` 重叠报告 | `implemented` | Jaccard、覆盖率、距离、最佳匹配；无融合字段 |
| APOE 138-aa 真实双方法 run | `implemented` / 待正式重跑 | CPU 已分别产出结果；新 adapter 与不可变正式 run 正在固化 |
| PSE 染色区域导入 | `planned` | 只有明确失败的 provider 接口 |
| 人工区域上传 | `planned` | 只有明确失败的 provider 接口 |
| UniProt 功能位点/PTM/天然界面 | `planned` | `annotation_status=not_implemented` |
| SASA MAX_ASA 来源/归一化 benchmark | `planned` | 当前常数已落盘，但来源登记和替代表对照未完成 |
| ScanNet PPBS/interface no-MSA | `planned` | 未安装、未测试 |
| ScanNet 带 MSA 模型 | `planned` | 未安装、未测试 |
| PeSTo | `planned` | 未安装、未测试；非商业许可证，产品接入前需授权审查 |
| GraphPPIS/MaSIF-site/DiscoTope | `planned` | 未安装、未测试；分别做技术和许可证审查 |
| VHH–抗原真实 benchmark | `planned` | 无科学验证 |

## Now

### S02-002：CPU-first 双方法正式运行

- 状态：`implemented`，等待使用新 adapter 发布不可变正式 run。
- 把 ScanNet 设备从 GPU-only 改成显式 `cpu`/`gpu`，默认 CPU；设备选择和 probe
  进入正式产物，不允许运行时 fallback。
- 使用同一份 138-aa PSE APOE `target.cif` 发布 SASA、ScanNet CPU、`3 × 3`
  comparison 和人工检查脚本。
- 完成后 Stage 03 仍保持 `awaiting_region_selection`，不能自动选择赢家。

## Next

- 人工检查 CPU 主线产生的两套 Top 3 与 PSE 原始颜色 annotation，明确批准区域集。
- 建立“人工批准区域集”契约，再允许 Stage 03 消费。
- 将 GPU 兼容优化作为独立 benchmark：评估兼容旧 CUDA 的硬件/容器，或经科学和
  许可证评审的现代化模型路径；不得修改当前 CPU 主线的模型 commit 或权重。
- 实现 UniProt/PTM/糖基化/天然界面 annotation 拉取，但默认只标注 warning。
- 登记 SASA MAX_ASA 常数来源，比较替代归一化表，并为阈值/权重建立 binder-specific
  benchmark；验证前保持当前 v0.1 参数不变。
- 设计 VHH–抗原 patch benchmark，比较 SASA、ScanNet PPBS、PeSTo 等方法。
- 实现 PSE annotation 与 manual provider，不改变 automatic 方法结果。

## Blocked

- Stage 02 CPU 自动选区主线当前没有外部 runtime 阻塞。
- 人工批准区域集及 Stage 03 handoff 契约尚未实现。
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
- 101 个 pytest 中 93 passed；8 个需要显式 PyMOL 环境的集成测试按设计跳过。
- 单元测试验证：
  - SASA evidence 不包含 ScanNet probability；
  - ScanNet evidence 不包含 raw SASA/rSASA；
  - comparison 的 `fused_score`/`winner` 固定为 `null`；
  - ScanNet residue 缺失和 CPU-only probe 明确失败；
  - PSE/manual provider 不会回退 automatic。
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

## 历史索引

已完成部分见 [`history/2026-07.md`](history/2026-07.md)；S02-001 的真实双方法 smoke
仍在 Blocked。
