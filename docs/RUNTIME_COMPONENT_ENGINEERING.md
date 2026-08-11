# EasyDesign 环境与模型组件工程规范

## 目的

本规范用于两类工作：

1. 将 RFdiffusion3、ProteinMPNN、OpenDDE 等新模型接入 EasyDesign；
2. 升级 Protenix、BoltzGen、ScanNet、TNP 等既有组件的环境、源码或权重。

两类工作的本质相同：**构建一个新的、不可变、可验证、可回滚的 component release**。
新增组件不是“把一个环境装上”；版本升级也不是“在旧环境里更新几个包”。二者都必须从锁定
身份、可靠传输、隔离安装、分层探针、灰度验证到人工切换走完同一条发布流水线。

目标可以概括为“稳、准、快”：

- **稳**：断网、慢源、进程退出、磁盘不足、重复执行和部分失败都不会破坏已完成结果；
- **准**：版本、build、wheel、源码、模型、许可、设备和实际运行记录能够一一对应；
- **快**：传输来源可替换，已验证字节可复用，失败能够快速换路而不是整项重来。

本规范只允许在当前 clone 所在的本地 Linux GPU 主机执行。环境、模型、缓存、日志和状态都
属于当前 clone 的 `runtime/`；不得引用其他 clone、共享 runtime、远程 executor 或公共算力。

## 一条核心原则：身份固定，传输可变

每个组件必须拆成两个互不混淆的层次。

### 不可变身份

| 对象 | 必须固定的身份 |
|---|---|
| Conda 包 | channel identity、package、version、build、archive SHA-256 |
| Pip 包 | requirement、兼容 tag、最终 wheel 文件名和 SHA-256 |
| Git 源码 | canonical source、40 位 commit、目录 content SHA-256 |
| 普通模型/数据文件 | 逻辑 asset ID、大小、SHA-256、许可 |
| Hugging Face snapshot | repository、revision、逐文件相对路径、大小和 SHA-256 |
| 运行适配器 | backend ID、输入输出契约版本、probe contract 版本 |

任何会改变科学结果或运行兼容性的内容，都必须产生新的身份。禁止使用 `latest`、浮动 branch、
无 hash 的模型链接、未固定的 Git HEAD 或仅靠目录名称暗示版本。

### 可替换传输

以下内容可以变化，但不能改变最终身份：

- 官方站点、国内镜像、组织内部 HTTPS 镜像；
- HTTP/1.1、HTTP/2、Git archive、Git smart HTTP；
- Pip index、Conda mirror、Hugging Face mirror；
- 分段下载的具体连接和重试顺序。

来源只能改变“字节从哪里来”，不能改变“最后接受什么字节”。每次安装 request 必须记录来源
策略，每个 receipt 必须记录实际来源；环境 ID 和资产 ID 不得包含镜像选择。

## Component release

建议将一个科学组件理解为以下不可变集合：

```text
component release
├── component ID
├── environment lock
│   ├── Python ABI
│   ├── Conda explicit packages + SHA-256
│   ├── Pip wheels + SHA-256
│   └── CUDA/Torch/JAX/TensorFlow compatibility declaration
├── source assets
│   └── canonical repository + fixed commit + content SHA-256
├── model/data assets
│   └── relative destination + size + SHA-256 + license
├── backend contract
│   ├── executable and entry point
│   ├── input/output schema
│   ├── resource/device policy
│   └── timeout and failure semantics
└── acceptance contract
    ├── install probe
    ├── doctor probe
    ├── minimal real smoke
    └── scientific pilot/gray evidence
```

推荐用上述内容的规范化摘要生成 release identity。环境路径继续使用 lock-addressed 形式，例如：

```text
runtime/envs/<component-id>-<environment-lock-sha-prefix>/
runtime/models/<component-id>/<asset-identity>/
runtime/state/components/<component-release-id>/
```

旧 release 不原地修改。新旧环境和模型可以并存，由当前 clone 的 profile 明确选择一个版本。

## 新组件接入流程

### 1. 先定义边界，再尝试安装

新增 RFdiffusion3、ProteinMPNN 或 OpenDDE 时，先回答：

