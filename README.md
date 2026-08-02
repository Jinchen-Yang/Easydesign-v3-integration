# EasyDesign

EasyDesign 是一个面向多类 binder 的契约优先、可追溯七阶段设计平台。长期目标是让用户
提供 target 和少量明确的设计约束，即可通过一次配置、一个入口完成从结构准备、候选区域
发现、生成、复折叠、筛选到下单候选包的完整流程。

EasyDesign 的长期范围不局限于 VHH，计划通过可替换的 binder profile、生成后端和筛选
规则支持 VHH/nanobody、蛋白 binder、肽 binder 以及后续经过验证的其他分子类型。不同
binder 的科学约束不会被强行混成一种算法。

- 当前版本：`0.1.0-dev39`（包版本 `0.1.0.dev39`）
- 仓库基础架构：`implemented`
- 统一运行契约：`implemented`
- EasyDesign 1.0 整体状态：`planned`；各子能力状态见阶段 `STATUS.md`
- EasyDesign 1.0：先聚焦 VHH，跑通第一条真实、完整、可审计的参考主线
- 长期产品边界：多 binder 类型的一键式端到端设计平台
- 当前不承诺设计准确率；已提供 Developer Preview CLI 和 localhost 科研工作台，尚无
  公开 release

这里的“一键式”是指用户不需要手工拼接多个后端、搬运中间文件或猜测失败位置；关键科学
选择、失败状态和人工批准仍然显式保存，不能被“一键”隐藏。

## 五分钟开始

Linux 克隆后的标准入口只有仓库根部启动器。它从自身位置确定工作区，不依赖当前目录、
全局 `PATH`、`~/.config` 或用户级缓存。Protenix、PyMOL、ScanNet、BoltzGen 和 TNP
仍使用隔离环境，但环境、模型、缓存、状态和日志全部位于本仓库的 `runtime/`。

```bash
git clone git@github.com:Knitua/Easydesign.git
cd Easydesign

./easydesign setup --plan
./easydesign setup --component pymol-pse --detach
./easydesign setup --status
./easydesign doctor --full
./easydesign ui
```

`setup --plan` 不下载任何内容；完整 `setup` 在下载每个许可敏感资产前要求明确确认。
建议在开发机和空间受限服务器上按后端逐项安装，并在每一步后复核实际剩余空间：

```bash
./easydesign setup --component pymol-pse --plan
./easydesign setup --component pymol-pse --detach
./easydesign setup --component protenix-v2 --plan
./easydesign setup --component protenix-v2 --detach
./easydesign setup --component scannet-epitope --plan
./easydesign setup --component scannet-epitope --detach
./easydesign setup --component boltzgen --plan
./easydesign setup --component boltzgen --detach
./easydesign setup --component tnp --plan
./easydesign setup --component tnp --detach
```

每个组件计划只计算该后端环境、必需资产、当前未安装内容和最大单资产 staging 峰值，
不会把其他后端同时计入。`core-ui` 也可作为组件名，等价于 `--minimal`。不带
`--component` 的 `./easydesign setup` 仍表示完整安装。
七个 Linux 环境都从提交到 Git 的 `linux-64` Conda explicit lock 和精确 pip package
set 重建，不再在安装时重新解析宽范围依赖。环境 lock 改变会创建新目录，旧环境保持
不变。BoltzGen 的五个 checkpoint 与 molecule dataset 分别登记来源、大小、MIT 许可和
SHA-256；未确认的资产保持 `awaiting-approval`，后端不会被报告为可用。

远程服务器安装一律推荐 `--detach`。它会通过无 shell 的独立 worker 启动安装，并把
不可变 request、进程身份、终态 result 和 stdout/stderr 日志写在当前仓库
`runtime/state/setup-jobs/` 与 `runtime/logs/`。关闭 SSH、浏览器或 UI 不会关闭 worker；
重新登录后可读取同一任务：

```bash
./easydesign setup --status
./easydesign setup --status --job-id setup-YYYYMMDDTHHMMSSZ-XXXXXXXXXX
```

