# Coding Agent 工作协议

本文件是任何 Coding Agent 进入本仓库后必须自动执行的工作协议。用户无需在每次任务中
重复提醒更新 TODO、测试、文档或提交。

## 1. 开始任务前

1. 确认当前仓库、分支和工作树状态；不得覆盖他人未提交修改。
   同时执行 `git fetch origin`，比较本地 `HEAD` 与 `origin/main`；网络或权限失败时必须
   明确记录，不能把未核对状态写成“已同步”。
2. 阅读 `PROJECT_CHARTER.md`、`docs/ARCHITECTURE.md`、`TODO.md` 和
   `TODO_NOW.md`。
3. 阅读本次涉及的 workflow 阶段 `README.md`、`STATUS.md`；恢复旧任务时还要从
   `STATUS.md` 的历史索引读取最近一条相关记录。
4. 判断任务是否属于实质性任务。代码、依赖、配置、契约、架构或科学行为变化都属于
   实质性任务；纯解释、只读检查和错别字修正不属于。
5. 实质性阶段任务必须在对应 Stage `STATUS.md` 的 `Now` 中有明确任务、完成门槛和
   当前状态；跨阶段任务才进入顶层 `TODO_NOW.md`。若用户指定的新任务尚未记录，Agent
   应自行补充后继续执行，不必为此单独询问。
   每项实质性任务还必须归属一个稳定 ID：科学阶段使用 `S01–S07`，其他工作使用
   `ENG`、`UX`、`REP`、`UI`、`VAL`、`DATA`、`REL`、`PAPER` 或 `BIZ` 前缀。新前缀
   必须先登记到 `TODO.md` 的工作板块索引。
6. 七个 Stage `STATUS.md` 的“顶层摘要”是顶层路线图的唯一状态来源；开始任务时若发现
   `TODO.md` 或 `TODO_NOW.md` 与它们不一致，先运行
   `python scripts/sync_status_rollup.py` 修复，不得沿用过期摘要。

## 2. 实施规则

1. 阶段 README 中的输入、输出、不变量、失败和完成门槛就是阶段边界。
2. 科学与领域逻辑只放在 `src/easydesign/`；脚本、未来 CLI 和 UI 只能调用 Python API。
   新增或修改的 pipeline 能力必须通过统一 application/orchestration API 暴露；
   `easydesign` CLI、兼容脚本和未来 UI 不得各自形成第二套运行逻辑。
3. `core/` 不得依赖具体 stage 或重型 backend；backend 通过 adapter 隔离。
4. 不得扫描目录猜测输出；只能读取 manifest 声明的 artifact。
5. 不得静默切换结构来源、模型、backend、executor 或 filter profile。
6. run、已发布 manifest 和终态 attempt 不可覆盖；重试创建新 attempt。
7. 未经明确迁移任务和来源审查，不得复制旧仓代码、权重、结果或资产。
8. 未经授权不得添加许可证、Git remote、密钥、模型权重或第三方资产。
9. 工程验证与科学验证必须分别报告，不能把 smoke 运行描述为科学成功。
10. 用户 run 配置的规范事实源是 schema `0.7` 的 `stage01`–`stage07`；兼容旧布局只能在
    加载/迁移边界处理，run 内 resolved config 和新增示例不得继续写旧布局。
11. 多模型结构必须沿 Target Bundle 的 coordinate ensemble 身份传播；不得静默选择
    model 1、平均不支持 ensemble 的模型输出，或把 adapter 单模型限制写成全局限制。
12. 自动 Stage 02 结果不是批准结果。Stage 03 只能消费人工审批 attempt 正式发布的
    `hotspots.yaml`，不得读取候选池、PSE 颜色或编辑中的 review YAML 代替。
13. EasyDesign 1.0 的科学流程不得依赖 LLM/Agent 判断；未来 Agent 建议必须转为类型化
    配置、确定性校验和人工批准，并保持无 Agent 可运行。
14. `review-gated` 与 `unattended` 必须调用同一科学实现。前者在类型化 Decision Gate
    暂停，批准后在同一 run 新建 attempt；自动科学选择的 unattended 只能使用版本化
    deterministic policy。用户在初始 YAML 明确提供的区域可以连续运行，但必须保存真实
    human approver、逐区理由、配置 hash 和 acknowledgement，不得伪装成算法批准。实际向
    供应商下单永远不属于自动流程。
