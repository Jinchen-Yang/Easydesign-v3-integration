# 多用户产品的本地启动与验收

产品权限以 [多用户契约](MULTIUSER_PRODUCT_CONTRACT.md) 为准；测试证据以
[验收记录](MULTIUSER_ACCEPTANCE.md) 为准。以下操作针对独立开发 clone，不能作为切换生产服务的授权。

## 准备当前 clone

- 使用当前 clone 的 `.venv`、`runtime/`、`workspace/` 和冻结依赖。
- 新环境可用 `scripts/bootstrap.py --extra agent` 安装原生 Agent 所需的锁定依赖；
  bootstrap 会拒绝覆盖已有 `.venv`。已有环境必须先按环境维护流程检查。
- Easy 与 Professional 分别从 `web/easy/`、`web/workbench/` 的锁文件安装和构建。
  开发验收把构建输出指定到当前 clone 的唯一 `runtime/tmp/` 子目录。
- Easy 的产物必须同时包含 `index.html` 和 `account/index.html`；正常科研模式还要求
  Professional 的 `index.html`。所有产物路径都必须位于当前 clone。

## 初始化首位系统管理员

在 clone 根目录运行：

```bash
.venv/bin/python -B -m easydesign.product.accounts_cli bootstrap-admin \
  --username workspace-admin --display-name 管理员
```

密码通过终端隐藏输入并二次确认，不应出现在命令参数、日志、报告或浏览器录像中。
自动化入口支持 `--password-stdin`，应由现有秘密管理渠道直接提供输入。
首位管理员已存在时该命令拒绝再次初始化，不能用它覆盖账户数据库。

账户与会话状态位于当前 clone 的 `runtime/state/accounts/accounts.sqlite`。
将其与团队关系、资源准入和审计一并视为持久业务数据，不能当测试 cache 清理。

## 账户管理调试

用实际构建目录替换下列占位路径：

```bash
.venv/bin/python -B -m easydesign.product.server \
  --multi-user --accounts-only --port 14383 \
  --easy-web runtime/tmp/BUILD/easy \
  --web runtime/tmp/BUILD/workbench
```

访问 `http://127.0.0.1:14383/account/`。该模式用于账户、审核、团队与权限界面验收；
它不加载科学 provider，不启动科学 supervisor。科学执行请求必须明确报告当前模式不可用，
不能把无 worker 的排队请求当作任务已经启动。开启科研前须通过该拒绝路径的回归验收。

## 正常多用户科研模式

移除 `--accounts-only`，并配置当前 clone 的模型配置、provider 凭据和可用科学 runtime。
入口参数包括：

| 参数 | 含义 |
| --- | --- |
| `--models PATH` | 当前 clone 内的模型配置，默认 `config/llm.yaml` |
| `--env-file PATH` | 当前 clone 内的私有 provider 凭据文件，只解析为值，不执行 |
| `--gpu-devices 0,1` | 可选的物理 GPU 编号集合；必须非负、无重复 |
| `--prediction-backend NAME` | 显式选择支持的预测 backend |
| `--public-origin https://HOST` | 反向代理场景下唯一可信的公开 HTTPS origin |

服务只监听 loopback；公开访问由受控反向代理提供。浏览器必须使用服务配置的同源入口，
以便会话 Cookie、CSRF 和 origin 校验同时生效。不要用共享工作区 token 替代个人登录。

## 管理员与团队的首次使用

1. 用户注册后进入待审核状态。系统管理员在账户页批准，用户再进入自己的工作区。
2. 个人项目默认私有。团队创建者邀请成员，成员接受后才获得相应团队访问权。
3. 用户显式选择团队 scope，可协作维护草稿；带 revision 的更新冲突必须刷新后重新编辑。
4. 团队普通成员不能启动草稿、批准科学 Gate 或恢复计算。由当前有效的团队管理员操作。
5. 系统管理员可审计式只读查看他人 scope；平台管理身份不自动成为科研审批人。
6. 管理员为个人与团队配置资源限额；团队计算同时计入实际发起人的个人额度和团队额度。

## 比赛额度设置

本次比赛预设为个人累计最终设计额度 30，Pilot 阶段预算 30、Scale 阶段预算 30。
这三项可在管理员后台的“资源额度”中调整；比赛结束后可继续使用同一套产品和管理入口。

| 配置字段 | 作用 | 允许值 |
| --- | --- | --- |
| `final_designs_allowance` | 个人跨个人空间和团队空间累计的最终设计额度 | 0–1,000,000；勾选“不限制”提交 `null` |
| `pilot_stage_budget` | 新项目的 Pilot 阶段预算 | 1–10,000；“使用原生默认”提交 `null` |
| `scale_stage_budget` | 新项目的 Scale 阶段预算 | 1–10,000；“使用原生默认”提交 `null` |
| `max_candidates_per_job` | 每次执行的资源上限 | 独立于累计余额；不会自动改写已审批的科学计划 |

阶段预算在新项目中冻结，后续设置变更不追改旧项目。个人项目使用个人阶段预算，团队项目
使用团队阶段预算；最终设计额度按实际科学审批人的个人账户记账，团队成员关系不会增加
个人额度。团队没有额外的最终设计余额池，团队资源页面只展示获准查看的团队内汇总。

资源页面分别展示额度、预留、已交付和剩余。Pilot 不消耗最终设计额度；Scale 科学负结果
按后台公布的核算规则处理，技术失败、待恢复或证据不确定的工作保留预留，不能当作成功或
自动退款。具体结算依据、已覆盖的边界及测试记录以当前验收文档为准。

额度不足时，接口返回 `final_designs_exhausted`，审批/启动不会被悄悄缩减到较小预算。
管理员可调整额度；科学方案需要修改时仍应走相应 Gate。管理员总览接口为
`GET /api/v1/admin/final-designs`，只读且审计；配额修改继续使用既有
`POST /api/v1/admin/quotas/{subject}`。

账户停用、会话撤销和成员移除必须对后续请求立即生效。既有科学证据及审批人归属不应改写。
计算资源的恢复与释放由准入记录、worker 状态和原生任务共同决定；不能通过删除状态文件、
手工清 GPU 租约或终止其他任务来消除界面上的占用。

## 验收与生产切换

完整工程检查入口：

```bash
.venv/bin/python -B scripts/dev.py verify --mode integration
```

Easy/Professional 的类型检查、单元测试、构建及账号浏览器测试另按各自 `package.json` 执行，
保留唯一测试输出目录。验收至少包含两个用户、两个团队、普通成员、团队管理员和全站只读管理员。

分别记录 HTTP fixture、真实隔离子进程、连接实际账户后端的浏览器交互、原生科学 Gate fixture，
以及真实模型/GPU 科学运行的覆盖范围。任何失败、xfail、缺失依赖或未执行环节都必须保留在验收结论中。

与并行后端开发的合并应在独立集成 worktree 中进行。完成合并后的验证并取得部署批准，
才能规划生产切换；当前文档不授权重启服务、迁移账户数据或覆盖已有科学工作区。
