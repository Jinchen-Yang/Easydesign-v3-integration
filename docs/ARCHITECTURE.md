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
├── easydesign                # 从自身位置发现工作区的唯一启动器
├── easydesign-workspace.yaml # 可移植工作区声明
├── environment.yml           # easydesign-core Conda 环境入口
├── environments/             # 环境配方与 linux-64 内容身份锁
├── pyproject.toml            # Python 包、运行依赖和开发依赖
├── Makefile                  # 环境、检查、测试和构建入口
├── workflow/                 # 七阶段契约、动态状态和阶段历史
├── src/easydesign/           # 唯一 Python 实现
├── configs/                  # 默认值、backend、filter 和执行 profile
├── tests/                    # unit、integration、e2e 和 fixture
├── resources/                # 已审查小型资产与来源登记
├── examples/                 # 最小可复现示例
├── scripts/                  # 仅调用 API 的开发脚本
├── runtime/                  # 本机环境、模型、缓存、状态与隔离区，Git 忽略
├── projects/                 # 用户输入和 canonical 配置，Git 忽略
├── runs/                     # 不可变科学运行与可再生索引，Git 忽略
└── archives/                 # 只移动、不删除的可恢复归档，Git 忽略
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

当前统一使用 Conda 管理环境，但每个重型工具仍保持隔离。所有本机可变状态收敛在当前
仓库的 `runtime/`，不再要求用户拼接分散在 home、系统盘和数据盘的路径：

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

根启动器按 lock 身份安装到 `runtime/envs/<environment-id>-<lock-sha>/`。lock 变化时
建立新目录并切换 append-only 注册记录，旧环境保留；失败 staging 移入
`runtime/quarantine/`，不会递归删除。提交到 Git 的
`environments/locks/*-linux-64.conda-lock.txt` 是 Conda explicit package set；
需要 pip 的环境另有精确 `pip-lock.txt`，schema 0.2 JSON 同时冻结 sidecar SHA-256、
Python 版本、探针和安装预算。`environment.yml` 与 `environments/*.yml` 只作为人类
可读配方，不参与正式 setup 的依赖重新解析。`pyproject.toml` 仍是 EasyDesign 自身
Python API 和 console-script 声明源；core 在锁定依赖后以 `--no-deps`、
`--no-build-isolation` editable 安装当前源码。
安装选择分为完整、最小和单组件三种投影。单组件以
`core-ui`、`pymol-pse`、`protenix-v2`、`scannet-epitope`、`boltzgen` 或 `tnp`
为稳定 ID，同时选择恰好对应的环境 lock 与必需资产集合。环境先构建，资产逐个 staging
并校验后发布，因此磁盘峰值按“环境及其缓存 + 已发布资产 + 最大单资产 staging”计算，
不再假设所有后端与所有资产同一时刻重复存在。完整安装与组件安装共用
`setup_workspace()`，CLI 和 UI 不得维护第二套映射。
长时安装由 `orchestration.setup_jobs` 提供唯一任务 API。CLI 的 `setup --detach` 和
UI 安装中心都通过该 API 启动 `python -m easydesign.setup_worker`：无 shell、关闭
stdin、独立进程 session，并将不可变 request/process/result 写到
`runtime/state/setup-jobs/`。安装状态以终态 result 为事实来源；创建 UI 的进程退出后
仍能恢复，不再把浏览器内存中的 `Popen` 当成状态事实来源。stdout/stderr 只作为诊断
日志，不参与成功判定。
默认 pip index 固定为官方 PyPI；部署者可对单次 setup 显式提供无凭据 HTTPS index。
该 URL 进入 setup request，并只覆盖 worker 子进程的 `PIP_INDEX_URL`。EasyDesign 不
修改全局 pip/代理配置，也不进行未记录的镜像 fallback。
`environments/protenix-v2.yml` 固定 EasyDesign 1.0 当前结构预测后端的独立环境。
`environments/pymol-pse.yml` 固定 PyMOL PSE 导入环境的 Python 3.11 和
`pymol-open-source=3.1.0`。Core 不导入 PyMOL，也不扫描 Conda 或系统 Python；正式 CLI
从仓库内 profile 的 environment/asset ID 解析可执行文件。Adapter 先做精确版本探针，再用
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
BoltzGen 的 diverse/adherence、inverse-fold、folding、affinity 五个 checkpoint 和
`mols.zip` 必须全部由 asset registry 标记可用。adapter 将六个本地绝对路径显式传给
BoltzGen 并设置 offline mode，不允许回到 Hugging Face 默认标识后隐式联网。
`backends/executors/local_multi_gpu.py` 只负责 GPU 资源门槛和每设备一个串行 worker；
候选完整性由 Stage 04 collector 定义。这三层不得互相复制职责。

