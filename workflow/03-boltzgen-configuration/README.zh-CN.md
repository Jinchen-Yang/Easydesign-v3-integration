# 03 — BoltzGen 配置生成

        [English](README.md) · [契约](CONTRACT.zh-CN.md)

        ## 目的

        把 target、hotspot、VHH scaffold 和先验解析成通过校验的 BoltzGen 策略。

        ## 支持场景

        - 在入选 hotspot sets 和已审查 VHH scaffolds 之间生成策略矩阵。
- 把所有资产引用解析成自包含执行 bundle。
- 根据声明的 BoltzGen 能力/版本校验生成的 YAML。

        ## 边界

        本阶段只负责声明的转换和输出校验。外部工具通过 backend adapter 访问。
        Orchestration、UI 行为和下游科学决策不属于本阶段。

        ## 非目标

        - 执行 BoltzGen。
- 在 EasyDesign 1.0 实现非 VHH binder 主线。
- 把集群路径或密钥写入科学配置。

        ## 实现状态

        `planned`。本目录只规定预期行为；存在这些文档不代表科学实现已经完成。
