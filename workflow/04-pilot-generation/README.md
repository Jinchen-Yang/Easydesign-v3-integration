# 04 — 小批量生成

        **状态：** `planned`

        **契约版本：** 概念版 `0.1`；首次实现验证后再冻结机器 schema。

        ## 目的

        执行真实、小批量的 BoltzGen pilot，并保留任务和环境溯源。

        ## 支持范围

        - 在已校验策略之间分配有边界的 pilot 预算。
- 通过 executor adapter 提交并收集任务状态。
- 不修改原始产物地规范化成功候选。

        ## 输入

        - 已校验策略 bundle 和 pilot 预算。
- BoltzGen backend、executor profile、资源限制、重试和 seed 规则。

        ## 输出

        - 每个 attempt 的不可变原始输出和日志。
- 包含全部终态的任务表。
- 可回溯 strategy、task、seed 和 attempt 的候选索引。

        ## 不变量

        - 收集过程不改写原始输出。
- 执行器状态与科学结果状态分离。
- 部分失败不能通过只报告成功任务来隐藏。

        ## 失败与重试

        - 后端能力与计划不一致；资源、scheduler 或任务失败。
- 输出不完整、损坏或无法关联策略。

        失败必须写成带类型错误信息的终态 attempt，不能转换为空成功。重试建立新 attempt，
        引用并保留失败 attempt。

        ## 溯源

        Manifest 记录上游 manifest/artifact hash、解析后配置、代码版本、adapter/backend
        身份与版本、适用时的模型身份、随机种子、executor profile、时间、警告和全部 attempt。

        ## 完成门槛

        - 全部任务达到终态并进入 manifest。
- 成功输出通过收集校验；部分完成必须符合显式规则。

        ## 非目标

        - 生产规模生成。
- 筛选或宣布科学赢家。

        外部工具只通过 adapter 访问；orchestration、UI 行为和下游决策不属于本阶段。
