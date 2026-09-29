# A 机部署、科学执行器与重构余项

核验日期：2026-09-29。应用源码固定为 `a33317b4089df81d0394020c393c4407d8be7c69`。

## 使用入口与验收边界

- 主站：<https://easydesign.pro/>，自动进入 `/app/`。
- 账号：<https://easydesign.pro/app/#/account>，新用户注册后即可登录。
- 演示：<https://easydesign.pro/app/#/demo>，试用溶菌酶后可逐阶段截图。
- 教程材料：`runtime/releases/tutorial-materials-science-a33317b.zip`，包含启用执行器后的界面截图与说明。
  之前的 `tutorial-materials-a33317b.zip` 是历史预览状态，仍保留，制作 PPT 请使用新包。
- 已退出 `--accounts-only`，公网 `compute_available=true`，GPU 接口显示 connected。
  5 个科学环境及 14 项模型/资产在 A 的独立 runtime 中安装、校验并注册完成。
  当前预测后端为 Protenix-v2，执行器允许 GPU 4、5、6、7；其他 GPU 的外部任务未干预。
- 尚未创建真实设计项目或启动科学任务；后端探针和 GPU 算子通过，不代表完整研究流程或双机算力池已验收。
- 新库保留在 A；B 的账号、项目与研究记录未迁移，使用者可在主站自行注册。

## Kimi 已交付的范围

`1d813b2` 已实现第三套 `/app/` 静态分发、`--app-web`、资源白名单与 HTML 404。
`8204882` 已抽取其扫描范围内的硬编码中文。此前统一 SPA、访客演示、会话恢复、
路由拆包、豆豆图片和结构资源迁移也已进入当前版本。
这些提交不是“重构全部完成”的证明，剩余项以本次代码与浏览器核验为准。

## 本次补齐

- `8f340c0`：注册默认 active，更新注册文案，保留停用/拒绝/人工 pending 门禁。
- `2a91fb4`：HTTP 注册即用回归。
- `6ab6460`：真实 `/login` 只返回 user/CSRF；前端随后读取 `/accounts/me` 得到 scopes。
  修复此前真实登录及会话恢复读取缺失 scopes 的崩溃；注册响应状态同步为 registered。
- `a33317b`：Easy 页内导航滚动不再覆盖 Hash Router；输入类型接入现有词典。

## 尚未完成的重构

| 事项 | 当前证据与下一步 |
| --- | --- |
| Easy/Pro 共享数据层 | 两个 adapter 仍分别存在（539 与 430 行），契约、轮询与请求状态未统一。保留同一 request_id 和恢复时的实例语义。 |
| 草稿覆盖 | `draftRecovery` 的实际业务写入仍集中在 Easy 设计输入，Pro/Gate 备注等需要补齐并做过期恢复测试。 |
| 完整国际化 | 公网中文模式下 Pro 仍显示 Projects、Agent Workspace 等英文；演示存在 `{stage}`、`{name}` 未插值文本。中文扫描归零不等于全部界面已翻译。 |
| 真实科学纵向验收 | A 的环境、模型、GPU 和模型接口已接通；真实研究输入、Gate、计算、恢复、结果仍需专项验收。当前截图和模拟演示不能替代。 |
| 旧面退役 | 旧 Easy/Workbench 源码和 release 保留；稳定观察后再按兼容链接与回退要求清理。 |
| A/B 统一算力 | 未实现，当前 A/B 之间只有保留测试站的入口转发，不能当成双机调度。 |

注册审核通知已不再是本次注册流程的必需项；HTML 404 已完成，不再照抄旧清单为待办。

## 部署实况与回退

A 的独立目录为 `/data/Easydesign-v3-production`；科学模型、旧环境和其他服务均未覆盖。
主站：Cloudflare → A cloudflared → A loopback 8096 网关 → A loopback 18771 应用。

实际隧道还承载 test 域名，不能当作主站专用隧道处理。
测试站保持：Cloudflare → A 的 8097 SSH 转发 → B 的 127.0.0.1:18771。
3080 原隧道容器已停止并设 restart=no，原静态网站容器、文件、token 均保留。
没有修改 Cloudflare DNS/ingress，也没有把 3080 留在服务请求链路中。

A 的四个自启动服务：`easydesign-production`、`easydesign-gateway`、
`easydesign-tunnel`、`easydesign-test-forward`。
最终静态目录：`runtime/releases/production-tutorial-final/app`。
之前两次新构建与原 hashed assets 均保留；新版本资产目录包含旧 hashed 文件，防止旧标签页失效。
当前部署完整文件清单为本地证据 `a-deployed-app-sha256.json`；历史 `final-assets-sha256.json`
记录的 index 已被后一次入口构建替代，该入口对应 `tutorial-assets-sha256.json`，不能只用旧清单核对当前 index。

数据库使用 SQLite backup API 备份；服务/config/source 备份位于
`runtime/backups/pre-login-fix`、`runtime/backups/pre-tutorial-final` 与 `runtime/backups/pre-scientific-enable`。
禁止用旧备份覆盖上线后产生的新账号或数据。

如需回退网络入口：先在 3080 恢复原 `easydesign-tunnel` 的 unless-stopped 策略并启动，
确认连接后停 A 隧道；这会把主站恢复为旧静态图谱站，不是回滚成当前应用。
应用/UI 回退应保留新数据库，只切换已保留且兼容的代码与静态目录，切换前重新核对活动任务。

