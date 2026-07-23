# 02 — Hotspot 识别

        [English](README.md) · [契约](CONTRACT.zh-CN.md)

        ## 目的

        生成可比较的 hotspot 候选和 avoid 区域，并保留明确证据。

        ## 支持场景

        - 人工指定残基或导入 hotspot 定义。
- 成熟 SASA/表面几何基线，加上明确标注的自定义排序。
- 带残基映射的已知复合物界面迁移。
- UniProt 功能注释和用户提供的生物学先验。

        ## 边界

        本阶段只负责声明的转换和输出校验。外部工具通过 backend adapter 访问。
        Orchestration、UI 行为和下游科学决策不属于本阶段。

        ## 非目标

        - 把几何 patch 分数包装成能量学 hotspot 预测。
- 选择最终 binder 序列。
- 因为方法意见不一致就丢弃候选方法。

        ## 实现状态

        `planned`。本目录只规定预期行为；存在这些文档不代表科学实现已经完成。