只有 `result.json` 显示 `succeeded`，且 `./easydesign env status`、资产状态和版本探针
均通过，后端才算可用。`incomplete` 通常表示仍待许可资产，`failed` 表示安装器捕获到
明确错误，`interrupted` 表示进程已不在且没有终态记录；以上状态都不会触发自动删除。
完整安装与故障恢复流程见 [环境安装手册](environments/README.md)。
安装器只把 `HOME`、`TMPDIR`、Conda/Pip/Corepack/Playwright 缓存等环境变量传给自己的
子进程；pip 子进程忽略系统/用户 pip 配置并禁止 user-site。不写 shell profile、系统
代理、Git 全局配置、base Conda 或 `/etc/environment`。父进程已有的代理变量只读继承
给子进程，EasyDesign 不清空、不创建也不持久化代理配置。如 Conda 不在 `PATH`：

```bash
./easydesign setup --conda /absolute/path/to/conda
```

长时间安装同时使用 `--detach`：

```bash
./easydesign setup --component boltzgen --conda /absolute/path/to/conda --detach
```

默认 package index 是官方 `https://pypi.org/simple`。如果当前服务器已实测官方 CDN
吞吐过低，可只为这一次安装显式选择可信 HTTPS 镜像；例如中国大陆服务器：

```bash
./easydesign setup --component boltzgen \
  --pip-index-url https://pypi.tuna.tsinghua.edu.cn/simple \
  --detach
```

EasyDesign 不会自动切换镜像，也不会把该值写进 pip 全局配置或代理；选择结果进入 setup
request 供审计。带用户名、密码、query 或 fragment 的 index URL 会被拒绝。

查看哪些资产仍待许可确认：

```bash
./easydesign assets status
./easydesign setup --accept-license ASSET_ID
```

`--accept-license` 只确认命令中精确列出的资产，不会一次性接受其他条款。

`./easydesign doctor` 只检查当前工作区、core 和本次配置实际需要的后端；
`./easydesign doctor --full` 要求五个科学后端及其必需资产全部达到当前 lock，并在任一
后端尚未安装、版本过期或资产缺失时返回非零退出码。工作区已经声明但尚未安装完整的
后端会显示“已声明但未完整可用”，不会再被误报成 profile 缺失或完整安装成功。

本机部署描述固定为仓库内 `runtime/profile.yaml` schema 0.2。它只保存环境/资产 ID
和相对路径；实际 executable 由带 SHA-256 的注册表解析。普通使用不再读取
`/root/.config/easydesign`、`~/.cache/easydesign`、`~/.local/share/easydesign`
或 `~/.local/state/easydesign`。旧部署必须显式导入，且原文件保持不变：

```bash
./easydesign workspace import-legacy \
  --profile /root/.config/easydesign/profile.yaml \
  --env-root /root/autodl-tmp/conda_envs
```

然后从真实 target 创建用户项目：

```bash
./easydesign init apoe --target apoe.fasta --stop-after 2 \
  --stage02-method both --execution-mode review-gated
# 也可从远程身份开始
easydesign init ubiquitin --pdb-id 1UBQ --chain A
easydesign init egfr --uniprot P00533 --scope-range 25:646
easydesign init egfr-search --uniprot-query EGFR --taxon-id 9606
# 复用已验证 A3M，或显式只读 sequence-hash cache
easydesign init apoe-offline --target apoe.fasta --precomputed-msa apoe.a3m
easydesign init apoe-cache --target apoe.fasta --msa-cache-mode offline
# 再导入已有 Bundle 时必须同时给来源 run，以便验证 ArtifactRef
easydesign init copied-target \
  --target-bundle /path/to/target-bundle.json \
  --source-run-root /path/to/source-run
./easydesign config validate apoe/easydesign.yaml
./easydesign doctor --config apoe/easydesign.yaml
./easydesign run apoe/easydesign.yaml
```