站点专属环境路径只能出现在工作区内未提交的注册表或 SSH profile 中。仓库代码不得硬编码
`/root/autodl-tmp`、SMART 路径、用户名或密钥。

正常运行只使用 `runtime/profile.yaml` schema 0.2；它只保存相对路径与
environment/asset ID，不保存 `/root/...` 等机器绝对路径。用户 `easydesign.yaml`
只保存科学配置。run 记录 profile ID 与文件 SHA-256，以及实际 backend/model/device
identity，但不复制机器绝对路径。旧用户级 profile 只能通过显式
`workspace import-legacy` 复制校验证据后迁移，原文件和旧环境保持不变。

### 5.1 WorkspaceContext 与写入边界

`WorkspaceContext` 从 `easydesign-workspace.yaml` 解析唯一部署边界，并被 CLI、UI、
缓存、后台 worker 和 SSH executor 显式传递。正常 EasyDesign 本地写入只允许：

```text
runtime/
projects/
runs/
archives/
.git/        # 仅用户明确执行 Git 工作流时
```

外部输入、Conda executable 和 SSH 身份可以按用户明确选择只读访问；SSH 任务只写
profile 声明的远程工作区。业务代码不得修改 `/etc/environment`、shell profile、
系统代理、Git 全局配置和 base Conda。发布先写全新 staging，校验后原子移动；目标已
存在一律拒绝覆盖。缓存、旧环境、旧模型、quarantine 和 run 不自动清理。
安装子进程使用仓库内 HOME/XDG/cache/tmp、独立 Git config、`PIP_CONFIG_FILE=/dev/null`
和关闭 user-site；这些变量不会写回父 shell。网络代理如由宿主显式提供，只对当前子进程
只读继承，EasyDesign 不创建、修改或删除代理配置。

### 5.2 稳定工作区与单一 main

正式 runtime 必须依附于长期稳定的主仓库目录，不得安装在以任务 ID、临时分支或
worktree 命名的开发目录中。Conda 环境包含绝对 prefix，仓库路径变化后必须在新路径按
lock 重建；不得直接移动环境目录并宣称可用。

EasyDesign 的 Git 拓扑固定为单一 `main`。不创建开发分支或额外 worktree；科学流程中的
“branch run”仅表示不可变 run lineage 的科学分叉，与 Git branch 无关。GitHub 只同步
`main`，runtime、projects、runs 和 archives 继续位于 Git 忽略边界。

## 6. 运行目录层级

```text
runs/
├── run-index.json                 # 可再生导航索引，不是科学 artifact
├── _development/                  # backend smoke、外部服务诊断
├── _archive/                      # 旧布局迁移清单，不放当前项目 run
└── <project_id>/
    ├── PROJECT.json               # 可再生项目导航投影
    ├── PRIMARY                    # 可选的主展示 run ID
    └── <run_id>/
      ├── input-snapshot/
      ├── config-snapshot/
      │   ├── easydesign.yaml
      │   ├── resolved-config.json
      │   ├── CURRENT
      │   └── revisions/
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
      ├── ...
      └── results/                  # 面向人的最终汇总，不取代正式 artifact
```

同一次实验从 Stage 01 到 Stage 07 始终使用同一个 run 根目录；七个 Stage 是同级目录，
下游不得嵌套到上游目录。`attempt-0001/` 直接位于 Stage 目录，取消没有语义增量的
`attempts/` 中间层。后端安装和服务可用性 smoke 不属于项目 run，必须进入
`_development/`。Stage 目录只在真正开始时创建，未到达阶段不得预创建空壳。

