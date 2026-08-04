# EasyDesign

[中文](README.md) · [English](README.en.md)

EasyDesign 是一个以契约、证据和可恢复执行为核心的蛋白结合分子七阶段设计工作台。

当前版本：`0.1.0.dev46`。本仓库仍是 Developer Preview：不发布 PyPI，不附加新的
开源许可证，并保留 `Private :: Do Not Upload` 分类。请先完成知识产权、许可证和数据
权限审查，再将它用于仓库授权范围之外的环境。

## 七阶段工作流

```text
01 目标结构 → 02 结合区域 → 03 设计方案 → 04 小规模生成
                                          ↓
07 最终候选 ← 06 规模化 ← 05 筛选验证
```

- 第 01–03 步冻结目标、用户设计输入和可执行方案。
- 第 04→05 步作为连续任务完成小规模生成与筛选。
- 第 06→07 步作为连续任务完成用户指定规模的放大与最终筛选。
- 用户始终明确选择“当前机器”或已授权的 Suzhou2 公共算力；二者不是自动 fallback。
- 科学停止、运行失败和人工确认是不同状态，历史 manifest 和 artifact 不会被回写。

## 五分钟安装 core、CLI 和 UI

前提：Git、[uv](https://docs.astral.sh/uv/)、Python 3.11 或 3.12。推荐 Python 3.11。

```bash
git clone https://github.com/Knitua/Easydesign.git
cd Easydesign

uv sync --frozen --extra ui
source .venv/bin/activate

easydesign --version
```

`uv sync` 会创建 `.venv`，并以 editable 方式安装当前源码。`uv.lock` 固定精确版本、来源
和平台条件；`--frozen` 禁止安装时重新求解或修改 lock。激活 `.venv` 后，所有产品命令
都直接以 `easydesign` 开头。

每次新开终端只需：

```bash
cd Easydesign
source .venv/bin/activate
```

开发者安装额外检查工具：

```bash
uv sync --frozen --extra ui --extra dev
source .venv/bin/activate
easydesign --version
```

不希望激活环境时，可以用 `uv run easydesign ...`；CI 和自动化也采用这种形式。普通用户
主流程保持 `easydesign ...`。

<details>
<summary>没有 uv 时的 pip 兼容入口</summary>

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[ui,dev]"
```

该路径不严格消费 `uv.lock`，因此不能提供与 `uv sync --frozen` 相同的依赖复现保证。

</details>

到这里仅完成 core、CLI 和 UI。界面可以打开并浏览已有证据，但这不代表五个科学后端、
模型或本机 GPU 已经可运行。

## 安装五个独立科学环境

完整本机七阶段计算需要 Linux、NVIDIA GPU 和可用的 Conda：

```bash
conda --version
nvidia-smi
```

PyMOL、BoltzGen、Protenix-v2、ScanNet 和 TNP 不进入 `.venv`。EasyDesign 按仓库内精确
Conda lock 分别发布到 `runtime/envs/`，模型和缓存分别进入 `runtime/models/` 与
`runtime/cache/`；它不会修改 base Conda、shell profile、系统代理或全局 pip 配置。

必须逐个组件安装。每项先查看计划和待授权资产，再启动后台任务；当前组件达到终态后
才能开始下一项。

### 1. PyMOL/PSE

```bash
easydesign setup --component pymol-pse --plan
easydesign setup --component pymol-pse --detach
easydesign setup --status
```

### 2. BoltzGen

```bash
easydesign setup --component boltzgen --plan
easydesign setup --component boltzgen --detach
easydesign setup --status
```

### 3. Protenix-v2

```bash
easydesign setup --component protenix-v2 --plan
easydesign setup --component protenix-v2 --detach
easydesign setup --status
```

### 4. ScanNet

```bash
easydesign setup --component scannet-epitope --plan
easydesign setup --component scannet-epitope --detach
easydesign setup --status
```

### 5. TNP

```bash
easydesign setup --component tnp --plan
easydesign setup --component tnp --detach
easydesign setup --status
```

不要同时启动这些大型安装，也不要使用无 `--component` 的全量 setup：core/UI 已由 uv
管理，第二个 core Conda 环境没有必要。

### 精确批准资产许可

每次以真实输出为准，不要复制历史资产 ID：

```bash
easydesign assets status
easydesign setup --component COMPONENT --plan

easydesign setup --component COMPONENT \
  --accept-license ASSET_ID_1 \
  --accept-license ASSET_ID_2 \
  --detach
```

`--accept-license` 可以重复，但没有“一次接受所有许可”的命令。未批准资产保持
`awaiting-approval`，不能被报告为后端可用。

### 等待终态并验收

```bash
easydesign setup --status
easydesign setup --status --job-id JOB_ID
easydesign env status
easydesign assets status
```

只有任务 `result.json` 为 `succeeded` 才完成该组件。`incomplete`、`failed` 和
`interrupted` 都不是成功，也不会触发自动清理。五项全部完成后：

```bash
easydesign env status
easydesign assets status
easydesign doctor --full
```

只有 `doctor --full` 成功，才代表完整本机科学工作台已就绪。安装原理、磁盘峰值、镜像、
缓存和安全恢复见 [环境安装手册](environments/README.md)。

平台边界：

- Linux + NVIDIA：完整本机七阶段科学执行。
- macOS：core、UI、证据浏览与远程客户端能力。
- Windows：本轮不承诺原生运行，推荐 WSL2。
- 无本地 GPU：可以连接获授权且已经部署 Manager 的 Suzhou2。

## 可选：配置 Suzhou2 仓库专用 SSH 密钥

只有获得 Suzhou2 权限的用户才需要本节。先读取指纹，再通过管理员或另一可信渠道独立
核对；不能仅凭首次网络连接自动信任。

```bash
easydesign remote pair-scan \
  --host SUZHOU2_HOST \
  --port 22
```

创建或复用当前仓库专用 Ed25519 密钥：

```bash
easydesign remote pair-begin suzhou2 \
  --controller-id MY_CONTROLLER \
  --host SUZHOU2_HOST \
  --port 22 \
  --user root \
  --confirm-fingerprint SHA256:VERIFIED_FINGERPRINT
```

密钥位于 `runtime/secrets/ssh/suzhou2/`。完整密钥对会被复用；只剩一半时命令会停止，
不会覆盖重建。私钥权限保持 `0600`，密钥和 known-host 不进入 Git 或科学配置。

用 OpenSSH 交互输入一次远端密码并幂等安装公钥：

```bash
ssh-copy-id \
  -i runtime/secrets/ssh/suzhou2/id_ed25519.pub \
  -o UserKnownHostsFile=runtime/secrets/ssh/suzhou2/known_hosts \
  -o StrictHostKeyChecking=yes \
  -o IdentitiesOnly=yes \
  -p 22 root@SUZHOU2_HOST
```

密码只由 OpenSSH 读取，不进入 EasyDesign 参数、环境变量、浏览器、日志或磁盘。然后确认
Manager、协议、精确 EasyDesign 版本、连续链和资源状态：

```bash
easydesign remote pair-confirm suzhou2
```

逻辑解绑：

```bash
easydesign remote unpair suzhou2 --confirmed
```

解绑只追加 registry revision，不删除本地密钥、known-host、远端公钥或历史证据。

## 启动 UI

```bash
easydesign ui serve \
  --host 127.0.0.1 \
  --port 18769
```

浏览器打开 `http://127.0.0.1:18769`：

- `doctor --full` 通过：可选择当前机器执行完整科学流程。
- `pair-confirm` 通过：可主动选择 Suzhou2 公共算力。
- 只完成 uv core：仅适合浏览证据或前端开发。

UI 不用启动门伪装环境就绪；真实任务仍在提交前执行结构化 GPU、磁盘、环境、模型和许可
preflight。

## 当前证据与边界

- Stage 01–07 工程链、APOE PSE 区域导入和真实小规模/远程 smoke 均有不可变证据。
- 当前筛选阈值和 APOE 历史结论不会因 UI 或安装方式变化而改写。
- 结果用于研究决策支持，不等于实验验证、临床结论、生物安全批准或供应商订单。
- 外部模型、数据库、权重和服务继续受各自许可证、条款与数据政策约束。
- 公开许可证、PyPI 和正式多用户安全边界仍待独立决策。

动态进展见 [TODO_NOW.md](TODO_NOW.md)，完整任务见 [TODO.md](TODO.md)，科学案例见
[Case Registry](docs/validation/CASE_REGISTRY.md)。

## 文档索引

- [环境安装与恢复](environments/README.md)
- [开发、测试与 uv lock](DEVELOPMENT.md)
- [架构与跨仓同步](docs/ARCHITECTURE.md)
- [七阶段命令与契约](workflow/README.md)
- [UI 工作台](docs/product/UI_WORKBENCH.md)
- [数据安全](DATA_SAFETY.md)
- [项目章程](PROJECT_CHARTER.md)
