# EasyDesign 运行目录与续跑规则

本文件定义 EasyDesign `workspace/runs/` 的稳定语义。它是工程规则的唯一长期说明；运行目录中的
JSON、manifest 和指针只是该规则在某个项目上的实例，不替代本文件。

2026-08-06 之前的 status/history 中出现的 `runs/...` 是迁移前路径记录；当前物理位置为
`workspace/runs/...`，迁移没有改写其中的科学 manifest 或 artifact。

## 1. 四个概念

```text
Project
└── Run
    ├── Stage
    │   └── Attempt
    └── Manifest revisions
```

- **Project**：同一个设计目标或研究主题，例如 `apoe-s02-006-pse`。
- **Run**：在同一 target、上游科学选择和配置 lineage 下，从 Stage 01 向后推进的一次
  完整实验。正常的逐阶段运行不会为每个 Stage 新建一个 run。
- **Stage**：七阶段中的一个步骤。只有真正开始该 Stage 时才创建对应目录。
- **Attempt**：同一 Stage 的重试、恢复或人工批准后续。已发布 attempt 不可覆盖。

## 2. 标准目录

```text
workspace/runs/
├── run-index.json
├── <project_id>/
│   ├── PROJECT.json
│   ├── PRIMARY
│   └── <run_id>/
│       ├── input-snapshot/
│       ├── config-snapshot/
│       │   ├── easydesign.yaml
│       │   ├── resolved-config.json
│       │   ├── CURRENT
│       │   └── revisions/
│       ├── manifests/
│       │   └── LATEST
│       ├── 01-target-preparation/
│       ├── 02-hotspot-discovery/
│       └── ...
├── _archive/
└── _selftests/
```

说明：

- `run-index.json` 是项目目录、分类和主展示 run 的可再生索引。
- `PROJECT.json` 是给人和本地 CLI 使用的项目导航投影；它不属于科学证据。
- `PRIMARY` 指向项目首页应展示的 run；没有显式主 run 时可以不存在。
- `config-snapshot/easydesign.yaml` 和 `resolved-config.json` 是创建 run 时的首个配置。
- 正常逐阶段延续时，新配置写入 `config-snapshot/revisions/`，`CURRENT` 指向当前解析
  配置；旧 revision 保留。
- Stage 目录采用惰性创建。尚未开始的 Stage 不创建空目录。
- 科学事实仍以最新 `RunManifest` 声明的 `StageManifest` 和 `ArtifactRef` 为准，不能
  因某个目录存在就推断 Stage 已完成。

## 3. 什么时候留在同一 Run

以下动作属于同一实验，必须留在同一个 run：

- Stage 01 完成后配置并运行 Stage 02。
- Stage 02 批准后运行 Stage 03。
- 后续 Stage 在不改变已完成上游科学选择的情况下继续。
- operational retry、断点恢复或不足候选的补跑。
- review-gated 的人工批准；批准形成新 attempt 或 manifest revision，不复制上游目录。

正常延续会：

1. 验证当前 run 为 `succeeded` 且已完成 Stage 连续。
2. 验证已完成 Stage 的配置和输入身份没有被改变。
3. 保存新的配置 revision。
4. 创建新的不可变 RunManifest revision，把 run 重新置为 `running`。
5. 只创建并执行下一 Stage。

## 4. 什么时候建立分支 Run

以下动作会使已有下游结论失效，必须新建带 lineage 的分支 run：

- 更换 target、输入结构、序列、MSA 或 design scope。
- 重新选择 Stage 02 区域。
- 修改已经执行过的 Stage 的科学参数、scaffold、filter profile 或预算语义。
- 从较早 Stage 重新开始另一种科学方案。

分支必须记录 parent run、fork stage、来源 manifest SHA-256 和变更原因。分支不得覆盖
父 run；也不得把父 run 的大目录复制成新的事实来源。现有 legacy continuation 在完成
内容寻址迁移前保持可读，但不再作为新运行的默认方式。

## 5. 归档与空目录

- 归档是可恢复的目录治理，不改变科学 artifact 或 checksum。
- 正在运行、持有锁或被活动 local job receipt 引用的 run 不得移动。
- 归档完成后，若原项目目录只剩可再生导航文件，则清理导航文件和空项目壳。
- 空目录清理只能针对 `run-index.json` 已声明为归档项目的精确一级目录；禁止递归删除、
  glob 删除或触碰未登记内容。
- `_archive/` 和 `_selftests/` 不显示在普通项目列表。

## 6. 历史兼容与迁移

- 已存在的 RunManifest、StageManifest、artifact 和 checksum 永不重写。
- 历史上“每推进一个 Stage 就复制出一个新 run”的目录保持可读，并标记为 legacy
  lineage；迁移只改变索引分类或物理位置。
- APOE 等真实案例先生成 dry-run 迁移报告并完成 manifest 闭包验证，再执行受控移动。
- 后续可引入内容寻址对象存储减少跨分支重复，但不属于本轮 `ENG-017` 的完成门槛。

## 7. 产品和 Agent 约束

- Agent-native façade 默认延续同一项目的已批准 foundation；重新选区或更换上游输入必须
  显式建立新的 foundation/run identity。
- CLI、worker、Viewer 和脚本只能调用统一 orchestration API，不得各自复制目录逻辑。
- `workspace/runs/` 不进入 Git；本文件、架构文档、测试和代码共同定义行为。
- Agent 结束涉及目录或 continuation 的任务前，必须验证：无空 Stage 预创建、旧
  manifest 不变、同 run revision 链完整、分支 lineage 明确、归档可恢复。
