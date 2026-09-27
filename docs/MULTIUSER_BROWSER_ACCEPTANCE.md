# 多用户真实账户后端浏览器验收

## 592e1e5 集成与比赛设置复验

集成分支 `codex/v3-multiuser-integration-20260927`，后端代码快照 `1f4ca10`。
本段为本轮集成结果，取代后文历史版本的当前状态判断。
配套的统一 Python 集成门已于 2026-09-27T16:18:22Z 通过：1,643 passed、11 skipped。

- Easy 最终 staging：`runtime/tmp/frontend-easy-build-20260927T155306297283`
- Professional staging：`runtime/tmp/frontend-workbench-build-20260927T143219336265`
- 真实账户服务 fixture：`runtime/tmp/multiuser-browser-integrated-20260927T155334/`；
  receipt 为该目录下 `browser-fixture.json`。服务仅使用合成账号，未配置计算 launcher，验收后已停止。
- 独立 CLI 浏览器连接实际 `MultiUserServer`，未拦截 API 响应。以下断言全部通过，页面异常数为 0：
  - 注册、管理员审核及登录。
  - Professional 在无执行器及管理员观察模式下禁用项目创建。
  - 无效或空的 GPU 配额不能保存；有效值持久化到后端。
  - 在管理员界面设置个人累计最终设计额度、Pilot/Scale 阶段预算为 **12 / 6 / 12**，
    保存后通过真实 API 核对一致。
  - 对该成员读取真实个人余额：额度 12、预留 0、已交付 0、剩余 12。
  - 管理员最终设计总览接口返回 200；无账本活动的账号可在用户管理/个人额度页查看，
    不要求出现在按账本活动聚合的总览中。

账号路由 fixture 浏览器回归：Easy **15 通过**，Professional **3 通过**。证据分别为：

- `runtime/tmp/frontend-easy-e2e-20260927T151627719014/`
- `runtime/tmp/frontend-workbench-e2e-20260927T151620710050/`

额外保留并执行了来源分支的豆豆与性能用例（原断言未放宽）：桌面/手机豆豆共 **6 项通过**，
桌面项目打开与 Site 切换性能 **1 项通过**。手机首次打开测试发现了两个可用性问题：
旧 demo 表格规则隐藏了“打开”列，浮动豆豆又遮住了底部入口。Live 专用移动样式现已恢复
动作列并留出滚动空间；按钮可点击且结构可加载。

**剩余性能限制：**同一手机性能用例仍未稳定满足首次打开小于 1,500 ms 的目标，原始配置
重复观察为约 1,564–1,745 ms。保留原性能断言；不将该用例记为通过。一个未改善结果的
renderer 预加载实验已撤回。相关证据：

- `runtime/tmp/upstream-easy-regression-cjs-20260927T153200/`
- `runtime/tmp/upstream-easy-mobile-fixed-20260927T154100/`
- `runtime/tmp/upstream-easy-mobile-repeat-20260927T154600/`

原聊天用例会重写仓库内 4 张文档 PNG；本轮确认它们仅为该测试生成后，已恢复为已提交版本。
运行日志和失败 trace 保留在唯一的 `runtime/tmp/` 输出中。没有修改测试阈值或参考快照来掩盖失败。

## 历史账户后端浏览器验收

记录时间：2026-09-27T11:10:57Z。当前开发工作树尚未提交；本记录不是部署或真实科学运行验收。

## 环境与证据范围

- 两个界面均由当前工作树 Vite 构建，输出：
  `runtime/tmp/multiuser-browser-build-20260927T105500/{easy,workbench}`。
  这是用于本轮交互检查的 staging，后续代码修改需要相应复验。
- 浏览器连接真实 `MultiUserServer`、`AccountStore` 和 scope façade，未拦截或伪造 HTTP 响应。
- 合成账户数据库与测试业务数据位于
  `runtime/tmp/multiuser-browser-20260927T105500/`；服务 receipt 为该目录的
  `browser-fixture.json`，日志为 `runtime/logs/multiuser-browser-20260927T105500.log`。
