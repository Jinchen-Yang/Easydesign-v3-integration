# 配置目录

- `defaults/`：可移植默认值。
- `backends/`：外部工具能力和版本要求。
- `filters/`：版本化、体系专属科学筛选规则。
- `profiles/local/`：本地执行参数。
- `profiles/smart/`：未来 SMART/Slurm 执行参数。

站点路径和密钥只能放在被忽略的本地配置或环境变量中，不能提交。

`backends/protenix-v2.yaml` 只声明可移植能力、版本和环境变量名；服务器上的可执行文件、
模型目录和 GPU 选择由本地 profile 或显式调用参数提供。

`backends/scannet-epitope.yaml` 固定 ScanNet commit、epitope/no-MSA 模型、显式
Python/repository 环境变量和执行设备规则。CPU 是当前默认主线；GPU 只能显式选择，
两者都禁止在运行中静默切换。站点上的 Conda prefix 不写入仓库。
