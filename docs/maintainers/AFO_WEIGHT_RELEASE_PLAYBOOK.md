# AFO 权重转换与发布手册

本文供 EasyDesign 维护者在升级 OpenFold3/AFO runner 或权重时使用。用户安装方法只写在
主 README；转换、供应链、校验和 stable 提升过程以本文为准。

## 不变量

- 每次发布使用新的 `release_id`，已发布 release、archive 和 catalog identity 永不覆盖。
- 原始 checkpoint、runner commit、OpenFold3 model source commit、wheel、requirements lock、
  conversion receipt 和 bundle 都必须以 SHA-256 固定。
- 同一 checkpoint 必须在两个独立输出目录转换两次；压缩与解压内容都必须完全一致。
- bundle 先以 `candidate` 发布并完成公网新机验证，科学批准后再以独立提交提升为 `stable`。
- runtime bundle 只包含预转换权重和 JAX/CUDA 运行环境，不包含 PyTorch 转换环境。
- OpenFold3 自训权重的许可来自 OpenFold3 model source。runner 中随源码保存的 Google AF3
  权重条款不能标记成 OpenFold3 权重许可。
- 自动模板数据库不是 AFO runtime bundle 的一部分；模板数据库必须作为独立 release 管理。

## 1. 创建不可变工作单

先为本次发布确定下列值并写入工作单，禁止使用 `latest`：

```text
release_id
backend_version
model_id
runner_repository + runner_commit
OpenFold3 model repository + model source commit
raw checkpoint path + size + SHA-256
Python version
CUDA/JAX target
converter/parity test revision
license/model-card revision
```

推荐发布名：

```text
afo-<runner-version>-<model-id>
```

开始前确认 runner 和 EasyDesign checkout 均为预期 commit，且 tracked worktree clean。构建器
会从 Git object 导出 runner；不得把未提交的工作树文件打进发布物。

## 2. 准备转换环境和输入

转换环境允许包含 PyTorch，但不得复用为最终 runtime 环境。下面的变量只是示例；所有路径
都应位于本次发布专用目录：

```bash
export AFO_RELEASE_ID=afo-X-Y-Z-MODEL
export AFO_WORK_ROOT=/data/afo-release-work/$AFO_RELEASE_ID
export AFO_RUNNER_ROOT=$AFO_WORK_ROOT/runner
export AFO_RAW_CHECKPOINT=$AFO_WORK_ROOT/input/model.pt
export AFO_CONVERSION_PYTHON=$AFO_WORK_ROOT/conversion-env/bin/python
export AFO_CONVERSION_A=$AFO_WORK_ROOT/conversion-a
export AFO_CONVERSION_B=$AFO_WORK_ROOT/conversion-b
```

记录输入 identity：

```bash
git -C "$AFO_RUNNER_ROOT" rev-parse HEAD
git -C "$AFO_RUNNER_ROOT" status --short
stat --printf='%s\n' "$AFO_RAW_CHECKPOINT"
sha256sum "$AFO_RAW_CHECKPOINT"
"$AFO_CONVERSION_PYTHON" --version
"$AFO_CONVERSION_PYTHON" -c 'import torch; print(torch.__version__)'
```

把命令输出和 `pip freeze` 保存进 conversion evidence。不要依赖 shell history 充当 receipt。

## 3. 独立转换两次

使用 runner commit 自带的转换器，分别写入两个全新目录：

```bash
"$AFO_CONVERSION_PYTHON" "$AFO_RUNNER_ROOT/convert_of3_weights.py" \
  --of3_checkpoint "$AFO_RAW_CHECKPOINT" \
  --output_dir "$AFO_CONVERSION_A" \
  --use_ema

"$AFO_CONVERSION_PYTHON" "$AFO_RUNNER_ROOT/convert_of3_weights.py" \
  --of3_checkpoint "$AFO_RAW_CHECKPOINT" \
  --output_dir "$AFO_CONVERSION_B" \
  --use_ema
```

比较压缩文件，并比较流式解压后的内容：

