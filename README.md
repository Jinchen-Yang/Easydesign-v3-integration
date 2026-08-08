# EasyDesign Local

[English](docs/README.en.md) · [开发指南](DEVELOPMENT.md) · [数据安全](DATA_SAFETY.md)

EasyDesign Local 是一个 Agent 原生的本地蛋白设计研究工作台：Codex 理解问题、讨论策略
并调用工具，研究者批准关键科学选择，EasyDesign 负责确定性执行、manifest、checksum
和不可变证据。公开流程只有：

```text
prepare → strategize → pilot loop → scale → select
```

内部仍保留经过验证的七阶段科学实现，但研究者不再直接操作 Stage 编号。本产品没有完整
Workbench、远程提交、Suzhou2、Manager 或 18769 activation。

## 安装

```bash
cd /root/autodl-tmp/Protein_design/easydesign-local
uv sync --frozen --extra dev
source .venv/bin/activate
easydesign --version
```

`.venv` 不复制重型科学环境和模型。首次使用只读链接已验证 runtime：

```bash
easydesign runtime link /root/autodl-tmp/Protein_design/easydesign-clean/runtime
easydesign runtime status
easydesign doctor --full
```

来源 registry、inventory 或资产身份变化后会 fail closed，必须重新 link；cache、日志、job
和科学结果仍只写本 worktree。

OpenFold3/AFO 正在灰度接入，Protenix 仍是默认结构预测后端。只有持有经过校验的离线
bundle 时才安装；安装会创建本地不可变 Python 3.12/JAX 环境并执行真实 GPU smoke：

```bash
easydesign runtime install openfold3 --bundle /absolute/path/to/bundle
easydesign runtime status
easydesign doctor --full
```

安装成功也不会自动切换默认后端。固定科学面板、人工批准和单独的默认切换 commit 全部
完成前，AFO 只能显式选择，Protenix 继续作为默认及显式 fallback。资产身份、硬件边界和
灰度验收说明见 [OpenFold3 后端](docs/OPENFOLD3_BACKEND.md)。

## 用 Codex 开始研究

从本仓库或其子目录启动 Codex。根 `AGENTS.md` 会把蛋白设计任务路由到仓库级
`$easydesign-research` Skill；研究任务不会加载开发协议。可以直接说：

```text
为 P02649 新建一个 EasyDesign 项目，先准备靶点；遇到歧义停下来和我讨论。
```

```text
恢复 workspace/projects/apoe，查看目前证据，和我讨论下一轮 pilot 策略，不要自动批准。
```

```text
检查这个已染色 PSE 的 A/B/C 位点，启动只读 Viewer；我确认前不要 freeze strategy。
```

Codex 每次恢复项目只需读取：

```bash
easydesign project status workspace/projects/apoe --json
```

该结果包含当前 target/site foundation、strategy revisions、pilot/production runs、待批准项
和结构化下一步；不要扫描目录猜状态。

## 语义化命令

创建项目支持 PSE、本地结构、本地序列、PDB ID、UniProt accession/query 和经过验证的
target bundle：

```bash
easydesign project init workspace/projects/apoe --uniprot P02649
easydesign target prepare workspace/projects/apoe
```

位点入口按证据选择，最终都汇合为不可变 `target-and-site-ready` foundation：

```bash
easydesign site propose workspace/projects/apoe --from-pse-colors
easydesign site propose workspace/projects/apoe --input workspace/projects/apoe/SITE.yaml
easydesign site scan workspace/projects/apoe --method both
easydesign view workspace/projects/apoe --run RUN_ID --port 8000
easydesign site approve workspace/projects/apoe --input PROPOSAL --confirm
```

SASA 与 ScanNet 独立保存，不融合分数；A/B/C 在只读 Viewer 中固定为红/蓝/黄。

策略由研究者和 Codex 讨论后起草，校验不发布，显式批准才 freeze：

```bash
easydesign strategy draft workspace/projects/apoe
easydesign strategy validate workspace/projects/apoe --config workspace/projects/apoe/strategy-draft.yaml
easydesign strategy freeze workspace/projects/apoe --config workspace/projects/apoe/strategy-draft.yaml --confirm
```

策略支持 target crop、approved binding subset、七 scaffold 或子集、CDR range/插入长度、
显式多 variant，以及带 SHA-256 和真实 backend check 的专家 BoltzGen YAML。

每轮 pilot 是独立不可变 run；科学负结果仍是有效证据：

```bash
easydesign pilot plan workspace/projects/apoe --strategy strategy-r000001
easydesign pilot run workspace/projects/apoe --strategy strategy-r000001 --confirm --detach
easydesign pilot review workspace/projects/apoe --run PILOT_RUN
easydesign pilot promote workspace/projects/apoe --run PILOT_RUN --strategy ID1,ID2 --confirm
```

规模化和选择默认 50,000 / Top 200；不足 200 时不重复、不补齐：

```bash
easydesign scale plan workspace/projects/apoe --selection SELECTION
easydesign scale run workspace/projects/apoe --selection SELECTION --count 50000 --confirm --detach
easydesign select plan workspace/projects/apoe --run PRODUCTION_RUN --top 200
easydesign select run workspace/projects/apoe --run PRODUCTION_RUN --top 200 --confirm --detach
```

任务控制统一为 `easydesign job status|watch|resume|drain`。`Ctrl-C` 只脱离观察，`drain`
只在安全检查点停止新调度。所有命令支持 `--json`，文本和 JSON 来自同一 `CommandResult`。

## 数据位置与批准边界

- `workspace/projects/`：输入、可变 draft、不可变 site/strategy/promotion receipt；
- `workspace/runs/`：不可变科学 run、manifest、attempt 和 artifact；
- `runtime/`：本产品 receipt、profile、cache、日志、job、validation 和 quarantine；
- `examples/apoe-ui-demo/`：Git 跟踪、checksum 不变的只读科学证据。

读取、校验、染色、扫描、规划、review 和 Viewer 可直接执行。`site approve`、
`strategy freeze`、`pilot run/promote`、`scale run` 和 `select run` 必须由研究者显式确认。
旧七 YAML 项目只读识别，不原地迁移。

结果用于研究决策支持，不等于实验验证、临床结论、生物安全批准或供应商订单。本分支为
私有 Developer Preview，不发布 PyPI。