正常的“配置下一步”在同一 run 中保存新的 config/RunManifest revision；只有改变
target、已完成 Stage 参数、上游科学决定或重新选区时才创建分支 run。完整稳定规则见
[`RUN_LAYOUT.md`](architecture/RUN_LAYOUT.md)。

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
Workbench 的交互式重选不重复询问三套理由：产品请求只提交规范区域、真实批准人和两个
acknowledgement；orchestration 从 canonical `design.intent` 生成 design goal，并将
生物学/结构说明限制为“用户选择、无独立生物学证据”和“编号/坐标已验证、未自动结构
优选”。生成后的 typed approval 仍进入 resolved config 和审计链，React 不生成科学
依据。该显式用户提交本身就是 human approval，无论后续运行方式是否为 review-gated，
都不再制造一次内容相同的第二审批。automatic review-gated 的候选选择仍保留独立门。

重新选择 Stage 02 时，continuation 显式声明 `continue_after_stage=1`。core 逐一验证
Stage 01 的 StageManifest 状态和 ArtifactRef checksum，再建立新 run；它不要求来源
RunManifest 整体已经 `succeeded`，因为来源可能正在等待旧 Stage 02 审批或已经包含
不应被复制的下游结果。没有显式前缀的普通 continuation 仍要求完整 succeeded run。
UI job 只通过原子 job record 显示 `queued/running/terminal`，不使用固定等待时间、
目录猜测或终端文本。

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

已成功结束的 Stage 02 可以在不改变上游科学身份时继续同一个 run：当前终态
RunManifest 保持不可变，新配置写入 `config-snapshot/revisions/`，新的 RunManifest
revision 将 run 重新置为 `running`。如果从较早 Stage 改写参数或重新选区，则建立带
parent/fork 证据的分支 run。legacy `--from-run --run-id NEW_ID` 复制式 continuation
继续可读，但不再是产品默认路径。

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
  ├── nanobody-filter-standard-v1.5 历史唯一赢家策略
  ├── nanobody-filter-standard-v1.6 多 Tier A 晋级与诊断 warning
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
请求。v1.6 在 full-target 之前按 `F_YAML` 晋级最多三个 Tier A；100 条扩增和
full-target 是诊断，不会因零结构通过撤销晋级。`stopped-no-tier-a` 仍是成功执行得到的
科学负结果；旧 v1.5 的 `stopped-no-scale-winner` 继续按历史契约读取。后端、文件、
数量或 checksum 故障在两个版本中都属于 operational failure。

### Stage 06 分片规模生成

Stage 06 v0.2 默认消费 Stage 05 v1.6 发布的 1–3 个晋级策略。用户配置的
`total_candidate_count` 是唯一全局预算，产品推荐并默认 50,000，但最终执行严格采用
用户提交的正整数。预算在晋级策略间等额分配，余数按 `F_YAML` promotion rank 分配；
50,000 条对应 1/2/3 组时分别为 `50000`、`25000/25000`、
`16667/16667/16666`。研究负责人也可以在旧 v1.5
`stopped-no-scale-winner` 后显式授权放大一个已经由 Stage 05 扩展过的 Tier A；该例外
不会改变 Stage 05 结论，并形成独立 `ScaleStrategyAuthorization`。没有 Tier A 时禁止
越过。Stage 06 同时把 Stage 03 strategy YAML、Stage 05 bundle 和 Stage 04 candidate
index 声明为输入；后者仅用于从正式 ArtifactRef 测量候选磁盘基线，不能成为 manifest
外的隐式读取。

```text
ScaleResourceReport
  → ScalePlanV0_2 / equal-across-promoted-v1
      ├── strategy A / independent shard + ordinal space
      ├── strategy B / independent shard + ordinal space
      └── strategy C / independent shard + ordinal space
  → shared BoltzGen task executor
  → per-strategy + global exact merge / ScaleCoverageReportV0_2
  → ScaleBundleV0_2
```

新任务使用 `user-defined-v1` profile，按每个 strategy 最多 2,500 条切分，尾部分片可以
更小；用户输入的总数同时形成不可变的预算授权。`smoke-1000` 与
`production-50000` 仅用于兼容和恢复 dev34 已冻结配置，仍严格对应 1,000/50,000。
当前资源门使用 Stage 04 声明 artifact 的每候选字节数
乘 20 的保守容量代理，且要求执行后仍保留文件系统总容量的 25%；预检失败发生在创建
task 前。