- 它是独立 backend，还是另一个 backend 的内部步骤？
- 它需要独立 Python/CUDA 环境吗？
- 哪些模型、数据库、源码和可执行文件是运行必需项？
- 输入输出是什么，失败如何分类？
- 运行在 CPU 还是 GPU，最低驱动和显存是多少？
- 许可是否允许下载、内部运行、再分发和生成结果？

“科学上相关”不等于“应该共用环境”。ProteinMPNN 即使与 RFdiffusion3 连续使用，也应优先
保持独立锁定环境，通过文件协议和 manifest 连接；只有依赖栈、生命周期和资源策略确实一致
时才考虑合并。

### 2. 建立兼容矩阵

接入前必须冻结并记录：

| 层次 | 需要验证的内容 |
|---|---|
| 主机 | Linux、CPU 架构、glibc、NVIDIA driver |
| Python | major/minor、ABI、关键扩展支持范围 |
| GPU 用户态 | CUDA runtime、cuDNN、cuBLAS、NCCL |
| 框架 | Torch/JAX/TensorFlow 及其 CUDA build |
| 模型 | checkpoint 格式、代码 commit、预处理版本 |
| 工具 | DSSP、ANARCI、HHsuite 等外部 executable |
| 资源 | GPU 型号、显存、RAM、磁盘峰值、预期时长 |

仓库内 CUDA runtime 与服务器驱动是两层。安装旧 CUDA 10 或新 CUDA 13 用户态包不等于修改
系统驱动；但必须用实际设备探针验证驱动是否能够承载该 runtime。不能仅凭包名推断兼容。

### 3. 构建锁，而不是保存一次成功的 shell 历史

锁文件必须由经过审查的配方生成并进入 Git。禁止把以下内容当成正式 lock：

- `pip freeze` 的偶然输出；
- 未固定 build/hash 的 `environment.yml`；
- 指向 `main`、`master` 或 tag 的 Git URL；
- Hugging Face cache 中碰巧存在的一组文件；
- 开发者 home 下某个“能跑”的 Conda 环境。

Conda 应生成逐包 explicit lock，并保存原始 archive basename 和 SHA-256。Pip 除了固定版本，
还应将选定 wheel 的文件名、Python/platform tag 和 SHA-256 提升为可提交的 lock 身份。

当前 EasyDesign 已对下载后的 wheel 逐个计算 SHA、记录 receipt 并在当前 clone 离线复用；但
如果 tracked pip lock 仍只有 `package==version`，新机器首次安装时仍可能接受上游同版本的不同
wheel 字节。新组件和下一次版本升级应补齐 tracked wheel hash lock，达到跨机器 bit-level
复现，而不是只保证版本号相同。

### 4. 模型、源码和许可独立登记

环境 lock 不应隐式负责下载模型。每个资产单独声明：

- 稳定 asset ID；
- canonical source；
- 等价传输候选；
- revision、大小和 SHA-256；
- 仓库内相对 destination；
- license 和是否要求显式接受；
- 解压后的内容身份与结构约束。

Git archive 和 Git clone 必须生成同一种通用 receipt：

```json
{
  "source": "canonical repository",
  "revision": "40-character commit",
  "content_sha256": "normalized directory hash",
  "transport_source_id": "actual source",
  "archive_sha256": "optional pinned archive identity"
}
```

安装器、`runtime status`、`doctor` 和正式 backend 必须共同消费这一份契约。禁止各自发明一套
marker。没有 receipt 时，只允许验证源码目录自身的 `.git`；禁止 `git -C` 向父目录发现
EasyDesign 或其他仓库。

## 稳定可靠的下载器

### 候选来源与健康状态

每类 artifact 都应有经过审查的候选来源列表。自动策略按本机实测排序，而不是硬编码“镜像
永远更快”。每个候选需要：

- 连接超时、首字节超时、低速阈值和总 attempt timeout；
- HTTP 状态、TLS、Range 和内容长度探针；
- 当前 job 内的健康评分；
- 连续 `403/404/429/5xx` 或低速后的 circuit breaker；
- 退避与切换原因记录。

本次安装中 USTC 部分 PyPI 链接连续返回 `403`，虽然逐 wheel fallback 能成功，但仍会让后续
每个 wheel 先重复尝试已知故障源。未来必须加入 job-local source demotion：同一来源达到阈值
后，在冷却期内直接尝试下一来源；这只改变传输顺序，不改变 package identity。

