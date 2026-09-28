# test.easydesign.pro 开发与部署对应关系

核验日期：2026-09-29（北京时间）。这是本次开发的基线快照，不代表之后自动同步。

| 角色 | 目录 | 核验结果 |
| --- | --- | --- |
| 本次唯一开发树（cloudlay） | `/home/cloudlay/Code/Easydesign-v3-integration` | 分支 `codex/v3-multiuser-integration-20260927`；开始开发前干净 |
| test 实际运行目录（苏州二） | `/data/Easydesign-v3-test` | 服务工作目录、实际进程 cwd、Python 模块来源均指向这里；工作树干净 |
| test 前端构建（苏州二） | `/data/Easydesign-v3-test/runtime/releases/ui-fa9ee24/{easy,workbench}` | 运行进程的 `--easy-web` / `--web` 参数解析到这些目录 |

共同基线提交：`fa9ee2408cdeac8b17b1f23ef883b0c64fbfd06f`，
`fix(site): recognize verified GPCR outer-pore mechanisms`。

线上服务为 `easydesign-v3-test.service`，监听 `127.0.0.1:18771`，
配置的公开 origin 是 `https://test.easydesign.pro`。公开 `/account/` 和同服务源站响应
均为 688 字节，SHA-256 为
`ee9c43fa5efc5648e63608189c3bf9f88a915829f9cd111ff364b036515a99c2`。
公开 `/easy/assets/account-BAsZliUl.js` 与实际 release 文件均为 35109 字节，
SHA-256 均为 `dad2894a19f5dcabd5f118ace75704a3942930cf252444182ee50e235a3f765d`。
没有根据可能陈旧的 systemd Description 或目录名称判断版本。

## 不属于本次开发目标的目录

- `/home/cloudlay/Code/Easydesign-v3-multiuser`：同仓库的旧主工作树，提交
  `71f924c8930d341837611e06081144c535e18c88`。已全部包含在集成树中；集成树另外有
  35 个提交。保持原状，不在此实现本批优化。
- `/home/cloudlay/Code/Easydesign`：旧 UI `main`，提交
  `3c911cade01e19c8d69f9d1903116794dfd04369`，不是当前 test 的开发基线。
- 苏州二 `/data/Easydesign-final`：独立且仍在推进的开发线；本轮先后看到提交
  `3af3a9f1605c9b5a8437ad17c013fd5cfa65a8bd` 和
  `51bccf7affb658783a89bf4df9b867861fb719cd`。它不是 test 的运行目录，后续还可能变化。

## 本次拓扑例外与发布边界

旧主工作树干净且其 HEAD 是当前集成树的祖先，但 Git 不允许锁定主工作树。
用户本次明确允许保留它原状，只在 integration 开发；没有修改检查器、伪造锁、改分支名、
新建或删除工作树。其余数据、测试与科学权限规则仍生效。

本地 V3 的 `suzhou2-snapshot` remote 是历史本地 Git bundle，**不是实时苏州远程**；
集成分支没有 upstream。不得把向该 bundle 的操作当作推送成功，也不得为推送改写其他目录。

开发提交、测试通过、线上发布是三件不同的事。此基线核验未修改线上代码、服务、数据库、
科学任务或前端构建。正式切换必须再次核对线上 HEAD、保存数据备份和回退对应关系。

本批缓存改动发布前还须验证：旧页面引用的内容哈希资源在切换后和回滚后仍能读取。
3D 查看器会延迟加载脚本；仅保留旧 release 目录或假定 CDN 已缓存并不足够。
发布流程需保留可路由的旧 assets（同名必须校验内容完全一致，不覆盖不同内容），
或提供显式版本化资源路径，并验证跨版本打开的页面。此项尚未部署实施。
