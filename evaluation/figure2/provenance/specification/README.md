# EasyDesign Figure 2 Evaluation Pack

用于 EasyDesign v2.1 架构冻结后的论文级测评。

Figure 2 推荐仍做 a–h 八个 panel，但只围绕四个问题：
1. Usable：是否更快、更少操作错误地完成真实任务？
2. Effective：相同后端与预算下，困难 GPCR 的最终设计是否更好？
3. Generalizable：是否泛化到非 GPCR / 标准 target？
4. Trustworthy：是否更可靠、更可复现、更少“假完成”？

核心公平性：
- 同 target / site（controlled benchmark）
- 同生成后端与版本
- 同 evaluator
- 同 candidate budget
- 同 seed policy
- Plain Codex 与 EasyDesign 必须使用同一个 Codex 模型与 reasoning setting
- candidate 不能当统计独立 replicate

First Pilot 永远保持 7 scaffolds × 40 candidates × X explicit conditions。
50,000 仅为 Scale 默认值，不是 invariant。

正常使用：把整个 ZIP 给 Codex，并发送 `PROMPT_00_MASTER_EVALUATION.md`。