### 续传粒度

- 普通大文件、Conda archive、Git archive：使用稳定 partial 文件和 HTTP Range 续传；
- Pip：以单个 wheel 为原子缓存单元，已完成 wheel 不重下；来源切换时当前未完成 wheel 可以
  重试，但不能丢失此前 wheel；
- Hugging Face：按逐文件 identity 缓存，禁止一次不透明地下载整个 snapshot；
- 解压和安装：永远从已校验的本地文件进行，不边下载边发布最终环境。

partial/cache key 必须基于 artifact identity，而不是临时 URL；不同来源的等价字节才能安全
续传。完成后先验证大小与 SHA，再原子 rename。错误字节进入 quarantine，不覆盖正确缓存。

### 进度必须反映真实阶段

进度输出至少包含：

- component、phase、当前 artifact；
- item index/total；
- bytes completed/total、当前速率和 ETA；
- 当前来源和发生切换的原因；
- 下载、离线安装、probe、publish 的明确状态。

观察器重复展示最后一条状态不等于重复下载。长时间无字节变化时，worker 必须报告“仍在
解压/安装/验证”或触发低速切换，不能只把同一下载行打印几十次。

## 隔离、原子性和幂等性

### 当前 clone 是唯一边界

除了用户选择全局安装和使用的 `uv`，所有可变内容必须位于当前 clone：

```text
runtime/envs/
runtime/models/
runtime/cache/
runtime/tmp/
runtime/home/
runtime/state/
runtime/logs/
runtime/quarantine/
```

安装子进程必须重写 HOME、XDG、Conda/Pip/UV/Hugging Face/Torch cache 和临时目录，清除宿主
`PYTHONPATH`、`PYTHONHOME`、`VIRTUAL_ENV` 和外部 Conda 状态。运行目标环境的 probe 或正式
backend 时，将目标 prefix 的 `bin/`、`lib/` 和 `CONDA_PREFIX` 显式放在最前面。

路径来自 `easydesign-workspace.yaml` 和 profile 的仓库内相对声明；不得硬编码 `/data`、主机名、
用户 home 或另一个 clone 的绝对路径。

### 环境必须 staging 后发布

目标状态机应为：

```text
plan
  → materialize verified packages
  → create staging environment
  → offline install
  → inventory
  → install probe
  → atomic publish to lock-addressed prefix
  → component asset verification
  → component acceptance probe
```

失败只允许留下 receipt、正确 cache 和 quarantine；不得留下一个看似正式、实际未通过 probe 的
最终 prefix。已有旧环境也不得在原地升级。

当前实现已经做到 lock-addressed prefix、cache 复用、失败记录与 quarantine，但科学 Conda 环境
的创建仍需进一步统一为独立 staging prefix，只有探针通过后才发布。这应在纳入下一个大型组件
前完成。

### `all` 应按组件完成事务

一键安装的理想顺序是：

```text
component A: environment → assets → acceptance
component B: environment → assets → acceptance
...
```

不能先创建全部环境，再统一处理全部资产。本次 `all` 在 TNP 环境探针失败后停止，导致已经通过
环境探针的 ScanNet 尚未安装源码/模型资产。状态记录虽然没有伪造成功，但用户容易误以为 ScanNet
已经完整可用。未来应以 component 为恢复和完成单位，并对已完成 release 自动跳过。

## 分层探针

“安装成功”不能只有一种含义。至少需要四层证据。

### 1. Artifact integrity

确认下载字节和锁一致：大小、SHA、commit、目录 content hash、许可 receipt。这只能证明文件
正确，不能证明能够导入或运行。

### 2. Install probe

环境发布前自动执行，成本应控制在秒级到数分钟：

- 使用目标环境的绝对 Python/executable；
- 导入核心包并检查版本；
- 检查 `torch.version.cuda`、JAX/TensorFlow build 等；
- 检查必要 CLI 确实位于目标 prefix；
- 执行一个小的库级操作，而不只是 `import`。

