# Claim Governance and Stop Rules

## 计算结果可写
- higher computational HQ yield
- better interface confidence
- lower interface PAE
- improved hotspot engagement
- higher computational selectivity margin
- better reproducibility
- lower false-completion rate

## 没有实验不允许写
- higher binding affinity
- higher experimental hit rate
- better expression
- stronger biological activity
- higher in-vitro selectivity

## Architecture freeze
benchmark 可增加 evaluation instrumentation：
logger、metrics exporter、plotter、fault fixtures。
不要因为结果不好重新设计 EasyDesign science architecture。

## 真 bug
若 benchmark 暴露 production bug：
1. 记录 bug
2. 冻结当前 benchmark version
3. 修 bug
4. bump benchmark version
5. 所有受影响方法重新跑

禁止只重跑 EasyDesign。

## Leakage
禁止：
- 看结果后手调 rules
- target-specific threshold tuning
- benchmark-target hard-coded special cases
- 只排除 EasyDesign 失败 target

post-hoc 必须标 exploratory。
