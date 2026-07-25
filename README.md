# EasyDesign

EasyDesign 是一个面向多类 binder 的契约优先、可追溯七阶段设计平台。长期目标是让用户
提供 target 和少量明确的设计约束，即可通过一次配置、一个入口完成从结构准备、候选区域
发现、生成、复折叠、筛选到下单候选包的完整流程。

EasyDesign 的长期范围不局限于 VHH，计划通过可替换的 binder profile、生成后端和筛选
规则支持 VHH/nanobody、蛋白 binder、肽 binder 以及后续经过验证的其他分子类型。不同
binder 的科学约束不会被强行混成一种算法。

- 当前版本：`0.1.0-dev2`（包版本 `0.1.0.dev2`）
- 仓库基础架构：`implemented`
- 统一运行契约：`implemented`
- EasyDesign 1.0 整体状态：`planned`；各子能力状态见阶段 `STATUS.md`
- EasyDesign 1.0：先聚焦 VHH，跑通第一条真实、完整、可审计的参考主线
- 长期产品边界：多 binder 类型的一键式端到端设计平台
- 当前不承诺设计准确率；已提供 Developer Preview CLI，尚无正式 UI 或公开 release

这里的“一键式”是指用户不需要手工拼接多个后端、搬运中间文件或猜测失败位置；关键科学
选择、失败状态和人工批准仍然显式保存，不能被“一键”隐藏。

## 五分钟开始

EasyDesign core 可以使用 Conda，也可以安装到已有的 Python 3.11 环境。Protenix、PyMOL
和 ScanNet 等重型工具仍保持独立环境，不会被 `pip install easydesign` 混装。

```bash
git clone git@github.com:Knitua/Easydesign.git
cd Easydesign

# 开发安装
python -m pip install -e ".[dev]"

# 或从本地 wheel 安装
python -m build
python -m pip install dist/easydesign-0.1.0.dev2-py3-none-any.whl
```

先创建用户级本机 profile：

```bash
easydesign profile init
easydesign profile show
```

`profile init` 不扫描 Conda 或模型目录。使用者需要显式填写本机绝对路径，例如：

```yaml
schema_version: "0.1"
profile_id: local
runs_root: /absolute/path/to/runs
backends:
  protenix_v2:
    executable: /absolute/path/to/protenix
    model_root: /absolute/path/to/protenix-model-root
    model_checkpoint: /absolute/path/to/protenix-v2.pt
    cuda_visible_devices: "0"
  pymol_pse:
    python: /absolute/path/to/pymol-pse/bin/python
  scannet_epitope:
    python: /absolute/path/to/scannet/bin/python
    repository_root: /absolute/path/to/ScanNet
    execution_device: cpu
```

然后从真实 target 创建用户项目：

```bash
easydesign init apoe --target apoe.fasta --stop-after 2 \
  --stage02-method both
easydesign config validate apoe/easydesign.yaml
easydesign doctor --config apoe/easydesign.yaml
easydesign run apoe/easydesign.yaml
```

`init` 当前接受 FASTA、裸序列文件和单 Target PSE。sequence/FASTA 默认使用 required
remote MSA、ColabFold public、无模板 Protenix-v2；PSE 直接导入坐标。Stage 02 默认运行
彼此独立的 SASA 与 ScanNet CPU 选区，也可在初始 YAML 中选择只运行其中一种。
PDB/mmCIF、Stage 01 UniProt source 和 Stage 03–07 尚未接入该命令时会明确失败，不会
静默回退。

新项目配置固定显示 `stage01`–`stage07`，未实现阶段写 `null`；`design` 保存 binder
profile 与用途。旧配置可显式迁移，原文件不会被覆盖：

```bash
easydesign config migrate old.yaml --output easydesign-0.3.yaml
```

Stage 02 自动计算结束后会停在 `awaiting-human-approval`，不会伪装成整个 run 已完成。
从同一种方法选择 2–3 个完整区域并补充理由后，才发布 Stage 03 可用的
`hotspots.yaml`：

