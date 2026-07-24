# 资源与来源

`scaffolds/vhh/` 只允许存放经过审查、允许再分发的小型 VHH scaffold。
`provenance/ASSET_REGISTER.tsv` 是资产来源的事实来源。每项资产使用前必须记录稳定
身份、文件 checksum、来源、不可变版本、许可证、用途、再分发权和审查状态。

当前没有导入任何旧仓 scaffold、模型权重或第三方结构。权重和大型数据不得进入 Git。

Stage 01 Target Viewer 是当前唯一随 Python wheel 分发的第三方前端资产：

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
