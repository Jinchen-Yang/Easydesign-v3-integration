# EasyDesign 案例登记表

本文件记录产品工作台中的主案例、可恢复归档和开发者自检边界。科学事实仍以服务器
`run-index.json`、RunManifest、StageManifest 和 ArtifactRef 为准；本表不替代运行记录。

## 活跃产品案例

| 项目 | 输入与用途 | 当前边界 | 服务器路径 |
| --- | --- | --- | --- |
| `apoe-s02-006-pse` | 138 aa 单 Target PSE；包含红/蓝/黄用户区域，用于 Stage 01–06 和远程规模运行展示 | v1.5 Stage 05 科学停止保持冻结；v1.6 独立重评晋级唯一 Tier A，并通过采用记录接入 Suzhou2 20×2500、50,000 候选；Stage 07 尚未开始 | `workspace/runs/apoe-s02-006-pse/`；采用记录在 `workspace/projects/apoe-s02-006-pse/evidence-adoptions/` |
| `apoe-fasta` | 冻结 143 aa FASTA + 609-depth 预计算 A3M；用于清晰的 sequence→Protenix Stage 01 与按步骤设计起点 | `20260727-002-stage01-protenix` 已真实调用 Protenix-v2，发布 143 aa Target Bundle 0.4 与 Viewer；首个失败 run 保留为修复前证据 | `workspace/runs/apoe-fasta/` |

两个活跃项目目录现在均包含可再生 `PROJECT.json` 和 `PRIMARY`。PSE 项目主展示 run 固定为
`20260726-004-stage05-pilot-filter`，FASTA 项目固定为
`20260727-002-stage01-protenix`。导航文件不替代 manifest；详细 Project/Run/Stage/
Attempt 规则见 [`RUN_LAYOUT.md`](RUN_LAYOUT.md)。

APOE FASTA 的固定 A3M SHA-256：

```text
12d913001bd955c05544b084f396f6b17bc0086ae69cfca5cd376ab722f72716
```

真实验收 run：

```text
workspace/runs/apoe-fasta/20260727-002-stage01-protenix
```

该 run 已同时证明 143 aa、MSA depth 609、predicted/Protenix-v2 2.0.0、Target Bundle
0.4、Viewer 和 Stage 02 可消费交接。`20260727-001-stage01-protenix` 保留
`precomputed-msa-missing` 失败证据，用于证明决策恢复路径修复前后的区别，不冒充成功。

## 可恢复归档

Stage 01 六入口验证、旧 APOE 开发 run、手工区域等价 run 和 CLI smoke 等 17 个
非主项目已移动到：

```text
workspace/runs/_archive/<project_id>/<run_id>/
```

归档不删除运行、不重写 manifest、不修改 artifact checksum。设置页面和 CLI 可查看与
恢复：

```bash
easydesign projects list --include-archived
easydesign projects restore PROJECT_ID
```

恢复后再次验证 manifest/ArtifactRef 闭包。运行中、带锁或仍被远程任务记录引用的项目
拒绝归档。活跃项目和归档项目都不得仅凭目录扫描进入产品；分类以 `run-index.json` 为
唯一事实来源。

2026-07-28 已在再次核对 run-index 后清理这 17 个项目留在 `workspace/runs/` 顶层的空目录壳；
实际 run 仍完整位于 `_archive/`。`workspace/runs/` 顶层当前只保留两个活跃项目及
`_archive/_development/_selftests/_validation` 系统目录。

## 开发者自检

开发者自检使用 `developer-smoke-run`，保存在 `workspace/runs/_selftests/`，不进入普通项目列表：

- `deterministic-seven-stage`：无网络/GPU，真实创建七阶段工程证据链；标记
  `synthetic-engineering-smoke`，禁止用于科学结论或下单。
- `real-backend-micro`：固定非 APOE fixture 的真实工具链。只有 Stage 01–05 coherent
  run 和 Stage 06/07 adapter probe 真正完成后才可报告通过。当前执行器已使用固定
  `validation-1ubq-cif` asset、1 个区域、1 个 scaffold 和极小预算接入七阶段工作区；
  环境或模型未安装/未许可时明确停在 `blocked`，不得报告通过。

科学停止不等于后端失败。真实后端微型自检必须分别报告工程链路、后端健康和科学结果。

当前确定性验收：

```text
selftest-20260727t104835z-f73dfb
workspace/runs/_selftests/selftest-20260727t104835z-f73dfb/synthetic-7b3b6c1c7288
```

该记录完成 Stage 01–07 工程链，并通过 `developer-smoke-run` 分类从普通项目页隔离。

真实后端 fixture：

```text
asset_id: validation-1ubq-cif
source: https://files.rcsb.org/download/1UBQ.cif
size: 103220 bytes
sha256: 056f98710cb2b36f633c45e41902a02eb446e82871da21ff2dd44f74a56ca0f6
```

下载受资产登记和 wwPDB 使用条款确认门控制。fixture、生成的 PSE、后端输出和自检 run
只存在于当前工作区 runtime/runs，不进入 Git。

## 治理规则

1. 主案例变化必须同步本文件、`ROADMAP.md` 和对应 Stage status/history。
2. 新案例先说明用途、来源、许可、输入 hash 和完成门槛，再进入产品列表。
3. 归档失败不得通过 UI 过滤或硬编码隐藏；必须修复 index、锁、远程引用或完整性问题。
4. 大型运行、权重、PSE 和缓存保持 runtime-only；经授权的只读 evidence bundle 另按
   DATA-004 规则处理。
