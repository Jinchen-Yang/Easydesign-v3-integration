# 资源与来源

`scaffolds/vhh/` 只允许存放经过审查、允许再分发的小型 VHH scaffold。
`provenance/ASSET_REGISTER.tsv` 是资产来源的事实来源。每项资产使用前必须记录稳定
身份、文件 checksum、来源、不可变版本、许可证、用途、再分发权和审查状态。
`configs/runtime-assets.yaml` 是自包含安装器实际消费的机器目录；当前登记 15 项
runtime 资产。两者必须在同一次提交中同步：前者负责长期来源审计，后者负责下载、
许可确认、大小和 SHA-256 校验。

Stage 03 已引入 `official-vhh7-v1`：它来自 BoltzGen `0.3.2` 的固定官方 commit，
包括七个 VHH scaffold 的 YAML/mmCIF 和上游 MIT license。文件由 Python package
data 分发，运行时先验证固定 SHA-256，再复制到不可变 attempt；不使用旧仓来源不明的
scaffold。权重和大型数据不得进入 Git。

BoltzGen runtime 除固定源码和 molecule dataset 外，还显式登记 diverse、adherence、
inverse-fold、folding 和 affinity 五个 checkpoint。EasyDesign 只把校验后的仓库内
路径传给隔离子进程，并启用 offline mode；缺少任一资产时 backend 不得显示为可用，
也不得让上游库按 Hugging Face ID 静默联网。大型资产只进入 Git 忽略的
`runtime/models/`，新工作区下载前必须完成对应许可确认。

固定 registry：

```text
7eow, 7xl0, 8coh, 8z8v, gontivimab, isecarosmab, sonelokimab
```

升级 registry 必须同时更新来源 commit、逐文件 hash、license、package-data 测试、
Stage 03 backend 校验和资产登记。

Stage 01 Target Viewer 与 Stage 01/02 浏览器 PyMOL 是当前随 Python wheel
分发的第三方前端资产。Mol* 规则如下：

- 固定 Mol* `5.11.0` 官方 npm tarball；
- 只提取 `build/viewer/molstar.js`、`molstar.css` 和根 `LICENSE`，不提交
  `node_modules`、source map、示例图片或 CDN 引用；
- `molstar.js` 保留上游生成的 `Bundled license information`，包含 React、scheduler、
  react-dom 和 immutable 的相应版权/许可证 notice；
- `scripts/check_target_viewer_assets.py` 固定三个文件的大小和 SHA-256；
- `web/target-viewer/package-lock.json` 记录完整开发依赖图；Node 和 Playwright 只用于
  资产维护与测试，不属于 EasyDesign Python runtime。

任何 Mol* 升级必须重新检查 npm integrity、bundle license notices、静态字节、wheel
内容和浏览器测试，不得把“npm package 标记为 MIT”当成跳过 bundle 依赖审查的理由。

浏览器 PyMOL 固定复用 ChatPyMol commit
`43517d2dc0795357f35f93a2bde8cfc442f568c5` 已审计的离线运行资产：

- Pyodide `0.22.1`，Apache-2.0；
- NumPy `1.23.5` Emscripten wheel，BSD-3-Clause；
- Open-Source PyMOL WASM `2.6.0a0`，Open-Source PyMOL license；
- EasyDesign 移植浏览器渲染、完整 PML 请求/响应循环、关键词 Skill 路由和
  六份经审计的 PML Skill；参考说明文档 SHA-256 固定为
  `22567ed89e0aef96cdab56b114ee98ade20540bcf42876e97738712429b0fa8f`；
- 不移植 ChatPyMol 的 Node 文件库、第二套项目系统、MCP、用户主目录写入或删除接口；
- `scripts/check_browser_pymol_assets.py` 固定运行必需文件的大小和 SHA-256；
- 所有资产只从 EasyDesign wheel/localhost 提供，页面不得访问 CDN。

PyMOL 是 Schrödinger, LLC 的商标；EasyDesign 是独立项目，并非其官方产品，
也未获其背书。升级任一浏览器资产必须重新审计许可证、逐文件 hash、wheel 内容、
触摸交互和离线浏览器测试。

Stage 07 的 TNP 仅作为独立 runtime 使用，不随 wheel 分发源码、模型或依赖：

- 固定 TNP commit `29dcac72f1380e8538e8870f45a699d3c6156162`；
- 固定上游为 `https://github.com/oxpig/TNP.git`；
- 固定上游 BSD-3-Clause `LICENCE` 与 `bin/TNP` 源文件 SHA-256；
- `environments/tnp.yml` 固定 Python 3.10、ANARCI、Biopython、DSSP、
  ImmuneBuilder/NanoBodyBuilder2、Torch 和直接数值依赖；
- EasyDesign doctor 要求 source checkout 为 clean fixed commit，并执行 import/help probe；
- TNP 运行产生的模型、权重、JSON、liability CSV 和结构只进入 Git 忽略的 run；
- 公开 release 前仍需重新审查 TNP 及其完整依赖图、模型下载来源和再分发边界。

TNP 官方说明固定 Biopython `1.77`。ANARCI 的官方 Bioconda 版本字符串是
`2024.05.21`，其 Python distribution metadata 为 `1.3`。TNP 官方链接的 salilab DSSP
`3.0.0` 在当前求解结果中会错误寻找 Boost `1.73` ABI，因此真实验证环境固定采用
conda-forge DSSP `4.6.1` 与 Boost `1.90`。ImmuneBuilder/PDBFixer 所需的
`pkg_resources` 由 setuptools `80.9.0` 保留；TNP `setup.py` 未声明但 CDR3
compactness 会直接导入的 scikit-learn 固定为 `1.7.2`。任何环境升级必须重新运行真实
batch smoke，不能只通过 import 就宣称兼容。
