# 02 — Hotspot 识别

        **状态：** `planned`

        **契约版本：** 概念版 `0.1`；首次实现验证后再冻结机器 schema。

        ## 目的

        生成可比较、有证据来源的 hotspot 候选和 avoid 区域。

        ## 支持范围

        - 人工指定或导入 hotspot。
- 成熟 SASA/表面几何基线以及明确标注的自定义排序。
- 已知复合物界面迁移。
- UniProt 功能注释和用户生物学先验。

        ## 输入

        - 通过校验的 Target Bundle 和规范残基映射。
- 启用的 hotspot source adapters。
- 可选 preferred、forbidden、功能、竞争结合与可及性先验。

        ## 输出

        - 仅使用规范残基 ID 的 hotspot sets 和 avoid 区域。
- 每个候选的来源、证据、方法版本、分数、置信度和警告。
- 保留不同方法分歧的比较结果。

        ## 不变量

        - 每个残基都能通过 Stage 01 映射解析。
- 不同方法的分数不被虚假等价。
- 启发式、迁移证据和用户输入始终可以区分。

        ## 失败与重试

        - 残基无法映射或不在 target 中。
- 所有方法均无法产生有效候选，或参考注释/复合物不一致。

        失败必须写成带类型错误信息的终态 attempt，不能转换为空成功。重试建立新 attempt，
        引用并保留失败 attempt。

        ## 溯源

        Manifest 记录上游 manifest/artifact hash、解析后配置、代码版本、adapter/backend
        身份与版本、适用时的模型身份、随机种子、executor profile、时间、警告和全部 attempt。

        ## 完成门槛

        - 至少一个有效候选，或明确记录无候选的科学负结果。
- 入选候选无需重新编号即可供 Stage 03 使用。

        ## 非目标

        - 把几何 patch 分数称为能量学 hotspot。
- 选择最终 binder 序列。

        外部工具只通过 adapter 访问；orchestration、UI 行为和下游决策不属于本阶段。
