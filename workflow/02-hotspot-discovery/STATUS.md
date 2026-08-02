# Stage 02 状态

稳定职责和契约见 [`README.md`](README.md)。本文件只记录动态状态、验证证据和阶段历史。

## 顶层摘要

| 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新时间 |
| --- | --- | --- | --- | --- |
| `planned` | automatic、PSE/YAML、交互选区共享人工批准交接；dev37 支持模型用完整 PML 一次修改多个 `ed_region_A/B/C`。 | 复验真实 provider 多区域 PML 往返，同时推进科学 benchmark 和 REP-002 独立 overlay。 | Stage 03 handoff 无工程阻塞；GPU、外部证据和 VHH–抗原科学验证仍是后续工作。 | 2026-08-02 |

## 当前结论

- 阶段总体状态：`planned`；三条工程输入路线已实现，外部 annotation 扩展和科学
  benchmark 尚未完成。
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
- schema 0.6 的 `detect/automatic/user-provided` 已实现：PSE 固定红/蓝/黄与 YAML
  sequence/label/auth/UniProt 编号共享 `UserProvidedRegionSet`，成员不扩展、不删除、
  不重排；显式 automatic 不消费颜色。
- APOE PSE 颜色和 YAML auth 列表真实运行均得到 A/B/C `9/14/14`，规范 label 成员完全
  相同、provenance 不同；两条 review-gated run 均通过 attempt-0002 发布
  `hotspots.yaml` 0.3。
- 用户区域 unattended 使用初始 YAML 中的真实人员批准，明确记录
  `approval_authority=human` 与 `approval_source=initial-run-config`，不冒充机器 policy。
- S02-009 产品入口允许任何成功 Stage 01 Target Bundle 重新选择区域，不要求 PSE
  染色。PSE 来源颜色、当前批准区域和本次编辑区域是三个独立图层；保存时只把编辑层
  规范化为 `label_seq_id` 的 `manual-residue-list`，并创建新的 continuation run，
  不追溯修改旧 Stage 02–07。
- UI-013 不再逐区询问设计目的和两类理由；设计目的继承 canonical `design.intent`，
  orchestration 只生成关于用户选择和已验证编号/坐标的保守说明。真实批准人和证据限制
  acknowledgement 仍为必填。
- UI-014/ENG-020 修复了重新运行 Stage 02 的状态边界：只验证并复制 Stage 01 成功
  前缀，不要求来源整条 run 已终态；显式人工选区提交一次即发布 human approval。
  automatic review-gated 仍在候选生成后等待科学选择。工作台只在 job
  `queued/running` 时显示进度，并在终态打开新分支。
- 区域编辑器不再提供独立橡皮擦。Mol* 和序列均使用同一 toggle：同区再次点击取消，
  切换画笔后点击则移动到新区。
- REP-009 用完整 PML 替代 S02-010 的模型侧 typed 区域协议。模型直接理解一次请求中
  对一个或多个区域的修改，把最终 `ed_region_A/B/C` selection 写入完整 PML；服务端
  不再预解析单个操作，只把通过校验的 PML 确定性反映射为 `label_seq_id` 编辑草稿；场景
  revision 本身不发布区域，仍需人工批准。要求“寻找最佳区域”时，服务端只形成待确认的
  SASA/ScanNet plan，模型不能直接输出区域或改变两种方法的排序。
- dev31 将助手中未限定的残基数字固定为界面规范 `label_seq_id`；只有显式声明
  原始/auth/author/PDB 时才使用 author 编号。dev37 进一步删除服务端单区域文字解析器：
  编号表、当前区域和完整 PML直接提供给模型，返回 PML 再验证并反映射。真实平台请求
  已验证规范编号 32–36 精确形成 A 区 5 个残基；多区域清空已通过工程回归，live provider
  复验仍是下一门槛。
- 结构助手改为部署者统一提供的平台能力：浏览器请求不再包含 provider 或用户 API key，
  设置页不再提供密钥表单；公开状态只报告“EasyDesign 结构助手”是否可用。部署者选择
  的实际 provider/model 仅留在服务端审计记录，平台不可用不影响手工或自动选区。
