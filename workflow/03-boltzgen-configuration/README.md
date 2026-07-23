# 03 — BoltzGen 配置生成

        **状态：** `planned`

        **契约版本：** 概念版 `0.1`；首次实现验证后再冻结机器 schema。

        ## 目的

        把 target、hotspot、VHH scaffold 和先验解析成可执行且通过校验的策略。

        ## 支持范围

        - 在 hotspot sets 与已审查 VHH scaffolds 之间生成策略矩阵。
- 解析自包含资产 bundle。
- 按声明的 BoltzGen 版本和能力校验 YAML。

        ## 输入

        - Target Bundle manifest 和入选 hotspot sets。
- 带来源审查的 VHH scaffold registry。
- 设计先验、BoltzGen 能力和 pilot 策略规则。

        ## 输出

        - 带稳定 strategy ID 的 BoltzGen YAML。
- 连接 target、hotspot、scaffold 和参数的策略 manifest。
- 解析后资产 bundle 和校验报告。

        ## 不变量

        - 策略可由 manifest 和资产 checksum 重建。
- YAML 不声明后端不支持的能力。
- Scaffold 使用前完成来源审查。

        ## 失败与重试

        - Scaffold 缺失或未经审查。
- 字段/版本不兼容，或 hotspot 无法无歧义表达。

        失败必须写成带类型错误信息的终态 attempt，不能转换为空成功。重试建立新 attempt，
        引用并保留失败 attempt。

        ## 溯源

        Manifest 记录上游 manifest/artifact hash、解析后配置、代码版本、adapter/backend
        身份与版本、适用时的模型身份、随机种子、executor profile、时间、警告和全部 attempt。

        ## 完成门槛

        - 全部策略通过指定后端校验，资产 checksum 一致。
- Stage 04 无需修改科学配置即可执行。

        ## 非目标

        - 执行 BoltzGen。
- 在 1.0 实现非 VHH 主线。
- 写入集群路径或密钥。

        外部工具只通过 adapter 访问；orchestration、UI 行为和下游决策不属于本阶段。