Stage 01 已实现本地 PDB/mmCIF、PDB ID、FASTA/裸序列、UniProt accession/名称、
单 Target PSE 和已有 Target Bundle 六类 source。FASTA/UniProt 会先用 RCSB 官方
Sequence Search/Data API 寻找满足严格 scope 门槛的实验结构；没有唯一合格结构时，
`review-gated` 停在选择门，`unattended` 按 YAML 明确转 required-MSA Protenix-v2。
PSE 直接导入坐标。六类入口和 remote/cache/precomputed 三种 required-MSA 路径均已达到
工程 `smoke-validated`；这不代表结构选择或预测准确率经过科学验证。Stage 02 可运行
独立 SASA/ScanNet 和用户区域。Stage 03 已实现基础 VHH 策略编译：每个批准区域与七个
官方 scaffold 组合、只写 positive binding，并由 BoltzGen 0.3.2 官方校验。Stage 04
Developer Preview 已提供严格候选收集、双 GPU 调度、原子进度与恢复；APOE 21×40 共
840 个完整候选已通过真实工程 smoke。Stage 05 的新 v1.6 规则只按 pilot 的 Tier A 与
`F_YAML` 晋级最多三组，100 条扩增及 full-target Protenix 作为诊断证据；零结构通过会
产生 warning，但不会撤销 Tier A 晋级。旧 APOE v1.5 仍不可变地保留
`stopped-no-scale-winner`：唯一 Tier A 扩展后有 12 个 local-gate pass，Top 10 的
binder pose 均不稳定。Stage 06 v0.2 已实现晋级策略共享全局预算、每策略分片恢复和
精确 coverage；一、二、三组分别分配 50,000、25,000/25,000、16,667/16,667/16,666。
Suzhou2 上的历史 APOE 单策略 50k 已在旧人工授权契约下完成，不会被伪装成 v1.6 原生
多策略运行。Stage 07 已支持旧/新 ScaleBundle、跨 YAML 全局竞争、Protenix 多 seed、
TNP required evidence 和确定性 20+20 审核包；APOE Stage 07 仍需先完成历史 50k
采用记录、远端后端探针与资源预检。

## 本地科研工作台

UI 与 CLI 调用同一套 Python API；科学事实仍来自 manifest，不保存第二份数据库。

```bash
./easydesign ui
```

浏览器打开 `http://127.0.0.1:8765`。远程服务器使用 SSH 端口转发：

```bash
ssh -L 8765:127.0.0.1:8765 USER@SERVER
```

若 runtime profile 声明了 SSH executor，新建设计可在“预算与资源”中选择运行位置。
命令行使用相同的远程 API：

```bash
easydesign remote list
easydesign remote probe suzhou2-a100x8

# 从 Stage 01 起提交完整项目
easydesign remote submit suzhou2-a100x8 \
  --job-id demo-remote-001 --run-id run-remote-001 \
  --config PROJECT/easydesign.yaml --project-root PROJECT

# 查看结构化进度，并把只读运行记录同步给本机/合作者 UI
easydesign remote watch suzhou2-a100x8 demo-remote-001
easydesign remote sync suzhou2-a100x8 demo-remote-001 \
  --to runs/PROJECT_ID/RUN_ID --mode metadata

# 仅当远端 worker 已停止时恢复未完成任务
easydesign remote resume suzhou2-a100x8 demo-remote-001
```

`metadata` 适合协作查看进度和正式报告；运行完成后可用 `complete` 拉取 manifest 声明的
完整候选闭包。两者都验证大小与 SHA-256，不同步模型权重、密钥或未声明目录。

默认界面使用中文并只保留“我的项目 / 新建设计 / 运行任务”三个主入口。工作台提供六入口
项目向导、标准 YAML、配置与环境检查、真实任务启动、人工确认、结构化进度、完成当前
任务后停止调度、恢复、只读回放和七阶段结果视图。内部运行编号、代码身份、hash 与原始
输出只进入单次运行的“技术记录”。

“新建设计”提供全流程设计、按步骤设计和开发者自检三条路线。全流程设计的七个 Stage
始终可浏览，只有检查与启动受完整性门槛约束；按步骤设计先完成 Stage 01 并进入结构页，
再通过新的 continuation run 配置下一步；开发者自检与普通科研项目隔离。选择本地 PSE、
PDB/mmCIF 或 FASTA 后，页面会立即显示“正在接收 / 文件已接收 / 接收失败”和文件大小、
SHA-256 摘要。

普通项目页只读取 `run-index.json` 中的 `project-run`。归档项目可以恢复，开发者自检只在
设置中显示。Stage 02 结构页可隐藏 PSE 来源颜色、清空本次编辑层，并用 A/B/C 三色重新
选择区域；保存永远创建新分支，不修改历史 Stage 02–07。

