# 01 — Target 准备

**阶段状态：** `planned`。sequence/FASTA 纵向切片已实现；单 Target PSE 导入已完成
真实 smoke；其他入口仍未实现。

**契约版本：** Target Bundle `0.3`，兼容读取 `0.1/0.2`。

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

当前用户入口是一个 target 文件和一个 `easydesign.yaml`。YAML 中的
`stage01.target.source`
相对于 YAML 自身解析，`format: auto` 使用文件后缀和内容强证据识别输入。PDB/mmCIF
等尚未实现的入口可以被识别，但会明确报错，不会回退为 sequence 或 PSE。

Developer Preview 推荐先通过统一入口创建和运行，不需要 Agent 手工编排：

```bash
easydesign init PROJECT_DIR --target TARGET_FILE --stop-after 1
easydesign config validate PROJECT_DIR/easydesign.yaml
easydesign doctor --config PROJECT_DIR/easydesign.yaml
easydesign run PROJECT_DIR/easydesign.yaml
```

CLI 只调用本阶段相同 Python API；其成功不会提高本阶段的科学证据等级。

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
schema_version: "0.3"
project_id: apoe
workflow:
  stop_after_stage: 1
stage01:
  target:
    id: apoe4-fragment-41-183
    source: apoe4-fragment-41-183.fasta
    format: auto
    identity:
      uniprot_accession: null
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
stage02: null
stage03: null
stage04: null
stage05: null
stage06: null
stage07: null
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
让每次重试/切换产生新的 immutable attempt；耗尽 provider 计划后正式失败，不执行
no-MSA。A3M 必须来自当前 attempt、首条 query 与规范 target 完全相同、depth 至少为 2，
才允许启动结构预测。Protenix 2.0.0 CLI 不暴露 ticket，必须明确记录“不可见”状态，不能
伪造 ticket；直接 ticket/status 采集和本地/缓存 MSA 仍在 TODO。
使用公共 provider 会把 target 序列提交给第三方服务；当前只批准内部研究运行。敏感或商业
序列在完成服务条款、隐私和数据处理审查前，必须使用经过批准的自建
`custom-colabfold`/本地 MSA，不得由 UI 静默发送到公共 endpoint。

PSE 路径使用排他的 YAML 分支：

```yaml
schema_version: "0.3"
project_id: apoe
workflow:
  stop_after_stage: 1
stage01:
  target:
    id: apoe-1b68-pse
    source: apoe_abc.pse
    format: auto
    identity:
      uniprot_accession: null
  structure_prediction: null
stage02: null
stage03: null
stage04: null
stage05: null
stage06: null
stage07: null
```

PSE 必须省略 `structure_prediction`；提供该区块会明确失败。反之，sequence/FASTA 必须
提供 `structure_prediction`。PyMOL 只存在于独立环境，正式 CLI 从用户级 runtime
profile 读取显式绝对 Python 路径；core 禁止扫描 Conda 或系统 Python，也禁止版本
fallback。

## 输出

- 规范 `target.cif`；后端明确需要时才派生 `target.pdb`。
- `sequence.fasta`、逐残基编号映射、结构质量报告和来源记录。
- `target-bundle.json` 及其中每个 artifact 的相对路径、大小、SHA-256 和生产 attempt。
- `coordinate_ensemble`：model 数量、稳定 model IDs、代表 model 和共享残基身份策略。
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

sequence/FASTA MSA-backed attempt 使用同一浅层布局：

```text
01-target-preparation/attempt-0001/
├── inputs/
│   ├── protenix-input.json
│   └── protenix-input-update-msa.json
├── work/
│   ├── msa/
│   └── prediction/
├── logs/
├── attempt-manifest.json
└── artifacts/
    ├── target.cif
    ├── sequence.fasta
    ├── residue-mapping.json
    ├── structure-quality.json
    ├── provenance.json
    ├── target-msa.a3m
    └── target-bundle.json
```

PSE 与 sequence 的正式交接均以 Target Bundle 声明的 `target.cif`（`file_format=mmcif`）
为准。两者可以有不同序列长度和坐标来源，但文件协议、编号映射和 manifest 链必须一致；
backend 工作目录中的 PDB/CIF 不属于正式交接。

Target Bundle `0.3` 允许 `target.cif` 包含一个或多个
`_atom_site.pdbx_PDB_model_num`。`sequence.fasta` 与 mapping 描述所有模型共享的残基
身份；模型可以缺部分残基或原子，但同一 `label_seq_id` 在不同模型中的氨基酸类型必须
一致。下游不得把 ensemble 静默压成 model 1。代表模型只服务于展示和输出质心，不替代
多模型科学共识。