探针必须在与正式运行相同的隔离环境变量下执行。本次 TNP 的 `mkdssp/ANARCI` 误报说明：使用
目标 Python 但不激活目标 `PATH`，仍然不是一个有效的环境探针。

### 3. `easydesign doctor`

`doctor` 是可重复执行的产品级 readiness 检查。它读取当前 runtime profile，调用正式 backend
adapter，核对环境、源码、模型、设备和输入输出契约是否能够组合工作。它不安装、不下载，也不
创建科学 run。

默认运行：

```bash
easydesign doctor
```

默认只对当前 profile 已配置 backend 做正式检查。`--full` 表示要求所有已知可选 backend 也
存在；例如 OpenFold3/AFO 未安装时，`doctor --full` 应失败，因此不能把它作为所有部署的固定
命令。

`doctor` 仍不是完整科学推理。版本、checkpoint、源码、设备和 adapter 能通过，不代表所有真实
输入都能成功。

### 4. Minimal real smoke 与 scientific pilot

每个组件必须提供最小、固定、低成本的真实输入，并验证结构化输出：

- RFdiffusion 类：固定短结构与少量 diffusion steps；
- ProteinMPNN：固定小 PDB、固定 seed、少量序列；
- 结构预测：固定短链/小复合物，验证输出结构和 confidence schema；
- TNP/打分器：固定少量序列，验证结果字段、单位和有限值。

smoke 证明端到端计算链路；pilot 才验证真实研究数据、资源估计、失败率和科学分布。高成本 smoke
不应偷偷放进安装器，但必须有显式命令、固定预算、receipt 和 checksum。

## 既有组件升级流程

Protenix 发布新版本或新权重时，不修改当前 lock；创建一个新的候选 release。

### 什么时候必须新建环境

出现以下任一变化时，默认新建环境：

- Python minor/ABI 改变；
- Conda/Pip package、build 或 wheel 改变；
- Torch/JAX/TensorFlow 或 CUDA 用户态改变；
- 上游源码 commit 改变；
- 编译选项、外部 CLI 或系统库契约改变；
- probe 所依赖的能力发生改变。

只更换模型权重、而代码和依赖完全不变时，环境可以复用，但仍要创建新的 component release，
因为模型 identity 已变化。

仅新增等价镜像、调整来源优先级或修复下载器时，不应更新科学 lock；这是 transport release，
不是 component identity 变化。

### 升级流水线

```text
upstream release review
  → license/security review
  → new environment/source/model locks
  → clean-clone installation
  → install probes
  → doctor
  → deterministic smoke
  → old/new gray comparison
  → researcher approval
  → new profile revision
  → monitored pilot
  → optional old-release retirement
```

新旧 release 必须并存，profile 切换单独提交。回滚只需要恢复旧 profile revision，不能依赖重新
下载旧包。旧环境和模型只有在明确确认、不再被任何 run/manifest 引用后才能退役；删除仍需用户
对精确路径单独授权。

### 升级比较

比较不能只看“能运行”：

- 固定输入、seed、参数和硬件；
- 同时记录成功率、时长、峰值显存/RAM、输出 schema；
- 比较核心科学指标分布，而不是只比较单个案例；
- 明确指标定义是否变化；
- 保存两边环境、模型、源码和 adapter identity；
- 不允许新版本静默成为默认后端。

## 失败语义

必须区分：

| 状态 | 含义 |
|---|---|
| transport failure | 来源不可用、超时、低速、校验失败 |
| install failure | 解包、Conda/Pip、编译或磁盘失败 |
| probe failure | 环境存在但能力或依赖不满足 |
| asset incomplete | 环境通过，但模型/源码/许可尚未完成 |
| operational failure | 正式运行超时、OOM、进程退出 |
| scientific negative | 工具正常完成，但没有合格候选 |
| awaiting approval | 许可、site、strategy 或升级切换等待研究者 |

任何一类都不能被记录为另一类，更不能用 fallback 伪装成功。科学 fallback 必须由显式配置和
研究者决策触发；只有完全等价的传输来源可以自动切换。

## 本次安装暴露的问题与永久规则