Stage 01/02 的统一结构工作区默认使用离线浏览器 PyMOL，并可平级切换到 Mol*。两种
查看器读取同一份经过 SHA-256 校验的 `target.cif`，共享当前残基、红/蓝/黄区域和
label/auth 编号。EasyDesign 平台结构助手按照 ChatPyMol 原生机制读取当前完整 PML、
结构 metadata、最近十轮对话和动态 PML Skills，并返回完整的新 PML 场景；PyMOL 执行
原生场景，Mol* 只显示可可靠投影的部分。用户明确写入 `ed_region_A/B/C` 的残基仍须
经过规范编号映射和人工批准；助手不能判断“最佳 hotspot”，这类请求只形成待确认的
SASA/ScanNet 执行计划。普通使用者无需选择模型或填写 API key；部署者在仓库内
`runtime/secrets/structure-assistant/platform-provider.yaml` 配置单一平台服务。平台
服务未启用时，结构查看、手工选区和自动算法仍可正常使用。

APOE 当前页面会把第5步标为“未达到继续条件”，并提供 840 个小规模候选、21 个策略、
100 个扩展候选和 10 个 Protenix 复核候选的分页分析；第6/7步同时显示“软件能力已实现 /
本次运行尚未开始”。没有真实 `FinalCandidatePackage` 时，湿实验候选草案按钮保持禁用。

### 查看仓库内 APOE 共享结果

`main` 包含一个经过完整性校验的 APOE 只读证据包。它保留 Stage 01–05 的运行记录、
Stage 04 双 GPU 历史、全部筛选指标，以及 12 个初筛候选和 10 个 Protenix 复核候选
所需结构；不包含约 970 MB 的 BoltzGen 后端中间目录。

```bash
python scripts/serve_ui_evidence_bundle.py examples/apoe-ui-demo --port 8765
```

脚本会先逐文件验证 SHA-256 和 Run/Stage manifest 闭包，再启动本地工作台。浏览器打开
`http://127.0.0.1:8765`。这个共享包用于结果审阅，不能替代完整 run 进行恢复执行或重新
计算。详细边界见 [`examples/apoe-ui-demo/README.md`](examples/apoe-ui-demo/README.md)。

新项目配置固定显示 `stage01`–`stage07`，未实现阶段写 `null`；`design` 保存 binder
profile 与用途。旧配置可显式迁移，原文件不会被覆盖：

```bash
easydesign config migrate old.yaml --output easydesign-0.7.yaml
```

默认 `review-gated` 会在 UniProt identity、chain/construct、实验结构和 hotspot 等科学
选择点暂停：

```bash
easydesign decisions show RUN_DIR
easydesign decisions export RUN_DIR --output decision.yaml
# 选择 option、填写 approved_by
easydesign decisions approve RUN_DIR --input decision.yaml
```

`approve` 校验 request revision/hash 后，在同一 run 创建新 attempt 并继续。需要完全
自动化时可在初始配置选择 `unattended`；自动科学选择只允许版本化硬规则，不调用 LLM，
不融合 Stage 02 方法，也不会执行真实下单。用户提供区域可以在初始 YAML 中由真实人员
预先签署，使 pipeline 连续运行，但仍记录 human authority、理由和 acknowledgement。
`init --stop-after 2` 在 review-gated 中默认同时
写入 SASA/ScanNet，在 unattended 中默认只写 SASA；可用 `--stage02-method` 显式修改。

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

已结束的 Stage 02 run 可显式继续到 Stage 03，原 run 不会被改写：

```bash
easydesign doctor --config downstream/easydesign.yaml
easydesign run downstream/easydesign.yaml \
  --from-run /absolute/path/to/succeeded-stage02-run \
  --run-id downstream-stage03
```

Stage 03 输出 `StrategyBundle`、design matrix 和每个 region×scaffold 的
`design.yaml`。当前基础模板不做 crop/CDR 优化，非 hotspot residue 保持中性。

继续运行 Stage 04 时，新配置将 `stop_after_stage` 设为 4，并从已成功 Stage 03 run
创建不可变 continuation：

```bash
easydesign run downstream/easydesign.yaml \
  --from-run /absolute/path/to/succeeded-stage03-run \
  --run-id downstream-stage04

# 另一个终端只读进度
easydesign runs watch /absolute/path/to/downstream-stage04

# 进程中断或任务未达标时，仅恢复缺口
easydesign runs resume /absolute/path/to/downstream-stage04
```

Stage 04 的 40 指每个策略 40 个“metric row + 原始 complex CIF + refold CIF”完整候选，
不是 40 次启动，也不是 BoltzGen 最终 `budget=30` 目录中的数量。

当配置执行到 Stage 05 时，同一命令会继续做 v1.6 pilot 筛选。只晋级 Tier A，最多三组；
没有 Tier A 会形成可审计科学停止。每个晋级策略的 100 条扩增和 full-target 复核必须
完整运行；科学负结果形成 warning，后端、文件或校验错误仍是必须恢复的运行失败：