- 真实 APOE PSE 编辑器已显示结构与来源红/蓝/黄，并把 A/B/C `9/14/14` 规范成员保存到
  `runs/apoe-s02-006-pse/20260727-003-stage02-reselection-lineage`。新 run 的 Stage 01
  来自校验后的 continuation、Stage 02 attempt-0001 状态为等待人工确认；DesignSession
  已记录新 run key，原审计 run 的 `LATEST` 仍为 `run-manifest.v0004.json`。

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
| PSE 固定红/蓝/黄区域导入 | `smoke-validated` | 原始 APOE PSE → Target Bundle annotation → 9/14/14 → hotspots.yaml 0.3 |
| YAML 人工区域上传 | `smoke-validated` | sequence/label/auth/UniProt 四编号契约；APOE auth 9/14/14 与 PSE 完全一致 |
| 显式 UniProt 功能位点/PTM/topology | `implemented` | 三种策略、确定性映射、零 accession 零网络请求和失败语义测试 |
| 天然界面/文献/疾病突变 annotation | `planned` | 未实现 |
| 人工批准与 `hotspots.yaml` | `smoke-validated` | automatic/user region_source、revision/hash、完整区域、两类 acknowledgement 与 APOE 真实审批 |
| detect/automatic 显式优先级 | `implemented` | detect 标准色命中或 automatic fallback；explicit automatic 不消费 annotation |
| UI 交互式 A/B/C 重选 | `smoke-validated` | 真实 APOE PSE 可见结构、三图层与 9/14/14 新分支通过；dev19 增加缺失确认逐项反馈、问题字段聚焦、job 进度和成功跳转 |
| 自然语言明确残基/分析计划 | `implemented` | 完整 PML 四字段响应、`ed_region_A/B/C` 到 label/auth 往返、无坐标请求和人工 branch 边界通过工程测试；真实 provider 连续区域编辑待复验 |
| unattended 单方法 handoff | `implemented` | policy ID、完整 Top 2–3、structural-only 显式许可；无跨方法融合 |
| SASA MAX_ASA 来源/归一化 benchmark | `planned` | 当前常数已落盘，但来源登记和替代表对照未完成 |
| ScanNet PPBS/interface no-MSA | `planned` | 未安装、未测试 |
| ScanNet 带 MSA 模型 | `planned` | 未安装、未测试 |
| PeSTo | `planned` | 未安装、未测试；非商业许可证，产品接入前需授权审查 |
| GraphPPIS/MaSIF-site/DiscoTope | `planned` | 未安装、未测试；分别做技术和许可证审查 |
| VHH–抗原真实 benchmark | `planned` | 无科学验证 |

## Now

### S02-008：用户区域与 automatic 科学 benchmark

- 状态：`planned`；不阻塞 Stage 03 工程开发。
- 对已染色 APOE 区域、SASA 与 ScanNet 分别做结构/生物学复核，不能因为成功生成
  `hotspots.yaml` 就宣称区域科学正确。
- 完成门槛：建立预注册 VHH–抗原 benchmark、负例和区域级指标，分别报告工程成功与
  科学结果。

### S02-009：交互式用户区域重选

- 状态：`smoke-validated`。
- 当前边界：任意 Stage 01 Target Bundle 都可进入编辑器；一个残基只能属于一个编辑
  区域，同区再次点击取消，重新着色时从旧区移动到新区。PSE 来源 annotation 保持只读
  且永不删除。
- 产品语义：进入编辑器时优先把当前批准区域复制到本次可编辑层；没有批准区域时复制
  PSE 来源红/蓝/黄。APOE 因而默认显示 A/B/C `9/14/14`，而不是让只读颜色与左侧
  `0/0/0` 计数同时出现。“从空白开始”会清空编辑层并隐藏两个只读参考图层；“恢复上游
  区域”可重新复制上游成员。
- 完成证据：APOE PSE 完成真实浏览器三图层显示与新 Stage 02 run；无颜色结构使用相同
  manifest-only 投影并由浏览器/契约测试覆盖。历史 dev13 分支按当时契约停在人工审批
  门；dev18 起显式人工提交一次完成批准，automatic review-gated 仍等待选择。旧 run
  保持不可变。

## Next

- 使用已发布的 APOE PSE 用户区域 `hotspots.yaml` 启动 Stage 03；该选择是用户先验，
  不是自动算法赢家，也不是科学验证结论。
- 将 GPU 兼容优化作为独立 benchmark：评估兼容旧 CUDA 的硬件/容器，或经科学和
  许可证评审的现代化模型路径；不得修改当前 CPU 主线的模型 commit 或权重。
- 扩展天然复合物界面、文献、疾病突变和自动身份发现；均先作为证据/warning。
- 登记 SASA MAX_ASA 常数来源，比较替代归一化表，并为阈值/权重建立 binder-specific
  benchmark；验证前保持当前 v0.1 参数不变。
