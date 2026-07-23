# 04 契约 — 小批量生成

        [English](CONTRACT.md)

        **契约状态：** 概念版 `0.1`；机器 schema 刻意延后到首次实现验证完成后再冻结。

        ## 输入

        - 已校验策略 bundle 和 pilot 预算。
- BoltzGen 后端以及 local/Slurm/SMART-capable executor profile。
- 资源限制、重试规则和确定性 seed 规则。

        ## 输出

        - 每个 attempt 的不可变后端原始输出和日志。
- 包含 submitted、running、succeeded、failed、cancelled 状态的任务表。
- 带 strategy 和源 artifact 链接的规范化候选索引。
- 解析后的环境和后端溯源。

        ## 不变量

        - 收集过程绝不重写原始输出。
- 每个候选映射到唯一 strategy、task、seed 和 attempt。
- 执行器状态与科学结果状态保持分离。

        ## 失败状态

        - 后端能力或 executable 与已校验计划不一致。
- 资源、scheduler 或任务失败。
- 输出不完整、损坏或无法关联回策略。

        失败必须写成带类型错误信息的终态 attempt 记录，不能转换成空成功。重试必须建立
        新 attempt，并引用失败 attempt。

        ## 溯源要求

        Manifest 必须记录上游 manifest 和 artifact hash、解析后配置、代码 revision、
        adapter/backend 身份和版本、适用时的模型身份、随机种子、executor profile、
        时间、警告和全部 attempt 状态。

        ## 完成门槛

        - 所有任务达到终态且都在 manifest 中。
- 成功输出通过结构化收集校验。
- 部分完成必须明确记录，且只有配置门槛允许时才可接受。