15. Stage 02 `automatic` 禁止读取 PSE 颜色；`detect` 和 `user-provided` 只能通过
    Target Bundle 声明的 `source-annotations.json` 或类型化 YAML residue selector
    进入统一 `UserProvidedRegionSet`。不得从普通 PDB/mmCIF 私有字段猜颜色，不得扩展、
    删除或重排用户区域成员。
16. UniProt/RCSB 等远程响应必须经过有界 timeout/retry、显式 cache mode 和 run 内
    snapshot；API 失败不得解释成空候选，也不得在 `online` 模式静默读取旧 cache。
17. SSH 远程执行必须来自 runtime profile 的显式 executor；禁止扫描 SSH config、自动
    选择机器或把密钥写入科学 YAML。结果同步只能使用 manifest-derived 文件白名单并
    重新验证 SHA-256；heartbeat 只表示进程存活，不能把中间文件计作完整候选。

## 3. 完成任务前

Agent 必须自动完成以下收尾工作：

1. 添加与风险相称的 unit、integration 或 e2e 测试。
2. 运行 `make check` 和 `make test`；打包或依赖变化还要运行 `make build`。
   必须显式使用 `easydesign-core` 的 Python 3.11，例如
   `make check PYTHON=/root/autodl-tmp/conda_envs/easydesign-core/bin/python3.11`；
   不得使用服务器系统 Python 代替后误判代码失败。
   修改 Target Viewer、Mol* 资产、CSP、本地服务或浏览器行为时还必须运行
   `make test-web`；测试必须证明所有 HTTP 请求留在 `127.0.0.1`。
   修改 CLI、安装入口或 package data 时，`make build` 必须在隔离环境安装最新 wheel，
   验证 `easydesign --version` 和 `python -m easydesign --help`。
3. 接口、目录或依赖方向变化时更新 `docs/ARCHITECTURE.md`。
4. 阶段行为或契约变化时更新对应 workflow `README.md`。
5. 更新每个受影响 Stage 的 `STATUS.md`：
   - 同步更新“顶层摘要”的总体状态、一句话进展、当前重心、主要阻塞和日期；
   - 已完成的 `Now` 在被移除或替换前，必须先追加到该 Stage 的
     `history/YYYY-MM.md`；
   - 从 `Now` 移除已归档工作或切换到下一个明确任务；
   - 更新功能矩阵、验证证据和 Blocked；
   - 在当日工作日志中只追加决策、测试证据、run/attempt 和 commit。
6. 每次 Stage 顶层摘要变化后运行 `python scripts/sync_status_rollup.py`，自动刷新
   `TODO.md` 和 `TODO_NOW.md` 的七阶段实时表；禁止手工编辑自动生成区块。
7. 跨阶段 Now/Next/Blocked 发生变化时更新 `TODO_NOW.md` 的人工维护区块；阶段内部
   细节不得复制到顶层。只有宏观里程碑的全部完成门槛通过后，才改变其总体状态。
   顶层每个活跃条目必须带工作板块 ID；完成的非 Stage 工作在移出 Now 前追加到共享
   `docs/history/YYYY-MM/`，并记录问题、方案、验证、遗留边界和提交身份。
8. Stage 历史采用“工作项关闭即归档、按月追加到同一文件”的制度：
   - 每条记录必须包含状态、完成时间、完成内容、验证证据、遇到的问题、解决办法和
     遗留问题；
   - `完成时间` 是完成门槛实际满足并准备从 `Now` 移除的时间，必须采用带 UTC offset
     的 RFC 3339 秒级格式，例如 `2026-07-25T14:30:00+08:00`；禁止只写日期、无时区
     本地时间或事后猜测的时间；
   - 未完成工作不得伪装成已结束记录：仍在执行的留在 `Now`，等待外部条件的进入
     `Blocked`，并在已完成部分的历史记录中交代边界；
   - `STATUS.md` 的历史索引必须链接对应月份文件；
   - 顶层 `docs/history/YYYY-MM/` 只记录跨阶段里程碑，不复制阶段细节。
   历史记录不得改写，有误时追加更正。
