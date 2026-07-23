# 01 — Target 准备

**阶段状态：** `planned`。sequence/FASTA 纵向切片已实现；其他入口仍未实现。

**契约版本：** sequence/FASTA 与预测 Target Bundle 机器契约 `0.1`。

## 目的

把六类异构输入解析成规范、可追溯、可由 Stage 02 直接消费的 Target Bundle。

## 支持范围

- 本地 PDB/mmCIF。
- RCSB PDB identifier。
- FASTA 文件或裸氨基酸序列。
- 带物种上下文的 UniProt accession、基因或蛋白名称。
- PyMOL PSE 会话。
- 已经准备好的标准 Target Bundle。

当前只实现单条、由 20 种标准氨基酸组成的 sequence/FASTA 路径。FASTA 标题不参与序列
identity；裸序列和同内容 FASTA 必须得到相同规范序列 SHA-256。多记录、空记录和含歧义
残基的输入明确失败，不静默选择第一条记录。

## 输入

- 恰好一种 source kind 及其专属参数。
- 结构选择规则和显式预测 fallback 规则。
- 可选 chain/domain 选择与生物学约束。

sequence/FASTA 路径通过通用 `StructurePredictionRequest` 访问预测 backend。EasyDesign 1.0
当前实现为 `protenix==2.0.0` / `protenix-v2`；AFO、AF3 或其他模型只能作为实现同一契约的
后续 adapter，不得改变 Stage 01 输出。

## 输出

- 规范 `target.cif`；后端明确需要时才派生 `target.pdb`。
- `sequence.fasta`、逐残基编号映射、结构质量报告和来源记录。
- `target-bundle.json` 及其中每个 artifact 的相对路径、大小、SHA-256 和生产 attempt。
- 说明结构属于实验、导入还是预测来源的 manifest。

## 不变量

- 残基身份和编号映射无歧义；预测 CIF 中的聚合物序列必须与规范输入逐位相同。
- 搜索、排序、下载、转换、MSA、模板策略和 fallback 全部留痕。
- 原始输入按 checksum 引用，attempt 和正式 artifact 不覆盖。
- 远程 MSA 失败不得静默降级为 no-MSA；no-MSA 只作为明确标记的工程 smoke。
- `easydesign-core` 不导入 Protenix；adapter 只转换请求/结果，独立环境执行重型工具。
- 预测结构不得描述成实验结构，smoke 分数不得描述成科学验证。

## 失败与重试

典型失败包括来源无效或有歧义、找不到符合规则的结构、序列/结构不匹配、chain 未解析、
MSA 服务失败、预测输出缺失、checksum 不一致和格式转换失败。

失败必须写成带类型错误信息的终态 attempt，不能转换为空成功。重试建立新 attempt，
引用并保留失败 attempt；切换 MSA 服务、预测 backend 或模型必须显式创建新配置和溯源。

## 溯源

Manifest 记录上游 manifest/artifact hash、解析后配置、代码版本、adapter/backend 身份与
版本、模型和 checkpoint hash、随机种子、resolved recycle/diffusion 参数、MSA 来源和
输入 hash、模板模式、executor profile、时间、警告和全部 attempt。

第三方 package、模型和运行缓存按 `resources/provenance/ASSET_REGISTER.tsv` 登记。模型、
MSA、run 和缓存均位于 Git 忽略目录，不随仓库分发。

## 完成门槛

- 六类入口全部通过各自契约测试和至少一个真实 fixture。
- 全部必需 Target Bundle artifact 校验通过并有 checksum。
- Stage 02 可以只通过 Target Bundle 和残基映射解析每个残基，无需扫描 backend 目录。
- sequence/FASTA 路径同时通过 no-MSA 工程 smoke 和 APOE remote-MSA/no-template 真实运行。

## 非目标

- 选择 hotspot。
- 生成 binder。
- 自动决定有争议的 accession、isoform、物种或结构来源。
- 把预测结构描述成实验结构。

外部工具只通过 adapter 访问；orchestration、UI 行为和下游决策不属于本阶段。
