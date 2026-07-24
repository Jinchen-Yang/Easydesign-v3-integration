# Coding Agent 工作协议

本文件是任何 Coding Agent 进入本仓库后必须自动执行的工作协议。用户无需在每次任务中
重复提醒更新 TODO、测试、文档或提交。

## 1. 开始任务前

1. 确认当前仓库、分支和工作树状态；不得覆盖他人未提交修改。
2. 阅读 `PROJECT_CHARTER.md`、`docs/ARCHITECTURE.md`、`TODO.md` 和
   `TODO_NOW.md`。
3. 阅读本次涉及的 workflow 阶段 `README.md`、`STATUS.md`；恢复旧任务时还要从
   `STATUS.md` 的历史索引读取最近一条相关记录。
4. 判断任务是否属于实质性任务。代码、依赖、配置、契约、架构或科学行为变化都属于
   实质性任务；纯解释、只读检查和错别字修正不属于。
5. 实质性阶段任务必须在对应 Stage `STATUS.md` 的 `Now` 中有明确任务、完成门槛和
   当前状态；跨阶段任务才进入顶层 `TODO_NOW.md`。若用户指定的新任务尚未记录，Agent
   应自行补充后继续执行，不必为此单独询问。

## 2. 实施规则

1. 阶段 README 中的输入、输出、不变量、失败和完成门槛就是阶段边界。
2. 科学与领域逻辑只放在 `src/easydesign/`；脚本、未来 CLI 和 UI 只能调用 Python API。
3. `core/` 不得依赖具体 stage 或重型 backend；backend 通过 adapter 隔离。
4. 不得扫描目录猜测输出；只能读取 manifest 声明的 artifact。
5. 不得静默切换结构来源、模型、backend、executor 或 filter profile。
6. run、已发布 manifest 和终态 attempt 不可覆盖；重试创建新 attempt。
7. 未经明确迁移任务和来源审查，不得复制旧仓代码、权重、结果或资产。
8. 未经授权不得添加许可证、Git remote、密钥、模型权重或第三方资产。
9. 工程验证与科学验证必须分别报告，不能把 smoke 运行描述为科学成功。

## 3. 完成任务前

Agent 必须自动完成以下收尾工作：

1. 添加与风险相称的 unit、integration 或 e2e 测试。
2. 运行 `make check` 和 `make test`；打包或依赖变化还要运行 `make build`。
3. 接口、目录或依赖方向变化时更新 `docs/ARCHITECTURE.md`。
4. 阶段行为或契约变化时更新对应 workflow `README.md`。
5. 更新每个受影响 Stage 的 `STATUS.md`：
   - 已完成的 `Now` 在被移除或替换前，必须先追加到该 Stage 的
     `history/YYYY-MM.md`；
   - 从 `Now` 移除已归档工作或切换到下一个明确任务；
   - 更新功能矩阵、验证证据和 Blocked；
   - 在当日工作日志中只追加决策、测试证据、run/attempt 和 commit。
6. 跨阶段重点发生变化时更新 `TODO_NOW.md`；阶段内部细节不得复制到顶层。
7. 只有宏观里程碑的全部完成门槛通过后，才更新 `TODO.md` 的状态。
8. Stage 历史采用“工作项关闭即归档、按月追加到同一文件”的制度：
   - 每条记录必须包含状态、完成内容、验证证据、遇到的问题、解决办法和遗留问题；
   - 未完成工作不得伪装成已结束记录：仍在执行的留在 `Now`，等待外部条件的进入
     `Blocked`，并在已完成部分的历史记录中交代边界；
   - `STATUS.md` 的历史索引必须链接对应月份文件；
   - 顶层 `docs/history/YYYY-MM/` 只记录跨阶段里程碑，不复制阶段细节。
   历史记录不得改写，有误时追加更正。
9. 检查 `git diff --check`，创建一个目的清楚的 Conventional Commit。
10. 默认不 push、不创建 remote、不触发外部下单或其他不可逆外部操作。

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
