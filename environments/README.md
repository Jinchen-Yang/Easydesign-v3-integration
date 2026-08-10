# EasyDesign 环境安装手册

本目录保存可进入 Git 的环境配方和 `linux-64` 锁文件。真正的 Conda 环境、模型、缓存、
安装状态和日志只写入当前 clone 的 `runtime/`，不写入系统盘用户配置、base Conda、
shell profile、Git 全局配置或系统代理。

## 推荐流程

先按根 README 使用 uv 创建并激活 `.venv`。可以用一个串行后台任务安装全部组件：

```bash
easydesign runtime plan all
easydesign runtime install all --detach
```

也可以逐个执行；完整的五组命令见根 README，推荐顺序为：

```text
pymol-pse
→ boltzgen
→ protenix-v2
→ scannet-epitope
→ tnp
```

顺序不是科学依赖，只是便于先验证核心、PSE 和生成主线，并在每次大下载后复核空间。
core 已由 uv 管理，因此新部署只使用显式科学 component，不创建第二套 core 环境。
产品命令只使用 uv 管理的当前仓库 `.venv`，且没有自动 Conda fallback。

安装目标始终由当前 clone 决定。Conda 环境、模型、下载缓存和临时文件分别进入：

```text
runtime/envs/
runtime/models/
runtime/cache/
runtime/tmp/
```

可在安装前后核验挂载点和占用：

```bash
pwd
df -h . runtime
du -sh runtime/envs runtime/models runtime/cache runtime/tmp runtime/quarantine
easydesign runtime status
```

输出路径若不位于当前仓库，安装器必须拒绝，而不是改写 `~/.config`、`~/.cache` 或系统盘。
环境配方和锁文件进入 Git；实际环境与模型不进入 Git。

安装来源与锁定身份是两个独立层次。Conda lock 固定每个 package URL identity、build 和
SHA-256；pip lock 固定 requirement；文件资产固定大小/SHA-256，Git 资产固定 commit。
`config/runtime-sources.yaml` 只登记可替换的传输地址。默认 `--source auto` 会探测后排序，
`official` 严格只用官方地址，`china` 国内优先并在全部不可用时回退官方：

```bash
easydesign runtime install boltzgen --source auto --detach
easydesign runtime install boltzgen --source official --detach
easydesign runtime install boltzgen --source china --detach
```

如需指定本组织自己的 HTTPS Python index，仍可单次覆盖 Pip：

```bash
easydesign runtime install boltzgen \
  --source official \
  --pip-index-url https://pypi.tuna.tsinghua.edu.cn/simple \
  --detach
```

来源策略和 Pip override 都进入不可变 `request.json`，实际选中的来源进入结果记录；它们只
传给本任务的子进程，不修改系统代理、`.condarc`、pip 配置或后续任务。Conda 包和普通文件
使用稳定的仓库内 partial，跨等价来源续传；最终大小/SHA 不一致的字节进入 quarantine。
Git fallback 只有在目录中登记了可信候选时才发生，并且最终 commit 必须等于 lock。

## 为什么推荐 `--detach`

科学后端会下载数 GB 的 Conda、pip 和模型资产。普通前台进程的 stdout 如果跟随客户端
终端连接关闭，Python/pip 可能因输出管道断开而退出，即使依赖本身没有冲突。

`--detach` 使用以下固定契约：

- `shell=False`，不解释用户 shell 文本。
- 独立进程 session，关闭客户端终端或网页不会向本机 worker 发送挂断信号。
- stdin 为关闭状态，许可必须在启动前显式确认。
- 子进程的 HOME、TMP、Conda/pip/npm/Playwright cache 全部指向仓库 `runtime/`。
- `request.json`、`process.json` 和 `result.json` 均只创建一次，不覆盖历史字节。
- stdout/stderr 进入 `runtime/logs/`，状态查询不解析终端文本。
- pip 连接使用 120 秒超时、10 次网络重试；支持的 pip 版本同时启用断点续传重试。

查询所有任务或一个任务：

```bash
easydesign runtime jobs
easydesign runtime jobs --job-id setup-YYYYMMDDTHHMMSSZ-XXXXXXXXXX
```

任务目录：

```text
runtime/state/setup-jobs/<job-id>/
├── request.json
├── process.json
└── result.json       # 只有 worker 达到终态后出现
```

任务可能处于：

| 状态 | 含义 |
|---|---|
| `running` | worker 身份与当前进程匹配，仍在安装 |
| `succeeded` | 环境和本次已授权资产均通过 |
| `incomplete` | 安装安全结束，但许可资产等尚未完整 |
| `failed` | worker 捕获到明确失败，错误已记录 |
| `interrupted` | worker 已不在且没有终态记录，需要查看日志后安全重试 |

## 许可、重试与磁盘

先查看资产和许可：

```bash
easydesign runtime status
easydesign runtime plan boltzgen
```

确认精确资产后再启动：

```bash
easydesign runtime install boltzgen \
  --accept-license ASSET_ID \
  --detach
```

每个 `--accept-license` 只授权该 ID。本次未授权资产保持 `awaiting-approval`，不能被报告
为可用。重试 runtime install 会校验并复用已发布的正确环境、包缓存和资产；lock 变化会创建新环境
目录，旧环境、失败 staging、缓存和运行结果全部保留。

计划中的 `incremental_peak_bytes` 是本组件的环境、保留缓存、最终资产和最大单资产
staging 峰值；runtime install 还要求固定保留至少 10 GiB。不要通过删除历史数据
绕过磁盘门。

## 完成验收

安装任务成功不等于全产品已经可用。依次运行：

```bash
easydesign runtime jobs --job-id JOB_ID
easydesign runtime status
easydesign doctor --full
```

`doctor --full` 只有在当前锁定环境、必需模型/权重、版本探针和设备检查均通过时才返回
成功。CLI 只读取这一批结构化记录，不维护第二套安装状态。

## 故障处理原则

正常主路径要求 `conda --version` 成功，不需要指定路径。只有 Conda executable 不在
`PATH` 时才通过环境变量提供当前机器上的可执行文件；该参数不是环境安装目录：

```bash
export EASYDESIGN_CONDA_EXE=runtime/tools/miniforge3/bin/conda
easydesign runtime install pymol-pse \
  --conda "$EASYDESIGN_CONDA_EXE" \
  --detach
```

环境仍发布到当前仓库的 `runtime/envs/`。

- 网络中断：查看任务的 stdout/stderr，再以同一 component 和 source policy 重新运行；
  已验证 cache 和未完成 partial 会被复用。
- 许可未确认：精确确认缺失的 asset ID 后重新运行。
- 环境失败：失败 staging 会进入 `runtime/quarantine/`；不得自动删除。
- 磁盘不足：停止创建新任务，扩容或由用户对精确路径另行决定；EasyDesign 不清理数据。
- 仓库移动：Conda prefix 可能失效，应在新路径按 lock 新建环境；旧环境继续保留。

任何 runtime install 过程都不得调用递归删除、修改系统代理、修改 base Conda 或覆盖已有科学运行。
