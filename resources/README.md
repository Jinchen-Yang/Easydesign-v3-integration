# 资源与来源

`scaffolds/vhh/` 只允许存放经过审查、允许再分发的小型 VHH scaffold。
`provenance/ASSET_REGISTER.tsv` 是资产来源的事实来源。每项资产使用前必须记录稳定
身份、文件 checksum、来源、不可变版本、许可证、用途、再分发权和审查状态。

Stage 03 已引入 `official-vhh7-v1`：它来自 BoltzGen `0.3.2` 的固定官方 commit，
包括七个 VHH scaffold 的 YAML/mmCIF 和上游 MIT license。文件由 Python package
data 分发，运行时先验证固定 SHA-256，再复制到不可变 attempt；不使用旧仓来源不明的
scaffold。权重和大型数据不得进入 Git。

固定 registry：

```text
7eow, 7xl0, 8coh, 8z8v, gontivimab, isecarosmab, sonelokimab
```

升级 registry 必须同时更新来源 commit、逐文件 hash、license、package-data 测试、
Stage 03 backend 校验和资产登记。

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