```bash
easydesign hotspots export RUN_DIR \
  --method sasa \
  --output hotspots-review.yaml
# 编辑 approved_by、design_goal、两类 rationale；structural-only 还需确认限制
easydesign hotspots approve RUN_DIR --input hotspots-review.yaml
```

`stage01.target.identity.uniprot_accession` 可以为空。Stage 02 的 UniProt annotation 支持
`off/if_available/required`；没有 accession 时 `if_available` 不发网络请求，结构方法仍
可运行，但审批必须确认 `structural_only` 的证据边界。Annotation 不改变 SASA/ScanNet
原始排名。

查看已有 run：

```bash
easydesign runs list
easydesign runs show PROJECT_ID/RUN_ID
easydesign viewer serve /absolute/path/to/run --port 8000
```

## 七个阶段

| 阶段 | 目标 |
| --- | --- |
| [`01-target-preparation`](workflow/01-target-preparation/README.md) | 将六类输入统一为标准 Target Bundle。 |
| [`02-hotspot-discovery`](workflow/02-hotspot-discovery/README.md) | 生成带证据的候选表面区域和 avoid 区域。 |
| [`03-boltzgen-configuration`](workflow/03-boltzgen-configuration/README.md) | 生成并校验 binder 设计策略；1.0 首先实现 VHH BoltzGen YAML。 |
| [`04-pilot-generation`](workflow/04-pilot-generation/README.md) | 运行可完整追溯的小批量 BoltzGen pilot。 |
| [`05-pilot-filtering`](workflow/05-pilot-filtering/README.md) | 使用体系专属、版本化规则筛选 pilot。 |
| [`06-scale-generation-and-refolding`](workflow/06-scale-generation-and-refolding/README.md) | 放大策略并调用可替换结构预测后端。 |
| [`07-final-filtering-and-selection`](workflow/07-final-filtering-and-selection/README.md) | 终筛、去冗余并生成供人工批准的 Top N。 |

## 从哪里开始

- 项目目标和开发铁律：[`PROJECT_CHARTER.md`](PROJECT_CHARTER.md)
- 宏观路线图：[`TODO.md`](TODO.md)
- 当前任务和历史：[`TODO_NOW.md`](TODO_NOW.md)
- 阶段交接规则：[`workflow/README.md`](workflow/README.md)
- 仓库和运行架构：[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- 旧仓审计基线：[`docs/legacy/BASELINE.md`](docs/legacy/BASELINE.md)

## 开发环境与检查

全部环境先使用 Conda 管理。EasyDesign 主环境是 Python 3.11 的 `easydesign-core`；
BoltzGen、Boltz2、Protenix-v2、AF3/AFO 等重型工具保持各自独立环境，通过 adapter 调用。

在仓库开发 Conda 环境中：

```bash
conda env create -f environment.yml
conda activate easydesign-core
make check
make test
make build
```

Protenix-v2 使用独立的 [`environments/protenix-v2.yml`](environments/protenix-v2.yml)，
不安装进 `easydesign-core`。模型参数和公共缓存位于 `models/`，不进入 Git。

Stage 01 成功 run 会自动生成自包含 Mol* Target Viewer，但不会自动启动常驻服务。查看
最新报告：

```bash
easydesign viewer serve runs/apoe/20260724-006-stage01-msa --port 8000
```

服务只绑定 `127.0.0.1`；远程服务器按照脚本提示使用 SSH 端口转发。页面直接展示 mmCIF、
label/auth residue mapping、整体质量和安全来源信息；PSE 原始颜色可以切换，但始终标记为
未解释 annotation。Viewer 是只读报告，不保存 hotspot，也不替代科学验证。

Proteindigger1 使用 `/root/miniconda3/bin/conda`，环境实际存放在
`/root/autodl-tmp/conda_envs/`；该站点路径只用于部署，不进入核心代码。

当前仓库保持私有，远程托管于
[`Knitua/Easydesign`](https://github.com/Knitua/Easydesign)；没有公开许可证、正式
PyPI release 或 UI。Developer Preview CLI 不是稳定公开 API 承诺。
