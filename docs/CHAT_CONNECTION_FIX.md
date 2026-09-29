# 豆豆聊天连接提示修复

核验日期：2026-09-30。应用版本 `e43731ad6a07817fc68750313e798bd2f3099c69`。

## 原因与修复

统一应用的 GuestView 使用固定演示，没有 AccountTransportContext。聊天面板因此使用普通
fetch 请求旧 `/api/rabbit/chat`；A/B 多用户后端实际使用带工作区的
`/api/v1/scopes/:scope/rabbit/chat`，旧地址返回 404。
前端未检查 HTTP 状态，直接把错误 JSON 中缺少 configured 字段解释为 false，
显示「聊天服务尚未连接」。这条提示不能证明模型服务没有配置。

本次修复：

- 演示页不请求旧接口，也不允许匿名发送；显示进入个人/团队工作区的说明及登录/选择工作区入口。
- 工作区内先检查 HTTP 状态和 configured 字段类型；401/403、读取失败、明确未配置分别处理。
- 连接读取失败提供重试；只有明确 configured=true 且当前用户可编辑时才允许发送。
- 忽略关闭面板或切换传输身份后迟到的状态响应，避免旧状态覆盖新工作区。
- 未开放匿名模型调用，未改变后端接口、科学执行权限或模型密钥。

## 实测

证据目录 `runtime/tmp/production-deploy/chat-diagnosis/`：

- 两站配置文件中的聊天凭证均可通过现有加载器正常读取，bridge 脚本存在；没有输出密钥。
- `a-probe.log`：通过主站现有普通 QA 账号登录，工作区聊天状态为 configured=true，
  DeepSeek 实际请求收到 51 字符回复、suggestions 和 done，无错误事件。
  只发送一条连接检查问候，未创建科研项目或执行科学审批；专用 QA 随后恢复 suspended，撤销会话。
- `unit.log`：144 项前端测试通过，包含访客零接口请求、404/503 重试、401 分类、
  明确未配置及旧响应不能覆盖新状态。
- `e2e.log`：8 项既有浏览器回归通过；TypeScript、构建及 dev-local 验证通过。
- `a-public-final.log`、`b-public-final.log`：两站公网实际页面显示工作区引导，
  不再显示错误的未连接提示，访客发出的聊天 API 请求数为零。
- `public-assets.json`：新构建变化资源及上一版主入口的公网 SHA256 核验。

首次公网检查的请求计数器错误地把 `/app/mascot/rabbit/` 图片也计为聊天请求；
已将计数限定为 `/api/` 路径后重新验证。原失败日志保留，没有修改产品以规避断言。

## 发布

先 B 后 A 更新至相同版本。每站静态目录为
`runtime/releases/chat-status-e43731a/{app,easy,workbench}`，包含 264 项文件；
历史 hashed 资产与 legacy 静态文件保留。生效 drop-in：`99-z-chat-status-e43731a.conf`。
源码差异只有 web/app 和文档，Python、科学代码及依赖不变。

各站 `runtime/backups/pre-chat-status-e43731a/` 保留 SQLite backup API 副本、旧源码、unit、
发布前后快照。切换前后用户完整行 hash 相同，SQLite quick_check=ok。
回退需先检查实时任务，禁用新 drop-in、恢复兼容代码/静态配置；保留现有数据库和研究数据。

主站可用的访问路径是：登录 → 我的工作区 → 进入 Easy 工作区 → 点击豆豆。
固定演示页即使已经登录，也需先选择工作区，让对话明确归属到该账号/团队。
