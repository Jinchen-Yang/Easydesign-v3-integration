# EasyDesign 架构

本文档是仓库层级、依赖方向、运行目录和环境边界的事实来源。它描述稳定职责，不罗列缓存、
构建产物或每一个临时文件。

## 1. 仓库总览

```text
easydesign-clean/
├── README.md                 # 项目入口与当前状态
├── PROJECT_CHARTER.md        # 战略、1.0 边界与工程规则
├── AGENTS.md                 # Agent 自动工作协议
├── TODO.md                   # 宏观里程碑和七阶段状态索引
├── TODO_NOW.md               # 跨阶段当前重点、阻塞和历史索引
├── environment.yml           # easydesign-core Conda 环境入口
├── environments/             # 重型 backend 的独立 Conda 环境声明
├── pyproject.toml            # Python 包、运行依赖和开发依赖
├── Makefile                  # 环境、检查、测试和构建入口
├── workflow/                 # 七阶段契约、动态状态和阶段历史
├── src/easydesign/           # 唯一 Python 实现
├── configs/                  # 默认值、backend、filter 和执行 profile
├── tests/                    # unit、integration、e2e 和 fixture
├── resources/                # 已审查小型资产与来源登记
├── examples/                 # 最小可复现示例
├── scripts/                  # 仅调用 API 的开发脚本
├── runs/                     # 项目 run、开发验证、历史归档和可再生索引，Git 忽略
└── models/                   # 权重和模型缓存，Git 忽略
```

## 2. Python 源码层级

```text
src/easydesign/
├── cli.py                   # Developer Preview 参数解析与展示
├── __main__.py              # python -m easydesign
├── core/
│   ├── artifacts.py         # ArtifactRef、文件身份和路径约束
│   ├── attempts.py          # Attempt、执行状态和终态规则
│   ├── manifests.py         # StageManifest 与 RunManifest
│   ├── serialization.py     # 规范 JSON 读写
│   ├── hashing.py           # SHA-256 与完整性验证
│   ├── tasks.py             # TaskRecord、TaskEvent 与 ProgressSnapshot
│   ├── timestamps.py        # 时区时间统一为 UTC
│   └── errors.py            # 稳定、可分类的核心异常
├── stages/
│   ├── s01_target_preparation/
│   ├── s02_hotspot_discovery/
│   ├── s03_boltzgen_configuration/
│   ├── s04_pilot_generation/
│   ├── s05_pilot_filtering/
│   ├── s06_scale_generation_and_refolding/
│   └── s07_final_filtering_and_selection/
├── backends/
│   ├── target_sources/      # PDB/mmCIF、RCSB、序列、UniProt、PSE
│   ├── hotspot/             # 人工、SASA、界面迁移和注释来源
│   ├── boltzgen/            # BoltzGen 能力、请求与结果转换
│   ├── structure_prediction/# Protenix-v2、AFO、AF3 等通用预测接口
│   ├── tnp.py               # 固定 TNP Python 3.10 文件协议 adapter
│   └── executors/           # local、Slurm、SMART 执行
├── orchestration/
│   ├── application.py       # CLI/UI 共用的 init/doctor/run/runs API
│   ├── profile.py           # 本机 backend 路径和 profile identity
│   ├── project.py           # 从真实 target 初始化用户项目
│   └── ...                  # 阶段执行、Workspace、迁移和配置
├── filtering/               # Stage 05/07 共用的版本化筛选框架
└── reporting/               # 运行、候选、证据和人工审核报告
```

### 目录所有权

- `core/` 只定义跨阶段通用契约，不依赖具体 stage、BoltzGen、预测模型或集群。
- `stages/` 实现七个阶段的领域转换，只通过 backend interface 使用外部工具。
- `backends/` 负责把通用请求转换成外部工具格式，再把结果规范化；不决定流程顺序。
- `orchestration/` 串联阶段和管理恢复；不重新实现结构处理、hotspot 或 filter。
- `filtering/` 提供通用规则执行与审计；具体阈值由版本化配置提供。
- `reporting/` 只消费正式 manifest 和 artifact，不扫描 backend 私有目录。
- `cli.py`、`scripts/` 和未来 UI 只调用 orchestration/API，不承载科学逻辑。

## 3. 允许的依赖方向

```text
CLI / UI / scripts
        ↓
orchestration
        ↓
stages ─────────→ filtering / reporting
        ↓
core interfaces
        ↑
backend adapters ─→ 外部可执行程序或服务
```

禁止：

- `core` 导入 `stages` 或具体 backend；
- Stage 01 导入 Stage 02–07；
- backend 调用 orchestration 决定下一阶段；
- CLI/UI 直接读取模型私有输出并形成第二套 pipeline；
- 通过绝对服务器路径在模块之间传递 artifact。

## 4. Workflow 文档层级

每个 Stage 的稳定契约、动态状态和历史必须分开：

```text
workflow/<NN-stage-name>/
├── README.md                 # 稳定职责、输入输出、不变量和完成门槛
├── STATUS.md                 # 功能矩阵、Now/Next/Blocked、验证和近期日志
├── history/
│   └── YYYY-MM.md            # 已结束的阶段日志，只追加
└── examples/
```

各 Stage `STATUS.md` 的“顶层摘要”是状态事实来源。`scripts/sync_status_rollup.py`
从七个摘要生成 `TODO.md` 和 `TODO_NOW.md` 的实时表，`make check` 拒绝任何不同步。
顶层人工维护内容只保留宏观路线和跨阶段 Now/Next/Blocked；阶段证据仍留在对应 STATUS
与 history，避免复制详情。

Stage 工作项与顶层跨阶段工作项在完成后统一使用以下时间字段：

