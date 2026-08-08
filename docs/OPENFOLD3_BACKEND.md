# OpenFold3/AFO 灰度后端

EasyDesign Local 将 OpenFold3 preview2 权重运行在 `alphafold3-open 3.1.3` JAX runner
上，后端 ID 为 `openfold3-af3-jax`。它与 `protenix-v2` 并行存在；在固定面板完成且研究者
明确批准前，Protenix 始终是默认后端，不允许静默 fallback 或自动切换。

## 冻结身份

- 原始模型：`of3-p2-155k.pt`，SHA-256
  `af09eac4f29cef856633af07558cb143226fe95ebbef2c20921769d4a5f4bee4`；
- runner：`alphafold3-open 3.1.3`，commit
  `b811498caf10001eab4029e7b903453ef48f4d37`；
- wheel SHA-256：
  `d8a54a63627542cbbad4d0df98d2c6f10ecb716955da110c4f4415e01383a942`；
- 正式依赖：Python 3.12、JAX/JAX CUDA 0.10.2、dm-haiku 0.0.16、RDKit
  2025.9.4、tokamax 0.0.12；正式环境不得包含 PyTorch；
- templates 固定禁用，任何结果不得标记为 Google AF3。

转换必须在独立 PyTorch 2.8.0 环境中执行两次。只有压缩文件和未压缩内容的 SHA-256
都分别一致时，bundle builder 才会发布转换 receipt。发布包包含精确 wheelhouse、冻结
runner、许可证/模型条款、model card、转换日志、checksums 和 smoke 输入；它不包含虚构
的 Zenodo/Hugging Face URL。

## 安装与硬件门

```bash
easydesign runtime install openfold3 --bundle /absolute/path/to/bundle
easydesign runtime status --json
easydesign doctor --full --json
```

安装器逐项校验 bundle 后，在 `runtime/tmp/` 建立全新环境，离线安装依赖、构建 AF3 CCD
数据并执行最小无 MSA GPU 推理。全部通过后才原子写入：

```text
runtime/envs/openfold3-p2-af3-jax/<environment-lock-sha>/
runtime/models/openfold3-p2-af3-jax/<converted-weight-sha>/
runtime/state/components/openfold3-p2-af3-jax/
```

失败 staging 移入 `runtime/quarantine/`，当前 profile 不变。`tokamax 0.0.12` 的无补丁
Pallas-Triton 内核要求足够的 per-block shared memory；RTX 4080 SUPER（compute capability
8.9，101,376 bytes available）无法满足已观察到的 110,592-byte kernel 请求。严格的无
本地补丁环境在该硬件上必须 fail closed，不能把旧 AFO patch 偷带进正式环境。应在兼容
的 datacenter GPU 上继续 smoke 和固定面板验证，或先通过单独评审变更依赖/runner 契约。

## MSA、复合物和证据

- 单链 Stage 1 可显式使用公共 ColabFold MSA，并记录 endpoint、cache 和输入身份；
- Stage 5/7 使用预计算 target A3M，binder query-only，不访问公共网络；
- target 固定为 chain A，binder 固定为 chain B，AF3 JSON v4 中 `templates: []`；
- 原始 summary/full-confidence、CIF 和全部 sample 都保留并校验；
- `pairwise_iptm` 取 A→B，`binder_ptm` 取 chain B，interface PAE 从 A/B 跨链矩阵计算；
- AFO 无 gPDE 等价指标，公开结果为 `N/A`，不得推造数值。

Pilot 使用单次低成本预测。AFO final profile 对 Top 60 使用 seeds
`101,202,303,404,505`，每 seed 5 samples；每 seed 选择 ranking score 最高的
representative，至少 3/5 representatives 分别通过硬门后再执行 RMSD/contact Jaccard
共识。25 份输出均进入 evidence。Top 400 初筛仍为 seed 101 × 1。

## 对比与人工批准

```bash
easydesign runtime compare openfold3 \
  --panel config/openfold3-validation-panel.yaml \
  --evidence /absolute/path/to/frozen-observations.yaml

easydesign runtime approve openfold3 \
  --report /absolute/path/to/validation-report.json \
  --reviewer NAME \
  --decision approve-default-switch \
  --confirm
```

比较报告要求 AFO、OpenFold3 PyTorch 和 Protenix 对固定面板均有带 checksum 的真实观察，
不设置虚假的自动一致率门。批准命令只发布 append-only 审核 receipt，仍不会修改默认
后端；默认切换必须是后续独立 `science:` commit。Protenix 的删除不属于本轮。
