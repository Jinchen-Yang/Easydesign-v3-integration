# EasyDesign Local

[产品理念](docs/PRODUCT_PHILOSOPHY.md) · [开发指南](DEVELOPMENT.md) ·
[数据安全](DATA_SAFETY.md)

EasyDesign Local 是一个由 Codex 辅助、研究者批准、在本机 GPU 上执行的蛋白设计工作台。
公开流程是：

```text
prepare → strategize → pilot loop → scale → select
```

EasyDesign 负责确定性工具、任务执行、manifest、checksum 和不可变科学证据；Codex 负责结合
项目状态与研究经验提出方案；位点、策略、放大和最终交付由研究者批准。

## 从全新机器开始

### 1. Clone 并安装主环境

```bash
git clone -b easydesign-local https://github.com/Knitua/Easydesign.git
cd Easydesign

curl --proto '=https' --tlsv1.2 -LsSf \
  https://astral.sh/uv/0.12.3/install.sh \
  | env UV_NO_MODIFY_PATH=1 sh
export PATH="$HOME/.local/bin:$PATH"
uv --version

./scripts/bootstrap.py --index auto
source .venv/bin/activate
easydesign --version
```

已经全局安装 `uv 0.12.3` 的机器可以跳过 uv 安装命令；uv 本身由宿主机管理，bootstrap
不会复制、升级或删除它。调用全局 uv 时，bootstrap 会把 HOME、配置、cache、Python 下载
和临时文件全部隔离到当前 clone 的 `runtime/`。随后它从官方源、阿里云和清华源中实测
选择可用来源；`uv.lock` 保证各来源安装的依赖版本和校验身份一致。`.venv` 先在
`runtime/tmp/` 中完成安装与验证，再原子发布；失败内容只进入 `runtime/quarantine/`。
该步骤不包含大型科学模型与独立环境。

### 2. 安装本仓库的 Miniforge

EasyDesign 主程序由 `uv` 安装在 `.venv/`；PyMOL、BoltzGen、Protenix、ScanNet 和 TNP
还包含 CUDA、编译库等独立依赖，需要 Conda 按仓库中的 explicit lock 分别创建重型环境。
因此新机器还需要一套只属于当前 clone 的 Miniforge。用户明确运行下面的命令后，它会下载
固定版本、校验 SHA-256 并安装到 `runtime/tools/`，不会修改系统 Python、系统 Conda 或
shell profile：

```bash
easydesign runtime install miniforge
```

该命令默认使用 `--source auto`，只用小请求探测官方源和仓库登记的国内镜像，选择当前主机
可用且较快的传输地址；版本、文件大小和 SHA-256 始终由仓库锁决定。网络中断后重复同一
命令会从 `runtime/cache/downloads/` 的 partial 继续，而不是从头下载。需要严格限定来源时
可以使用 `--source official`；`--source china` 表示国内优先，均不可用时回退官方。

### 3. 安装科学环境

安装顺序是：

```text
pymol-pse → boltzgen → protenix-v2 → scannet-epitope → tnp
```

以下两种方式二选一。已有 setup job 运行时，CLI 会拒绝启动第二个任务并返回现有任务的
观察命令，避免多个安装进程争用同一 cache。

#### 方式 A：一个后台任务安装全部组件

先查看五个组件的合并计划，再启动一个串行后台任务：

```bash
easydesign runtime plan all
easydesign runtime install all --detach
```

`all` 只创建一个 setup job；它按上述顺序处理五个环境及对应资产，不会并发运行五个 Conda
安装。catalog 当前包含经过人工批准的 AFO `stable`，同一个前台或 `--detach` job 会在这五项
之后安装并激活该 stable；未来的 `candidate` 绝不会被 `all` 静默安装。任务中断后可重新执行同一
命令，已经完成且校验通过的环境、资产和下载 cache 会被复用。

#### 方式 B：逐个安装组件

每个组件都先查看自己的计划，等待当前 job 完成后再启动下一个：

```bash
# 1. PyMOL/PSE
easydesign runtime plan pymol-pse
easydesign runtime install pymol-pse --detach

# 2. BoltzGen
easydesign runtime plan boltzgen
easydesign runtime install boltzgen --detach

# 3. Protenix v2
easydesign runtime plan protenix-v2
easydesign runtime install protenix-v2 --detach

# 4. ScanNet epitope
easydesign runtime plan scannet-epitope
easydesign runtime install scannet-epitope --detach

# 5. TNP
easydesign runtime plan tnp
easydesign runtime install tnp --detach
```

两种方式都使用同一套候选来源策略，而不是固定唯一下载源。Conda 包先按逐包 SHA-256
下载到当前 clone 的 cache，再从本地显式视图创建环境；Pip index、Hugging Face 文件和
Git source 的实际选择会写入安装 request、环境或资产记录。镜像只改变传输，不改变
package 版本、build、模型 SHA 或 Git commit。需要复现严格官方传输时，在对应安装命令中
加入 `--source official`。

安装命令会打印 `SETUP_JOB_ID` 和对应的观察命令。复制它给出的命令，或运行：

```bash
easydesign runtime jobs --job-id SETUP_JOB_ID --watch
```

