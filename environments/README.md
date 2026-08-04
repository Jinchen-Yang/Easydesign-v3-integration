# EasyDesign 环境安装手册

本目录保存可进入 Git 的环境配方和 `linux-64` 锁文件。真正的 Conda 环境、模型、缓存、
安装状态和日志只写入当前 clone 的 `runtime/`，不写入系统盘用户配置、base Conda、
shell profile、Git 全局配置或系统代理。

## 推荐流程

先按根 README 使用 uv 创建并激活 core/UI `.venv`。在 Linux 数据盘的仓库根目录运行：

```bash
easydesign setup --component pymol-pse --plan
easydesign setup --component pymol-pse --detach
easydesign setup --status
```

逐后端重复上述流程，推荐顺序为：

```text
pymol-pse
→ boltzgen
→ protenix-v2
→ scannet-epitope
→ tnp
```

顺序不是科学依赖，只是便于先验证核心、PSE 和生成主线，并在每次大下载后复核空间。
core/UI 已由 uv 管理，因此新部署不使用无 `--component` 的全量 setup，也不重复创建
core/UI Conda 环境。

安装目标始终由当前 clone 决定。例如仓库位于数据盘：

```text
/root/autodl-tmp/Protein_design/easydesign-clean/
```

则 Conda 环境、模型、下载缓存和临时文件分别进入：

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
easydesign env status
easydesign assets status
```

输出路径若不位于当前仓库，安装器必须拒绝，而不是改写 `~/.config`、`~/.cache` 或系统盘。
环境配方和锁文件进入 Git；实际环境与模型不进入 Git。

默认使用官方 `https://pypi.org/simple`。网络诊断证明官方 CDN 很慢时，可以显式选择
可信 HTTPS 镜像：

```bash
easydesign setup --component boltzgen \
  --pip-index-url https://pypi.tuna.tsinghua.edu.cn/simple \
  --detach
```

该选择只进入本任务的子进程和 `request.json`，不会修改系统代理、pip 配置或后续任务。
EasyDesign 不自动猜测地区或切换镜像；任何镜像都应由部署者明确选择。

下载源选择建议：

1. 先使用官方源执行单组件后台安装。
2. 只有日志明确显示 CDN 超时或连接中断时，才显式指定可信镜像重试。
3. 重试会保留失败环境到 `runtime/quarantine/`，并复用仓库内缓存；禁止用清理命令换取重试。
4. `pip_index_url` 会写入不可变任务请求，便于团队复现和审计。

## 为什么推荐 `--detach`

科学后端会下载数 GB 的 Conda、pip 和模型资产。普通前台进程的 stdout 如果跟随 SSH
连接关闭，Python/pip 可能因输出管道断开而退出，即使依赖本身没有冲突。

`--detach` 使用以下固定契约：

- `shell=False`，不解释用户 shell 文本。
- 独立进程 session，关闭 SSH 或网页不会向 worker 发送挂断信号。
- stdin 为关闭状态，许可必须在启动前显式确认。
- 子进程的 HOME、TMP、Conda/pip/npm/Playwright cache 全部指向仓库 `runtime/`。
- `request.json`、`process.json` 和 `result.json` 均只创建一次，不覆盖历史字节。
- stdout/stderr 进入 `runtime/logs/`，状态查询不解析终端文本。
- pip 连接使用 120 秒超时、10 次网络重试；支持的 pip 版本同时启用断点续传重试。

查询所有任务或一个任务：

```bash
easydesign setup --status
easydesign setup --status --job-id setup-YYYYMMDDTHHMMSSZ-XXXXXXXXXX
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
easydesign assets status
easydesign setup --component boltzgen --plan
```

确认精确资产后再启动：

```bash
easydesign setup --component boltzgen \
  --accept-license ASSET_ID \
  --detach
```

每个 `--accept-license` 只授权该 ID。本次未授权资产保持 `awaiting-approval`，不能被报告
为可用。重试 setup 会校验并复用已发布的正确环境、包缓存和资产；lock 变化会创建新环境
目录，旧环境、失败 staging、缓存和运行结果全部保留。

计划中的 `incremental_peak_bytes` 是本组件的环境、保留缓存、最终资产和最大单资产
staging 峰值；setup 还要求保留至少 10% 文件系统容量或 5 GiB。不要通过删除历史数据
绕过磁盘门。

## 完成验收

安装任务成功不等于全产品已经可用。依次运行：

```bash
easydesign setup --status --job-id JOB_ID
easydesign env status
easydesign assets status
easydesign doctor --full
```

`doctor --full` 只有在当前锁定环境、必需模型/权重、版本探针和设备检查均通过时才返回
成功。UI 的“安装与环境”页面读取同一批结构化记录，不维护第二套安装状态。

## 故障处理原则

正常主路径要求 `conda --version` 成功，不需要指定路径。只有 Conda executable 不在
`PATH` 时才显式提供；该参数不是环境安装目录：

```bash
easydesign setup --component pymol-pse \
  --conda /root/miniconda3/bin/conda \
  --plan
```

环境仍发布到当前仓库的 `runtime/envs/`。

- 网络中断：查看任务的 stdout/stderr，再以同一 component 重新运行；缓存会被复用。
- 许可未确认：精确确认缺失的 asset ID 后重新运行。
- 环境失败：失败 staging 会进入 `runtime/quarantine/`；不得自动删除。
- 磁盘不足：停止创建新任务，扩容或由用户对精确路径另行决定；EasyDesign 不清理数据。
- 仓库移动：Conda prefix 可能失效，应在新路径按 lock 新建环境；旧环境继续保留。

任何 setup 过程都不得调用递归删除、修改系统代理、修改 base Conda 或覆盖已有科学运行。