当前 PSE adapter 仍严格单 state，Protenix adapter 仍严格单 seed/单 sample，因此这两条
已实现入口均发布 `model_count: 1`。这是 adapter 范围，不再是 Target Bundle 的全局
限制；本地 PDB/mmCIF、预测 ensemble、多 state PSE 和多 seed/sample 策略仍待实现。

### 便携式 Target Viewer

sequence/FASTA 和 PSE 两条正式路径在成功发布 StageManifest 与 RunManifest 后，会调用同一
reporting API 生成只读 Mol* 报告：

```text
results/01-target-preparation/target-viewer/
├── LATEST
└── report-0001/
    ├── index.html
    ├── viewer-data.json
    ├── report-manifest.json
    ├── data/
    │   ├── target.cif
    │   ├── sequence.fasta
    │   └── residue-mapping.json
    └── assets/
        ├── molstar.js
        ├── molstar.css
        ├── easydesign-viewer.js
        ├── easydesign-viewer.css
        └── MOLSTAR_LICENSE.txt
```

报告只从当前 RunManifest 声明的 succeeded Stage 01 manifest 进入 Target Bundle，并逐一
验证 ArtifactRef 的路径、大小和 SHA-256。它不扫描 Protenix、PyMOL 或其他 backend
目录，也不写回 Stage 01 artifact。每次调用生成新的 `report-XXXX`，原子更新 reporting
自己的 `LATEST`；报告不可覆盖，最新 revision 失败时不得回退到旧成功报告。

报告包含 `target.cif`、FASTA 和 mapping 的自包含副本，以及固定 Mol* 5.11.0 本地资产；
不会访问 CDN、上传结构、复制日志、原始 YAML、完整 MSA、密钥或绝对路径。页面可旋转、
缩放、平移、居中，显示 model 数量和代表 model，切换 cartoon/surface/stick，通过
Mol* 序列面板和三维点击显示
label/auth 编号，并下载报告目录中的三个副本。Protenix 只展示已有整体质量，不推测逐残基
pLDDT。

PSE 报告提供“默认结构颜色 / PSE 来源颜色”开关；颜色始终标记为
`uninterpreted annotation`，不代表 hotspot 或 binding residue。没有 annotation 的
sequence 报告明确写 `not_applicable`，不能用空数组冒充已查询。

Viewer 失败只形成 reporting failure，不改变已经发布的 StageManifest、RunManifest 或
Stage 02 handoff。Stage 01 不自动启动常驻服务；需要查看时执行：

```bash
python scripts/serve_target_viewer.py \
  runs/apoe/20260724-006-stage01-msa \
  --port 8000
```

服务启动前验证报告状态和全部 checksum，只绑定 `127.0.0.1`，根目录严格限制为单个
report revision。远程服务器使用 SSH 端口转发，不开放 `0.0.0.0` 或公网访问。

## 不变量

- 残基身份和编号映射无歧义；预测 CIF 中的聚合物序列必须与规范输入逐位相同。
- Target Bundle 声明的 model IDs 必须与 mmCIF 完全一致；跨模型同一 label residue
  类型不得冲突，模型缺失坐标必须显式保留为缺失证据。
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
- Target Viewer 是正式 artifact 的只读派生报告，不进入 StageManifest，也不能改变
  Stage 01 科学执行状态。
- Viewer 只能读取 manifest 声明的 Target Bundle；报告 revision 和报告副本不可覆盖。
- 浏览器只访问报告自己的 localhost origin；禁止 CDN、外部 API 和整个 run 目录暴露。

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
- sequence 与 PSE 的 Target Viewer 都通过 Python checksum/revision 契约、Chromium
  localhost 浏览器测试和真实 APOE 可移植性 smoke。

## 非目标

- 选择 hotspot。
- 生成 binder。
- 自动决定有争议的 accession、isoform、物种或结构来源。
- 把预测结构描述成实验结构。
- 在 Stage 01 将 PyMOL 颜色称为成熟 hotspot 证据。
- 在 Viewer 中保存 hotspot、批准区域或自动推进 Stage 02。
- 首版处理复合物、receptor/ligand、多聚体、配体保留、公开上传，或让用户选择
  object/chain/state。

外部工具只通过 adapter 访问；orchestration、UI 行为和下游决策不属于本阶段。
