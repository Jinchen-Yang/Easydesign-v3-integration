# Panel E/F — Non-GPCR Generalization

## 推荐标准 target panel
BenchBB 七个 target：
- PD-L1
- EGFR
- IL7Rα
- BHRF1
- SpCas9
- BBF-14
- MBP

如果 EasyDesign 只生成 VHH：
BenchBB 仅用作 standardized target panel。
不要把 VHH computational yield 与历史 mini-protein wet-lab hit-rate 直接比较。

## 扩展 family
资源允许时加入：
- soluble protein
- receptor ectodomain
- ion channel
- lipid-associated target
- viral protein
- synthetic protein

目标至少 3–4 个 target family。

## Metrics
与 GPCR 共用 universal evaluator core：
HQ yield、independent interface confidence、interface PAE、hotspot coverage、clash-free fraction、target deformation、BSA/ΔSASA、interface physics、developability、diversity。

不要每个 target 单独调阈值，除非规则预注册且有明确物理原因。

## Generalization summaries
- per-target paired effect
- target win rate
- median improvement
- worst-target effect
- family-specific effect
- variance across targets
- accepted designs/GPU-hour
- failure rate by target family

主文优先原始 per-target effect。