```bash
sha256sum \
  "$AFO_CONVERSION_A/of3_ported_weights.bin.zst" \
  "$AFO_CONVERSION_B/of3_ported_weights.bin.zst"

zstd -dc "$AFO_CONVERSION_A/of3_ported_weights.bin.zst" | sha256sum
zstd -dc "$AFO_CONVERSION_B/of3_ported_weights.bin.zst" | sha256sum
```

四项 size/SHA 必须写入 conversion receipt。任何差异都停止发布，不允许任选其中一份继续。

## 4. Converter tests 与 PyTorch/JAX parity

至少运行 runner 对应版本的全部 converter tests，并保存完整命令、收集数、通过数、退出码和
日志 SHA。当前 3.1.4 基线为 43/43。

Parity harness 至少覆盖：

- pair features；
- Pairformer 首尾 block；
- MSA 首尾 block；
- template block；
- confidence head；
- diffusion transformer；
- diffusion conditioning。

每项 receipt 必须记录 tolerance、maximum relative error、退出码和日志 SHA。升级 runner 后
不得照抄旧误差；应由本次真实输出重新生成。conversion receipt 使用当前 bundle schema，且
必须能由 `src/easydesign/orchestration/openfold3_bundle.py` 逐字段交叉验证。

如果仓库版本尚无自动生成 receipt 的命令，应先补生成器，禁止手工拼接一个看似通过的 JSON。

## 5. 冻结 runtime wheelhouse

为精确 Python 和目标 Linux/CUDA 平台准备：

- runner wheel；
- JAX/JAXLIB/CUDA wheels；
- 所有递归依赖 wheels；
- 带 hash 的 `requirements.txt`；
- runner source archive；
- `LICENSE`、`NOTICE`、model card、OpenFold3 `README` 和 `CITATION`；
- conversion receipt 及其引用的全部日志；
- 最小 GPU smoke 输入。

使用离线安装在空 Python 环境中验证 wheelhouse，不能从 PyPI 补包。保存 runner wheel SHA、
requirements lock SHA 和 runner tree SHA。

## 6. 构建确定性 bundle

从 EasyDesign 仓库根目录运行正式 builder：

```bash
python scripts/build_openfold3_bundle.py \
  --output "$AFO_WORK_ROOT/bundle/$AFO_RELEASE_ID" \
  --source "$AFO_RUNNER_ROOT" \
  --wheelhouse "$AFO_WORK_ROOT/wheelhouse" \
  --requirements "$AFO_WORK_ROOT/requirements.txt" \
  --raw-checkpoint "$AFO_RAW_CHECKPOINT" \
  --first-conversion "$AFO_CONVERSION_A" \
  --second-conversion "$AFO_CONVERSION_B" \
  --validation-receipt "$AFO_WORK_ROOT/validation/receipt.json" \
  --openfold3-source "$AFO_WORK_ROOT/openfold3-model-source"
```

命令同时生成 bundle directory 和 `.tar.zst`，并打印 archive size/SHA。再用另一全新输出目录
运行一次 builder；两个 `.tar.zst` 必须字节一致。最后检查：

```bash
sha256sum "$AFO_WORK_ROOT/bundle/$AFO_RELEASE_ID.tar.zst"
tar --use-compress-program=unzstd -tf \
  "$AFO_WORK_ROOT/bundle/$AFO_RELEASE_ID.tar.zst" >/dev/null
```

不要使用普通 `tar` 临时重打包；正式 builder 负责固定路径顺序、时间戳、uid/gid 和压缩参数。

## 7. 上传并登记 candidate

使用终端上传到 Hugging Face model repository：

```bash
hf auth whoami
hf upload knitua/Easydesign-afo \
  "$AFO_WORK_ROOT/bundle/$AFO_RELEASE_ID.tar.zst" \
  "releases/$AFO_RELEASE_ID/$AFO_RELEASE_ID.tar.zst" \
  --repo-type model \
  --commit-message "release: $AFO_RELEASE_ID"
```

记录上传产生的 Hub commit，并用该 commit 组成不可变 HTTPS URL；catalog 不能使用 `main`。
若发布 S3 镜像，也必须是只读对象，并具有相同 size/SHA。

在 `config/afo-releases.yaml` 新增条目：