Stage 04–06 共同调用 `orchestration/boltzgen_tasks.py` 和 local multi-GPU executor。
Stage 06 不复制生成/收集逻辑，也不把 Stage 04/05 候选计入 scale 数量。运行状态仍使用
原子 progress/state 与 append-only events；发布中断后，终态 artifact 只有在模型 identity
或原始 bytes 完全一致时才可复用。Stage 07 只读取 StageManifest 声明、checksum 正确且
覆盖无缺口的 ScaleBundle/CandidateIndex。

### 整个 run 的 SSH 控制面

跨主机能力位于 deployment 层，不是新的科学 executor 类型：

```text
控制端 runtime profile
→ 严格 known-host / dedicated identity / version probe
→ 校验 succeeded source RunManifest 与 config hash
→ rsync 完整 continuation source
→ 远端 systemd EasyDesign worker
→ 远端 local-multi-gpu executor
→ 远端独立 manifest / progress / events / task heartbeat
→ manifest 驱动的控制端只读镜像 / resume
```

这样 Stage 04/06 仍只维护一套本地多 GPU 任务语义；SSH 只负责把整个 EasyDesign run
提交到另一台机器。科学配置不保存 IP、密钥或机器绝对路径，它们只存在于控制端 runtime
profile。远端版本必须与控制端完全一致，远端 runs root 必须预先存在并通过容量探针。
控制端保存版本化 `SshRemoteJobRecord`（submission、当前 systemd unit、unit 历史和
resume 次数）；科学事实和恢复身份仍以远端 run 为准。
SSH 会话断开不影响 systemd worker，状态查询也不得从终端文本或目录名称推测进度。
Continuation preflight 从 source RunManifest 的最高连续 Stage 推导 `start_stage`，只探测
后续仍会执行的 backend；Stage 06 continuation 因而只要求 BoltzGen，而不会重复要求
Stage 01 的 PyMOL 或 Stage 05 的 Protenix 环境。

BoltzGen adapter 在重型 subprocess 存活期间周期性发出 `TaskHeartbeat`；Stage 04/06
将每个运行中 task 的最新 heartbeat 原子写入 `ProgressSnapshot`，终态移除。heartbeat
不读取后端中间目录，也不增加候选计数。远程控制端通过 `runs watch --once --json`
读取同一 snapshot。

结果回传分两层：`metadata` 拉取当前 Run/Stage manifest 闭包、顶层声明 artifact 和
runtime progress/state/events；`complete` 再递归拉取 JSON 中出现的 ArtifactRef。同步
使用 rsync `--files-from` 的 manifest-derived 白名单，随后逐一验证大小/SHA-256，并在
控制端 runs root 写只读镜像。SSH host、identity、绝对路径和 profile 不进入科学配置或
浏览器响应。

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
  ├── ScaleBundle 0.1/0.2 与 strategy allocation 验证
  ├── local metric cache
  ├── resumable (candidate, seed) tasks
  ├── TNP batch attempt
  └── FinalCandidatePackage publication
