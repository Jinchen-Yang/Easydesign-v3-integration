# Stage 03 状态

稳定职责见 [`03-boltzgen-configuration.md`](03-boltzgen-configuration.md)。

| 总体状态 | 当前结论 | 更新时间 |
| --- | --- | --- |
| `implemented` | StrategyBundle 0.3 的因果实验元数据、首轮七 scaffold × 40、binding subset、crop、CDR override 和原生 YAML identity 已实现。 | 2026-08-12 |

## 当前能力

- 只从 manifest 读取 target/hotspot，并验证 checksum。
- `official-vhh7-v1` 七个 scaffold 固定来源 commit、license 和逐文件 hash。
- 0.3 只编译显式实验，不强制全局笛卡尔积；每组完整保存 hypothesis、role、evidence、
  changed/held-constant factors、预期和失败解释。
- 新项目首轮由 research façade 强制 `official-vhh7-v1` 七个 scaffold 各 40 个候选；
  已有 Pilot 后的迭代不受首轮 baseline 规则替代。
- strategy-local CDR scaffold、专家 YAML 原字节复制、源 SHA-256、统一 backend check、
  design matrix 和逐策略 validation report 已实现。
- StrategyBundle 0.1 仅为既有 manifest 的只读兼容格式，不是新配置入口。

## 仍有效的验证事实

- APOE 0.1 路径的 21/21 BoltzGen check 证明旧 basic matrix 可重读；它不替代 0.2 的
  新能力验证。
- 0.3 的 experiment contract 与首轮 baseline，以及 0.2 的 explicit variant、crop、CDR
  override、未批准 residue 拒绝和新旧 reader
  已有单元/集成回归。

## 待完成

- 在当前 clone 的本地 BoltzGen runtime 上完成 0.3 最小真实 backend smoke 后，才能把
  0.3 提升为 `smoke-validated`。