```text
- 完成时间：2026-07-25T14:30:00+08:00
```

它表示完成门槛实际满足、工作即将从 `Now` 移出的时间，而不是月度文件创建时间或
Agent 开始工作的时间。秒级时间和显式 UTC offset 都是必需项；仓库检查会遍历所有
`workflow/*/history/YYYY-MM.md` 和 `docs/history/YYYY-MM/TODO_NOW.md`，拒绝缺失、
重复、无时区或仅含日期的完成记录。

## 5. 环境拓扑

当前统一使用 Conda 管理环境，但每个重型工具仍保持隔离：

```text
easydesign-core (Python 3.11)
├── pipeline、manifest、配置、轻量生信、测试和报告
├── subprocess/JSON+PDB → pymol-pse 环境
├── subprocess/PDB+CSV  → scannet-epitope 隔离环境（CPU 默认，GPU 可选）
├── subprocess/文件协议 → boltzgen 环境
├── subprocess/文件协议 → boltz2 环境
├── subprocess/文件协议 → protenix-v2/AF3/AFO 环境
└── executor adapter     → local/Slurm/SMART
```

`environment.yml` 创建 `easydesign-core`；`pyproject.toml` 是 Python 依赖和
`easydesign` console-script 的唯一声明源。源码 editable 安装、普通本地安装和 wheel
安装都必须产生同一个命令入口。
`environments/protenix-v2.yml` 固定 EasyDesign 1.0 当前结构预测后端的独立环境。
`environments/pymol-pse.yml` 固定 PyMOL PSE 导入环境的 Python 3.11 和
`pymol-open-source=3.1.0`。Core 不导入 PyMOL，也不扫描 Conda 或系统 Python；正式 CLI
从用户级 runtime profile 读取绝对 Python 路径。Adapter 先做精确版本探针，再用
无 shell 的 argv 执行只依赖标准库和 PyMOL 的 worker。请求和 response 使用 JSON，
worker 导出的原始蛋白坐标使用 PDB，core 再规范化为 mmCIF。
`environments/scannet-epitope.yml` 当前固定 ScanNet 的遗留 Python 3.6.12、
TensorFlow GPU 1.14、CUDA 10 与 cuDNN 依赖；同一环境可通过隐藏 CUDA 设备执行 CPU。
Core 把规范结构转换成单链、连续工具编号 PDB，ScanNet 输出 CSV 后再通过显式 mapping
回到 mmCIF label/auth 编号。Adapter 必须显式选择 `cpu` 或 `gpu`，默认 CPU，并用 runtime
probe 证明实际计算设备与请求一致；禁止设备间静默 fallback。当前 CPU 是 1.0 主线，GPU
兼容性与性能优化是后续 benchmark，不阻塞 Stage 02。
`environments/reporting-web.yml` 固定 Node.js 22，只用于更新 Mol* 静态资产、
Playwright Chromium 测试和许可证审计。EasyDesign 运行时、报告生成与本地服务仍只依赖
`easydesign-core` Python；Node、npm 和浏览器不会进入科学 pipeline。
重型 backend 按其上游要求使用独立 Conda 环境、容器或 module。Core 不激活环境，不向
重型环境安装自身依赖；adapter 使用显式 executable、工作目录、请求文件和结果 manifest。

Stage 04 generation 复用 Stage 03 的精确 version/commit/cache probe。
`backends/boltzgen/generation.py` 只把类型化请求转换为无 shell argv；
`backends/executors/local_multi_gpu.py` 只负责 GPU 资源门槛和每设备一个串行 worker；
候选完整性由 Stage 04 collector 定义。这三层不得互相复制职责。

站点专属环境路径只能出现在未提交的本地 profile 或调用参数中。仓库代码不得硬编码
`/root/autodl-tmp`、SMART 路径、用户名或密钥。

Runtime profile 默认位于操作系统标准用户配置目录。解析优先级为 `--profile`、
`EASYDESIGN_PROFILE`、用户级默认文件；只选择一个完整 profile，不扫描环境、不合并多个
文件。profile 保存 executable、模型和设备等部署信息，用户 `easydesign.yaml` 只保存
科学配置。run 记录 profile ID 与文件 SHA-256，以及实际 backend/model/device identity，
但不复制机器绝对路径。

## 6. 运行目录层级

```text
runs/
├── run-index.json                 # 可再生导航索引，不是科学 artifact
├── _development/                  # backend smoke、外部服务诊断
├── _archive/                      # 旧布局迁移清单，不放当前项目 run
└── <project_id>/<run_id>/
    ├── input-snapshot/
    ├── config-snapshot/
    │   ├── easydesign.yaml
    │   └── resolved-config.json
    ├── manifests/
    │   ├── LATEST
    │   ├── run-manifest.v0001.json
    │   └── run-manifest.v0002.json
    ├── 01-target-preparation/
    │   └── attempt-0001/
    │       ├── inputs/
    │       ├── logs/
    │       └── artifacts/
    ├── 02-hotspot-discovery/
    ├── 03-boltzgen-configuration/
    ├── 04-pilot-generation/
    ├── 05-pilot-filtering/
    ├── 06-scale-generation-and-refolding/
    ├── 07-final-filtering-and-selection/
    └── results/                    # 面向人的最终汇总，不取代正式 artifact
```

同一次实验从 Stage 01 到 Stage 07 始终使用同一个 run 根目录；七个 Stage 是同级目录，
下游不得嵌套到上游目录。`attempt-0001/` 直接位于 Stage 目录，取消没有语义增量的
`attempts/` 中间层。后端安装和服务可用性 smoke 不属于项目 run，必须进入
`_development/`。

