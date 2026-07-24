# ADR-0001：Stage 01 使用便携式本地 Mol* 报告

- 状态：`accepted`
- 日期：2026-07-24
- 决策范围：Stage 01 reporting、静态资产、失败语义和本地服务

## 背景

Stage 01 已能从 sequence/FASTA 预测和 PyMOL PSE 导入发布规范 Target Bundle。使用者需要
在进入 Stage 02 前直接查看最终 `target.cif`、残基编号映射、来源和整体质量，但正式
artifact 不能被 UI 改写，远程服务器也不能暴露整个 run 或把私有结构上传到第三方网站。

## 决策

1. 使用 Mol* `5.11.0` 直接渲染 mmCIF，不生成展示专用 PDB。
2. 每个报告包含本地 Mol* JS/CSS、MIT license、CIF、FASTA、mapping 和最小安全
   `viewer-data.json`；页面不引用 CDN 或外部 API。
3. 报告是只读派生产物，使用独立 `report-XXXX` revision 和 report manifest，不进入
   StageManifest。Stage 01 的科学成功以正式 Target Bundle 和 manifest 为准。
4. 报告生成失败不推翻 Stage/Run success，也不阻止 Stage 02 消费 Target Bundle。最新
   report 失败时明确拒绝打开，不自动回退旧成功 revision。
5. PSE 颜色通过 `(label_asym_id, label_seq_id)` 映射显示，但永远标注为
   `uninterpreted annotation`；首版不保存 hotspot 或人工选择。
6. 查看服务只绑定 `127.0.0.1`，在启动前验证 report manifest 和全部 checksum，server
   root 只包含一个 report revision；远程访问采用 SSH 端口转发。
7. Mol* 发布字节从官方 npm tarball提取并固定 SHA-256。Node.js 22、npm 和 Playwright
   只用于资产维护和浏览器测试，Python wheel 与运行时不依赖 Node。
8. Mol* 5.11.0 官方预构建 bundle 初始化时使用动态函数，因此 `script-src` 需要
   `'unsafe-eval'`。该例外只适用于经过 checksum 验证的本地同源 bundle；CSP 仍禁止外部
   script/connect，页面不渲染用户 HTML，服务也不暴露 run 其他目录。

## 理由

- Mol* 原生支持 mmCIF、序列面板、残基选择和多种 representation，能复用 Stage 01 的
  规范结构与 label/auth mapping。
- 自包含报告便于复制、归档和离线审核，也避免公开 CDN、第三方上传和整个 run 暴露。
- 独立 reporting revision 保持科学 artifact 不可变，同时允许修复页面或重新生成报告。
- 将 reporting failure 与科学 failure 分离，可避免可视化/WebGL/磁盘问题伪装成结构
  预测失败，或反过来把页面成功误报为科学验证。

## 后果

- 每个 report 约增加 5–6 MB 静态资产；当前接受该成本以换取便携性和最小暴露面。
- 官方预构建 bundle 不能使用完全禁止 eval 的 CSP；若未来能固定经审计的 CSP-compatible
  Mol* build，应通过新资产 revision 移除此例外。
- Mol* 更新必须同步 npm lockfile、固定字节、SHA-256、资产登记、许可证审查和 Chromium
  测试。
- 第一版桌面 Chromium 通过自动验收；Safari/Firefox、Stage 02 overlay、人工批准和远程
  托管另立决策，不在本 ADR 内。