- 管理员、Alice、Bob 及团队均为专用合成 fixture。账户管理模式没有计算 launcher、模型或
  provider 凭据；本轮未创建真实科学任务，也未执行科学 Gate 审批。
- 本轮使用 DOM 可访问性状态和 HTTP 状态码进行断言。MCP 的文件访问根不包含开发 clone，
  因此没有保存截图，不以截图作为验收证据。

## 已通过的交互

| 场景 | 观察结果 |
| --- | --- |
| Alice、Bob 自助注册 | 真实注册成功，提示等待管理员审核 |
| 待审核 Alice 登录 | 被拒绝，页面展示账户未获批/停用信息 |
| 平台管理员审核 | 两个账户均从待审核变为已启用 |
| 普通用户登录 | Alice 登录成功，管理员后台入口不存在 |
| 团队显式共享 | Alice 创建 Alpha；Bob 接受邀请前只看到个人工作区 |
| 邀请与接受 | Alice 发出成员邀请，Bob 登录后看到邀请并成功接受 |
| 团队草稿协作 | Alice 创建 r1；Bob 看见同一草稿并保存新标题成为 r2 |
| 成员的执行边界 | 成员草稿界面无启动、邀请控制；直接 HTTP 启动返回 403 `team_admin_required` |
| 个人空间隔离 | Bob 读取 Alice 私有 scope 的项目列表返回 404 |
| Easy 团队入口 | 正确显示 Bob、Alpha、团队协作成员、未连接执行器；开始设计禁用 |
| Professional 团队入口 | 保持同一 team scope，显示成员和未连接执行器状态；可列出空项目工作区 |
| 跨标签页退出 | 账户页退出返回 200；已打开的 Professional 标签页跳回登录，旧用户和团队内容均消失 |
| 平台管理员观察 | 从后台进入 Alice 的 Easy scope，显示明确只读提示，开始设计禁用 |
| 观察者直接写请求 | 管理员尝试在 Alice scope 创建草稿返回 403 `read_only_scope` |
| 观察者审计 | 实际审计接口中可见对应 scope 的 `admin.scope.read` 记录 |

## 最终构建复验（2026-09-27T12:04:39Z）

前端后续修复后的构建：

- Easy：`runtime/tmp/frontend-easy-build-20260927T112120635917`
- Professional：`runtime/tmp/frontend-workbench-build-20260927T112133582509`

使用新的真实账户后端 fixture
`runtime/tmp/multiuser-browser-final-20260927T120317/`，以当前 clone 的 Node/Playwright
运行 DOM 与 HTTP 校验，没有保存截图或 trace。以下全部通过，浏览器页面异常数为 0：

1. 个人所有者处于账号管理模式时，Professional 的 `New project` 和
   `Create your first project` 均禁用，并显示未连接科学执行器的说明。
2. 平台管理员只读观察他人个人 scope 时，两个创建按钮均禁用，同时保留只读审计提示。
3. 管理员配额编辑将 GPU 槽位填为 0 或空值时，显示具体字段错误并禁用保存。
4. 填入有效值 2 后保存，实际后端返回 200；重新读取配额确认 `max_gpu_devices=2`。

最初发现的 Professional 创建控件问题已完成实后端复验。快速退出后立即登录的用户名清空现象
在前端专门回归中未复现；测试已断言新输入保留，不能把那次导航未稳定的观察说成鉴权失败。

最终账号路由 stub 浏览器回归另有 Easy 9 项、Professional 3 项通过；它们验证更完整的
角色组合、草稿冲突、跨标签页、旧 token 入口拒用，与上面的实后端记录分别计数。

## 未覆盖范围

未覆盖真实候选结果/结构下载展示、已存在项目的全部五个科学 Gate、真实 provider/GPU
科学执行。相关工程单元与子进程证据见主验收记录，不能由本轮账号浏览器结果推导。

两个临时账户服务均已停止；所有 fixture、日志和已生成证据保留，没有为复测删除数据库或覆盖其他工作区。
