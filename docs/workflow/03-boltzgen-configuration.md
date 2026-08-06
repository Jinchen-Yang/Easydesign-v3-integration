# 03 — BoltzGen 配置生成

**状态：** `implemented`

**契约版本：** `0.1`

## 目的

Stage 03 把 Stage 02 已批准的区域和经过来源审查的 VHH scaffold 编译为可直接交给
BoltzGen 0.3.2 的确定性策略矩阵。它只负责“配置编译与官方校验”，不执行结构生成，也不
判断哪个区域更好。

EasyDesign 1.0 的基础策略固定为：

```text
每个已批准区域
× official-vhh7-v1 的七个 scaffold
× H_all + C_full
→ 一个 BoltzGen design.yaml
```

区域数来自上游 `hotspots.yaml`，不是代码常数。APOE 当前有 A/B/C 三个区域，因此形成
`3 × 7 = 21` 个策略；一、二或三个区域以及其他合法区域 ID 使用同一实现。

## 使用场景与科学边界

- 适用于 Stage 02 已完成正式审批、希望先用最小 VHH 模板跑通 pilot 的项目。
- 所有 hotspot 成员都写成 target chain A 的 positive `binding` residue。
- 非 hotspot residue 完全不出现在 binding constraint 中，保持中性；绝不自动生成
  `not_binding`。
- 当前不做 crop、区域融合、CDR 长度优化、局部几何选模或 Agent 判断。
- 这一步通过只证明 YAML 可被固定 BoltzGen 版本解析，不证明生成候选会结合、稳定或可
  实验表达。

高级模板、区域几何驱动策略和 `guides/` 草案属于后续提高款，不改变 1.0 基础模板。

## 输入

Stage 03 只能从当前 RunManifest 引用的成功 StageManifest 获得：

1. Stage 01 `target-bundle`；
2. Stage 01 `target-structure`，即 protein-only、规范 chain A 的 `target.cif`；
3. Stage 02 `hotspots`，即已批准且 `ready_for_stage03: true` 的
   `hotspots.yaml` 0.1–0.3。

每个 ArtifactRef 必须通过路径边界、大小和 SHA-256 校验。Stage 03 不读取候选区域、
PSE 原始颜色、review 草稿或 backend 私有目录，也不扫描文件夹猜输入。

已结束的 Stage 02 run 通过显式 continuation 建立新的 downstream run：Stage 01/02
目录和 manifest 引用按字节复制并复验，`continuation-source.json` 记录源 RunManifest
身份；原 run 不会被改写。

## 配置

用户配置 schema `0.7`：

```yaml
workflow:
  execution_mode: unattended
  stop_after_stage: 3
  max_strategy_rounds: 1

stage03:
  profile: boltzgen-vhh-basic-v1
  scaffold_registry: official-vhh7-v1
  candidates_per_strategy: 40
  # 普通科研运行省略该字段，使用全部七个官方 scaffold。
  # 开发者真实后端微型自检可显式选择严格非空子集：
  # scaffold_ids: [7eow]

stage04: null
stage05: null
stage06: null
stage07: null
```

`max_strategy_rounds` 当前只接受 `1`。Stage 03 1.0 只接受
`design.binder_profile: vhh`，未知 profile/registry/字段会在创建 run 前失败。
`scaffold_ids` 省略时固定使用 registry 的全部七个 scaffold；若提供，只允许
`official-vhh7-v1` 中的非空、无重复子集。这个缩减入口用于固定成本的真实 backend
probe，不改变普通 1.0 默认矩阵，也不能在运行后静默减少 scaffold。

机器部署位置进入未提交的 runtime profile：

```yaml
backends:
  boltzgen:
    executable: /absolute/path/to/boltzgen
    repository_root: /absolute/path/to/boltzgen-repository
    cache_root: /absolute/path/to/boltzgen-cache
    timeout_seconds: 300
    validation_workers: 4
    offline_mode: true
```

`cache_root` 指向 Hugging Face cache 本身（其下直接包含
`datasets--boltzgen--inference-data`），不是它的父目录。1.0 默认显式 offline；
cache 缺失时明确失败，禁止在校验中临时联网或切换来源。

Core 不导入 BoltzGen，也不扫描 Conda 环境。Adapter 使用无 shell argv，先验证
`boltzgen 0.3.2`、干净 repository 和固定 commit，再以显式有界 worker 并发执行官方
`boltzgen check`。每份 YAML 仍有独立 return code/stdout/stderr/hash，报告按
StrategyBundle 顺序汇总；并发只减少重复初始化的等待，不合并或跳过检查。

## Scaffold registry

`official-vhh7-v1` 固定来自 BoltzGen commit
`a3149cf18eeb58648d1abbb27539bd73f746cdda`：

```text
7eow
7xl0
8coh
8z8v
gontivimab
isecarosmab
sonelokimab
```

上游为 MIT。十四个 YAML/mmCIF 资产和 license 以官方字节随 wheel 分发；编译时先验证
固定 SHA-256，再复制到当前 attempt。来源、commit、许可证、原始 ID 和每个文件 hash
同时写入资产登记与 `scaffold-resolution.json`。来源不明的旧仓 scaffold 不会进入
registry。

## 算法

对 `hotspots.yaml.hotspot_sets` 中的每个区域：

