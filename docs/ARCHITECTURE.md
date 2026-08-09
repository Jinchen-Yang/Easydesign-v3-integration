# EasyDesign Local 架构

## 产品模型

```text
研究者批准 ───────────────┐
                          ▼
Codex + easydesign-research Skill
        │  project status / typed commands
        ▼
Agent-native façade (CommandResult)
        │
        ├── project/site/strategy immutable revisions
        ├── LocalStepJob + detached local_worker
        └── read-only evidence viewer
                          │
                          ▼
internal Stage 01–07 / backends / filters
                          │
                          ▼
manifest + artifact + attempt + checksum
```

EasyDesign 提供工具与审计，Skill 提供经验和判断框架，Codex 负责推理与调用，研究者掌握
site、strategy、pilot、scale、select 以及经验发布的确认权。公开接口只使用
`prepare / strategize / pilot / scale / select`，数字 Stage 仅保留为内部科学身份。

## 源码职责

```text
src/easydesign/
├── core/             manifest、artifact、attempt、decision、hash、序列化
├── stages/           内部七阶段科学模型和算法
├── backends/         PSE、UniProt/PDB、Protenix、ScanNet、BoltzGen、TNP、本地 GPU
├── filtering/        冻结的 VHH filter profile
├── orchestration/    internal Stage、continuation、research façade、project/job/runtime
├── reporting/        manifest 验证后的报告和只读 Viewer
├── resources/        VHH scaffold 与 filter profile package data
├── cli.py            语义化参数解析与 CommandResult 输出
├── local_worker.py   持久本地科学 worker
└── workspace_context.py
```

`.agents/skills/easydesign-research/` 只有指令和经验 reference，不复制科学脚本。依赖方向
保持 `core/stages/backends/filtering → orchestration → CLI/worker/reporting`，科学层不依赖
Agent 产品壳。

## 项目与 lineage

```text
workspace/projects/<project>/
├── PROJECT.yaml
├── DECISIONS.md
├── strategy-draft.yaml
├── inputs/
├── strategies/strategy-rNNNNNN.yaml
├── config-revisions/easydesign.rev-NNNNNN.yaml
├── site-proposal.<method>.<run-id>.yaml
├── site-approved.rNNNNNN.yaml
├── CONFIG_CURRENT
├── SITE_CURRENT
├── STRATEGY_CURRENT
└── PROMOTION_CURRENT
```

Draft 是可变讨论区；site approval、strategy revision、promotion receipt 和 canonical config
均只追加。科学结果只写 `workspace/runs/`：foundation 保存内部 Stage 1/2；每轮 pilot 从
foundation 复制并校验前缀后运行内部 Stage 3–5；production 从人工 promotion 的 pilot
前缀派生并执行 Stage 6；最终选择在同一 production lineage 追加 Stage 7。

旧七 YAML 项目识别为 `legacy-stage-project`，仅允许状态和只读查看，不原地迁移。

## Strategy compiler

旧 schema 0.1 basic matrix 保持可读。新 schema 0.2 只编译显式 variant，不强制全局
region × scaffold 笛卡尔积；binding residues 必须属于 approved site，crop 必须覆盖选择
residue，scaffold 必须来自 checksum registry。CDR override 生成 variant-local scaffold YAML；
专家原生 YAML 保存源 SHA-256 并通过同一 BoltzGen 0.3.2 adapter 校验，不能绕过 manifest。

## Worker、Viewer 与 runtime

LocalStepJob receipt append-only，worker 由独立 process session 持有。前台 Ctrl-C 不向科学
进程发信号；drain 只对分片调度写安全检查点请求。未确认的高成本命令只返回资源计划，
不得创建 revision、run、job 或 attempt。

Viewer 只从 manifest 引用加载 target/site、pilot 代表候选和最终 evidence；无编辑、上传、
批准或远程提交控件。Runtime 有两个显式模式：全新机器通过 `runtime plan/install/jobs` 从
锁定配方逐组件发布环境、模型和 append-only registry；已有机器可通过 `runtime link` 只读
复用另一套已验证环境和模型。两种模式的 cache、日志、job、validation 和 run 都只写当前
worktree，link 来源永不写入。

本分支不得整体合回 UI main。共享科学修复使用独立 `core:` commit，并通过
`scripts/dev.py core-sync-report --against main` 报告；UI 恢复开发后只能逐个 cherry-pick。