早期运行可以整体迁移，但不得改写内部文件。迁移前后必须验证目录 fingerprint 和所有
manifest artifact 引用，并在 `_archive/migrations/` 保存旧路径、新路径、文件数、字节数
和 SHA-256。使用旧布局的已发布 run 只整体移动，内部 `attempts/` 层保留为历史证据。

### 用户输入到后端输入

本地 source 路径的用户界面只有 source 文件与一个配置；远程 source 只需要配置：

```text
target.fasta | target.pdb | target.cif | target.pse | target-bundle.json
easydesign.yaml
```

`easydesign.yaml` schema `0.7` 固定展示 `stage01` 至 `stage07`；`design` 保存跨阶段
binder profile/intent，未实现阶段写 `null`。`stage01.target.source` 是
`local-file | pdb-id | uniprot | uniprot-search | target-bundle` 的 discriminated union；
本地路径相对于 YAML 解析。旧 schema 0.3 只在加载边界规范化，run 内
`resolved-config.json` 永远保存 0.7。

统一 Stage 01 source pipeline 是：

```text
snapshot/identity/scope
→ local inventory 或 UniProt/RCSB retrieval
→ strict candidate QC
→ experimental selection 或显式 Protenix fallback
→ protein-only chain A normalization
→ mapping/QC/provenance/Target Bundle
→ Viewer
```

`orchestration/stage01_handlers/` 是唯一 source dispatcher 层，六个入口分别由
`local_structure.py`、`pdb_id.py`、`sequence.py`、`uniprot.py`、`pse.py` 和
`target_bundle.py` 接收。它们共享 identity/scope/structure selection、Decision Gate、
Protenix request、Bundle 发布与失败证据，不复制科学规则。旧
`stage01_sources.execute_stage01_source()` 只保留兼容门面。

FASTA 与 UniProt 不直接跳到预测：先用 RCSB Sequence Search v2/Data API 查实验结构。
`experimental-strict-v1` 要求 scope 100% 坐标覆盖、100% 序列一致、每个 residue 有 CA，
并限制 X-ray ≤3.5 Å、cryo-EM ≤4.0 Å。NMR 只作为 review-only 选项。PDB ID/本地结构是
用户显式选择，QC 失败时不自动换结构。

用户不提交 Protenix JSON。orchestration 规范化序列并创建通用
`StructurePredictionRequest`，Protenix adapter 再把它写入：

```text
01-target-preparation/attempt-0001/inputs/protenix-input.json
```

原 YAML 和 target 文件进入 run 的 snapshot；解析后的格式、序列 SHA-256 和通用预测请求
写入 `resolved-config.json`。

sequence/FASTA 的 `stage01.structure_prediction` 必须包含 MSA policy：

```yaml
stage01:
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
```

默认 provider `colabfold-public` 被解析为
`https://api.colabfold.com` + `--msa_server_mode colabfold`；两者由同一 preset 绑定，
不能分别覆盖。`providers` 是显式顺序计划：重试或切换 provider 必须创建新 attempt，
终态证据不可覆盖。用户 YAML 不接受 `mode: disabled`，但 Python API 仍保留 no-MSA
能力，只供明确标记的内部工程 smoke。`resolved-config.json` schema `0.4` 保存 endpoint、
server mode、timeout、最大 attempt 数和 backoff；公共 MSA 服务没有可承诺的 SLA。

当前 adapter 已为每个 MSA invocation 绑定 endpoint 和 wall-clock timeout。多 provider
执行器由 `orchestration/sequence_prediction.py` 实现：同一 provider 的每次重试和
provider 切换都会创建新的 immutable attempt；A3M 必须位于当前 attempt work 目录，
首条 query 必须与规范序列完全一致且 depth 至少为 2。成功后 executor 只选择契约限定的
单 seed/单 sample，发布与 PSE 路径相同的 `target.cif`、sequence、residue mapping、
quality、provenance、Target Bundle 和 Stage/Run manifests，并额外发布 `target-msa.a3m`。

Protenix 2.0.0 CLI 不暴露远程 ticket，因此 provenance 会明确记录
`not-exposed-by-protenix-cli-2.0.0`，不能伪造 ticket。可直接采集 ticket/status 的服务
sequence-hash cache 和预计算 A3M 已实现并由 schema 0.6 显式选择；自建
ColabFold/MMseqs2 profile 仍属于后续实现。

旧版目录（只用于解释历史，不再生成）：

```text
runs/<project_id>/<run_id>/
├── manifests/
├── 01-target-preparation/
│   ├── attempts/
│   │   └── attempt-0001/
│   └── ...
```

PSE 路径同样只接受 `target.pse + easydesign.yaml`，但与 sequence 路径排他：

- PSE 配置必须省略 `structure_prediction`，因为其坐标直接标记为 `imported`；
- adapter 生成 `attempt-0001/inputs/pse-request.json`，只引用 run 内 source snapshot
  和 SHA-256；
- worker 私有 response/PDB 留在 `attempt-0001/work/`，正式 artifact 由 core 写入
  `attempt-0001/artifacts/`；
- `source-annotations.json` 只保存逐残基 CA 颜色，不赋予 hotspot 语义；
- PSE 成功后发布 Attempt、StageManifest 和新的 RunManifest revision，更新 `LATEST`
  指针；不生成 Protenix JSON，也不触发 MSA 或预测。

### Target Bundle ensemble 与 Stage 02 独立方法边界

Target Bundle `0.4` 声明 `coordinate_ensemble` 和可选 Stage 01 evidence/context
ArtifactRef；mmCIF 可以包含一个或多个 model，残基
身份跨模型共享，缺失坐标保留为证据。PSE 与 Protenix 当前 adapter 都仍只生成单模型，
但该限制不再进入通用 Bundle 契约。Viewer 显示 model 数量和代表 model。

