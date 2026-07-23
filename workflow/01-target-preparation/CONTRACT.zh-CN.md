# 01 契约 — Target 准备

        [English](CONTRACT.md)

        **契约状态：** 概念版 `0.1`；机器 schema 刻意延后到首次实现验证完成后再冻结。

        ## 输入

        - TargetRequest：恰好一种 source kind 及其专属参数。
- 结构选择规则和显式的预测回退规则。
- 可选 chain/domain 选择和生物学约束。

        ## 输出

        - 规范 `target.cif`；只有声明的后端确实需要时才派生 `target.pdb`。
- `sequence.fasta` 和显式残基编号映射表。
- Target metadata、来源记录、结构质量报告和 artifact checksum。
- 说明结构属于实验、导入还是预测来源的阶段 manifest。

        ## 不变量

        - 规范残基身份和编号映射没有歧义。
- 每次搜索、排序、下载、转换和回退都有记录。
- 原始输入用 checksum 引用且绝不覆盖。

        ## 失败状态

        - 来源请求无效或有歧义。
- 声明规则下找不到可接受结构。
- 序列/结构不匹配、不支持的化学成分或 chain 选择未解决。
- 格式转换或编号映射校验失败。

        失败必须写成带类型错误信息的终态 attempt 记录，不能转换成空成功。重试必须建立
        新 attempt，并引用失败 attempt。

        ## 溯源要求

        Manifest 必须记录上游 manifest 和 artifact hash、解析后配置、代码 revision、
        adapter/backend 身份和版本、适用时的模型身份、随机种子、executor profile、
        时间、警告和全部 attempt 状态。

        ## 完成门槛

        - 所有必需 Target Bundle artifact 均通过校验并有 checksum。
- 来源与回退决策明确可见。
- Stage 02 可以通过映射解析每一个残基。