```bash
easydesign run downstream/easydesign.yaml \
  --from-run /absolute/path/to/succeeded-stage04-run \
  --run-id downstream-stage05

easydesign runs watch /absolute/path/to/downstream-stage05
easydesign runs resume /absolute/path/to/downstream-stage05
```

Stage 05 的 target 使用 required MSA，binder 使用 query-only；不得无 MSA 静默降级。
筛选分数只用于结构工程排序，不表示实验亲和力或成功概率。

Stage 06 将一至三个晋级策略共享的全局预算精确完成后，Stage 07 使用同一个统一入口
做全局竞争；不会给不同 YAML 预留候选名额，但会保留完整来源：

```bash
easydesign run downstream/easydesign.yaml \
  --from-run /absolute/path/to/succeeded-stage06-run \
  --run-id downstream-stage07

easydesign runs watch /absolute/path/to/downstream-stage07
easydesign runs resume /absolute/path/to/downstream-stage07
```

Stage 07 的非空结果最多包含 20 个 primary 和 20 个 backup；不足时不补齐。候选包始终
等待人工审阅且未下单，1000-candidate 路径只能称为 `smoke-review-package`。

### 提交到另一台计算服务器

控制端 runtime profile 可以显式登记 SSH executor。EasyDesign 不扫描 SSH config，也不
复制控制端私钥；`identity_file`、known-hosts、远端工作目录、远端 EasyDesign 和远端
profile 都必须给绝对路径。科学 YAML 不保存主机地址或密钥。

```yaml
remote_executors:
  suzhou2-a100x8:
    host: 192.0.2.10
    user: root
    port: 22
    identity_file: /absolute/path/to/dedicated_ed25519
    known_hosts_file: /absolute/path/to/known_hosts
    ssh_executable: /usr/bin/ssh
    rsync_executable: /usr/bin/rsync
    remote_work_root: /data/easydesign
    remote_runs_root: /data/easydesign/runs
    remote_easydesign_executable: /data/easydesign/bin/easydesign
    remote_profile: /data/easydesign/profile.yaml
```

先做只读探针，再提交一个 checksum 验证通过的终态上游 run：

```bash
easydesign remote probe suzhou2-a100x8
easydesign remote submit suzhou2-a100x8 \
  --job-id target-scale-50k \
  --run-id stage06-50k \
  --config easydesign.yaml \
  --from-run /absolute/path/to/succeeded-stage05-run
easydesign remote status suzhou2-a100x8 target-scale-50k
```

控制端先校验配置、代码版本和上游 manifest，再用 rsync 复制完整 continuation 输入；
远端通过 systemd transient worker 独立执行并维护自己的 RunManifest、分片状态和事件。
SSH 连接中断不会终止任务。远端仍使用 `local-multi-gpu` 执行器，因此 GPU 列表写在
`stage04.executor.devices`，SSH 只负责跨主机提交，不复制 Stage 04/06 科学逻辑。
Continuation 的 preflight 只探测尚未完成阶段需要的 backend；例如从成功 Stage 05
继续 Stage 06 时，远端只要求 BoltzGen，不要求重新安装或探测 PyMOL/Protenix。

PSE 项目默认使用 `stage02.mode: detect`：若 Target Bundle 中存在固定
红 `A`、蓝 `B`、黄 `C`，则把这些颜色作为用户区域；没有标准色才运行 YAML 中的
SASA/ScanNet fallback。普通结构或序列可以在初始 YAML 用
`user-provided/residue-list` 指定 `sequence`、`label`、`auth` 或 `uniprot` 编号。
用户区域导出审批时不传 `--method`：

```bash
easydesign hotspots export RUN_DIR --output hotspots-review.yaml
```

`stage01.target.identity.uniprot_accession` 可以为空。Stage 02 的 UniProt annotation 支持
`off/if_available/required`；没有 accession 时 `if_available` 不发网络请求，结构方法仍
可运行，但审批必须确认 `structural_only` 的证据边界。Annotation 不改变 SASA/ScanNet
原始排名。

查看已有 run：

```bash
easydesign runs list
easydesign runs show PROJECT_ID/RUN_ID
easydesign runs watch /absolute/path/to/running-stage04
easydesign runs resume /absolute/path/to/interrupted-stage04
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