```

ScaleBundle 0.2 的全部 strategy 使用相同门槛和评分进入一个全局候选池；不会按 YAML
预留 primary/backup 名额。全局去重后仍保留每个 candidate 的 strategy lineage，
FinalCandidatePackage 0.2 发布主备候选的来源和来源分布。旧单策略 ScaleBundle 0.1
继续是合法输入。

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
是否完整限制用户阅读后续配置；完整性只在项目事务、preflight 和真实启动三个动作边界
统一判断。项目名必须在浏览器传输文件前预检。浏览器计算 SHA-256 后调用同源
`/api/v1/uploads/raw`，服务把最多 64 MiB 的内容写入
`runtime/tmp/ui-uploads/<token>/`，并把 UploadReceipt 0.2 的不可变 revision 保存在
`runtime/state/ui/upload-receipts/`。receipt 不含机器绝对路径，服务重启后仍可恢复。
上传容量阈值来自仓库根 `easydesign-workspace.yaml`：
`upload_warning_bytes/upload_blocking_bytes` 默认分别为 1 GiB 和 5 GiB；UI 与
后端共享这一声明，不从用户主目录或环境变量猜测。

项目发布先在全新的 runtime staging 中完成配置、输入和元数据验证，再原子移动到此前
不存在的 `projects/<project_id>/`，最后创建 DesignSession。成功发布时输入本身移动到
项目目录，receipt 改为 referenced；失败内容移入 quarantine 并保留失败 receipt，不得
产生正式项目、空会话或首页卡片。7 天只触发建议，1/5 GiB 分别触发提醒/阻止；不存在
自动删除定时器。

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

设置页也不建立第二套环境状态。UI-023 将其分成“当前设备 / 公共算力 /
项目存档”三个产品上下文：当前设备只投影 `setup_plan()`、environment registry、
asset registry 和 setup job；公共算力只投影 `RemoteExecutorRegistry` 与
`ExecutionTargets`；项目存档只读取 `run-index.json` 中的 `archived-project-run`。
环境检查在设置页进入、window focus、visibility 恢复和 setup job 运行期间自动刷新；
React 不扫描 Conda、模型目录或 GPU 输出。工作区路径、注册表 ID、安装任务和隔离区
只在默认折叠的技术详情中显示。

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

### 仓库共享的只读运行证据

完整 `runs/` 仍属于 runtime-only。`reporting.evidence_bundle` 只为经明确授权的协作审阅
生成精简副本：

```text
完整 run
→ 验证当前 RunManifest / StageManifest / ArtifactRef
→ 复制正式 manifest 闭包
→ 补充 UI 指定的重点候选结构
→ 排除 backend tasks/work/runtime
→ bundle-manifest.json（逐文件大小与 SHA-256）
→ evidence-runs/run-index.json
```

共享包可以作为 `easydesign ui serve` 的只读 `runs_root`，但不是可恢复执行目录。生成器
不得篡改原 manifest 或把被裁剪的中间文件伪装为正式 artifact；如果正式 ArtifactRef
位于通常被裁剪的目录，仍必须按 manifest 闭包复制。`serve_ui_evidence_bundle.py`
先验证 bundle 清单和科学 manifest 闭包，再启动 localhost UI。

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
- 2026-07-27：跨服务器计算采用 whole-run SSH control plane；远端继续使用同一
  local-multi-GPU Stage executor，并独立维护 manifest/progress/resume。Stage 05
  `stopped-no-scale-winner` 之后只允许对已扩展 Tier A 进行带双重确认和 Bundle
  SHA-256 的人工探索性放大。完整取舍见
  [`ADR-0003`](decisions/ADR-0003-ssh-remote-runs-and-manual-scale-authority.md)。
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

## Stage 01/02 双查看器与结构交互会话

Workbench 的结构交互保持产品状态、科学状态和第三方渲染运行时三层分离：

```text
StageManifest → verified target.cif / mapping / source annotations
                      │
                      ├─ browser PyMOL（默认，离线 WASM）
                      └─ Mol*（平级切换）
                              │
projects/<project>/interactive-sessions/<session>/revision
                              │
       完整 PML SceneVersion / 明确残基草稿 / 待确认算法计划
                              │
             人工提交后才建立新的 Stage 02 branch