Stage 02 automatic 按 YAML 选择一个或两个独立 provider：

- SASA provider 只读取坐标、编号和用户显式 avoid，输出 rSASA/几何排序；
- ScanNet provider 只读取坐标和逐残基模型 probability，输出独立概率排序；
- 比较层只计算区域重合与空间距离，不产生融合分数或默认赢家；
- PSE颜色和人工区域不进入 automatic；可选 UniProt/PTM annotation 只形成证据/warning，
  不修改两种方法的排名。

SASA 对每个 coordinate model 独立计算 rSASA/图，再按显式 70% 阈值形成保守共识；
ScanNet v0.1 遇到多模型明确返回 `unsupported_ensemble`。只运行一种方法时不创建另一
方法或 comparison 的空产物。

自动 attempt 成功后 RunManifest `1.2` 保持 `running`，写
`workflow_state=awaiting-human-approval`。人工审批通过单独的 `attempt-0002` 选择同一
方法的 2–3 个完整区域并发布 `hotspots.yaml`；该文件是 Stage 03 唯一入口。structural-only
审批必须显式确认科学证据限制。

Stage 02 schema 0.6 还提供统一的用户区域边界：

```text
Target Bundle
├── target.cif + mapping + PSE source annotation ─→ 固定 R/B/Y 解析 ─┐
└── target.cif + mapping + YAML residue selectors ─→ 编号解析 ───────┤
                                                                    ↓
                      UserProvidedRegionSet → approval → hotspots.yaml 0.3
```

标准 PDB/mmCIF 不承载 EasyDesign 私有颜色；PSE 颜色保存在 Stage 01
`source-annotations.json`，Stage 02 通过 ArtifactRef/SHA-256 消费。`detect` 只有在
annotation 中存在固定红/蓝/黄时走用户区域，否则进入显式 automatic fallback；
`automatic` 从不读取颜色。PSE 和 YAML 最终共享同一不可变区域类型、mapping 校验和
审批实现，避免形成两套 Stage 03 handoff。

automatic unattended 仍是 deterministic-policy。用户区域 unattended 必须由初始配置
提供真实审批人、逐区理由和 acknowledgement，输出明确记录
`approval_authority=human` 与 `approval_source=initial-run-config`，不能伪装成算法批准。

### Stage 03 策略编译与 continuation

Stage 03 把已批准 `hotspots.yaml` 编译为 BoltzGen 配置；它不执行生成，也不重新判断
区域。依赖方向固定为：

```text
RunManifest
├── Stage 01 → target-bundle + target-structure
└── Stage 02 → approved hotspots.yaml
                     ↓ checksum/identity
      boltzgen-vhh-basic-v1 compiler
                     ↓ region × official-vhh7-v1
      design.yaml + StrategyBundle + validation report
                     ↓
              Stage 04 manifest-only handoff
```

编译器位于 `stages/s03_boltzgen_configuration/`，只实现区域到版本化策略的领域转换；
BoltzGen version/commit probe 和官方 `check` 位于 `backends/boltzgen/`；
`orchestration/stage03.py` 负责上游 manifest、attempt、StageManifest 和 RunManifest。
CLI 不拼接 YAML。

基础模板把每个区域全部 label residue 写成 positive `binding`，其余 residue 不写任何
标记。registry、模板 profile、candidate budget 和区域数来自类型化配置/输入；APOE
三分区不是代码常数。

`official-vhh7-v1` 的十四个 YAML/mmCIF 与上游 MIT license 作为 package data 分发。
每个文件在源代码中固定 SHA-256，运行时验证后复制到 attempt；StrategyBundle 同时记录
BoltzGen `0.3.2`、固定 commit 和上游 artifact hash。

已成功结束的 Stage 02 run 不能追加 RunManifest revision。下游工作使用显式
`--from-run` continuation：新 run 按字节复制 Stage 01/02 目录和输入 snapshot，复验原
ArtifactRef，并在 `continuation-source.json` 记录源 RunManifest hash。源 run 和其
artifact 保持不变；这不是扫描或重新导入科学结果。

### Stage 04 任务、进度和恢复

Stage 04 只读取 Stage 03 manifest 声明的 `StrategyBundle` 与 strategy YAML。一次
strategy generation 是稳定 `TaskRecord`，每次后端启动是新的 task attempt：

```text
PilotPlan
  ├── TaskRecord strategy-1
  │     ├── task attempt-0001
  │     └── task attempt-0002
  └── TaskRecord strategy-2
        └── task attempt-0001
```

运行中的可恢复状态位于 Stage attempt 的 `runtime/`：

```text
progress.json       原子替换，供 CLI/UI 快照读取
task-state.json     原子替换，保存 task attempts 与 candidate lineage
task-events.jsonl   append-only，严格连续 sequence
```

`runs watch` 只读 `progress.json`；`runs resume` 验证 plan checksum、候选结构 checksum
和 task state 后，只启动未达预算策略。中断时已形成 metric row、原始 complex CIF 与
refold CIF 的完整候选可以恢复，旧 task attempt 以结构化 interrupted error 关闭；任何
文件都不会被覆盖。

BoltzGen 的 `num_designs` 是本次生成请求，`budget=30` 是官方最终多样性目录预算，
`pass_filters` 是后续证据。Stage 04 的成功条件独立定义为：每个策略达到配置数量的
完整候选，且每个候选同时具有唯一 metric row、原始 complex CIF、refold CIF 和 checksum。
只有终态成功时才发布 `CandidateIndex` 和 `PilotBundle` 给 Stage 05。

### Stage 05 筛选、扩展与 full-target 验证

Stage 05 把筛选规则与执行恢复分成三层：

