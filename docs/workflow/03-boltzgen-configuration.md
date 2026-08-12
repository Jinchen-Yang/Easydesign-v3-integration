# 03 — BoltzGen 配置生成（内部科学契约）

**状态：** `implemented`

**契约版本：** legacy `0.1` / explicit plan `0.2` / causal experiment plan `0.3`

## 目的与边界

内部 Stage 03 把已批准 `hotspots.yaml`、规范 target 和登记的 VHH scaffold 编译成
BoltzGen 0.3.2 design specifications，并对每份 YAML 运行固定 backend check。它不生成
候选，不判断哪个实验更好，也不把 rationale 当成科学证据。

公开产品通过 `strategy validate/freeze` 和 `pilot run` 使用本契约；研究者不直接操作
Stage 编号。

## 输入

只能从当前 RunManifest 引用并通过 checksum 验证：

1. 成功 Stage 01 的 `target-bundle` 与 `target-structure`；
2. 成功并人工批准 Stage 02 的 `hotspots`；
3. frozen canonical config 中的 `stage03` plan；
4. `official-vhh7-v1` registry 的固定 scaffold 资产。

禁止扫描目录、读取 proposal 草稿、使用未批准 residue 或绕过 backend validation。

## 两种 schema

### 0.1 legacy basic matrix

未提供显式 variants 时，保持历史 `region × selected scaffold` 完整笛卡尔积，使用全部
approved region residues、full target、默认 CDR。旧 manifest 和 evidence 继续可读。

### 0.2 explicit plan

Agent-native strategy 可以声明多个独立 variant。每个 variant 显式给出：

- approved hotspot set 或其 residue 子集；
- 一个或多个 registry scaffold；
- 可选 target crop，必须覆盖全部选择 binding residues；
- 可选 CDR1/2/3 design range 与 insertion length override；
- 每个编译 strategy 的候选预算；
- 或一个已复制、记录源 SHA-256 的专家原生 BoltzGen YAML。

编译器只展开该 variant 明确列出的 scaffold，不建立跨所有 region/scaffold 的全局笛卡尔
积。未知 scaffold、未批准 residue、越界/遗漏 binding 的 crop、重复 CDR override、原生
YAML identity 漂移或 backend check 失败全部 fail closed。

### 0.3 causal experiment plan

当前 Agent-native 新策略使用 0.3。在 0.2 的技术字段之外，每个 variant 还必须完整记录：

- `hypothesis_id` 与实验 `role`；
- `evidence_refs`；
- 本组主动改变的 `changed_factors`；
- 与比较组保持一致的 `held_constant`；
- `rationale`、`expected_result` 与 `failure_interpretation`。

这些字段随 strategy bundle、design matrix 和 `pilot review` 证据传递，便于区分 scaffold、
site、crop、CDR 等因素并形成可反证诊断；它们不替代真实结果，也不自动证明因果关系。
元数据必须整组提供，禁止只填写部分字段。

新项目首轮在 research façade 冻结前额外执行 `PI-FIRST-PILOT-001`：baseline 必须覆盖
`official-vhh7-v1` 全部七个 scaffold，每个展开 strategy 固定 40 个候选，总数至少 280。
这是首轮产品策略，不把 Stage 03 编译器变成通用科学审批器；已有 Pilot 之后的迭代仍按
研究者批准的策略和候选预算编译。

CDR override 生成 strategy-local `scaffold.yaml`，保留官方 CIF 与来源身份；该派生 YAML
本身也作为 StageManifest artifact 记录。原生 YAML 按源字节写入 attempt，checksum 和
官方 check 均进入不可变证据。

## 不变量

- target structure SHA-256 必须与 approved hotspots 完全一致；
- non-hotspot residue 保持中性，绝不自动输出 `not_binding`；
- StrategyBundle 0.2 只要求 strategy ID 唯一及 scaffold 有 registry provenance；
- StrategyBundle 0.3 还保存完整 experiment contract，并由新项目首轮 façade 强制
  `7 scaffolds × 40 candidates` baseline；
- StrategyBundle 0.1 额外要求完整 region × scaffold matrix；
- 每份 design/scaffold YAML、validation log、bundle、StageManifest 都可校验；
- 任一 YAML check 失败时不发布部分成功 StrategyBundle；
- BoltzGen 0.3.2 随机种子状态仍记录为
  `unsupported-by-boltzgen-0.3.2`，不伪造确定性。

## 输出

```text
03-boltzgen-configuration/attempt-0001/
├── logs/validation/
└── artifacts/
    ├── strategy-bundle.json
    ├── design-matrix.json
    ├── design-matrix.tsv
    ├── validation-report.json
    ├── scaffold-resolution.json
    ├── boltzgen-capability.json
    ├── stage-manifest.json
    ├── assets/target.cif
    ├── assets/scaffolds/<official assets>
    └── strategies/<strategy-id>/
        ├── design.yaml
        ├── scaffold.yaml          # 仅 CDR override 时
        └── strategy-manifest.json
```

Stage 04 只消费 StageManifest 声明且 checksum 正确的 StrategyBundle 和 YAML，不扫描
`strategies/`。

## 完成门槛

- legacy 1/2/3 region matrix 与旧 bundle reader 回归通过；
- 0.3 experiment contract、首轮七 scaffold × 40、explicit multi-variant、binding subset、
  crop、CDR override 通过；
- 原生 YAML 字节 identity 与真实 BoltzGen check 通过；
- 所有非法输入 fail closed，失败不覆盖历史；
- Ruff、mypy、Python integration 与 manifest/checksum 回归通过。

工程 smoke 不等于 binder 科学验证。
