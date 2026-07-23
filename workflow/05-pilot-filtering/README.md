# 05 — Pilot 多重筛选

        **状态：** `planned`

        **契约版本：** 概念版 `0.1`；首次实现验证后再冻结机器 schema。

        ## 目的

        应用版本化、体系专属规则，选择进入放大阶段的策略。

        ## 支持范围

        - 结构、界面、hotspot contact、clash 和序列指标。
- 候选去重、聚类与多样性保留。
- 硬门槛和显式综合排序。

        ## 输入

        - Stage 04 候选索引和原始 artifact。
- 体系专属 filter profile、指标能力、去重和排序规则。

        ## 输出

        - 逐 candidate/规则的数值、阈值、通过/失败和原因。
- 去重/聚类分配、pilot shortlist 和入选策略。
- 冻结的 filter 配置和方法溯源。

        ## 不变量

        - 每个决策可由指标和配置重建。
- 缺失指标遵循显式 fail、skip 或 review 规则。
- 原始候选 artifact 不可变。

        ## 失败与重试

        - 必需指标无法生成或映射。
- Profile 无效/无版本；无人通过时记录科学负结果。

        失败必须写成带类型错误信息的终态 attempt，不能转换为空成功。重试建立新 attempt，
        引用并保留失败 attempt。

        ## 溯源

        Manifest 记录上游 manifest/artifact hash、解析后配置、代码版本、adapter/backend
        身份与版本、适用时的模型身份、随机种子、executor profile、时间、警告和全部 attempt。

        ## 完成门槛

        - 每个候选有可审计处置。
- 存在入选策略或明确 no-scale 决策。

        ## 非目标

        - 所有 target 共用一个万能阈值。
- 把综合分数称为实验验证。

        外部工具只通过 adapter 访问；orchestration、UI 行为和下游决策不属于本阶段。
