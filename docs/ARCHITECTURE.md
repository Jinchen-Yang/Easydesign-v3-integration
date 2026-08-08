# EasyDesign Local 架构

## 产品边界

本分支是本地研究者产品：一个 Python package、一个 `easydesign` 命令、一个持久 local
worker 和一个只读 Target Viewer。它不包含完整 UI、HTTP API、远程 executor、Manager、
setup 或正式 activation。

```text
CLI guidance / JSON
        │
        ▼
local_steps ── local_project/config revisions
        │
        ▼
LocalStepJob ── detached local_worker
        │
        ▼
application / continuation / stages 01–07
        │
        ├── immutable manifests, artifacts, attempts, decisions
        └── reporting ── read-only Mol* Target Viewer
```

## 源码职责

```text
src/easydesign/
├── core/             manifest、artifact、attempt、decision、hash、序列化
├── stages/           七阶段纯科学模型和算法
├── backends/         PSE、UniProt/PDB HTTP、Protenix、ScanNet、BoltzGen、TNP、本地 GPU
├── filtering/        冻结的 VHH filter profile 实现
├── orchestration/    配置、workspace、continuation、Stage 执行和本地 job
├── reporting/        manifest 验证后的报告、evidence bundle、Viewer overlay/server
├── resources/        VHH scaffold 与 filter profile package data
├── cli.py            参数解析与类型化终端输出
├── local_worker.py   持久科学 worker 入口
└── workspace_context.py
```

依赖方向固定为：`core/stages/backends/filtering` 不依赖 CLI/worker/reporting；产品壳只调用
orchestration API，不复制科学逻辑。

## 工作区

```text
easydesign-vscode/
├── .venv/                     独立 editable 本地产品环境
├── runtime/                   本产品可写状态
│   ├── cache/ logs/ tmp/
│   ├── state/local-jobs/
│   ├── state/local-projects/
│   ├── state/runtime-link.json[.revisions/]
│   ├── validation/ quarantine/
│   └── profile.yaml[.revisions/]
└── workspace/
    ├── projects/              新项目和 Stage YAML
    ├── runs/                  新的不可变科学 run
    └── archives/              仅用户明确保留的可恢复材料
```

共享 `/easydesign-clean/runtime` 不是本工作区。`runtime link` 只读取登记的 env/model、两个
registry marker、revision 与 inventory，写入本地 receipt/profile。backend 得到的是经过
identity 校验的绝对路径；所有 cache、日志、job 和下载位置仍指向本 worktree。

## 项目与配置 revision

项目根平铺七份严格 Stage 片段。`config-revisions/easydesign.rev-NNNNNN.yaml` 是完整
canonical 配置，`CONFIG_CURRENT` 每行追加一个项目内相对路径。

运行下一 Stage 时：

1. 从当前 run 加载已完成 Stage 的冻结 canonical 配置；
2. 只合并当前 Stage 片段；
3. 将 future Stage 设为 null，`stop_after_stage` 设为当前值；
4. 验证已完成配置没有漂移；
5. 发布新 revision，再由 worker 在同一 run continuation。

已完成 Stage 的相同调用是只读 no-op。任何已完成配置变化都拒绝原地覆盖，实验分支必须
显式建立新项目/run。

## LocalStepJob

job receipt 使用 base snapshot 加 append-only revisions。主 CLI 用 `start_new_session` 启动
`python -m easydesign.local_worker`，因此终端断开或 Ctrl-C 不会把信号传给科学 worker。

状态至少区分 `queued`、`running`、`detached`、`drain-requested`、
`awaiting-human-approval`、`succeeded`、`operational-failed` 和 worker lost。Stage 4/6
drain file 只让调度器在安全检查点停止新增 shard；不发送 SIGKILL。

## Stage 1/2

Stage 1 六类输入由同一 config/application API 处理：PSE、本地结构、本地序列、PDB ID、
UniProt accession、UniProt query。歧义发布 decision request，批准后以新 attempt 继续。

Stage 2 自动模式独立保存 SASA 和 ScanNet，不融合 score。人工模式使用严格 residue-list
配置。所有路径最后都必须发布明确 approval，正式 `hotspots.yaml` 才能成为 Stage 3 输入。

Target Viewer 只从 manifest 引用加载报告与区域 artifact；方法 layer 在内存中通过
`/stage02-regions.json` 提供。A/B/C 固定红、蓝、黄，页面没有写操作。

## 长任务与失败语义

Stage 4–7 的无 `--confirm` 调用只读取配置、GPU 和磁盘并返回 resource plan；不得创建
config revision、worker、Stage 或 attempt。确认后前台/后台都由同一 persistent worker
执行。

科学停止、awaiting approval、backend/operational failure、成功候选和合法空结果是不同
状态。Stage 5 无晋级不提示 Stage 6；Stage 7 无候选发布可审计空结果，不伪造成命中。

## 分支同步

本分支不得整体合回 UI main。共享科学修复必须形成独立 `core:` commit，
`scripts/dev.py core-sync-report --against main` 只读列出四类共享路径差异。恢复 UI 开发后
逐个 cherry-pick 并在两条分支分别跑 integration；产品裁剪和本地壳提交永不 cherry-pick。