9. 顶层 `TODO_NOW.md` 中已完成的跨阶段事项在移出 `Now` 前，也必须以同一 RFC 3339
   格式把 `完成时间` 写入共享 history；`make check` 同时验证 Stage history、共享
   history 和七阶段实时表。缺少时间戳或实时表不同步都属于质量门失败，不能以“只改了
   文档”为由跳过。
10. 检查 `git diff --check`，创建一个目的清楚的 Conventional Commit；不得使用
   `git add .` 盲目加入 run、权重、密钥、大文件或无关修改。
11. 对已经通过质量门的独立工作单元，必须 push 到已配置的 GitHub remote：
    - `main` 只接收可验证提交；未完成工作只能推到短期分支；
    - push 后必须用远端引用再次核对 commit SHA；
    - 网络、权限或 remote 异常时，在 `TODO_NOW.md` 的 `Blocked` 记录未推送 commit
      SHA，并在交付中明确报告；
    - 禁止仅根据 `git push` 命令已执行就声称远端已更新。
12. 未经授权不得新建或替换 remote，不得触发外部下单或其他不可逆外部操作。
13. 更新 Mol* 时必须在同一提交中同步：
    - `package.json` 与完整 `package-lock.json`；
    - 官方 npm tarball identity/integrity、vendored JS/CSS 和固定 SHA-256 检查；
    - Mol* license、bundle 内第三方 license notices 和资产登记；
    - Python wheel package-data 验证、Playwright 浏览器测试和 ADR/架构文档。
    许可证审计未通过时停止 vendoring，任务保持 Blocked，不能只替换 JS 文件。
14. 修改产品工作台时必须同步 React/TypeScript 源码、`pnpm-lock.yaml`、Python UI
    gateway、wheel package data 和 Playwright。浏览器端只消费 Python API 的类型化
    projection，不得复制科学阈值、从目录猜测 artifact、解析终端日志或暴露绝对路径。
    Stage capability、run state、scientific stop、operational failure 和 demo replay
    必须使用不同字段及明确文案；没有真实 FinalCandidatePackage 时禁止解锁下单草案。
15. 产品工作台默认界面必须使用中文产品语义，除品牌和科学缩写外不得直接显示内部
    manifest/artifact/checksum/run ID 等工程词；这些信息只能进入运行内“技术记录”。
    主导航保持用户任务导向，审批进入动态通知和对应运行，环境进入设置。Stage 05 大型
    报告必须通过 manifest-only 后端分页投影，前端不得整体加载报告、复制阈值或根据
    内部 rule ID 自行判断科学结论。
16. `runs/` 仍不得提交。确需通过 Git 共享真实案例时，只能生成独立的只读 evidence
    bundle：必须验证 Run/Stage manifest 闭包和逐文件 SHA-256，排除 backend
    `tasks/work/runtime` 等重型中间目录，登记来源、授权、大小和科学边界，并证明仓库内
    UI 能读取。Evidence bundle 不得被描述为可恢复的完整 run，也不得包含密钥、模型
    权重或未审计第三方资产。
17. 跨主机计算只能使用 runtime profile 中显式声明的 SSH executor。提交前必须验证
    known-host、独立密钥、远端 EasyDesign 版本、GPU、磁盘、上游 manifest 和配置
    SHA-256；远端 run 自己发布 manifest、progress 和 events。禁止复制控制端私钥、
    静默采用未知主机、杀死远端既有进程，或因 SSH 提交成功就声称科学运行已完成。
    Stage 05 科学停止后的探索性放大还必须保存带来源 Bundle SHA-256 的人工授权，
    历史科学结论不得被改写。

## 4. 阻塞与询问

以下情况才需要暂停并询问用户：

- 需要产品或科学策略选择，且不同选择会实质改变结果；
- 缺少权限、凭据、许可证或外部资源；
- 需要不可逆操作或扩大任务范围；
- 发现无法安全绕开的他人修改。

一般实现细节、测试失败、依赖冲突和可恢复的工程问题应先自行诊断。发生阻塞时，不得把
任务标记为完成；应在 `TODO_NOW.md` 的 `Blocked` 中记录具体条件和已尝试方案。

## 5. 用户调用方式

用户可以直接说：

> 进入 easydesign-clean，严格按照 AGENTS.md 完成 TODO_NOW.md 中的 Now。

Agent 应自行完成读取上下文、实现、测试、文档/TODO 更新和本地提交。
