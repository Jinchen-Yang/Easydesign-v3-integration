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
