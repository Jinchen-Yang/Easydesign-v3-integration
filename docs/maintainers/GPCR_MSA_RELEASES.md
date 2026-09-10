# GPCR MSA release 维护手册

本手册只面向维护者离线生产数据 release。研究者接口不提供 Stockholm 转换、批量建库、
模板数据库扫描、服务器部署校验或独立 AFO 推理。

## 输入与输出

构建必须同时提供只读 Stockholm tar.gz 和每个 accession 的 canonical FASTA。source-only
结果不能发布为 schema 1.0；缺 FASTA、query 不唯一、重复 canonical sequence、任何转换
失败或 checksum 变化都会保留 staging 并拒绝发布。

```bash
.venv/bin/python scripts/maintainers/gpcr_msa_release_builder.py build \
  --source /path/to/gpcr-stockholm.tar.gz \
  --targets /path/to/canonical-fastas \
  --release-id gpcr-msa-YYYYMMDD-vN \
  --output-root runtime/databases/gpcr-msa/gpcr-msa-YYYYMMDD-vN
```

若某些 Stockholm query row 无法自动唯一识别，可以增加只读 JSON mapping：

```bash
  --query-names /path/to/accession-to-row-name.json
```

输出不可覆盖，且固定包含：

```text
<release-id>/
├── library-manifest.json
├── entries/<canonical-sequence-sha256>.a3m
└── release-receipt.json
```

生产工具不含主机名、数据盘或 clone 的固定绝对路径。新 release 完成独立 review/备份后，
才可注册到其他 clone 的 `runtime/databases/gpcr-msa/`。现有 schema 0.2 source-derived 库只
用于兼容解析，不得原地改写成 1.0 或补写伪造 release receipt。