```

- 浏览器 PyMOL 和 Mol* 只通过 manifest 派生 artifact token 获取同一结构；不得扫描
  run 目录或直接读取任意路径。
- Pyodide/PyMOL WASM 由 Python wheel 离线提供，不访问 CDN。PSE 文件解析仍在独立
  `pymol-pse` 环境完成，浏览器运行时不是科学输入 adapter。
- `StructureInteractionSession 0.4` 保存于 `projects/`，采用新 revision 发布，不提供
  删除或覆盖接口。每个 SceneVersion 保存完整 PML、parent/base version、SHA-256、
  actor、provider/model、Skill ID 和时间；它不加入 Run/StageManifest，也不改变
  Target Bundle。
- 模型 provider 接收固定系统规则、`safe-pml` 与最多两个关键词 Skill、当前完整 PML、
  场景摘要、结构 metadata、当前区域、最近十轮对话和用户请求；固定返回
  `assistantMessage/summary/conversationTitle/pml` 四字段 JSON。坐标、MSA、完整序列、
  密钥和绝对路径不进入请求。
- PML 是唯一可视化事实。安全追加时 PyMOL 只执行增量；旧内容变化、历史恢复、增量失败
  或状态不确定时，重新构建结构场景并完整重放。Mol* 只投影 representation、颜色、
  选择、聚焦和背景等可靠子集，不支持的命令标记为“仅 PyMOL”，但不能阻止保存。
- `ed_region_A/B/C` 由完整 PML 桥接到 Stage 02 编辑草稿，并确定性映射为
  `label_seq_id`。PML 修改不发布科学结果；SASA/ScanNet plan 只有人工确认后才调用既有
  deterministic backend，区域也只有人工批准后才形成新 Stage 02 branch。
- 部署者只在
  `runtime/secrets/structure-assistant/platform-provider.yaml` 配置一个平台
  provider。该文件拒绝符号链接并要求 POSIX `0600`；UI 只能读取通用服务状态，不能
  获取或选择 provider、模型、endpoint 和密钥。provider 不可用时不 fallback，也不
  影响无模型的七阶段流程。
- 同一结构工作区内的 PyMOL 与 Mol* pane 持续挂载；平级切换只调整显隐和交互焦点。
  浏览器继续缓存约 22 MB 的静态 Pyodide/PyMOL 资产，但每次真正挂载
  `NativePyMOLViewer` 时创建独立 Pyodide/PyMOL 运行时。Emscripten WebGL context 与
  创建它的 canvas 绑定，禁止把旧运行时重新绑定到新 canvas。返回已挂载的 PyMOL pane
  时在两个 animation frame 后同步 canvas、reshape、GL viewport 和 redraw。
- 首版不开放 MCP，不移植 ChatPyMol 的 Node 文件库、主目录写入、删除/分享接口或第二套
  project system。

## 产品会话、项目目录与开发者自检

`DesignSession 0.1` 是产品导航层，不是科学事实来源。它只记录设计模式、运行方式、当前
阶段、不可变配置 revision 和 run lineage：

```text
全流程设计 ── 一份 canonical 配置 ── 新科学 run
按步骤设计 ── Stage N 结果 ── config revision ── 同一 run 的 Stage N+1
修改上游决定 ── branch config ── 新分支 run
开发者自检 ── developer-smoke-run ── 与普通项目目录隔离
```

正常 continuation 验证上游 RunManifest 当前声明且通过 SHA-256 的连续 Stage，不复制
上游目录，也不覆盖旧 manifest。用户修改 Stage 02 区域或任何已完成上游决定时，系统
创建新分支；DesignSession 负责把同 run 的阶段推进和跨 run 分支呈现成用户可理解的
时间线，StageManifest 仍决定科学交接。

生成下一阶段 revision 时，本地输入和 precomputed MSA 也必须从源 run 的冻结快照验证，
再原子复制到产品项目的 `inputs/continuation/<source_run_id>/` 并写入相对路径，不能继续
引用旧项目目录。worker 继续同一 run 时保持稳定 run key，并把 run key、阶段和终态写回
DesignSession；分支运行才产生新的 run key。UI 服务启动时从 `run-index.json` 注册已验证
run，深链接不依赖用户先访问项目列表。

按步骤设计使用同一个七阶段工作区呈现结果与后续配置。Stage 轨道只负责导航；当前
Stage 的状态决定内容：

```text
succeeded / scientific-stop / operational-failed
→ manifest-only 结果投影

