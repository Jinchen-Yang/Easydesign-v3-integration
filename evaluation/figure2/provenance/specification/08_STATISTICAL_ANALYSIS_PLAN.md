# Statistical Analysis Plan

## 1. Analysis unit
candidate 不是主统计独立单位。

candidate-level 数据只用于计算每个 campaign 的：
HQ yield、quality summary、diversity、accepted count。

主比较单位：
target × independent run/campaign。

## 2. Repeats
Cheap agent benchmark：
每 task×method 至少 3 个独立 episode；成本低可 5–10。

GPU design benchmark：
理想每 target×method ≥3 independent campaign replicates。
资源不足时优先增加 target 数，并明确 limitation。

## 3. Pairing
同 target、site、X、budget、seed policy、evaluator 成对比较 method。

## 4. Primary analyses
Time：
paired median difference + bootstrap 95% CI；必要时 log-scale。

Completion/stop/recovery：
proportion + Wilson CI；paired difference；McNemar/paired permutation（适用时）。

HQ yield：
先按 campaign 算 yield，再做 target-level paired difference 和 bootstrap。
mixed-effects logistic model 可作为 secondary。

## 5. Optional mixed effects
数据足够时：
metric ~ method + target_family + method:target_family + (1|target) + (1|run)

proportion 可用 logistic/binomial mixed model。

## 6. Multiple comparisons
预注册主终点：
2a time_to_valid_project
2c HQ_yield
2f paired generalization effect
2g correct_stop / false_completion
2h traceability / replay

其他 secondary metrics 做 Benjamini-Hochberg FDR。

## 7. Effect size
至少给 absolute difference、relative difference、95% CI、N targets、N runs。
不要只给 p-value。

## 8. 不设“必须 +10%”
先冻结 benchmark，再如实报告。

## 9. Failed runs
所有 failed/aborted run 保留并进入 failure analysis。
不能删除 EasyDesign 失败 run。

## 10. Threshold locking
Evaluator threshold 在 method comparison unblind 前冻结、版本化、hash。
后改的只能标 exploratory。
