# 资源与来源

Git 中只分发经过审查的小型资产：固定 VHH scaffold、filter profile、Target Viewer 静态文件
和许可证。长期来源登记见 `docs/ASSET_REGISTER.tsv`，机器可验证目录见
`config/runtime-assets.yaml`；可替换的下载传输候选单独登记在
`config/runtime-sources.yaml`。

`official-vhh7-v1` 固定来自 BoltzGen 0.3.2 的官方 commit，包含七个 VHH scaffold 的
YAML/mmCIF 与上游 MIT license。运行时先验证 package data hash，再复制到不可变 attempt。

Target Viewer 固定 Mol* 5.11.0 的 `molstar.js`、`molstar.css` 和 LICENSE；无 CDN、无
source map、无 node_modules。`scripts/check_target_viewer_assets.py` 固定大小和 SHA-256，
Playwright 只属于开发测试环境。

重型环境和模型不进入本地 wheel。它们必须按锁定配方安装到当前 clone 的 `runtime/`：

- PyMOL/PSE、Protenix-v2、ScanNet、BoltzGen、TNP 的独立环境；
- Protenix checkpoint/CCD/PDB data；
- ScanNet fixed source/models；
- BoltzGen fixed source、dataset 与五个 checkpoint；
- TNP fixed source。

`easydesign runtime plan/install` 按固定配方和身份 lock 安装，并验证环境
inventory、文件 size/SHA-256、Git revision 和 registry revision；identity 变化后 fail
closed。`--source` 只选择传输候选；任何镜像结果仍需通过同一 SHA-256 或 commit，且实际
来源进入 receipt。模型运行启用 offline 策略，cache 始终写当前 clone 的 runtime。另一个 clone 的
环境、模型或 registry 不能作为本产品运行来源。

任何升级都必须同时更新来源、license、lock/registry identity、adapter probe 与相关科学
回归；不能用“可导入”代替完整 backend 可运行证据。
