# 05 契约 — Pilot 多重筛选

        [English](CONTRACT.md)

        **契约状态：** 概念版 `0.1`；机器 schema 刻意延后到首次实现验证完成后再冻结。

        ## 输入

        - Stage 04 候选索引及其引用的原始 artifact。
- 版本化体系专属 filter profile 和指标后端能力。
- 去重、多样性、门槛和排序规则。

        ## 输出

        - 按 candidate 和 rule 展开的通过/失败表，包含数值、阈值和原因。
- 去重和聚类分配。
- 排序后的 pilot shortlist 和入选放大策略。
- Filter 配置快照和方法溯源。

        ## 不变量

        - 每个决策都能从保留的指标和配置重建。
- 缺失指标遵循明确的 fail、skip 或 review 规则。
- 候选原始 artifact 保持不可变。

        ## 失败状态

        - 必需指标无法产生或无法映射到候选。
- Filter profile 无效、不兼容或没有版本。
- 没有策略通过；这应记录为有效的科学负结果。

        失败必须写成带类型错误信息的终态 attempt 记录，不能转换成空成功。重试必须建立
        新 attempt，并引用失败 attempt。

        ## 溯源要求

        Manifest 必须记录上游 manifest 和 artifact hash、解析后配置、代码 revision、
        adapter/backend 身份和版本、适用时的模型身份、随机种子、executor profile、
        时间、警告和全部 attempt 状态。

        ## 完成门槛

        - 每个候选都有可审计处置结果。
- 入选策略非空，或存在明确的不放大决策。
- Stage 06 收到冻结的 filter 快照和入选策略 manifest。
