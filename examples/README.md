# 示例目录

这里只放最小、可复现、允许再分发的示例。每个示例必须声明输入 checksum、配置、
预期 manifest 和证据等级，并区分软件 mock、`smoke-validated` 与
`scientifically-validated`。大型运行树放在 `runs/` 或外部存储，不进入 Git。

Stage 01 APOE 示例的用户输入只有 FASTA、`easydesign.yaml` 和来源审计记录。Protenix
JSON 必须由 adapter 在 run 的 attempt 中生成，不能作为用户输入 fixture 提交。
