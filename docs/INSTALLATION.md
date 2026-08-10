# EasyDesign Local 全新机器安装

本文只描述全新 Linux x86-64 GPU 主机。不复用其他 EasyDesign clone、旧 Conda 环境或共享
runtime。所有环境、模型、cache、日志和任务状态都写入当前 clone 的 `runtime/`。

## 1. Clone 并安装主环境

```bash
git clone -b easydesign-local git@github.com:Knitua/Easydesign.git
cd Easydesign

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

./scripts/bootstrap.py --index auto
source .venv/bin/activate
easydesign --version
```

`--index auto` 会探测官方 PyPI、阿里云和清华 TUNA。需要固定来源时使用
`official`、`aliyun` 或 `tsinghua`，例如：

```bash
./scripts/bootstrap.py --index aliyun
```

安装中断后直接重跑同一条命令。bootstrap 不修改系统 Python、依赖 lock 或 shell profile；
每次真实尝试的来源、Git/lock 身份和结果记录在 `runtime/state/bootstrap/`。

## 2. 安装本仓库固定的 Miniforge

```bash
mkdir -p runtime/tmp runtime/tools
curl -fL \
  https://github.com/conda-forge/miniforge/releases/download/26.3.2-2/Miniforge3-26.3.2-2-Linux-x86_64.sh \
  -o runtime/tmp/Miniforge3-26.3.2-2-Linux-x86_64.sh
printf '%s  %s\n' \
  42260ffe3830fb953d5eee1bbb32229ff06aa7c3833c1ed7a9a0420a95685d94 \
  runtime/tmp/Miniforge3-26.3.2-2-Linux-x86_64.sh \
  | sha256sum -c -
bash runtime/tmp/Miniforge3-26.3.2-2-Linux-x86_64.sh \
  -b -p "$PWD/runtime/tools/miniforge3"
runtime/tools/miniforge3/bin/conda --version
```

这套 Miniforge 只属于当前 clone，不修改系统 Conda 或 shell profile。

## 3. 依次安装科学组件

安装顺序固定为：

```text
pymol-pse → boltzgen → protenix-v2 → scannet-epitope → tnp
```

每次先查看计划，再安装一个组件：

```bash
easydesign runtime plan pymol-pse
easydesign runtime install pymol-pse \
  --conda "$PWD/runtime/tools/miniforge3/bin/conda" --detach
```

安装命令会输出 `SETUP_JOB_ID`。复制它给出的观察命令，或运行：

```bash
easydesign runtime jobs --job-id SETUP_JOB_ID --watch
```

完成后把 `pymol-pse` 依次替换为其余四个组件。遇到许可确认时，阅读提示并按命令要求显式
提供 `--accept-license`；不要跳过许可或伪造确认。`Ctrl-C` 只退出观察，后台安装继续。

## 4. 验收

五个组件全部完成后运行：

```bash
easydesign runtime status
easydesign doctor --full
```

只有 `doctor --full` 通过后，才把这台机器视为完整可用的 EasyDesign Local 主机。

## OpenFold3/AFO（可选灰度后端）

OpenFold3/AFO 当前不属于默认新机安装。只有持有经过校验的离线 bundle 时才执行：

```bash
easydesign runtime install openfold3 --bundle runtime/imports/openfold3-bundle
easydesign doctor --full
```

安装成功不会自动替换默认 Protenix。资产要求和验证边界见
[OpenFold3 后端](OPENFOLD3_BACKEND.md)。
