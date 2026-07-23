# EasyDesign 架构

本文档是仓库层级、依赖方向、运行目录和环境边界的事实来源。它描述稳定职责，不罗列缓存、
构建产物或每一个临时文件。

## 1. 仓库总览

```text
easydesign-clean/
├── README.md                 # 项目入口与当前状态
├── PROJECT_CHARTER.md        # 战略、1.0 边界与工程规则
├── AGENTS.md                 # Agent 自动工作协议
├── TODO.md                   # 宏观里程碑
├── TODO_NOW.md               # 当前任务、阻塞和只追加历史
├── environment.yml           # easydesign-core Conda 环境入口
├── pyproject.toml            # Python 包、运行依赖和开发依赖
├── Makefile                  # 环境、检查、测试和构建入口
├── workflow/                 # 七阶段人类可读契约
├── src/easydesign/           # 唯一 Python 实现
├── configs/                  # 默认值、backend、filter 和执行 profile
├── tests/                    # unit、integration、e2e 和 fixture
├── resources/                # 已审查小型资产与来源登记
├── examples/                 # 最小可复现示例
├── scripts/                  # 仅调用 API 的开发脚本
├── runs/                     # 运行产物，Git 忽略
└── models/                   # 权重和模型缓存，Git 忽略
```

## 2. Python 源码层级

```text
src/easydesign/
├── core/
│   ├── artifacts.py         # ArtifactRef、文件身份和路径约束
│   ├── attempts.py          # Attempt、执行状态和终态规则
│   ├── manifests.py         # StageManifest 与 RunManifest
│   ├── serialization.py     # 规范 JSON 读写
│   ├── hashing.py           # SHA-256 与完整性验证
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
│   ├── structure_prediction/# Phoenix、AFO、AF3 等通用预测接口
│   └── executors/           # local、Slurm、SMART 执行
├── orchestration/           # 规划、执行、恢复和跨阶段协调
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
- `scripts/`、未来 CLI 和 UI 只调用 orchestration/API，不承载科学逻辑。

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

## 4. 环境拓扑

当前统一使用 Conda 管理环境，但每个重型工具仍保持隔离：

```text
easydesign-core (Python 3.11)
├── pipeline、manifest、配置、轻量生信、测试和报告
├── subprocess/文件协议 → boltzgen 环境
├── subprocess/文件协议 → boltz2 环境
├── subprocess/文件协议 → AF3/AFO/Phoenix 环境
└── executor adapter     → local/Slurm/SMART
```

`environment.yml` 创建 `easydesign-core`；`pyproject.toml` 是 Python 依赖的唯一声明源。
重型 backend 按其上游要求使用独立 Conda 环境、容器或 module。Core 不激活环境，不向
重型环境安装自身依赖；adapter 使用显式 executable、工作目录、请求文件和结果 manifest。

站点专属环境路径只能出现在未提交的本地 profile 或调用参数中。仓库代码不得硬编码
`/root/autodl-tmp`、SMART 路径、用户名或密钥。

## 5. 运行目录层级

```text
runs/<project_id>/<run_id>/
├── manifests/
│   ├── run-manifest.v0001.json
│   ├── run-manifest.v0002.json
│   └── LATEST
├── config-snapshot/
├── 01-target-preparation/
│   ├── attempts/
│   │   ├── attempt-0001/
│   │   │   ├── attempt-manifest.json
│   │   │   ├── logs/
│   │   │   └── artifacts/
│   │   └── attempt-0002/
│   └── stage-manifest.json
├── 02-hotspot-discovery/
├── 03-boltzgen-configuration/
├── 04-pilot-generation/
├── 05-pilot-filtering/
├── 06-scale-generation-and-refolding/
└── 07-final-filtering-and-selection/
```

### 身份

- `project_id`：稳定项目 slug。
- `run_id`：一次完整七阶段运行的唯一 ID。
- `stage_id`：固定编号 `01`–`07`。
- `attempt_id`：阶段内单调递增的 `attempt-0001` 等。
- `artifact_id`：run 内稳定逻辑身份；文件内容同时用 SHA-256 验证。

Artifact 路径必须是相对于 run 根目录的 POSIX 路径，不能是绝对路径，不能包含 `..`，
不能逃出 run 根目录。

## 6. Manifest 与不可变性

- `ArtifactRef` 描述 artifact 的逻辑角色、相对路径、格式、大小、SHA-256 和生产者。
- `Attempt` 记录一次执行的状态、时间、backend、executor、seed、日志和错误。
- `StageManifest` 声明阶段接受的输入、产生的输出、attempt 历史和最终选择。
- `RunManifest` 声明项目/run 身份、代码/config 版本及七阶段 manifest 引用。

终态 Attempt 和已发布 StageManifest 不可修改。RunManifest 使用递增版本快照；`LATEST`
只是可原子替换的小型指针，不是科学产物。恢复执行先验证上游 checksum 和配置兼容性，
然后追加新 attempt 和新 run manifest 版本。

运行状态与证据成熟度分开：

- 执行状态：`pending`、`running`、`succeeded`、`failed`、`cancelled`。
- 证据状态：`planned`、`implemented`、`smoke-validated`、
  `scientifically-validated`、`production-ready`。

## 7. 配置与 adapter 边界

配置按可移植默认值、项目配置、环境 profile、显式调用参数的顺序解析，最终结果写入
`config-snapshot/`。密钥只来自环境变量或秘密管理系统。

后端专属字段留在 adapter 内。Core 只接收规范化能力、请求、结果和错误，使 RCSB/UniProt、
BoltzGen、Phoenix/AFO/AF3 以及 local/Slurm/SMART 可以替换而不改阶段契约。

## 8. 决策记录

- 2026-07-23：从零建立私有 clean repository；旧仓只读；采用七阶段、不可变 manifest、
  可替换 backend 和 Python-API-first 路线。
- 2026-07-24：开发期只维护中文文档，每阶段只保留一个合并后的 README。
- 2026-07-24：全部环境先由 Conda 管理；`easydesign-core` 使用 Python 3.11，重型工具
  继续独立环境；基础契约使用 Pydantic、规范 JSON、相对路径和 SHA-256。

重大决策先追加到本节。决策数量或协作规模增长后，再拆分为独立 ADR 文件。
