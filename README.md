# EasyDesign Local

[English](docs/README.en.md) · [开发指南](DEVELOPMENT.md) · [数据安全](DATA_SAFETY.md)

EasyDesign Local 是面向研究者的 VS Code/终端产品：在一台本地 Linux GPU 机器上，按
Stage 1–7 逐步运行蛋白结合分子设计，并用只读 Mol* Viewer 检查结构和结合区域。

它不包含完整 Workbench、HTTP API、远程提交、Suzhou2 或 Manager，也不会操作正式 UI
端口 18769。科学 manifest、artifact、attempt、decision 和 checksum 契约与主产品一致。

## 安装

需要 Git、[uv](https://docs.astral.sh/uv/) 和 Python 3.11（也支持 3.12）。

```bash
cd /root/autodl-tmp/Protein_design/easydesign-local
uv sync --frozen --extra dev
source .venv/bin/activate
easydesign --version
```

`.venv` 只安装 EasyDesign Local、CLI 和开发工具。五个重型科学后端及模型不复制、不重装，
而是只读链接已经验证的原 runtime：

```bash
easydesign runtime link /root/autodl-tmp/Protein_design/easydesign-clean/runtime
easydesign runtime status
easydesign doctor --full
```

link 会验证 registry revision、环境 lock/inventory、资产大小和 SHA-256/Git revision，并在
本仓库写独立 receipt/profile。来源 identity 改变后命令 fail closed，必须重新 link。

## 初始化项目

以下六类 Stage 1 输入都进入同一个严格接口：

```bash
easydesign step init workspace/projects/apoe --uniprot P02649
easydesign step init workspace/projects/apoe-search --uniprot-query APOE --taxon-id 9606
easydesign step init workspace/projects/pdb-case --pdb-id 1B68 --chain A
easydesign step init workspace/projects/pse-case --target inputs/target.pse
easydesign step init workspace/projects/structure-case --target inputs/target.cif --chain A
easydesign step init workspace/projects/sequence-case --target inputs/target.fasta
```

也支持经过 manifest/checksum 验证的 `--target-bundle`。项目根目录平铺生成七份 Stage YAML、
`inputs/`、append-only `config-revisions/` 和 `CONFIG_CURRENT`。

## 逐阶段运行

```bash
easydesign step validate 1 workspace/projects/apoe
easydesign step run 1 workspace/projects/apoe
```

每个命令都返回结构化状态，并打印下一步的精确命令。完成 Stage 1 后可在另一个 VS Code
终端启动只读 Viewer：

```bash
easydesign step view workspace/projects/apoe --run RUN_ID --port 8000
```

浏览器访问 `http://127.0.0.1:8000/`。Viewer 不会自动启动、后台常驻、打开浏览器、编辑或
批准任何科学输入。

Stage 2 默认分别运行 SASA 与 ScanNet，不融合结果：

```bash
easydesign step run 2 workspace/projects/apoe
```

Viewer 可在两种方法间只读切换，A/B/C 固定为红/蓝/黄。自动和手动区域都必须显式批准：

```bash
easydesign step template 2 workspace/projects/apoe --manual
easydesign step validate 2 workspace/projects/apoe \
  --config workspace/projects/apoe/02-hotspot-discovery.manual.yaml
easydesign step approve 2 workspace/projects/apoe \
  --input workspace/projects/apoe/02-approval.sasa.RUN_ID.yaml
```

Stage 3–7 同样按下一 Stage 顺序运行。Stage 4–7 使用规范科学预算；没有 `--confirm` 时只
显示候选/任务、GPU、磁盘和 backend 计划，不创建 worker、Stage 或 attempt：

```bash
easydesign step run 6 workspace/projects/apoe --confirm --detach
easydesign step status workspace/projects/apoe --run RUN_ID
easydesign step watch workspace/projects/apoe --run RUN_ID
easydesign step drain workspace/projects/apoe --job JOB_ID
easydesign step resume workspace/projects/apoe --run RUN_ID --detach
```

`Ctrl-C` 只结束当前观察，不杀科学 worker。`drain` 只在 Stage 4/6 安全检查点停止继续调度。
所有读取/运行命令支持 `--json`，终端提示与 JSON 来自同一个 `StepCommandResult`。

## 数据位置

- `workspace/projects/`：本产品新建的用户项目和 Stage YAML。
- `workspace/runs/`：本产品新建的不可变科学 run。
- `runtime/`：本产品自己的 receipt、日志、cache、tmp、validation 和 quarantine。
- 原仓库 `runtime/envs/`、`runtime/models/`：只读科学后端与模型。
- 本地 worker 使用 Linux Landlock 强制共享 runtime 只读；JIT、模型 cache、临时文件和日志
  只写当前 worktree 的 `runtime/`。
- `examples/apoe-ui-demo/`：Git 跟踪、只读保留的 APOE 科学证据回归包。

本产品拒绝读取或继续原 UI 的 `workspace/projects/` 与 `workspace/runs/`。完整布局见
[RUN_LAYOUT](docs/RUN_LAYOUT.md)，科学边界见七份 [workflow 文档](docs/workflow/README.md)。

## 边界

结果用于研究决策支持，不等于实验验证、临床结论、生物安全批准或供应商订单。外部模型、
数据库、权重和服务继续受各自许可证、条款与数据政策约束。本分支为私有 Developer
Preview，不发布 PyPI。
