# EasyDesign v3 Phase 3：原生 Pilot 排序与恢复

当前 v3 的计算定义以运行时 Specialist 使用的
[BoltzGen 指标参考](../../../../src/easydesign/agent/skills/pilot-diagnosis/references/boltzgen-pilot-ranking.md)
为唯一维护源。该参考只采用用户手册的指标计算部分，不纳入 lulu 项目策略、阈值或结论。
执行与授权边界见 [Phase 3/4 contract](../../../../docs/PHASE34_EXECUTION_CONTRACT.md)。

- 一个科学 Arm 可以包含七个 scaffold strategy，不能把单个 scaffold 失败称为整个 Arm 失败。
- 完整、可评价且有原生 PASS：排序全部 PASS，比较 Arm 并提出精确 Scale 分配，交 Scientist Gate 4。
- 完整、可评价且零 PASS：使用确定性失败 dossier 提出有边界的恢复建议。
- 未完成：保留操作状态、缺失项和暂定结果，不宣布科学失败或最终产率。
- 硬过滤来自实际 BoltzGen 配置和保存的过滤决定；旧 Stage 05 的阈值与 Tier 不迁移为 v3 原生硬门槛。
- AFO 是可选独立预测证据；Phase 3 Judge 是可选 second opinion。二者不构成原生排名或 Gate 4 的前提。
- 风险、弱证据和不确定性体现在排序及分配中；Scientist 决定是否推进，不自动启动下一轮或 Scale。

`pilot-diagnosis.md`、`metric-guide.md` 保留旧 Stage 05 工作流及更广泛的分析资料。
其中的 Dashboard、独立预测、Tier、Interpretation CLI 和自动扩展相关描述仅适用于其明确绑定的旧流程，
不能覆盖上述 v3 契约。对成功 Arm 的候选失败分析可以解释产率，不能把成功 Arm 改判为 Recovery。
