# 01 — Target 准备

**阶段状态：** `planned`。sequence/FASTA 纵向切片已实现；单 Target PSE 导入已完成
真实 smoke；其他入口仍未实现。

**契约版本：** Target Bundle `0.2`，兼容读取没有 source annotation 的 `0.1`。

## 目的

把六类异构输入解析成规范、可追溯、可由 Stage 02 直接消费的 Target Bundle。

## 支持范围

- 本地 PDB/mmCIF。
- RCSB PDB identifier。
- FASTA 文件或裸氨基酸序列。
- 带物种上下文的 UniProt accession、基因或蛋白名称。
- PyMOL PSE 会话。
- 已经准备好的标准 Target Bundle。

sequence/FASTA 当前只接受单条、由 20 种标准氨基酸组成的输入。FASTA 标题不参与序列
identity；裸序列和同内容 FASTA 必须得到相同规范序列 SHA-256。多记录、空记录和含歧义
残基的输入明确失败，不静默选择第一条记录。

当前用户入口是一个 target 文件和一个 `easydesign.yaml`。YAML 中的 `target.source`
相对于 YAML 自身解析，`format: auto` 使用文件后缀和内容强证据识别输入。PDB/mmCIF
等尚未实现的入口可以被识别，但会明确报错，不会回退为 sequence 或 PSE。

PSE 首版只实现可信本地、单蛋白、单链、单 coordinate state 导入。PSE 坐标直接标记为
`imported`，不运行 Protenix、MSA 或其他结构预测；逐残基 CA 颜色保存为
`uninterpreted` source annotation，Stage 01 不把颜色解释成 hotspot。

## 输入

- 恰好一种 source kind 及其专属参数。
- 结构选择规则和显式预测 fallback 规则。
- 可选 chain/domain 选择与生物学约束。

sequence/FASTA 路径通过通用 `StructurePredictionRequest` 访问预测 backend。EasyDesign 1.0
当前实现为 `protenix==2.0.0` / `protenix-v2`；AFO、AF3 或其他模型只能作为实现同一契约的
后续 adapter，不得改变 Stage 01 输出。

sequence/FASTA 的用户 YAML 必须声明 `msa` 和 `template_mode`。默认且当前唯一正式主线是
MSA-backed Protenix-v2；用户 YAML 禁止 `mode: disabled`，no-MSA 只保留为 Python API
内部工程 smoke。EasyDesign 保存原始输入和 YAML snapshot，生成
`resolved-config.json`，再由 adapter 生成 attempt 内部 `inputs/protenix-input.json`；
用户不维护 Protenix JSON。

当前标准配置：

```yaml
schema_version: "0.2"
project_id: apoe
target:
  id: apoe4-fragment-41-183
  source: apoe4-fragment-41-183.fasta
  format: auto
structure_prediction:
  backend: protenix-v2
  msa:
    mode: remote
    providers:
      - provider: colabfold-public
        timeout_seconds: 1800
        max_attempts: 3
        retry_backoff_seconds: 30
    no_msa_fallback: false
  template_mode: disabled
  parameter_profile: model-default
workflow:
  stop_after_stage: 1
```

远程 MSA 配置必须把 provider preset 同时解析成服务模式和明确 endpoint；只传
`--msa_server_mode` 不代表已经切换远程服务。attempt 必须保存 resolved endpoint、
ticket、状态历史、timeout、query identity、输出 A3M identity 和实际深度。endpoint
失败时不得静默切换到另一个 provider 或 no-MSA。

| Provider | Endpoint / mode | 当前定位 |
| --- | --- | --- |
| `colabfold-public` | `https://api.colabfold.com` / `colabfold` | 默认；APOE smoke 已通过，但公共服务无可承诺 SLA |
| `protenix-official` | `https://protenix-server.com/api/msa` / `protenix` | 可显式选择；当前持续 `PENDING`，不进入默认兜底链 |
| `custom-colabfold` | 用户显式 URL / `colabfold` | 自建服务接口；当前尚无 EasyDesign 管理的部署 |

同一 provider 可在声明预算内有限重试；`providers` 的后续成员是显式兜底顺序。正式执行器
必须让每次重试/切换产生新的 immutable attempt。目前已经完成 provider/endpoint 绑定、
timeout 和 resolved plan；多 provider 执行、ticket/status 采集和本地/缓存 MSA 仍在 TODO。
使用公共 provider 会把 target 序列提交给第三方服务；当前只批准内部研究运行。敏感或商业
序列在完成服务条款、隐私和数据处理审查前，必须使用经过批准的自建
`custom-colabfold`/本地 MSA，不得由 UI 静默发送到公共 endpoint。

PSE 路径使用排他的 YAML 分支：

```yaml
schema_version: "0.1"
project_id: apoe
target:
  id: apoe-1b68-pse
  source: apoe_abc.pse
  format: auto
workflow:
  stop_after_stage: 1
```

PSE 必须省略 `structure_prediction`；提供该区块会明确失败。反之，sequence/FASTA 必须
提供 `structure_prediction`。PyMOL 只存在于独立环境，调用方显式设置
`EASYDESIGN_PYMOL_PYTHON`；core 禁止扫描 Conda 或系统 Python，也禁止版本 fallback。