1. 验证 `target_structure_sha256` 与当前 Stage 01 target 完全相同。
2. 保留该区域全部 `label_seq_id`；不扩展、不删减、不重新评分。
3. 针对 registry 中每个 scaffold 建立稳定 strategy ID。
4. 生成引用便携 target/scaffold 的 BoltzGen YAML：

   ```yaml
   entities:
     - file:
         path: ../../assets/target.cif
         include:
           - chain:
               id: A
         binding_types:
           - chain:
               id: A
               binding: 10,14,17
     - file:
         path: ../../assets/scaffolds/7eow.yaml
   ```

5. YAML 中只出现 positive binding；未列出的 target residue 保持中性。
6. 对所有策略执行固定版本的官方 `boltzgen check`。
7. 只有完整笛卡尔积全部通过，才发布 StrategyBundle。

BoltzGen 0.3.2 没有可靠公开生成 seed，manifest 必须写
`unsupported-by-boltzgen-0.3.2`，不能伪造可重复随机种子。

## 输出

```text
03-boltzgen-configuration/attempt-0001/
├── logs/
│   ├── stdout.log
│   └── stderr.log
└── artifacts/
    ├── strategy-bundle.json
    ├── design-matrix.json
    ├── design-matrix.tsv
    ├── scaffold-resolution.json
    ├── boltzgen-capability.json
    ├── validation-report.json
    ├── stage-manifest.json
    ├── assets/
    │   ├── target.cif
    │   └── scaffolds/
    │       ├── BOLTZGEN_LICENSE.txt
    │       ├── <scaffold>.yaml
    │       └── <scaffold>.cif
    └── strategies/<strategy_id>/
        ├── design.yaml
        └── strategy-manifest.json
```

Stage 04 只消费 StageManifest 声明且 checksum 正确的 `strategy-bundle` 及其引用，不扫描
`strategies/`。

## 公共类型

- `ScaffoldAsset`：scaffold 的 spec、structure、来源、commit、license 和 SHA-256。
- `StrategyRecord`：区域、scaffold、H/C 策略、binding residue、预算和 design hash。
- `StrategyBundle`：完整 region × scaffold 矩阵和上游 artifact 身份。
- `StrategyValidationReport`：逐 strategy 官方校验结果。
- `Stage03Execution`：公共编排 API 返回的 run/manifest/bundle 路径和策略数。

## 不变量

- 区域数、区域 ID、scaffold 数和 candidate budget 均来自类型化输入。
- StrategyBundle 必须是区域与 registry 的完整笛卡尔积，不能漏项或重复。
- target、hotspots、scaffold、YAML 和 StageManifest 全部有可验证 SHA-256。
- 非 hotspot residue 永远保持中性。
- artifact、attempt 和已发布 manifest 不覆盖；重试建立新 attempt。
- CLI、脚本和未来 UI 只调用 orchestration API，不包含模板拼接逻辑。

## 失败、重试与科学停止

以下属于 operational failure：

- 上游 manifest 不是当前成功版本或 artifact checksum 不一致；
- `hotspots.yaml` 未批准、target identity 不匹配或编号不可表达；
- scaffold package hash、BoltzGen version/commit 或官方 YAML check 不通过；
- 基础模板不能表达 target。

失败必须留下终态 attempt/StageManifest/RunManifest 和结构化错误；不能发布部分成功
StrategyBundle。修复环境或输入后以新 attempt/run 重试，已发布证据不覆盖。

Stage 03 没有“科学负结果”：它只编译策略。候选数量不足、没有 Tier A 或没有最终候选
分别属于 Stage 04–07 的科学/运行状态。

## CLI

从已成功 Stage 02 run 继续：

```bash
easydesign doctor --config downstream/easydesign.yaml
easydesign run downstream/easydesign.yaml \
  --from-run workspace/runs/project/source-stage02-run \
  --run-id downstream-stage03
```

## 科研工作台

在“按步骤设计”中完成 Stage 02 后，工作台会自动定位到
“第3步：生成设计方案”，展示：

- Stage 02 已批准区域数；
- `official-vhh7-v1` 的七个 scaffold；
- `区域数 × scaffold 数` 的设计方案数；
- 每套方案的小规模候选预算和下一步总预算；
- positive binding、非 hotspot 中性以及“本步不生成候选”的边界。

用户点击“生成并验证设计方案”后，页面调用与 CLI 相同的 orchestration API，轮询真实
任务状态。成功时自动打开第4步；点击顶部第3步仍可返回查看真实设计矩阵、YAML 校验和
下载。界面参数来自 Python 类型化配置，前端不拼接 BoltzGen YAML。

新建项目配置若已经包含可连续的 Stage 01/02 unattended 路线，也可直接执行：

```bash
easydesign run project/easydesign.yaml
```

## 完成门槛

- 1/2/3 个区域、非 A/B/C ID、不同 candidate budget 和非 APOE target 的测试通过。
- scaffold registry 的来源、许可证、wheel 分发和固定 checksum 通过。
- manifest-only、checksum、不可覆盖和完整矩阵契约测试通过。
- APOE 三个批准区域形成 21 个 YAML，21/21 通过固定 BoltzGen 官方校验。
- `make check`、`make test`、`make build` 和安装后 console-script smoke 通过。

达到以上门槛后本阶段可标记 `smoke-validated`，但不等于科学验证。

## 非目标与后续提高款

- 执行 BoltzGen 或选择赢家。
- crop、H_core、H_cluster、CDR mask/长度优化。
- 区域融合、自适应预算、几何驱动 scaffold/template。
- 多策略轮次或自动调参。
- 非 VHH binder profile。
- LLM/Agent 判断。

这些项目保留在 Stage 03 `STATUS.md` 的 Next；不得用未验证高级逻辑改变 1.0 基础模板。
