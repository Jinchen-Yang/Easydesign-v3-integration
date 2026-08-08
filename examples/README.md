# 示例目录

这里只放经过审计、允许在当前私有仓库内共享的示例。每个示例必须声明输入 checksum、配置、
预期 manifest 和证据等级，并区分软件 mock、`smoke-validated` 与
`scientifically-validated`。完整大型运行树放在 `runs/` 或外部存储，不进入 Git；
仅允许提交显式任务批准、逐文件校验且移除后端中间目录的精简证据包。

Stage 01 APOE 示例的用户输入只有 FASTA、`easydesign.yaml` 和来源审计记录。Protenix
JSON 必须由 adapter 在 run 的 attempt 中生成，不能作为用户输入 fixture 提交。

[`apoe-pse-manual-regions.yaml`](apoe-pse-manual-regions.yaml) 展示 schema 0.6 的
`user-provided/residue-list`：用 auth chain A 指定与 runtime-only APOE PSE 红/蓝/黄
完全相同的三组残基。配置文件可以提交，但原始 PSE 不进入 Git。该示例只证明编号导入与
provenance 契约，不代表三组区域已经科学验证为 APOE binding sites。

[`apoe-ui-demo`](apoe-ui-demo/README.md) 是 DATA-004 生成的真实只读证据包。Local 分支
保持其 307 个文件和 checksum 原样，仅用于 manifest/report 回归，不索引或继续其中的
run。包内 README 的旧 UI 启动命令属于冻结历史说明，本产品不提供该 UI；数据验证通过
`reporting.verify_evidence_bundle` 完成。
