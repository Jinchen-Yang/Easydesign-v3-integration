# 资源与来源

Git 中只分发经过审查的小型资产：固定 VHH scaffold、filter profile、Target Viewer 静态文件
和许可证。长期来源登记见 `docs/ASSET_REGISTER.tsv`，机器可验证目录见
`config/runtime-assets.yaml`。

`official-vhh7-v1` 固定来自 BoltzGen 0.3.2 的官方 commit，包含七个 VHH scaffold 的
YAML/mmCIF 与上游 MIT license。运行时先验证 package data hash，再复制到不可变 attempt。

Target Viewer 固定 Mol* 5.11.0 的 `molstar.js`、`molstar.css` 和 LICENSE；无 CDN、无
source map、无 node_modules。`scripts/check_target_viewer_assets.py` 固定大小和 SHA-256，
Playwright 只属于开发测试环境。

重型环境和模型不进入本地 wheel，也不由本分支下载：

- PyMOL/PSE、Protenix-v2、ScanNet、BoltzGen、TNP 的独立环境；
- Protenix checkpoint/CCD/PDB data；
- ScanNet fixed source/models；
- BoltzGen fixed source、dataset 与五个 checkpoint；
- TNP fixed source。

它们只通过 `runtime link` 从已登记 source runtime 只读复用。link 首次验证环境 lock 与
inventory、文件 size/SHA-256、Git revision 和 registry revision；identity 变化后 fail
closed。模型运行启用 offline 策略，cache 写本产品 runtime，禁止向共享 source 写入。

任何升级都必须同时更新来源、license、lock/registry identity、adapter probe 与相关科学
回归；不能用“可导入”代替完整 backend 可运行证据。
