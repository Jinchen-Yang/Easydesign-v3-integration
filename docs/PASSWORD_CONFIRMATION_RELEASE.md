# 注册确认密码与浏览器凭证识别

发布日期：2026-09-30（Asia/Shanghai）。A/B 应用版本：
`f2cc3c5fc8dcb1c18214cb297b188d422ca89c02`。

## 行为

- 注册新增必填的「确认密码」。两次密码不同会显示中英提示、禁用注册按钮；
  提交处理也会检查，按 Enter 或直接触发表单提交都不会发送不一致的注册请求。
- 修改第一栏密码会重新检查确认栏。注册成功或切换登录/注册时清除密码和确认密码。
- 用户名使用明确的 label/id/name 和 `autocomplete=username`，关闭自动大写与拼写检查。
- 登录、会话恢复使用 `current-password`；注册、确认和修改后的密码使用 `new-password`。
  修改密码和会话恢复表单同时提供所属用户名，便于密码管理器关联账号。
- 已提供浏览器标准字段语义；是否弹出保存/生成密码提示仍由浏览器及用户设置决定。
- 确认密码是注册表单的防输错校验，不增加第二种身份认证。后端注册接口保持原契约，
  不上传第二份密码。邮箱验证未加入。

## 验证

证据目录：`runtime/tmp/production-deploy/password-confirm/`。

- `unit.log`：138 项前端测试通过，新增中英两种场景验证不一致零请求、修改原密码后重新校验、
  匹配后的注册请求、清除密码及 autocomplete 语义。
- `e2e.log`：现有 8 项浏览器回归通过。TypeScript 检查和 Vite 构建通过。
- `local-browser.log`：真实 Chrome 中不一致零请求，匹配后一次模拟成功请求。
- `a-live-browser.log`、`b-live-browser.log`：两站公网均确认不一致零请求、字段语义、中英切换和手机布局。
  匹配后使用既有 QA 用户名请求真实注册接口，返回预期的 409/username_unavailable；没有创建或修改账号。
  不把该重复用户名检查描述为新账号创建成功；正常创建路径由前端回归及既有后端验收覆盖。
- `public-assets.json`：新构建资源及旧主入口的公网哈希和入口页面核验结果。
- `dev-local.log`：局部工程验证通过；`release-verify.log` 中 make check 通过。
  曾额外启动全量后端回归，确认 Python/科学源码与依赖相对上线基线完全未变后停止重复验证，
  停止时为 76 passed、11 skipped。该日志是主动中断，**不是本轮全量 release 通过**。
  后端既有验证证据保留在主交接文档；本轮验收依据为改动范围内的前端测试、构建和公网检查。

## 部署与保留

两站各自的新静态目录为 `runtime/releases/password-confirm-f2cc3c5/{app,easy,workbench}`，
新增 systemd drop-in 为 `99-password-confirm-f2cc3c5.conf`。
原构建 81 个文件，补留历史 app 资源和 legacy 静态文件后各站 release 清单含 248 个文件。
原有 legacy 入口若已经使用统一 SPA，则同步指向新入口；其他 legacy 资源保留。

源应用与科学依赖未改变，只更新前端源码和文档。B 先发布并通过公网检查，再发布 A。
服务仅停止 Web 主进程，保留科学执行进程；没有 GPU 重置或科研审批。

- A：8 用户、2 团队、2 成员关系、25 admissions 前后一致，用户完整行 hash 一致。
  既有 held 请求的 id/request_id/state/worker_pid/worker_start 均保持一致；该 PID 发布前已不在 /proc，
  没有据此宣称仍有存活 worker 或执行科学恢复操作。
- B：18 用户、2 团队、3 成员关系、46 admissions 前后一致，无活动 admission，用户完整行 hash 一致。
- 两站 SQLite quick_check 均为 ok。备份位于各自 `runtime/backups/pre-password-confirm-f2cc3c5/`，
  包括 SQLite backup API 副本、旧源码、unit、发布前后快照。

回退时先检查实时任务，保留当前数据库，停 Web 主进程后禁用新 drop-in，恢复旧源码/静态配置并启动。
禁止用旧数据库覆盖新用户或研究记录。以前的 release 和配置仍保留。

A 先前单卡驱动异常不属于本次修改范围，也未在本轮重新验收或修复。
