# AFO/OpenFold3 多版本后端

EasyDesign Local 通过 `openfold3-af3-jax` 后端运行 OpenFold3 preview2 权重。每次科学
运行锁定精确 release，不跟随上游 `latest`；Protenix 在研究者完成固定面板批准并合入
独立 `science:` 提升提交前仍是新项目默认后端。

## 3.1.4 candidate 身份

- release ID：`afo-3-1-4-of3-p2-155k`；
- component/model：`openfold3-p2-af3-jax` / `of3-p2-155k`；
- adapter contract：`openfold3-af3-jax-cli-v1`；
- runner：`alphafold3-open 3.1.4`，commit
  `bc32b22ff5902e3daffd5d1f7203d7f2ab6cb997`；
- wheel SHA-256：
  `91b13810c3d51c18b75d0ad27b95b7448dee60933fa3688363c861dded0f7bf0`；
- 原始 `of3-p2-155k.pt` SHA-256：
  `af09eac4f29cef856633af07558cb143226fe95ebbef2c20921769d4a5f4bee4`；
- deterministic bundle archive：5,032,471,381 bytes，SHA-256
  `83b6d8e895090a0c74d21e495d50b75a7cb031389386f5b7cd9843b6d3501afd`；
- metric definition：`openfold3-p2-af3-jax-complex-confidence-v1`。

3.1.4 修正了 diffusion conditioning feature layout。旧 3.1.3 转换权重及 schema 0.1
bundle 被明确拒绝；原始 checkpoint 可复用，但必须用 3.1.4 转换器独立转换两次。
builder 解压两份 `.bin.zst`，同时比较压缩和未压缩内容的大小与 SHA-256。

## 供应链与 conversion receipt

正式 builder 要求输入仓库 HEAD 等于 manifest commit、tracked worktree clean，并使用
`git archive <commit>` 从 Git object 导出 runner；当前工作树文件永远不会直接进入 bundle。
实际 wheel 会重新计算 SHA-256。强类型 JSON receipt 至少保存两次转换、43 个 converter
tests、PyTorch/JAX parity harness、Python/PyTorch/inventory 和全部日志 checksum，builder
逐字段与 runner tree、checkpoint、转换文件和 release manifest 交叉验证。

正式 AFO runtime 只包含 Python 3.12/JAX 环境，不安装 PyTorch。发布后，预转换权重和冻结
wheelhouse 从 catalog 登记的 Hugging Face/S3 artifact 下载；传输地址不定义身份，下载结果
必须匹配 catalog 的精确 size/SHA。当前完整 archive 是 5,032,471,381 bytes（4.687 GiB），
另需解包、环境和 cache 空间。当前 catalog 仍为 `bundle: null`，所以公网 source 写入前安装器
必须 fail closed；archive 已生成不等于已经公开发布。
当前 3.1.4 条目是 `candidate`；只有显式 `--release` 才能安装，`runtime install all` 不会
静默选取 candidate。

bundle 中的 `of3-p2-155k` 及格式转换衍生权重按 OpenFold3 源仓库声明使用 Apache-2.0，
并固定 OpenFold3 source commit、LICENSE、README 和 CITATION。runner 源归档中保留的
Google AlphaFold 3 权重条款只适用于用户另行取得的 Google 权重，不是本 bundle 中
OpenFold3 权重的许可；bundle 不含 Google AF3 权重。

## 安装、并存和激活

```bash
easydesign runtime list afo
easydesign runtime install afo --release afo-3-1-4-of3-p2-155k
easydesign runtime activate afo --release afo-3-1-4-of3-p2-155k --confirm
```

`runtime install afo` 只解析唯一 `stable`；`--release` 安装指定 release 且不改变 active。
激活会生成 append-only profile revision。组件按 release ID 分目录，禁止同 ID 覆盖不同
identity。run 创建时把 profile SHA 和完整 AFO release identity 写入 resolved config 与
manifest；resume 只查找这份旧 revision，缺失时失败，绝不借用新的 active release。

安装器在 `runtime/tmp/` 建立环境、离线安装依赖、构建 AF3 CCD 并执行最小无 MSA GPU
smoke；成功后才发布 component receipt。clone 缺少 Python 3.12 时，安装器通过 bootstrap
固定的 `uv 0.12.3` 自动安装精确 Python `3.12.13` 到 clone-local `runtime/tools/uv-python/`；
随后 wheel 安装保持离线。失败 staging 进入 quarantine，当前 profile 不变。

## MSA、复合物和证据

- Stage 1 可显式选择 AFO，使用 ColabFold 或预计算 MSA；
- Stage 5/7 使用 target A3M，binder query-only，target/binder 固定 chain A/B；
- AF3 JSON v4；`de-novo` 对 target/binder 都写空模板；
- `target-conditioned` 只允许 Stage 1 冻结的 target A mmCIF，binder B 始终空模板；
- 禁止 binder template、自动模板搜索和静默 fallback；
- condition snapshot 固定结构/模板 JSON SHA、来源、A/模板 chain、zero-based
  query/template indices、缺失残基、author/label 编号转换和 resume 精确路径；
- predicted target 若来自当前执行 backend，evidence 明确标记 self-conditioning，不能作为
  完全独立验证；
- 保留 CIF、summary/full confidence 及全部 sample；
- `pairwise_iptm` 取 A→B，`binder_ptm` 取 B，interface PAE 从 A/B 跨链矩阵计算；
- AFO 的 gPDE 为 `N/A`，不得伪造。

AFO Stage 5 使用 `nanobody-filter-standard-v1.7`。Stage 7 使用
`nanobody-final-v1.6`：Top 400 做 seed 101 × 1，Top 60 做五个 seed × 五个 sample，
至少 3/5 seed representatives 通过硬门后再做 RMSD/contact Jaccard 共识；25 份输出全部
进入 evidence。prediction product、阶段记录和科学 provenance 均携带完整 release identity。
target-conditioned 使用独立 `target-conditioned-evidence-v1` advisory profile，不参与上述
de-novo gate、归一化、共识或最终选择。

## candidate 提升

```bash
easydesign runtime compare afo \
  --panel config/openfold3-validation-panel.yaml \
  --evidence workspace/reviews/afo/frozen-observations.json

easydesign runtime approve afo \
  --report runtime/validation/openfold3/REPORT/report.json \
  --reviewer NAME \
  --decision approve-stable-promotion \
  --confirm
```

固定面板只比较精确 AFO release 与 Protenix。report 和 approval receipt 绑定 release
manifest、runner tree、wheel、环境锁、conversion receipt 及转换权重 SHA；任一 identity
变化都必须重跑。批准命令不会修改 release manifest 或默认后端。后续独立 `science:`
catalog commit 引用 report/approval SHA，将 candidate 提升为 stable；再以独立科学提交切换
新项目默认。A100 安装、Stage 1、Stage 5、Stage 7 5×5 smoke 是提升前的实机门。