```yaml
- release_id: afo-X-Y-Z-MODEL
  channel: candidate
  backend_version: X.Y.Z
  runner_commit: FULL_COMMIT
  wheel_sha256: FULL_SHA256
  raw_checkpoint_sha256: FULL_SHA256
  bundle:
    sha256: FULL_SHA256
    size_bytes: EXACT_BYTES
    archive_format: tar.zst
    sources:
      - source_id: huggingface
        region: official
        url: https://huggingface.co/knitua/Easydesign-afo/resolve/FULL_HUB_COMMIT/releases/RELEASE/RELEASE.tar.zst
```

candidate 必须显式写 `--release` 安装，不得提前成为 `runtime install all` 的隐式选择。

## 8. 公网安装验收

在没有旧 cache、旧环境或本地 bundle 的全新 Linux x86-64/A100 clone 中依次验证：

```bash
easydesign runtime install miniforge
easydesign runtime install afo --release "$AFO_RELEASE_ID"
easydesign doctor --full
```

还必须保存以下不可变 receipt：

1. 真实 HTTPS 下载中断后的续传；
2. 重复安装幂等；
3. 篡改 partial/cache 后进入 quarantine 且不污染 active profile；
4. 最小无 MSA A100 GPU smoke；
5. 显式 AFO/Protenix Stage 路由；
6. Stage 1、Stage 5、Stage 7 和 resume 对 release/profile/SHA 的冻结。

验证中不得预填本地 bundle，也不得把已有安装目录复制进新 clone。

## 9. 科学批准与 stable 提升

用冻结 panel 生成 validation report，随后由研究者人工审批：

```bash
easydesign runtime compare afo \
  --panel config/openfold3-validation-panel.yaml \
  --evidence workspace/reviews/afo/frozen-observations.json

easydesign runtime approve afo \
  --report runtime/validation/openfold3/REPORT/report.json \
  --reviewer REVIEWER \
  --decision approve-stable-promotion \
  --confirm
```

把 validation report SHA 和 approval receipt SHA 写入 catalog。最后使用单独的 science commit
把 `channel: candidate` 改为 `channel: stable`。提升后重新验证：

```bash
easydesign runtime install afo
easydesign runtime install all --detach
```

stable 只改变省略 release ID 的安装解析，不设置项目默认预测后端。

## 10. 当前 3.1.4 参考 identity

下面这些值只用于核对现有 release，不得复制到未来版本：

```text
release_id                 afo-3-1-4-of3-p2-155k
runner_commit              bc32b22ff5902e3daffd5d1f7203d7f2ab6cb997
runner_tree_sha256         ac3ee1345df68ebe3a67c2b9fe6287c92bc556303e8398f5e7d0b91b03255dfa
OpenFold3 model commit     f5df7b8099b3603779a965ce8ff91a5987cd3449
raw checkpoint sha256      af09eac4f29cef856633af07558cb143226fe95ebbef2c20921769d4a5f4bee4
converted weight sha256    0c9a00607352395486e33a98367810e1ad56c87459289f40974579525d3959cf
converted raw sha256       0de50b57b661cd3c6055c05870a312dee3263d1da61501a49d489651e208424b
runner wheel sha256        91b13810c3d51c18b75d0ad27b95b7448dee60933fa3688363c861dded0f7bf0
environment lock sha256    5a4afff0b432fe495d17e792ed7d14225f2e86ad0dc06de74ac12b06f6e75dca
conversion receipt sha256  93f6a3b394c63d874646a040291eaa6b92b3cf0bc2470b5aacb7d06fab89443c
archive size bytes         5032471381
archive sha256             83b6d8e895090a0c74d21e495d50b75a7cb031389386f5b7cd9843b6d3501afd
Hub commit                 5d03182f5487c5392236b4fb096875b6f660d902
validation report sha256   b645065c5614c95071143c5b44df051b0ea59bc2a3e180abc916f87e69370423
approval receipt sha256    03cab2913fe97058ee865157cee2d3a7aae88d522d247fecad64716c50c89f8c
```

当前 bundle 解包后的 `release-manifest.json`、`metadata/validation/receipt.json` 和
`SHA256SUMS` 是这组 identity 的最终交叉核对来源。
