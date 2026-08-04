# Coding Agent 工作协议

本文件只保存所有任务都适用的安全内核和开发入口。专项规则按任务路径读取；不要在每轮
对话重复读取完整项目文档。

## 1. 安全内核

1. 用户输入、科学 run/manifest、activation release、唯一证据、环境和模型禁止擅自
   删除或覆盖；先完整阅读 `DATA_SAFETY.md`，并取得用户对精确目标的本次批准。
2. 保留用户和其他 Agent 的修改。开始写入前检查工作树；发现重叠修改时停止，非重叠
   修改可以继续但必须精确提交本任务文件。
3. 可再生开发 cache、bytecode、空占位和无引用 build 经精确检查后直接删除，不归档；
   业务运行时不得自动清理。远程操作只使用已配置 executor，禁止扫描 SSH config。
4. 官方开发保持唯一 `main`。已锁定且提交已进入 `main` 的历史 worktree/branch 只警告；
   未合并 branch、未锁定额外 worktree 或未知修改会阻止写入。
5. 相邻问题不阻塞当前验收时只在交付中报告；不得自动扩大范围、升版、部署或另开任务。

## 2. 任务模式

- `inspect`：只读分析，不写文件、不运行发布或运维动作。
- `dev-local`：默认模式；局部实现、风险分级测试、提交并推送 `main`。不升版本、不生成
  正式 wheel、不发布静态资产、不重启 18769、不访问 Manager。
- `integration`：公共契约、scientific/core/managed protocol 或跨子系统变更；运行完整
  Python 回归及相关浏览器测试，但仍不自动发布。
- `release`：只有用户明确要求发布时使用；允许升版、正式构建、18769 activation 和
  Manager 同步。
- `ops`：用户明确要求的部署/恢复/观察；不得顺带修改代码或科学事实。

任务不能静默升级到 `release` 或 `ops`。实现中发现需要扩大授权时先交付当前安全边界并
请求用户决定。

## 3. 按需读取

每个逻辑任务先运行：

```bash
.venv/bin/python scripts/dev.py context --mode MODE --path PATH
```

首次读取命令列出的指南并记录 `policy_bundle_id`。同一任务的后续轮次、状态询问和自动
上下文压缩只需传 `--known-bundle-id` 复核；ID 未变时不得重读全文。任务范围增加时只读
新增指南。新线程或新 Agent 必须独立运行一次。

| 路径或动作 | 必读指南 |
| --- | --- |
| `src/easydesign/core|stages|backends|filtering|orchestration/stage*`、`docs/workflow/` | `docs/agent/SCIENTIFIC_PIPELINE.md` |
| `src/easydesign/ui|reporting/`、`web/` | `docs/agent/UI_AND_REPORTING.md` |
| workspace、setup、registry、环境、资产、run、迁移、归档 | `docs/agent/RUNTIME_AND_DATA.md` |
| 版本、依赖、package data、wheel、18769、remote、Manager、systemd | `docs/agent/RELEASE_AND_REMOTE.md` |

`docs/CHARTER.md` 只在产品范围变化时读；`docs/ARCHITECTURE.md` 只在稳定接口或依赖
方向变化时读；`docs/ROADMAP.md` 只在路线图状态变化时读。Stage 任务只读
`docs/workflow/` 中该 Stage 的主文档和 status，不读其余六个 Stage。

## 4. 实现与验证

科学逻辑只放在 `src/easydesign/`；CLI、UI 和 scripts 只调用统一 API。禁止静默 fallback、
扫描目录猜 artifact、伪造成功或把工程 smoke 写成科学验证。

使用以下唯一验证入口：

```bash
.venv/bin/python scripts/dev.py verify --mode MODE
```

验证器根据变更路径选择测试，并在模式过低时拒绝继续。`dev-local` 不允许写 `dist/`、发布
UI 静态资产或访问远端；`release` 才运行完整 build 和 activation 门。

普通修复只通过 commit 和测试记录。仅当 Stage 契约、路线图状态、验证等级或 Blocked
实际变化时更新 Stage 文档或 ROADMAP；完成的跟踪事项才写带 RFC 3339 时间的历史。

提交前确认 scoped diff 和 `git diff --check`，使用 Conventional Commit。推送前再
`git fetch origin` 并核对 ahead/behind；推送后核对 `HEAD == origin/main`。CI 可读取时
等待终态，否则明确报告 commit 与 pending 状态。

## 5. 阻塞

只有产品/科学选择、权限许可、不可逆操作、任务范围扩大或无法绕开的重叠修改需要询问。
可恢复的测试和依赖问题先自行诊断，但不得因此升级发布范围或修改系统全局配置。