```text
filtering/
  ├── interface-geometry-v1          结构与界面指标
  ├── nanobody-filter-standard-v1.5 硬门、归一化、Tier 与排序
  └── protenix confidence parser     真实跨链 PAE/iPTM

orchestration/stage05.py
  ├── manifest-only 上游验证
  ├── 逐 candidate 指标 cache
  ├── 复用 BoltzGen task executor 扩展
  ├── Protenix full-target task executor
  └── Stage05Bundle / ScientificStop 发布
```

Stage 04/05 的 BoltzGen 调度共同调用 `orchestration/boltzgen_tasks.py`；Stage 05 不复制
命令、收集或恢复逻辑。结构指标 cache identity 同时钉住 candidate structure、target、
official design mask、hotspot set 和指标版本，避免 resume 时把旧值误用到新输入。

Stage 05 的 runtime `progress.json` 在
`pilot-structure-metrics`、`expansion-generation`、`expansion-structure-metrics` 和
`full-target-prediction` 间显式切换 phase；`runs watch` 根据 RunManifest 和 resolved
config 选择当前 Stage，不扫描目录猜测。结束前将 mutable progress 与 append-only event
journal 冻结为 StageManifest artifact。

Protenix complex request 是通用 `target+binder` 类型：target required MSA、binder
query-only、template disabled，full confidence 为必需输出。Stage 01 和 Stage 05/07
继续使用同一个 Protenix adapter；前者默认不需要 full-confidence matrix，后两者显式
请求。`stopped-no-tier-a` 和 `stopped-no-scale-winner` 是成功执行得到的科学负结果，
会终止 Run 但不会伪装成 operational failure。

### Stage 06 分片规模生成

Stage 06 只在 Stage 05 发布唯一 winner 后运行。它同时把 Stage 03 strategy YAML、
Stage 05 winner bundle 和 Stage 04 candidate index 声明为输入；后者仅用于从正式
ArtifactRef 测量候选磁盘基线，不能成为 manifest 外的隐式读取。

```text
ScaleResourceReport
  → ScalePlan
      ├── shard-0001 / stable ordinal range
      └── shard-0002 / stable ordinal range
  → shared BoltzGen task executor
  → exact merge / ScaleCoverageReport
  → ScaleBundle
```

`smoke-1000` 固定为两个 500-candidate shard；`production-50000` 固定为二十个
2500-candidate shard。profile 只定义能力，实际执行还必须满足初始配置中的
`preauthorized_candidate_limit`。当前资源门使用 Stage 04 声明 artifact 的每候选字节数
乘 20 的保守容量代理，且要求执行后仍保留文件系统总容量的 25%；预检失败发生在创建
task 前。

Stage 04–06 共同调用 `orchestration/boltzgen_tasks.py` 和 local multi-GPU executor。
Stage 06 不复制生成/收集逻辑，也不把 Stage 04/05 候选计入 scale 数量。运行状态仍使用
原子 progress/state 与 append-only events；发布中断后，终态 artifact 只有在模型 identity
或原始 bytes 完全一致时才可复用。Stage 07 只读取 StageManifest 声明、checksum 正确且
覆盖无缺口的 ScaleBundle/CandidateIndex。

### Stage 07 深度筛选、三 seed 与审核包

Stage 07 把确定性科学规则、重型后端和人工审核包分为三层：

```text
filtering/nanobody_final_v1_5.py
  ├── sequence/refold prefilter
  ├── S_deep / S_full / S_final
  ├── seed-pair consensus
  └── lazy-greedy diversity

backends/
  ├── structure_prediction/Protenix-v2
  └── tnp.py / Python 3.10 file protocol

orchestration/stage07.py
  ├── manifest-only upstream validation
  ├── local metric cache
  ├── resumable (candidate, seed) tasks
  ├── TNP batch attempt
  └── FinalCandidatePackage publication
```

Stage 05/07 共同调用 `complex_prediction_support.py` 构建 target-required-MSA、
binder-query-only、template-disabled 的 Protenix 请求；结构/界面原子选择和距离规则仍
只有 `interface-geometry-v1` 一个实现。Stage 07 不从 Protenix 或 TNP 私有目录扫描猜测
候选，只有严格 adapter 收集后形成的 ArtifactRef 才进入 manifest。

`S_full` 中依赖本批次分布的分量只从 seed 101 建立一次
`Seed101Normalization`。candidate identity 和 reference values 冻结为 artifact，
seed 202/303 必须复用同一参考，恢复执行也不能重算成不同 population。每个
`(candidate, seed)` 使用独立 TaskRecord；mutable prediction state/progress 原子更新，
events 和 operational failure 只追加。

TNP commit、license、Python 版本、源 executable SHA-256 和依赖由 adapter/asset register
共同固定。EasyDesign core 不导入 Torch、ANARCI、ImmuneBuilder 或 DSSP。TNP 原始 JSON
与每候选 CDR/Vernier liability CSV 均作为正式证据；TNP 失败时不得发布非空
FinalCandidatePackage。adapter 把 PATH、LD_LIBRARY_PATH 和 CONDA_PREFIX 限定到显式
Python 3.10 prefix，关闭 user-site 和 `CUDA_VISIBLE_DEVICES`；TNP 是 CPU evidence
backend，不与 BoltzGen/Protenix 抢占 GPU。Conda package identity、Python distribution
identity、DSSP executable、clean source commit 和未声明的间接依赖均由 doctor probe
逐项验证。

最终选择固定使用 90% `S_final` 与 10% design-sequence diversity 的确定性
lazy-greedy。包中主/备候选是建议，不是批准或订单：

```text
computed candidate
→ selected primary/backup
→ awaiting-human-review
→ not-ordered
```

