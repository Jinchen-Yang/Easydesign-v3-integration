# EasyDesign Local 路线图

## 当前产品

- 永久 worktree `/root/autodl-tmp/Protein_design/easydesign-local`，分支 `easydesign-local`；
- 独立 distribution `easydesign-local 0.1.0.dev1`，命令/import 仍为 `easydesign`；
- 公开流程 `prepare → strategize → pilot loop → scale → select`；
- Codex 使用 `.agents/skills/easydesign-research`，项目恢复只读 `project status --json`；
- 只读 evidence viewer；无 Workbench、HTTP API、远程 executor、Manager 或 18769 操作。

## 已冻结边界

- core manifest/artifact/attempt/decision/checksum 不降级；
- 内部 Stage 1–7、科学 backend、filter profile 和 VHH scaffold 保留；
- site、strategy、pilot、promotion、production 和 selection 不可变且人工 gate 清晰；
- SASA/ScanNet 独立，不融合分数；
- 科学负结果、科学停止、运维失败与可审计空结果严格区分；
- `examples/apoe-ui-demo/` 内容和 checksum 不变。

## 本次 Agent-native 验收

1. 双入口 AGENTS 和仓库级 Skill discovery/前向用例；
2. 六类 target source、PSE colors、文字 residue、SASA/ScanNet foundation；
3. strategy variant、crop、binding subset、CDR override、native YAML；
4. 独立 pilot lineage、负结果 review、人工 promotion；
5. 50,000 production、Top 200 不补齐；
6. persistent worker 的 detach/watch/drain/resume/lost/Ctrl-C；
7. Ruff、mypy、Python integration、Viewer Chromium、APOE tree hash 和数据零漂移。

## 后续经验建设

研究过程先把候选经验写入项目 `DECISIONS.md`。只有包含适用范围、证据 run、反例、
置信度、审核人和日期并经研究者批准后，才平铺加入 Skill reference。出现真正不同的触发
场景前不拆新 Skill。

本路线图不跟踪 UI、18769、Manager 或 Suzhou2；这些只属于主产品仓库。普通开发不升
版本、不构建 wheel，release 必须另行明确要求。