## 输出

- 规范 `target.cif`；后端明确需要时才派生 `target.pdb`。
- `sequence.fasta`、逐残基编号映射、结构质量报告和来源记录。
- `target-bundle.json` 及其中每个 artifact 的相对路径、大小、SHA-256 和生产 attempt。
- 说明结构属于实验、导入还是预测来源的 manifest。
- PSE 额外输出 `source-annotations.json`，记录 CA color index、RGB、hex 和颜色计数。

PSE attempt 的稳定目录为：

```text
01-target-preparation/attempt-0001/
├── inputs/pse-request.json
├── work/                         # worker 私有 response 和 raw PDB
├── logs/
└── artifacts/
    ├── target.cif
    ├── sequence.fasta
    ├── residue-mapping.json
    ├── structure-quality.json
    ├── provenance.json
    ├── source-annotations.json
    └── target-bundle.json
```

## 不变量

- 残基身份和编号映射无歧义；预测 CIF 中的聚合物序列必须与规范输入逐位相同。
- 搜索、排序、下载、转换、MSA、模板策略和 fallback 全部留痕。
- 原始输入按 checksum 引用，attempt 和正式 artifact 不覆盖。
- 同一次实验只有一个 `runs/<project_id>/<run_id>/`；Stage 01 输出不另建第二个 run 根。
- 远程 MSA 失败不得静默降级为 no-MSA；no-MSA 只作为明确标记的工程 smoke。
- 远程 MSA 的 provider、mode 和 endpoint 必须一致且可审计；禁止用解析模式名称推断
  实际请求端点。
- sequence/FASTA 正式 YAML 必须启用 MSA；公共服务失败时必须终止或进入 YAML 显式声明的
  下一 provider，禁止继续无 MSA 预测。
- `easydesign-core` 不导入 Protenix；adapter 只转换请求/结果，独立环境执行重型工具。
- 预测结构不得描述成实验结构，smoke 分数不得描述成科学验证。
- PSE 必须恰好一个含蛋白的 molecule object、一条非空 protein chain 和一个 state；
  至少 20 个标准氨基酸残基且每个残基恰好一个 CA。
- selection、measurement 等可视化对象只进入 inventory；水可忽略并计数。
- 额外蛋白 object/chain、配体或非溶剂重原子、多 state、非标准残基、残基编号歧义均失败；
  禁止使用旧版“选择最大 object/chain”逻辑。
- PSE source snapshot、worker raw PDB 和 response 的 SHA-256 必须逐层一致。

## 失败与重试

典型失败包括来源无效或有歧义、找不到符合规则的结构、序列/结构不匹配、chain 未解析、
MSA 服务失败、预测输出缺失、checksum 不一致和格式转换失败。

PSE 还包括 PyMOL Python 未显式配置、版本不是 `3.1.0`、worker 超时或非零退出、PSE
损坏、worker 输出缺失，以及违反上述单 Target 边界。失败 response、stdout/stderr 和
终态 attempt 必须保留；不能把失败会话回退为 sequence 预测。

失败必须写成带类型错误信息的终态 attempt，不能转换为空成功。重试建立新 attempt，
引用并保留失败 attempt；切换 MSA 服务必须符合 YAML 中有序 provider 计划，切换预测
backend 或模型必须显式创建新配置和溯源。公共服务不能假定永久稳定。

## 溯源

Manifest 记录上游 manifest/artifact hash、解析后配置、代码版本、adapter/backend 身份与
版本、模型和 checkpoint hash、随机种子、resolved recycle/diffusion 参数、MSA 来源和
输入 hash、模板模式、executor profile、时间、警告和全部 attempt。

第三方 package、模型和运行缓存按 `resources/provenance/ASSET_REGISTER.tsv` 登记。模型、
MSA、run 和缓存均位于 Git 忽略目录，不随仓库分发。

PSE provenance 还记录 PyMOL 版本、session inventory、被选中的唯一 object/chain/state、
原始 PSE SHA-256、水和非蛋白重原子计数、worker/adapter 时间及 `fallback_used=false`。

## 完成门槛

- 六类入口全部通过各自契约测试和至少一个真实 fixture。
- 全部必需 Target Bundle artifact 校验通过并有 checksum。
- Stage 02 可以只通过 Target Bundle 和残基映射解析每个残基，无需扫描 backend 目录。
- sequence/FASTA 路径通过内部 no-MSA 回归 smoke，并以
  remote-MSA/no-template 作为默认正式路径完成 APOE 真实运行和 Target Bundle 发布。
- PSE 路径通过合成成功/失败 session 契约测试和旧 APOE PSE 真实 smoke。

## 非目标

- 选择 hotspot。
- 生成 binder。
- 自动决定有争议的 accession、isoform、物种或结构来源。
- 把预测结构描述成实验结构。
- 在 Stage 01 将 PyMOL 颜色称为成熟 hotspot 证据。
- 首版处理复合物、receptor/ligand、多聚体、配体保留、公开上传，或让用户选择
  object/chain/state。

外部工具只通过 adapter 访问；orchestration、UI 行为和下游决策不属于本阶段。
