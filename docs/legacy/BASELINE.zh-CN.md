# 旧仓审计基线

[English](BASELINE.md)

这是审计记录，不是迁移授权。

- 检查路径：`/root/autodl-tmp/Protein_design/easydesign`
- 上游：`https://github.com/siyuanj/easydesign.git`
- 分支：`main`
- Commit：`bc67fb77fa32b95e609db6a0ca6400946f34f31d`
- 检查时 worktree：clean

已观察到的风险包括重复 package/UI 树、多套 target/hotspot 实现、环境专属执行与领域
逻辑混合，以及可能掩盖真实预测器的历史后端命名。已有 smoke 示例只能证明部分路径
曾经运行，不代表生产就绪或科学有效。

任何可复用思路、测试、配置或资产都必须重新接受技术、科学、来源和权利审查。
本 clean 仓没有复制任何旧仓内容。
