# EasyDesign 案例登记表

本文件记录产品工作台中的主案例、可恢复归档和开发者自检边界。科学事实仍以服务器
`run-index.json`、RunManifest、StageManifest 和 ArtifactRef 为准；本表不替代运行记录。

## 活跃产品案例

| 项目 | 输入与用途 | 当前边界 | 服务器路径 |
| --- | --- | --- | --- |
| `apoe-s02-006-pse` | 138 aa 单 Target PSE；包含红/蓝/黄用户区域，用于 Stage 01–05 和远程规模运行展示 | Stage 01–04 完成；Stage 05 合法科学停止；探索性 Stage 06 远程运行单独审计 | `runs/apoe-s02-006-pse/` |
| `apoe-fasta` | 冻结 143 aa FASTA + 609-depth 预计算 A3M；用于清晰的 sequence→Protenix Stage 01 与按步骤设计起点 | 必须以新 run 真实调用 Protenix；不得把旧 run 改名或重导入 Bundle 冒充 | `runs/apoe-fasta/` |

APOE FASTA 的固定 A3M SHA-256：

```text
12d913001bd955c05544b084f396f6b17bc0086ae69cfca5cd376ab722f72716
```

成功验收必须同时证明 143 aa、MSA depth 609、predicted/Protenix-v2、Target Bundle、
Viewer 和 Stage 02 可消费交接。

## 可恢复归档

Stage 01 六入口验证、旧 APOE 开发 run、手工区域等价 run 和 CLI smoke 等非主案例移动到：

```text
runs/_archive/<project_id>/<run_id>/
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

## 开发者自检

开发者自检使用 `developer-smoke-run`，保存在 `runs/_selftests/`，不进入普通项目列表：

- `deterministic-seven-stage`：无网络/GPU，真实创建七阶段工程证据链；标记
  `synthetic-engineering-smoke`，禁止用于科学结论或下单。
- `real-backend-micro`：固定非 APOE fixture 的真实工具链。只有 Stage 01–05 coherent
  run 和 Stage 06/07 adapter probe 真正完成后才可报告通过；当前仅登记待运行记录。

科学停止不等于后端失败。真实后端微型自检必须分别报告工程链路、后端健康和科学结果。

## 治理规则

1. 主案例变化必须同步本文件、顶层 TODO/TODO_NOW 和对应 Stage STATUS/history。
2. 新案例先说明用途、来源、许可、输入 hash 和完成门槛，再进入产品列表。
3. 归档失败不得通过 UI 过滤或硬编码隐藏；必须修复 index、锁、远程引用或完整性问题。
4. 大型运行、权重、PSE 和缓存保持 runtime-only；经授权的只读 evidence bundle 另按
   DATA-004 规则处理。
