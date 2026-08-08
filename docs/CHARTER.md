# EasyDesign Local 产品宪章

## 使命

为熟悉终端和 VS Code 的研究者提供简洁、逐阶段、可追溯的本地蛋白 binder 设计产品。
产品降低操作复杂度，但不隐藏科学选择、失败、人工批准点或证据限制。

## 产品范围

Local 0.1 保留完整七阶段 VHH 主线、科学 backend、filter、manifest 和只读结构报告；只在
当前 Linux GPU 主机执行。它不承诺 binder 准确率，也不包含新手 Workbench、远程算力池、
Manager、安装中心、正式 UI activation 或供应商下单。

一条成功软件运行不等于科学候选成功。无候选通过 filter 是有效负结果；backend failure
不是负结果；Stage 7 空结果必须可审计。

## 不可妥协的规则

1. Stage 只读取 manifest 声明且 checksum 正确的上游 artifact。
2. run、attempt、decision、config revision 和 job receipt 只追加，不原地覆盖历史。
3. 禁止静默 fallback、扫描目录猜事实、伪造成功、错误 backend 命名或吞异常。
4. 保存配置、代码 SHA、版本、随机种子、backend/model/environment identity。
5. CLI、worker、Viewer 和 scripts 不包含重复科学逻辑。
6. 联网 UniProt/PDB/MSA 请求必须有显式配置、cache/provenance 和失败语义。
7. 自动候选与人工批准分离；Stage 1 decision、Stage 2 hotspots 和高成本预算都有明确 gate。
8. Viewer 只读，不能编辑、上传、批准或提交任务。
9. Ctrl-C 不终止持久 worker；drain 只在安全检查点生效，禁止粗暴杀科学进程。
10. 用户输入、科学 runs、manifest、环境、模型和唯一证据受 `DATA_SAFETY.md` 保护。

## 数据与 runtime

本 worktree 独立拥有 `.venv`、`runtime/` 和 `workspace/`。共享 source runtime 只读提供已
验证的环境/模型；任何 job、cache、日志、下载和 bytecode 都写本产品。原 UI projects/runs
不读取、不索引、不继续，APOE Git evidence 只读用于回归。

## 分支治理

本产品永久位于 `codex/vscode-local`，不整体 merge 回 UI `main`。共享的 `core/`、
`stages/`、`filtering/` 或科学 backend 修复使用独立 `core:` commit。未来同步只能逐个
cherry-pick 经评审的 `core:` commit，并在两个产品各跑 integration。

UI/remote 删除、本地 CLI、runtime link、local worker 和 Viewer 产品壳提交永不回 main。

## 验证等级

- `implemented`：结构、Ruff、mypy、unit/integration 通过。
- `smoke-validated`：真实后端的小规模预定义案例形成完整 manifest 证据。
- `scientifically-validated`：预注册 benchmark 通过，不能由工程 smoke 代替。

默认开发只做风险分级验证；版本和本地 wheel staging 仅在明确 release 指令下进行。任何
任务不得以测试方便为由触碰 18769、Suzhou2、Manager 或主仓库。
