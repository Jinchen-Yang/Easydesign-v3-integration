# 02 契约 — Hotspot 识别

        [English](CONTRACT.md)

        **契约状态：** 概念版 `0.1`；机器 schema 刻意延后到首次实现验证完成后再冻结。

        ## 输入

        - 通过校验的 Target Bundle 和规范残基映射。
- 一个或多个启用的 hotspot-source adapter。
- 可选 preferred、forbidden、功能、竞争结合或可及性先验。

        ## 输出

        - 只使用规范残基 identifier 表达的 hotspot sets。
- Avoid 区域以及与 target 注释的冲突。
- 每个候选的来源、证据、方法版本、分数、置信度和警告。
- 保留不同方法分歧的比较报告。

        ## 不变量

        - 每个报告残基都能通过 Stage 01 映射解析。
- 不同方法的分数保留方法专属含义，不被虚假等价。
- 启发式、迁移证据和用户直接输入始终能够区分。

        ## 失败状态

        - 残基无法映射或不在规范 target 中。
- 所有启用方法都无法产生有效候选。
- 必需注释或参考复合物不一致。

        失败必须写成带类型错误信息的终态 attempt 记录，不能转换成空成功。重试必须建立
        新 attempt，并引用失败 attempt。

        ## 溯源要求

        Manifest 必须记录上游 manifest 和 artifact hash、解析后配置、代码 revision、
        adapter/backend 身份和版本、适用时的模型身份、随机种子、executor profile、
        时间、警告和全部 attempt 状态。

        ## 完成门槛

        - 至少存在一个有效 hotspot set，或记录明确的无候选结果。
- 证据和 avoid 区域得到保留。
- 入选候选无需重新编号即可供 Stage 03 使用。
