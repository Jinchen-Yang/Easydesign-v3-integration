# Agent 指南：UI 与报告

仅在修改 `src/easydesign/ui/`、`reporting/`、`web/` 或浏览器资产时读取。

## 产品与安全边界

- UI、CLI 和报告只消费 Python API 的类型化投影；不得解析终端文本、扫描 run 目录、
  复制科学阈值或暴露绝对路径。
- 默认页面使用中文产品语义；manifest、checksum、内部 ID 只进入技术记录。
- artifact 下载必须从 manifest 验证路径、大小和 SHA-256，并保持 localhost-only/CSP。
- PyMOL 与 Mol* 读取同一 verified structure；PML 是可视化事实，不是科学批准。
- 一个容器只拥有一个 Viewer；保持 generation token、串行加载、可见结构和触摸缩放回归。
- Stage capability、单次 run 状态、科学停止、运行失败和 demo replay 使用不同字段。

## 开发与构建

- 日常 UI 开发使用 `scripts/dev.py ui` 和非 18769 端口；development 模式禁用
  Suzhou2/Managed Worker 操作。
- `dev-local`/`integration` 的 Web build 只写 `runtime/` staging，不发布
  `src/easydesign/ui/static/`。
- 只有显式 `release` 才发布 React 构建产物、构建正式 wheel、重启 18769。
- UI 源变更补充对应 TypeScript/Playwright 与 Python projection 测试；普通局部变更先跑
  Chromium 聚焦用例，release 再跑完整浏览器矩阵。
- 修改 Mol*、PyMOL、PML、CSP、服务或 package data 时读取相应产品规范；不要为普通
  文案或 projection 修复加载全部科学 Stage 文档。