无候选通过时发布 `ScientificStop(stopped-no-final-candidate)`；缺工具、缺证据、任务未
完成或 checksum 损坏写 `OperationalFailure`，二者不能互相替代。

### 远程 adapter、cache 与 Decision Gate

UniProt/RCSB 共用 core 环境中的轻量 `httpx` adapter，不引入新 Conda 环境。adapter
实施 bounded connect/read timeout、429 `Retry-After`、有限网络/5xx retry 和 4xx
不重试。cache 位于操作系统用户 cache 目录，但 `online` 不允许失败后静默读取旧值；
`prefer-cache` 与 `offline` 必须由 YAML 显式声明。实际消费的 response 会复制到 attempt
artifact，并在 retrieval manifest 中保存 URL、参数、时间、ETag/Last-Modified、大小和
SHA-256。

`review-gated` 与 `unattended` 共享同一 Stage 实现。前者在 identity、chain/construct、
structure selection 和 hotspot selection 发布 `DecisionRequest`，RunManifest 保持
`running/awaiting-human-approval`；`DecisionRecord` 钉住 request revision/hash，批准后
同一 run 建立新 attempt 并清除 workflow state。后者使用带 policy ID 的确定性规则；
Stage 02 必须单方法，不能融合或调用 LLM。Stage 03/05/06/07 的 YAML、go/no-go、预算和
Top N gate 已进入路线图；实际供应商下单始终在系统之外。

### Binder 类型扩展边界

七阶段 pipeline 面向多类 binder，VHH 只是 1.0 的首个 reference profile。Stage 01–02
处理 target、候选表面区域和 target-side annotation，原则上不绑定 VHH；Stage 03–07
通过 binder-specific profile、backend、scaffold/representation 和 filter 承载分子差异。

新增蛋白或肽 binder 时不得复制 orchestration、manifest 或运行目录。新类型必须声明其
表示、长度/组成约束、生成后端能力、结构预测需求、筛选规则和最终候选包格式，并继续使用
相同的 artifact identity、attempt、恢复和报告机制。未来 CLI/UI 只选择 profile 并调用
同一 API。

### 身份

- `project_id`：稳定项目 slug。
- `run_id`：一次完整七阶段运行的唯一 ID。
- `stage_id`：固定编号 `01`–`07`。
- `attempt_id`：阶段内单调递增的 `attempt-0001` 等。
- `artifact_id`：run 内稳定逻辑身份；文件内容同时用 SHA-256 验证。

Artifact 路径必须是相对于 run 根目录的 POSIX 路径，不能是绝对路径，不能包含 `..`，
不能逃出 run 根目录。

## 7. Manifest 与不可变性

- `ArtifactRef` 描述 artifact 的逻辑角色、相对路径、格式、大小、SHA-256 和生产者。
- `Attempt` 记录一次执行的状态、时间、backend、executor、seed、日志和错误。
- `StageManifest` 声明阶段接受的输入、产生的输出、attempt 历史和最终选择。
- `RunManifest` 声明项目/run 身份、代码/config/profile 版本及七阶段 manifest 引用。

终态 Attempt 和已发布 StageManifest 不可修改。RunManifest 使用递增版本快照；`LATEST`
只是可原子替换的小型指针，不是科学产物。恢复执行先验证上游 checksum 和配置兼容性，
然后追加新 attempt 和新 run manifest 版本。

当前基础契约还强制：

- 只有成功的 Stage 可以发布正式 output；
- 正式 output 必须来自该 Stage 被选中的成功 attempt；
- 下游只能接受编号更早且已经成功的上游 StageManifest；
- 下游 ArtifactRef 必须与上游声明在身份、路径、大小、SHA-256 和生产者上完全一致；
- manifest JSON 使用“临时文件 + 原子硬链接”写入，目标存在时拒绝覆盖；
- RunManifest revision 必须时间递增，并用前一版本规范 JSON 的 SHA-256 串成审计链。

RunManifest `1.0` 的 `code_commit` 和 `1.1` 的结构化代码身份继续兼容读取。新 run 使用
`1.2` 的 `code_identity` 与可选 `workflow_state`：

- clean checkout 记录完整 Git commit；
- dirty checkout 记录基础 commit、`dirty=true` 和 package tree SHA-256；
- wheel/非 Git 安装记录 installed package tree SHA-256，不伪装为 commit。
- 外部人工输入暂停点保持执行状态 `running`，并记录 stage、action 和消息；批准后建立
  新 revision 清除 workflow state，不能把等待状态伪装成 run 成功。

源码树哈希覆盖 `src/easydesign`、打包资源和影响构建的项目元数据，排除 bytecode、cache
和 Git 元数据；revision 链保持同一代码身份。

### Reporting revision 与本地展示边界

`reporting/` 是正式科学 artifact 的只读消费者。Stage 01 成功后，
`generate_stage01_target_viewer()` 只沿当前 RunManifest → StageManifest →
Target Bundle 引用链读取 `target.cif`、sequence、mapping、quality、provenance 和可选
PSE annotation，并重新验证每个 ArtifactRef。它不访问 backend 私有 work/log 目录。

Target Viewer 输出位于同一 run 的
`results/01-target-preparation/target-viewer/report-XXXX/`。报告 manifest 使用独立 schema
和 revision，保存源 manifest/bundle/structure SHA-256、生成器与 Mol* 版本及所有报告
文件 identity；reporting 的 `LATEST` 与科学 RunManifest 的 `LATEST` 完全分离。报告通过
临时目录和原子 rename 发布，旧 revision 不覆盖。报告失败时最新 revision 保持 failed，
不得回退旧报告，也不得改写 StageManifest、RunManifest 或 Stage 02 handoff。