not-reached + 连续成功上游
→ Python stage_form_definition 产品投影
→ 用户确认
→ POST /runs/{run}/continue/{stage}
→ UiJobRecord 轮询
→ 完成后定位下一 Stage
```

Stage 02 的结构选区编辑器作为工作区内嵌内容存在，不再拥有独立的全屏导航语义。
Stage 03–07 的表单默认值由 orchestration 类型生成；React 不复制 profile、预算、
scaffold registry 或筛选参数。配置 revision、run lineage、StageManifest 和
ArtifactRef 仍分别承担产品导航、科学状态和产物身份，不因页面动画发生变化。

项目目录只读取 `run-index.json` 的 category：

- `project-run`：显示在普通项目和运行任务。
- `archived-project-run`：移动到 `runs/_archive/`，只在设置中显示，可恢复。
- `developer-smoke-run`：只在开发者自检历史中显示，禁止作为科学输入。

项目首页展示哪一次运行也由 `run-index.json` 显式声明。每个活跃项目最多一个
`is_project_primary: true`；没有声明时才按最近更新时间展示。选择主展示运行只改变
导航投影，不改写该 run 的 manifest、artifact、状态或 checksum，也不隐藏同项目的其他
历史运行。较新的 continuation、科学审批分支和远程探索运行因此不会自动替换用户已经
选定的项目首页结论。

归档是原子路径治理：移动前后都验证 RunManifest、StageManifest、ArtifactRef、大小和
SHA-256；运行中、带锁或被远程任务引用的项目拒绝移动。归档不会改写科学文件或其
checksum。

Mol* 工作台采用单实例生命周期。一个 React 容器只创建一个 Viewer；结构、表示和区域
图层通过串行 MVS state 更新，generation token 丢弃过期结果。首次结构加载固定
`keepCamera=false` 并显式重置取景；只有 hierarchy 同时包含 structure 和
representation 才报告“结构已就绪”。
Workbench 与便携 Target Viewer 都在 Mol* 宿主、canvas 和运行时内部画布层强制
`touch-action: none` 与局部 overscroll containment。Mol* 自带的双指手势因此接收完整
touch stream，页面本身不会在结构画布上抢占缩放。

开发者自检分两层：

- 快速确定性工程自检真实发布 Stage 01–07 的 manifest/attempt/artifact 链，但所有
  产物标记为 `synthetic-engineering-smoke`，禁止用于科学结论。
- 真实后端微型自检必须使用固定非 APOE fixture。当前 dev13 只建立诚实的
  `not-started` 记录和资源预检边界；在 Stage 01–05 coherent run 与 Stage 06/07
  adapter probe 真正执行前，不得报告为通过。

## Stage 04/06 双执行目标

`ExecutionTarget` 是运行时产品契约，不是科学配置。Host、用户、端口和 SSH key
不进入 `easydesign.yaml`；相同 Stage03/05 交接在两种位置产生同一类 Task、
Candidate、Progress 和 StageManifest：

```text
Stage 04 / Stage 06
        │
        ├─ local-current-host
        │    NvidiaSmiProbe → eligible devices → GpuLeaseStore → shared executor
        │
        └─ managed-ssh/suzhou2
             RemoteExecutorRegistry → RemoteJobBundle → ManagedQueue
             → ManagedWorker → GpuLeaseStore → same pipeline API
```

本机执行在 attempt 创建前冻结设备计划。`NvidiaSmiProbe` 排除外部进程、显存不足
和有效 EasyDesign 租约；`GpuLeaseStore` 用 append-only revision 和原子锁保证一卡一任务。
无资源是 `waiting-for-resources`，不是 operational failure。已冻结的计划在 resume 时不因
当前 GPU 枚举顺序而改变。

Suzhou2 的新 worker 只写入：

```text
/data/easydesign/managed-worker/
├─ service/
├─ config/
├─ runtime/{envs,models,state,logs,tmp,cache,quarantine}/
├─ queue/
├─ jobs/
├─ runs/
└─ archives/
```

`RemoteJobBundle` 只接受固定 stage range、candidate budget、manifest closure 和 checksum，
没有任意 shell 字段。`ManagedQueue` 在 `flock` 临界区内完成预留和状态 revision；
worker 在重启后对账 `admitting/running` 状态。服务 bootstrap 只在受管数据盘写配置和
systemd unit 建议，不自动修改 `/etc`。

SSH 配对由 `RemoteExecutorRegistry` 保存只追加 revision。每个控制端使用当前工作区
`runtime/secrets/ssh/` 中的独立密钥和确认过的 host fingerprint。逻辑解绑只禁用后续
远程操作，不删除私钥、远端公钥、队列或历史证据。

`begin_pairing` 在生成密钥前先检查工作区 key pair：完整时直接复用，只有一半时拒绝
覆盖。设置页的第三步可将一次性登录密码写入受控 OpenSSH PTY，执行幂等
`authorized_keys` 安装后立即改用工作区私钥探测 worker；密码不进入参数、环境、日志、
registry 或磁盘。手动复制公钥并执行免密探测仍是等价回退流程。

数据本地性是 job 契约的一部分：远端 Stage 04 与 05 是 `4→5`，Stage 06 与 07
是 `6→7`。若上一个受管 run 已在 Suzhou2，后续 job 只通过相对 managed-run
路径和当前 RunManifest SHA-256 引用它，不重传大型闭包。控制端同步分为：

- `metadata`：队列、进度、事件、错误和摘要；
- `review`：上述内容加报告、指标、少量审阅结构和批准材料；
- `complete`：只在用户明确请求时同步全部大型结果。

观察器默认每 15 秒只读远端结构化 revision 并通过 SSE 投影到 UI。SSH 暂时中断
不改写远端科学状态；恢复后从最后已知 revision 继续。
