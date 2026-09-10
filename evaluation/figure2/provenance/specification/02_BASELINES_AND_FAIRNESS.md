# Baselines and Fairness

## 主 baseline
1. EasyDesign Full
2. Plain Codex Same Model
3. Fixed Pipeline
4. Manual Expert（真实数据存在时）

## Controlled benchmark
锁死 target、structure、site、X、budget、evaluator、seed policy，用于因果归因。

## End-to-End benchmark
只给 target + goal + constraints，测完整产品能力。

## Candidate budget
EasyDesign First Pilot = 280×X。
Controlled 主比较中 Plain Codex 与 fixed pipeline 也必须给相同总候选预算。
如某方法提前停止，不补造结果；记录实际 generated count、budget utilization、HQ yield、accepted/GPU-hour。

## 模型公平
Plain Codex 与 EasyDesign 必须同模型、同 reasoning effort、尽可能同上下文与底层工具。
不要一个用高档模型，一个用低档模型。

## Evaluator fairness
同一 evaluator profile。
阈值在 unblind method comparison 前冻结。
最好使用与生成/内部筛选正交的 evaluator。

## Manual expert
只用真实专家。
分别记录 active human time、compute wall time、queue time、scientific decisions、operational corrections。
