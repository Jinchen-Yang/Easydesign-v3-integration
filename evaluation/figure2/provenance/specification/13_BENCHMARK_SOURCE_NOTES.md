# Benchmark Source Notes

## BioDesignBench
用途：作为“蛋白设计 Agent 应如何被评测”的方法学参照，不一定要求 EasyDesign 跑满全部任务。

公开信息：
- 76 expert-curated protein design tasks
- antibody / enzyme / mini-protein binder / scaffold / fluorescent protein
- de novo + redesign
- human and non-LLM baselines
- outcome + tool-use behavior
- 重要发现：强 Agent 常见缺口不是不会选工具，而是 evaluation depth 不足、很少比较候选、过早终止

来源：
https://pmc.ncbi.nlm.nih.gov/articles/PMC13174699/
https://pubmed.ncbi.nlm.nih.gov/42146566/

## BenchBB
用途：标准化非 GPCR binder target panel。

七个 target：
PD-L1, EGFR, IL7Rα, BHRF1, SpCas9, BBF-14, MBP

来源：
https://start.adaptyvbio.com/benchbb
https://www.adaptyvbio.com/blog/benchbb

如果 EasyDesign 是 VHH 模态：
只把 BenchBB 当 standardized targets；
不能把历史 mini-protein wet-lab hit-rate 当严格同模态 baseline。

## Binder scoring meta-analysis
3766 experimentally tested binders / 15 targets。
提示：
- 不要只用 iPTM/ipAE
- interface-focused ipSAE 更有预测力
- 与 Rosetta ΔG/ΔSASA、shape complementarity 等正交物理指标组合更合理

来源：
https://www.biorxiv.org/content/10.1101/2025.08.14.670059v2

该工作目前为 preprint。
