# 05 — Pilot 多重筛选

        [English](README.md) · [契约](CONTRACT.zh-CN.md)

        ## 目的

        应用版本化、体系专属的证据规则，选择进入放大阶段的策略。

        ## 支持场景

        - 计算或导入结构、界面、hotspot-contact、clash 和序列指标。
- 候选去重并保留多样性。
- 应用硬门槛和显式排序规则。

        ## 边界

        本阶段只负责声明的转换和输出校验。外部工具通过 backend adapter 访问。
        Orchestration、UI 行为和下游科学决策不属于本阶段。

        ## 非目标

        - 所有 target 共用一个万能阈值 profile。
- 不记录原因就丢弃失败候选。
- 把综合分数当成实验验证。

        ## 实现状态

        `planned`。本目录只规定预期行为；存在这些文档不代表科学实现已经完成。