每个 report 自带 mmCIF、mapping、FASTA、Mol* 5.11.0 JS/CSS 和许可证，复制到 run 外后
仍可查看。`viewer-data.json` 是面向展示的最小安全投影，只包含 target 身份、编号映射、
整体质量、安全 provenance、coordinate model identity 和可选未解释颜色；禁止绝对路径、
日志、用户配置、完整 MSA、密钥和未筛选 provenance。

本地服务先验证 report manifest 和全部 checksum，再把 server root 固定为单个
`report-XXXX/`，拒绝 path traversal 与 symlink 逃逸，只绑定 `127.0.0.1`。CSP 将脚本、
样式、结构请求和 worker 限制在自身 origin、必要的 `data:`/`blob:`；远程服务器只通过
SSH 端口转发访问。Mol* 5.11.0 官方预构建 bundle 初始化需要动态函数，因此
`script-src` 对经过 checksum 验证的本地同源 bundle保留 `'unsafe-eval'`；`connect-src`
仍只有自身，页面不接受用户 HTML。未来 CLI/UI 只能包装同一 reporting 与 serving API。

### 本地科研工作台边界

`easydesign ui serve` 使用 FastAPI/Uvicorn 固定监听 `127.0.0.1`，React/TypeScript
构建产物作为 Python package data 随 wheel 分发。Node.js 只用于前端构建和 Playwright
测试，不进入 EasyDesign 科学运行时。远程服务器只能通过 SSH 端口转发访问。

新建设计采用非线性五步向导：步骤切换只改变表单投影，不执行科学逻辑，也不以前序字段
是否完整限制用户阅读后续配置；完整性只在创建项目草稿、preflight 和真实启动三个动作
边界统一判断。浏览器选择本地文件后立即调用同源 `/api/v1/uploads`，服务把最多
64 MiB 的内容原子写入受控 `.ui-uploads/<token>/`，返回不含机器路径的 token、原始
basename、大小和 SHA-256。项目初始化只能消费当前服务签发的 token，成功复制到
`PROJECT/inputs/` 后使 token 失效并尽力清理临时副本。前端文件名本身不代表上传成功；
只有收到后端 receipt 才能将目标输入标记为就绪。

浏览器读取的是服务端从当前 RunManifest → StageManifest → ArtifactRef 生成的安全
projection。服务在投影和下载时重新校验 artifact 大小与 SHA-256；短期 HMAC token
只携带 run key、相对路径、大小、hash 和过期时间，不向浏览器暴露机器绝对路径。
run registry 只能注册配置 runs root 下的运行；artifact 请求再次阻止 path traversal
与 symlink 逃逸。UI 不启用 CORS、不访问 CDN，也不把 manifest 复制到新数据库。

真实长任务由独立 Python worker 调用统一 orchestration API。实时进度只来自原子
`progress.json` 和 append-only `task-events.jsonl`，通过同源 SSE 传输；前端直接应用
`ExecutionProgressProjection`，不解析终端文本。已完成 Stage 04/06 则从当前
StageManifest 声明并通过 SHA-256 的 task table、终态 progress 和 events 重建每张 GPU
的历史任务、attempt、失败重试、候选数与累计运行时间。两条路径共用：

```text
GET /api/v1/runs/{run}/stages/{4|6}/execution
```

“停止”通过 `EASYDESIGN_UI_DRAIN_FILE` 请求调度器完成当前
strategy/shard 后停止，不终止正在写产物的 backend。服务重启后可通过 manifest 和
结构化进度恢复观察，operational failure 可创建 resume job。

软件 capability 与单次 run state 是两套字段：例如 Stage 06/07 可以是
`implemented`，而一个在 Stage 05 科学停止的 run 必须是 `not-reached`。演示回放只根据
真实终态 manifest 构造 `simulated-preview` 时间线，不修改科学 artifact。下单 API 只有
在成功 Stage 07 明确声明并通过 checksum 的 `FinalCandidatePackage` 时才返回
`draft-ready`，且仍不调用供应商。

UI-004/UI-006 在科学 manifest 与 React 之间增加面向使用者的只读语义投影层。默认页面读取
`ProjectCardProjection`、run/stage projection 和 Stage 05 专用的 overview、strategy、
candidate、metric projection；内部 ID、代码身份、hash 和原始文件只进入运行内的
“技术记录”。React 只负责中文呈现、分页和交互，不能复制 filter threshold 或重新判断
候选是否通过。

Stage 05 的 840 个 pilot、100 个 expansion 和 10 个 full-target prediction 通过以下
分页接口访问，而不是把 7–9 MiB 报告整体发送给浏览器：

```text
GET /api/v1/runs/{run}/stages/5/overview
GET /api/v1/runs/{run}/stages/5/strategies
GET /api/v1/runs/{run}/stages/5/metrics
GET /api/v1/runs/{run}/stages/5/candidates
GET /api/v1/runs/{run}/stages/5/candidates/{candidate_id}
```

服务只读取当前 Stage 05 manifest 声明的 report 和 candidate index。JSON 缓存身份包含
artifact SHA-256；page size 最大 100，排序字段使用白名单。候选原始、复折叠和 Protenix
结构必须先从 manifest 声明的 candidate index 解析嵌套 ArtifactRef、复验大小和 hash，
才能签发短期 token。

Stage 05 策略身份来自 Stage 03 `strategy-bundle` / `design-matrix` ArtifactRef 与
Stage 05 report 的显式联接，禁止拆 strategy ID 猜 region 或 scaffold。策略指标聚合只
使用有限数值，保存样本数和缺失数，并计算均值、中位数、最小值与最大值；缺失值不按零
填充。页面默认顺序为策略/Tier、扩展策略、初筛候选、Protenix 复核，科学停止只在最后
解释能否进入 Stage 06。

