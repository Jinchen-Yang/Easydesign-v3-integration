# 配置目录

- `development-policy.json`：Agent 指南路由、验证等级和聚焦测试映射。
- `runtime-assets.yaml`：安装器消费的运行资产目录。
- `assistant-provider.example.yaml`：结构助手凭据文件的字段示例，不含密钥。
- `backends/`：三个已有外部工具的可移植能力和版本要求。

没有实际文件的 defaults、filters 和 profile 子目录不再保留。站点路径和密钥只能放在
Git 忽略的 workspace runtime 或秘密管理系统中，不能提交。正式入口使用
`easydesign profile init/show/validate`；禁止扫描 Conda、权重目录或系统 Python。

`backends/protenix-v2.yaml` 只声明可移植能力和版本；服务器上的可执行文件、模型目录、
checkpoint 和 GPU 选择由 runtime profile 提供。sequence/FASTA 默认使用
`colabfold-public` remote MSA；provider preset 必须同时解析为 endpoint 和 Protenix
server mode。公共服务没有可承诺的可用性，重试和备用 provider 必须在用户 YAML 中
显式声明，禁止回退 no-MSA。endpoint/mode 的唯一运行时事实来源是
`resolve_protenix_msa_provider()`；本目录不复制一份可能漂移的映射。

`backends/scannet-epitope.yaml` 固定 ScanNet commit、epitope/no-MSA 模型和执行设备
规则。实际 Python/repository 绝对路径只存在于 runtime profile。CPU 是当前默认主线；
GPU 只能显式选择，
两者都禁止在运行中静默切换。站点上的 Conda prefix 不写入仓库。
