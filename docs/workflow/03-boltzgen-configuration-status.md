# Stage 03 状态

稳定职责见 [`03-boltzgen-configuration.md`](03-boltzgen-configuration.md)。

| 总体状态 | 当前能力 | 验证边界 | 更新时间 |
| --- | --- | --- | --- |
| `implemented` | legacy 0.1 basic matrix 保持可读；0.2 支持显式 variant、binding subset、crop、CDR override 和原生 YAML identity。 | 新 0.2 已有 unit/integration 工程回归；真实 BoltzGen smoke 待本次完整验收记录。 | 2026-08-08 |

## 已实现

- manifest-only target/hotspot 输入和 checksum 验证；
- `official-vhh7-v1` 七 scaffold、固定 commit/license/hash；
- 0.1 完整 matrix 兼容读取与编译；
- 0.2 不强制全局笛卡尔积，只编译显式实验；
- approved residue subset 与 crop 覆盖校验；
- strategy-local CDR scaffold artifact；
- 专家 YAML 源 SHA-256、原字节复制和统一 backend check 路径；
- StrategyBundle、design matrix、逐策略 manifest 和 validation report。

## 已有历史证据

APOE 0.1 正式 smoke 的 21/21 BoltzGen check 仍有效且不被覆盖；具体旧 run/hash 保存在
`03-boltzgen-configuration-2026-07.md`。它证明 legacy basic path，不替代 0.2 新能力验证。

## 当前验收

- explicit 两 scaffold variant 不产生 3×7 全局 matrix；
- crop 写入 target include；CDR3 override 写入独立 scaffold；
- 未批准 binding residue fail closed；
- native YAML 字节与 source SHA-256 一致；
- 新旧 StrategyBundle reader 同时通过。

真实 backend smoke 完成后才能将 0.2 提升为 `smoke-validated`；不能用单元测试冒充。