遇到许可确认时，安装命令会在创建后台 job 前逐项询问；阅读提示后确认，或显式重复提供
要求的 `--accept-license ASSET_ID`。`Ctrl-C` 只退出观察，后台安装继续。

### 4. 验收

科学组件全部完成后运行：

```bash
easydesign runtime status
easydesign doctor --full
```

只有 `doctor --full` 通过后，才把这台机器视为完整可用的 EasyDesign Local 主机。

OpenFold3/AFO 3.1.4 当前是受支持的 `stable` 组件；完整的 `runtime install all` 会安装它，
但 EasyDesign 项目仍不设置任何预测后端默认值。
其完整预转换发布物包含权重、runner、冻结 wheelhouse、锁、许可、model card、转换 receipt
和 smoke 输入；安装不需要原始 PyTorch checkpoint 或转换环境。当前发布 archive 的下载体积
是 5,032,471,381 bytes（4.687 GiB），解包、建环境和缓存还需要额外磁盘空间。实机
验收基线是 Linux x86-64、NVIDIA A100 40 GB 和兼容 CUDA 12 的驱动；更小 GPU 尚不属于
本 release 的承诺范围。若当前 clone 尚无 Python 3.12，安装器会复用 bootstrap 已要求的
`uv 0.12.3`，把精确 Python `3.12.13` 安装到 `runtime/tools/uv-python/`；无需用户手工准备
转换环境或设置系统 Python。

该确定性 archive 已发布到公开 Hugging Face 仓库；catalog 锁定具体 Hub commit、
5,032,471,381-byte 大小和 SHA-256
`83b6d8e895090a0c74d21e495d50b75a7cb031389386f5b7cd9843b6d3501afd`，不会跟随
`main` 漂移。安装当前 stable 可以省略 release；需要精确复现时仍可显式写出 release：

```bash
easydesign runtime list afo
easydesign runtime install afo
# 精确安装指定 release（不会改变当前 active）：
easydesign runtime install afo --release afo-3-1-4-of3-p2-155k
easydesign runtime activate afo --release afo-3-1-4-of3-p2-155k --confirm
easydesign doctor --full
```

环境安装与科学选择彼此独立。项目创建不选择预测后端；运行需要预测的阶段时才显式选择，
未选会立即停止，不会静默回退 Protenix。各阶段可以混用后端：

```bash
easydesign project init workspace/projects/my-project --target target.cif

# 只有 Stage 1 真正需要预测 target 时才提供：
easydesign target prepare workspace/projects/my-project --prediction-backend protenix

# Stage 5 的验证后端单独选择：
easydesign pilot run workspace/projects/my-project --strategy strategy-r000001 \
  --prediction-backend afo --confirm

# Stage 7 两种科学模式分别选择，可混用：
easydesign select run workspace/projects/my-project --run PRODUCTION_RUN \
  --de-novo-backend afo --target-conditioned-backend protenix --confirm
```

本 stable 绑定不可变 2 案例 AFO/Protenix boundary-negative sanity report 与人工 approval
receipt，并通过小型 Stage 1→5→7/resume、target-conditioned、全新 clone 续传/幂等/
quarantine/A100 GPU smoke。该批准不等同于完整 14 案例或多 seed 科学认证；仓库转为公开
仍是产品发布阶段的独立决定。

AFO 与 Protenix 都保留两条科学证据：`de-novo` 禁用 target/binder 模板并承担独立筛选；
`target-conditioned` 只把 Stage 1 冻结的 target A 作为显式模板，binder B 仍无模板，也不做
自动模板搜索。条件化结果使用独立 advisory profile，不会混入 de-novo 晋级门；预测来源
与当前 backend 相同时会明确标记 self-conditioning。详细边界见
[OpenFold3 后端](docs/OPENFOLD3_BACKEND.md)。

## 用 Codex 开始

从仓库目录启动 Codex，直接描述研究目标，例如：

```text
为 P02649 新建一个 EasyDesign 项目，先准备靶点；遇到歧义停下来和我讨论。
```

Codex 会读取仓库级 `$easydesign-research` Skill，并通过语义化命令推进项目。也可以直接从
终端开始：

```bash
easydesign project init workspace/projects/apoe --uniprot P02649
easydesign target prepare workspace/projects/apoe --prediction-backend afo
easydesign project status workspace/projects/apoe --json
```

查看全部命令：

```bash
easydesign --help
easydesign project --help
easydesign runtime --help
```

## 数据位置与批准边界

- `workspace/projects/`：输入、draft、位点和策略 revision；
- `workspace/runs/`：不可变科学 run、manifest、attempt 和 artifact；
- `runtime/`：本机环境、模型、cache、日志、任务状态和安装 receipt；
- `examples/apoe-ui-demo/`：只读 APOE 科学证据示例，不得改写。

读取、校验、染色、扫描、规划和 review 可以直接执行。`site approve`、`strategy freeze`、
`pilot run/promote`、`scale run` 和 `select run` 必须由研究者显式确认。每个 run 还会冻结
已选 backend、AFO release、runtime profile SHA 和配置快照；`job resume` 只读取该快照，
不接受新的后端参数，也不受之后的 profile 激活变化影响。

本分支为私有 Developer Preview；结果用于研究决策支持，不等于实验或临床验证。
