# 配置目录

- `defaults/`：可移植默认值。
- `backends/`：外部工具能力和版本要求。
- `filters/`：版本化、体系专属科学筛选规则。
- `profiles/local/`：本地执行参数。
- `profiles/smart/`：未来 SMART/Slurm 执行参数。

站点路径和密钥只能放在被忽略的本地配置或环境变量中，不能提交。

`backends/protenix-v2.yaml` 只声明可移植能力、版本和环境变量名；服务器上的可执行文件、
模型目录和 GPU 选择由本地 profile 或显式调用参数提供。

`backends/scannet-epitope-gpu.yaml` 固定 ScanNet commit、epitope/no-MSA 模型、显式
Python/repository 环境变量和 GPU-only 规则；站点上的 Conda prefix 不写入仓库。