运行状态与证据成熟度分开：

- 执行状态：`pending`、`running`、`succeeded`、`failed`、`cancelled`。
- 证据状态：`planned`、`implemented`、`smoke-validated`、
  `scientifically-validated`、`production-ready`。

## 8. 配置与 adapter 边界

科学配置只从项目 `easydesign.yaml` 读取；本机部署只从一个 runtime profile 读取。
`--runs-root` 只能覆盖输出位置，不能覆盖科学阈值。最终安全投影写入
`config-snapshot/`；绝对 backend 路径不会进入正式 artifact。密钥只来自秘密管理系统。

后端专属字段留在 adapter 内。Core 只接收规范化能力、请求、结果和错误，使 RCSB/UniProt、
BoltzGen、Protenix-v2/AFO/AF3 以及 local/Slurm/SMART 可以替换而不改阶段契约。

## 9. 决策记录

- 2026-07-23：从零建立私有 clean repository；旧仓只读；采用七阶段、不可变 manifest、
  可替换 backend 和 Python-API-first 路线。
- 2026-07-24：开发期只维护中文文档，每阶段只保留一个合并后的 README。
- 2026-07-24：全部环境先由 Conda 管理；`easydesign-core` 使用 Python 3.11，重型工具
  继续独立环境；基础契约使用 Pydantic、规范 JSON、相对路径和 SHA-256。
- 2026-07-24：M1 基础运行契约完成工程验证；这只证明契约实现可用，不代表任一科学
  Stage 已实现或通过科学验证。
- 2026-07-24：阶段治理下沉到每个 workflow 的 `STATUS.md` 与 `history/`；顶层
  TODO/TODO_NOW 只做宏观汇总和索引，避免重复维护七套项目级任务。
- 2026-07-24：Stage 01 首个机器切片采用 sequence/FASTA → 通用结构预测接口 →
  Protenix-v2 2.0.0 → Target Bundle；重型环境只通过显式 executable、环境变量和文件
  协议访问，remote MSA 与 no-MSA 不得静默互换。
- 2026-07-24：用户 sequence 路径固定为 target 文件 + `easydesign.yaml`；Protenix JSON
  是 adapter 生成的 attempt input。正式 run、开发验证和历史迁移分区；新 run 取消
  `attempts/` 中间层，已有运行只做带 fingerprint 的整体迁移。
- 2026-07-24：PyMOL PSE 采用独立 Python 3.11 / PyMOL 3.1.0 环境和显式文件协议；
  Stage 01 首版只导入可信本地、单蛋白、单链、单 state 会话，颜色保持未解释 annotation，
  复合物、配体和人工 object/chain/state 选择留待后续契约。
- 2026-07-24：Stage 02 automatic 采用独立 SASA/geometry 与 ScanNet epitope no-MSA
  两条路线；禁止分数融合、CPU fallback 和 PSE颜色介入，先输出各自 Top 3 与重叠报告，
  人工批准后再交给 Stage 03。
- 2026-07-24：后续验证证明同一固定 ScanNet commit/权重可在 CPU 完成官方 1BRS 与
  APOE；Stage 02 改为显式 CPU 默认、GPU 可选且无设备 fallback。GPU 兼容性转为性能
  待办，不再阻塞 1.0 主线；上一条保留为最初 GPU-only 决策的历史事实。
- 2026-07-24：七个 Stage STATUS 的顶层摘要成为状态事实来源，由同步脚本生成顶层
  TODO/TODO_NOW 实时表，并由 `make check` 阻止摘要漂移。
- 2026-07-24：EasyDesign 的长期产品边界是多 binder 类型平台；VHH 是 1.0 reference
  profile，不是永久边界。蛋白、肽和后续类型必须通过 profile/adapter 复用同一七阶段
  orchestration、manifest、恢复和报告机制。
- 2026-07-24：Stage 01 采用 Mol* 5.11.0 自包含只读报告；报告使用独立 revision，不进入
  StageManifest，失败不影响科学状态。服务只暴露一个已校验 report 并固定绑定
  `127.0.0.1`。完整取舍见
  [`ADR-0001`](decisions/ADR-0001-portable-stage01-target-viewer.md)。
- 2026-07-25：先暂停 Stage 03，完成 Developer Preview CLI、用户级 runtime profile、
  RunManifest 1.1 code identity 和本地 wheel 安装；CLI/UI 继续只调用同一 application
  API。完整取舍见
  [`ADR-0002`](decisions/ADR-0002-developer-preview-cli-and-code-identity.md)。
- 2026-07-25：用户配置统一为 schema 0.3 的 `stage01`–`stage07`；Target Bundle 0.3
  支持 coordinate ensemble，SASA 将单模型推广为多模型共识；ScanNet 多模型明确拒绝。
- 2026-07-25：UniProt 身份只接受用户显式 accession，annotation 只作证据/warning；
  RunManifest 1.2 用 workflow state 表示等待人工批准，Stage 03 只能读取批准 attempt
  发布的 `hotspots.yaml`。
- 2026-07-25：schema 0.4 将 Stage 01 统一为六类 source、严格实验结构优先与
  Target Bundle 0.4；UniProt/RCSB 响应冻结进 run。`review-gated` 与 `unattended`
  共享实现，通用 DecisionRecord 批准后在同一 run 建立新 attempt，真实下单永不自动化。
  完整取舍见
  [`ADR-0002`](decisions/ADR-0002-developer-preview-cli-and-code-identity.md)。

重大决策同时在本节建立索引；涉及稳定接口和分发边界时新增独立 ADR。
