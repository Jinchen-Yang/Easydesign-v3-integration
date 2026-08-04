# 旧仓审计基线

本文仅是审计记录，不代表迁移授权。

- 检查路径：`/root/autodl-tmp/Protein_design/easydesign`
- 上游：`https://github.com/siyuanj/easydesign.git`
- 分支：`main`
- 基线 commit：`bc67fb77fa32b95e609db6a0ca6400946f34f31d`
- 检查时 worktree：clean

已观察到的风险包括重复 package/UI 树、多套 target/hotspot 实现、环境专属执行与
领域逻辑混合，以及可能掩盖真实预测器的历史后端命名。已有 smoke 示例只能证明
部分路径曾经运行，不代表 production-ready 或 scientifically-validated。

任何旧仓思路、测试、配置或资产都必须重新接受技术、科学、来源和权利审查。本
clean 仓初始化和本次精简均未复制旧仓代码、权重、运行结果或 scaffold。

## APOE MSA 资产审计（2026-07-24）

- 旧仓 `package/easydesign_competition/data/apoe/msa/` 只有一个 143-aa FASTA 和一个
  378-byte AF3 输入 JSON；JSON 只有单条 protein sequence，不含 `unpairedMsa`、
  `pairedMsa` 或 `templates`。
- 在旧仓中没有找到 `.a3m`、`.sto`、`.aln`、`.msa` 或内嵌 `unpairedMsa` 的 JSON。
- 对 Proteindigger1 的 `/root/autodl-tmp` 盘点得到 113 个 alignment 文件；文件名和
  内容均未匹配 APOE/P02649 或当前 143-aa 查询序列。
- 旧仓文档记录：真正使用过的 APOE MSA/template 来自 SMART 上
  `runs/target_feature_cache/<target_sha256>/target_data.json`，最初由一份 AF3
  full-pipeline data JSON 注入；该缓存和原始 data JSON 均不在 Proteindigger1。

因此“旧仓 APOE MSA → Protenix-v2”的复用测试尚未执行。未来从 SMART 取回后，必须先
校验查询序列、来源和 SHA-256，再作为 runtime artifact 使用；不得把现有 FASTA 或
单序列 AF3 JSON 误称为 MSA。
