# ADR-0002：Developer Preview CLI、Runtime Profile 与代码身份

- 状态：`accepted`
- 日期：2026-07-25
- 决策范围：安装入口、CLI/API 边界、本机配置和 RunManifest 代码身份

## 背景

Stage 01/02 已经有真实 Python API 和 APOE smoke，但使用者仍需手工构造 adapter、环境变量
和脚本。继续开发 Stage 03 会扩大“代码已经存在但普通使用者无法稳定调用”的差距。同时，
旧 RunManifest 只接受 Git commit，无法如实描述 dirty checkout 或从 wheel 运行的代码。

## 决策

1. 暂停 Stage 03，先提供 `easydesign` Developer Preview console-script。
2. CLI 只解析参数和展示结果；项目初始化、配置验证、环境诊断、pipeline、run 查询和
   Viewer 均调用可复用 Python API。
3. 用户科学参数只存在于 `easydesign.yaml`；机器路径只存在于一个用户级 runtime
   profile。CLI 不扫描 Conda、权重或系统 Python，也不合并多个 profile。
4. `easydesign run` 只执行当前真实实现的 Stage 01/02。Stage 03–07 在创建 workspace 前
   明确失败，禁止用占位成功推进。
5. RunManifest 1.1 使用结构化 `code_identity`：clean Git commit、dirty package tree
   hash 或 installed package tree hash。旧 1.0 manifest 保持可读。
6. 当前只支持私有源码、editable install、普通本地 install 和本地 wheel；不发布 PyPI，
   不添加公开 LICENSE，也不把 Developer Preview 称为稳定公开 API。
7. 顶层 TODO 除七阶段外统一维护工程、CLI、报告、UI、验证、数据、发布、论文和商业
   workstream；活跃任务必须带已登记 ID。

## 后果

- 使用者可以从真实 target 初始化项目，先验证配置与环境，再用一个命令运行 Stage 01/02。
- 重型 backend 仍需独立安装；`doctor` 只诊断，不负责下载权重或修改环境。
- CLI 本身可跨平台安装，但 Protenix/ScanNet 等 backend 的平台能力必须由 profile 和
  doctor 如实报告。
- dirty checkout 可以用于开发 smoke，但 manifest 会明确记录 dirty 状态和内容哈希。
- resume、结构输入、Stage 03、完整 UI、公开发布和兼容性承诺仍属于后续工作。

## 2026-07-25 修订：规范七阶段、Ensemble 与人工暂停点

Developer Preview 的配置和运行状态进一步收敛：

1. 用户配置 schema `0.3` 固定展示 `stage01`–`stage07`；未实现阶段必须为 `null`，
   旧布局只在加载/显式迁移边界兼容。
2. Target Bundle `0.3` 用 `coordinate_ensemble` 声明 model IDs、代表 model 和共享
   `label_seq_id` 身份。PSE 单 state 和 Protenix 单 sample 是 adapter 限制，不再是通用
   Bundle 限制。
3. SASA 对每个 model 独立计算，以显式 70% 阈值形成共识并采用最坏情况区域分离；
   ScanNet v0.1 遇到多模型明确拒绝，不隐式选择代表模型。
4. UniProt 只按用户显式 accession 查询，annotation 只提供证据/warning，不改变方法排名。
5. RunManifest `1.2` 增加可恢复 `workflow_state`。自动 Stage 02 完成后保持 running，
   人工批准新 attempt 才发布 Stage 03 唯一入口 `hotspots.yaml`。
6. EasyDesign 1.0 不依赖 LLM/Agent 进行流程判断；未来 Agent 建议必须落入类型化配置、
   确定性校验和人工批准。

这次修订保持原 ADR 的核心边界：CLI/UI 仍只是共享 Python API 的薄入口，旧 manifest
保持可读，等待人工输入不能被包装成执行成功。

## 2026-07-25 修订：Stage 01 六入口与通用 Decision Gate

Stage 01 与 Developer Preview 的运行边界进一步统一：

1. canonical schema `0.4` 以 discriminated union 表达 `local-file`、`pdb-id`、
   `uniprot`、`uniprot-search` 和 `target-bundle`；local-file 再识别
   sequence/FASTA、PDB/mmCIF 与 PSE，覆盖六类入口。
2. FASTA/sequence 与 UniProt 先调用官方 RCSB Search/Data API，并按明确 design scope
   重新验证 100% coverage、100% identity、CA 完整性和实验方法质量；不额外部署
   BLAST/MMseqs。
3. UniProt/RCSB 请求、响应、headers、时间和 SHA-256 冻结进 run。Stage 02 优先消费
   Stage 01 身份快照，不重复拉取漂移记录。
4. `target.cif` 固定为 protein-only、design-scope、规范 chain A；原 chain、author 和
   UniProt 编号进入 mapping，复合物和 ligand 只进入独立 context artifact。
5. Target Bundle `0.4` 纳入 identity、scope、candidate、retrieval、context 与可选 PDB
   投影，同时保持 0.1–0.3 读取兼容，历史 artifact 不重写。
6. `review-gated` 与 `unattended` 使用相同科学实现。前者在 identity、chain、structure、
   hotspot 等选择点发布 `DecisionRequest`；后者只允许版本化确定性 policy 生成
   `DecisionRecord`。
7. 批准记录钉住 request revision、输入 hash、选项和 authority；恢复时在同一 run
   新建 attempt，拒绝过期或篡改审批。API failure、零候选、歧义和 QC 不合格使用不同
   状态，网络失败不得静默读旧 cache 或直接预测。
8. Stage 03、05、06、07 后续复用相同 Decision Gate。`required_reviews` 不能因
   unattended 被绕过；Stage 07 最多生成候选下单包，实际采购永远由人执行。

这些变化仍遵守本 ADR 的原始原则：所有命令调用同一 Python API、用户 YAML 是科学配置
的唯一事实来源，自动化不制造科学批准。
