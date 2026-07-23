# 03 契约 — BoltzGen 配置生成

        [English](CONTRACT.md)

        **契约状态：** 概念版 `0.1`；机器 schema 刻意延后到首次实现验证完成后再冻结。

        ## 输入

        - Target Bundle manifest 和入选 hotspot sets。
- 带来源审查的 VHH scaffold registry。
- 设计先验、BoltzGen 后端能力和 pilot 策略规则。

        ## 输出

        - 带稳定 strategy identifier 的已校验 BoltzGen YAML。
- 连接 target、hotspot、scaffold 和参数的策略矩阵 manifest。
- 解析后的资产 bundle 和校验报告。

        ## 不变量

        - 可以仅凭 manifest 和不可变资产 checksum 重建策略。
- 生成 YAML 不会宣称后端不支持的能力。
- Scaffold 使用前已经通过来源审查。

        ## 失败状态

        - Scaffold 资产缺失或未经审查。
- BoltzGen 字段不受支持或后端版本不兼容。
- Hotspot 表达无法无歧义地转换。

        失败必须写成带类型错误信息的终态 attempt 记录，不能转换成空成功。重试必须建立
        新 attempt，并引用失败 attempt。

        ## 溯源要求

        Manifest 必须记录上游 manifest 和 artifact hash、解析后配置、代码 revision、
        adapter/backend 身份和版本、适用时的模型身份、随机种子、executor profile、
        时间、警告和全部 attempt 状态。

        ## 完成门槛

        - 所有计划策略都通过声明后端校验。
- 所有引用资产存在且 checksum 一致。
- Stage 04 无需修改科学配置即可执行。