## 验证证据

证据目录：`runtime/tmp/production-deploy/`。

- 产品后端：`product-final.log`，387 passed。
- 注册与静态分发专项：`final-account-tests.log`，47 passed。
- 前端：`app-tests-final.log`，72 passed；`app-e2e-final.log`，5 passed；类型检查与构建通过。
- `final-check.log`：结构、Ruff、mypy 通过。
- `target-viewer-tests.log`：5 passed、2 skipped；`wheel-check.log`：wheel 资源与入口校验通过。
- 公网真实浏览器：注册、登录、退出后重登、个人工作区、Easy/Pro 切换、页内导航与演示结构。
- 主域名 GET /app/ 为 200，根路径跳转正确；原测试站 GET /account/ 为 200。
- A 数据库 quick_check=ok，科学 admissions=0；四个服务 active，隧道 4 条连接。
- 完整仓库回归 `final-release-verify.log` 仍在执行；本机 NO_PROXY 中的 IPv6 条目导致过一次 httpx 解析失败。
  去除测试进程代理环境后，相关 `test_evidence_research.py` 全部 24 项通过，见 `evidence-research-clean-env.log`。
  另一处失败所在的 `test_prerequisite_recovery.py` 在同样干净环境中复跑 6 项全部通过，见 `prerequisite-recovery-clean-env.log`。
  尚未宣称全量 release 验证通过。
- Cloudflare 注入的统计 beacon 被现有 CSP 阻止，产品页面仍正常；未为了统计脚本放宽 CSP。

## 科学执行器验收

安装材料只复制到 A 的新目录；环境通过原生安装器由锁定 Conda 包与 wheel 重建，未直接搬用 B 的绝对路径环境。
模型及源码资产由原生校验器验证 SHA-256/revision，profile 和所有可执行路径均属于 A 当前 clone。

- `a-runtime-status-enabled.json`：PyMOL、BoltzGen、Protenix-v2、ScanNet、TNP 共 5 个环境，以及 14 项资产全部 available。
- `a-backend-gpu-probes.jsonl`：6 个必需 backend 探针全部 passed（含 BoltzGen generation 与 validation 两个入口）；Landlock ABI 1 通过。
  ScanNet 的实际 TensorFlow 运算在 CPU 上通过。
- 同一证据包含在 Landlock 写隔离下、物理 GPU 4 上的真实运算：Protenix 的 PyTorch 2.7.1/CUDA 12.6、BoltzGen 的 PyTorch 2.13.0/CUDA 13.0 矩阵计算通过；Protenix FusedLayerNorm CUDA 算子通过。
- `a-provider-probe.json`：7 个科学角色客户端配置成功；coordinator 与 target 两种模型调用路径均取得真实响应。
- `a-public-science-check.log`：公网登录仍有效，compute_available=true，资源 API 200/connected，发现 A 的 8 个 GPU；调度限制由服务参数固定为 4–7。
- 原生 `runtime install all` 在完成上述 19 个必需项目后，额外尝试安装可选 AFO；其下载网络不可达，整体安装任务因此记录 failed。
  未隐藏该失败，也未启用 AFO；上述独立诊断验证的是从一开始就配置的 Protenix-v2 路径。
- ops context 的 verification_profile 为 none；`dev.py verify` 不接受 ops 参数。运行时验收以上述原生诊断、实际算子和公网检查为准。

A 上完整安装、探针和服务切换证据位于 `runtime/logs/scientific-setup/`。
新环境与模型均保留，未覆盖 B 的研究数据、运行状态或科学环境。
专用 `tutorial-check` 验收账号已在截图完成后停用并撤销会话，记录保留；其他注册用户未改动。

## B 测试站同步更新

用户追加要求后，由子智能体更新 <https://test.easydesign.pro/> 至相同应用源码 `a33317b`。
静态入口使用 A 已部署包，接口同步支持 `/app/`、注册即用和登录后读取完整 scopes；保留 B 原有模型、配置、账号和研究数据。

- 公网真实浏览器通过：新用户注册、立即登录、`/accounts/me`、Easy/Pro 切换、实时算力、旧账户与项目链接转换。
- config、projects、usage 实际 scoped API 均 200；registration=open、compute_available=true，遥测显示 B 的 8 个 A100。
- 原 17 个用户的完整行 hash 保持一致，2 个团队保留；新增的专用 QA 账号已停用，且没有创建科学任务。
- 更新前出现用户科学任务；确认科学代码与依赖、权限检查不变，并验证服务只停止 Web 主进程、不会终止或重放独立科学 worker 后，执行了兼容升级。
  原两级 worker 的 PID/start ticks、boot ID、scope/assignment/config hash 前后一致；该任务随后自然进入 released 状态。
- 5100 个受保护文件的对比仅发现当前任务所在项目的 4 个 SQLite WAL/SHM 自然更新，其他 5096 个文件保持一致。
- 没有迁移 A/B 研究数据，也没有将 HTTP 入口转发改变为跨机器科学调度。

详细部署、备份、回退及验收证据见本地 `runtime/tmp/production-deploy/b-test-upgrade/README.md`。
