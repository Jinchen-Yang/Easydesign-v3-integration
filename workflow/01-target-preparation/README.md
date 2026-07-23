# 01 — Target 准备

        **状态：** `planned`

        **契约版本：** 概念版 `0.1`；首次实现验证后再冻结机器 schema。

        ## 目的

        把六类异构输入解析成规范、可追溯的 Target Bundle。

        ## 支持范围

        - 本地 PDB/mmCIF。
- RCSB PDB identifier。
- FASTA 文件或裸氨基酸序列。
- 带物种上下文的 UniProt accession、基因或蛋白名称。
- PyMOL PSE 会话。
- 已经准备好的标准 Target Bundle。

        ## 输入

        - 恰好一种 source kind 及其专属参数。
- 结构选择规则和显式预测 fallback 规则。
- 可选 chain/domain 选择与生物学约束。

        ## 输出

        - 规范 `target.cif`；后端明确需要时才派生 `target.pdb`。
- `sequence.fasta`、残基编号映射、结构质量报告和来源记录。
- 说明结构属于实验、导入还是预测来源的 manifest 及 checksum。

        ## 不变量

        - 残基身份和编号映射无歧义。
- 搜索、排序、下载、转换和 fallback 全部留痕。
- 原始输入按 checksum 引用且不覆盖。

        ## 失败与重试

        - 来源无效或有歧义；找不到符合规则的结构。
- 序列/结构不匹配、chain 未解析或格式转换/编号映射失败。

        失败必须写成带类型错误信息的终态 attempt，不能转换为空成功。重试建立新 attempt，
        引用并保留失败 attempt。

        ## 溯源

        Manifest 记录上游 manifest/artifact hash、解析后配置、代码版本、adapter/backend
        身份与版本、适用时的模型身份、随机种子、executor profile、时间、警告和全部 attempt。

        ## 完成门槛

        - 全部必需 Target Bundle artifact 校验通过并有 checksum。
- Stage 02 可以通过映射解析每个残基。

        ## 非目标

        - 选择 hotspot。
- 生成 binder。
- 把预测结构描述成实验结构。

        外部工具只通过 adapter 访问；orchestration、UI 行为和下游决策不属于本阶段。