| 本次问题 | 永久规则 |
|---|---|
| 文档仍描述远程/共享 runtime | 当前 clone 是唯一执行和状态边界 |
| 用户 `PYTHONPATH` 影响 Miniforge/环境 | 所有子进程清理宿主解释器状态 |
| 单一下载源极慢 | identity 与 transport 分离，多来源实测排序 |
| Conda 大包卡住 | 逐包缓存、Range 续传、低速切换、SHA 后发布 |
| Pip 整体安装长时间无进度 | 逐 wheel 获取、receipt、离线安装和逐项进度 |
| USTC 多个 wheel 连续 `403` | job-local source circuit breaker，避免重复撞故障源 |
| 大模型只有一个 URL | 分段续传、等价镜像、稳定 partial、最终 SHA |
| watcher 重复最后一行 | 明确区分下载、解压、安装、probe，不把轮询当进度 |
| TNP 已装命令却探针失败 | probe 必须激活目标 prefix 的 PATH/lib/CONDA_PREFIX |
| 新 installer receipt 与旧 doctor 冲突 | installer/status/doctor/backend 共用一个源码契约 |
| ScanNet 找到 EasyDesign Git HEAD | 无 receipt 时只接受源码目录自己的 `.git` |
| 环境通过但 ScanNet 资产未装 | completion 以 environment+assets+acceptance 为单位 |
| 安装探针通过被理解为模型可运行 | 分开 integrity、install probe、doctor、real smoke |

## 自动化验收矩阵

每个新增或升级组件至少通过以下测试：

### 静态契约

- 所有 lock/asset/source identity 完整且 schema 校验通过；
- 不存在浮动 URL、branch、`latest` 或绝对部署路径；
- 许可、磁盘估计、设备要求和 backend contract 已登记；
- README/文档中的组件列表由同一 registry 驱动或有测试约束。

### 下载故障注入

- 第一来源连接失败、持续低速、`403`、`429`、`5xx`；
- 中途断开后从正确 offset 续传；
- 不支持 Range 时安全重启当前 artifact；
- 镜像返回错误大小或错误 SHA 时拒绝并 quarantine；
- 已完成 cache 在重试时不重新下载；
- 连续故障源在当前 job 中被降级。

### 安装故障注入

- Ctrl-C 只退出观察，不终止 detached worker；
- worker 异常退出后 job 状态可诊断；
- 磁盘不足在写入前拒绝；
- staging 失败不改变已发布环境；
- 重复 install 幂等；
- lock 改变产生新路径，旧 release 不被覆盖；
- host HOME/PYTHONPATH/Conda/Pip 配置不被读取或修改。

### 运行验收

- install probe；
- `runtime status` identity 核对；
- `doctor` 正式 adapter probe；
- CPU/GPU 设备实际小计算；
- 固定真实 smoke；
- 一次失败 smoke 的日志、return code 和 receipt；
- 与旧 release 的资源和科学结果比较。

### 干净机器验收

最终必须在没有旧环境、旧 cache 和用户配置帮助的同类主机上，从 README/正式命令完成一次。
开发机“已经装过所以成功”不能作为发布证据。允许保留全局 `uv`，但 `.venv`、科学环境、模型、
cache 和状态必须从当前 clone 全新生成。

## Definition of Done

一个 component release 只有同时满足以下条件才能称为可用：

- [ ] 环境、源码、模型、数据、许可和 backend contract 全部有不可变身份；
- [ ] 官方与镜像来源只改变传输，不改变身份；
- [ ] clean clone 安装成功；
- [ ] 中断、慢源、坏源和重复执行测试通过；
- [ ] 环境从 staging 原子发布，失败结果可诊断且不覆盖旧环境；
- [ ] `runtime status` 显示当前 lock 和全部必需资产 `available`；
- [ ] install probe 在目标 prefix 环境中通过；
- [ ] `easydesign doctor` 对当前 profile 通过；
- [ ] 固定真实 smoke 通过并保存 checksum/receipt；
- [ ] 升级时完成旧/新灰度比较与研究者批准；
- [ ] profile 切换可回滚；
- [ ] 文档只给当前 clone 的正式入口，不暴露旧脚本或外部 runtime 路径。

做到这些以后，“新增一个模型”和“升级一个模型”就不再是两套临时操作，而是同一套可审计、
可恢复、可扩展的 component release 工程。
