# 配置目录

- `defaults/`：可移植默认值。
- `backends/`：外部工具能力和版本要求。
- `filters/`：版本化、体系专属科学筛选规则。
- `profiles/local/`：本地执行参数。
- `profiles/smart/`：未来 SMART/Slurm 执行参数。

站点路径和密钥只能放在被忽略的本地配置或环境变量中，不能提交。

`backends/protenix-v2.yaml` 只声明可移植能力、版本和环境变量名；服务器上的可执行文件、
模型目录和 GPU 选择由本地 profile 或显式调用参数提供。sequence/FASTA 默认使用
`colabfold-public` remote MSA；provider preset 必须同时解析为 endpoint 和 Protenix
server mode。公共服务没有可承诺的可用性，重试和备用 provider 必须在用户 YAML 中
显式声明，禁止回退 no-MSA。endpoint/mode 的唯一运行时事实来源是
`resolve_protenix_msa_provider()`；本目录不复制一份可能漂移的映射。

`backends/scannet-epitope.yaml` 固定 ScanNet commit、epitope/no-MSA 模型、显式
Python/repository 环境变量和执行设备规则。CPU 是当前默认主线；GPU 只能显式选择，
两者都禁止在运行中静默切换。站点上的 Conda prefix 不写入仓库。