- 设计 VHH–抗原 patch benchmark，比较 SASA、ScanNet PPBS、PeSTo 等方法。
- 扩展多 state/复合物 PSE 和可配置色板前先定义新的版本化契约；1.0 保持单 target、
  固定来源红/蓝/黄，并允许编辑层重新选择。

## Blocked

- Stage 02 CPU 自动选区主线当前没有外部 runtime 阻塞。
- Stage 03 handoff 已由用户提供 APOE 区域建立，不再受到 Stage 02 工程阻塞。
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
- 本次完整 pytest 收集 191 项：默认门禁 183 passed、8 个需要显式 PyMOL 环境变量的
  集成测试按设计 skipped；注入真实 PyMOL 3.1.0 interpreter 后这 8 项全部通过。
- dev4 wheel 的 6 类资产/console-script 验证通过；Playwright 为 3 passed、2 个
  runtime-only 真实报告测试按设计 skipped。
- 单元测试验证：
  - SASA evidence 不包含 ScanNet probability；
  - ScanNet evidence 不包含 raw SASA/rSASA；
  - comparison 的 `fused_score`/`winner` 固定为 `null`；
  - ScanNet residue 缺失和 CPU-only probe 明确失败；
  - PSE/manual 两类来源统一为不可变区域集；显式模式不互相回退。
  - 10 模型中 7/10 支持通过、6/10 失败，边共识使用 `ceil(N×0.70)`；
  - 多模型最坏情况中心距离/shell/重原子距离与 ScanNet 明确拒绝；
  - UniProt 缺 accession 不调用网络，显式 accession feature 映射和低 identity review；
  - structural-only 与 user-provided 分别必须 acknowledge，跨来源/旧 revision/改成员
    明确失败。
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
- S02-006 用户区域真实 PSE run：
  `runs/apoe-s02-006-pse/20260725-006-stage02-pse-colors-audited`。由原始
  397,738-byte PSE
  重新执行 Stage 01/02，`detect` 消费 checksum 正确的
  `source-annotations.json`，A/B/C 分别为 9/14/14 个成员；auth 编号与计划表完全一致。
  review-gated attempt-0002 发布 `hotspots.yaml` 0.3，`region_source` 为
  `pse-color-annotation`、authority 为 human，并记录两类 acknowledgement。
- S02-006 YAML 等价 run：
  `runs/apoe-s02-006-manual/20260725-007-stage02-manual-auth-audited`。同一原始 PSE 的
  Stage 01 结构配合 YAML auth residue-list，得到与颜色路线逐 label 完全一致的
  9/14/14 成员，`region_source` 为 `manual-residue-list`，并独立发布
  `hotspots.yaml` 0.3。
- unattended 人工区域真实 run：
  `runs/apoe-s02-006-unattended/20260725-008-stage02-manual-unattended-audited`。
  初始配置中的
  `approved_by=knitua`、每区 design goal/理由和两类 acknowledgement 被原样留痕，
  RunManifest 最终为 `succeeded`；审批 authority/source 明确为
  `human / initial-run-config`。
- 新测试覆盖固定色板与背景色、四种编号索引、越界/歧义、跨区域重叠 warning、代表模型
  坐标存在、用户来源审批和旧 automatic 审批回归；全量测试门禁见本次 history。

## 工作日志

### 2026-08-02

- REP-009 删除 `explicit_region_edit_intent` 及单区域正则 parser，允许模型以完整 PML
  表达“清空 B、C，只保留 A”等多区域意图，返回状态直接同步左栏、序列和两个查看器。
- PML 中未知对象/链/残基、不可映射编号、区域重叠和危险命令继续 fail closed；自动
  hotspot/SASA/ScanNet 仍只能生成待确认计划，不能直接改变 A/B/C。
- 多区域清空、author/label 反向映射、科学计划不可改区和一次模型修复已进入全量
  `422 passed / 8 skipped` 后端门禁；Workbench `77 passed / 1 skipped`。

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
- 完成 schema 0.6 用户区域通路：固定 PSE 红/蓝/黄与 YAML 人工残基统一规范化，
  `hotspots.yaml` 0.3 记录 discriminated region source；真实 APOE 两条路径成员对齐并
  分别发布 Stage 03 handoff。

## 历史索引

已完成部分见 [`history/2026-07.md`](history/2026-07.md)；当前未关闭项是 S02-008
科学 benchmark，不阻塞 Stage 03 工程开发。
