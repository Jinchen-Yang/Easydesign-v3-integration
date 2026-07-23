# 06 契约 — 放大生成与高精度复折叠

        [English](CONTRACT.md)

        **契约状态：** 概念版 `0.1`；机器 schema 刻意延后到首次实现验证完成后再冻结。

        ## 输入

        - 入选策略、冻结的 Stage 05 证据和显式规模预算。
- 生成后端、executor profile 和结构预测后端能力。
- 去重和昂贵评估预算分配规则。

        ## 输出

        - 带完整生成溯源的放大候选索引。
- 去重后的预测请求 manifest。
- 带模型溯源的结构预测原始结果和规范化结果。
- generated、selected、submitted、completed、failed 候选覆盖报告。

        ## 不变量

        - 规模预算是配置而非隐藏常量；50,000 属于未来 SMART production profile。
- 后端专属字段留在 adapter 内，并映射到通用结果契约。
- 预测覆盖率和失败偏差清晰可见。

        ## 失败状态

        - 预算、后端能力或 executor profile 不兼容。
- 候选身份在去重或请求准备中丢失。
- 预测输出不完整、损坏或无法规范化。

        失败必须写成带类型错误信息的终态 attempt 记录，不能转换成空成功。重试必须建立
        新 attempt，并引用失败 attempt。

        ## 溯源要求

        Manifest 必须记录上游 manifest 和 artifact hash、解析后配置、代码 revision、
        adapter/backend 身份和版本、适用时的模型身份、随机种子、executor profile、
        时间、警告和全部 attempt 状态。

        ## 完成门槛

        - 所有计划任务达到终态并报告覆盖情况。
- 每个规范化预测映射到唯一候选和模型执行。
- Stage 07 无需扫描后端专属目录即可评估结果。
