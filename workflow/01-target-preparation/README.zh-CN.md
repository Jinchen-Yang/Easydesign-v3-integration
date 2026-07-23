# 01 — Target 准备

        [English](README.md) · [契约](CONTRACT.zh-CN.md)

        ## 目的

        把异构 target 输入解析成一个规范、可追溯的 Target Bundle。

        ## 支持场景

        - 本地 PDB 或 mmCIF 结构。
- RCSB PDB identifier。
- FASTA 文件或裸氨基酸序列。
- 带物种上下文的 UniProt accession、基因或蛋白名称检索。
- PyMOL PSE 会话。
- 已经准备好的标准 Target Bundle。

        ## 边界

        本阶段只负责声明的转换和输出校验。外部工具通过 backend adapter 访问。
        Orchestration、UI 行为和下游科学决策不属于本阶段。

        ## 非目标

        - 选择 hotspot 或生成 binder 设计。
- 宣称预测 target 与实验结构等价。
- 静默用另一来源替换用户请求的来源。

        ## 实现状态

        `planned`。本目录只规定预期行为；存在这些文档不代表科学实现已经完成。
