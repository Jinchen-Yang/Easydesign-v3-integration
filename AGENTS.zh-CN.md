# Coding Agent 工作规则

1. 开始工作前阅读 `PROJECT_CHARTER.zh-CN.md`、`TODO.zh-CN.md` 和
   `TODO_NOW.zh-CN.md`。
2. 把 `workflow/<stage>/CONTRACT.zh-CN.md` 视为阶段边界。
3. 没有明确且经过审查的迁移任务和来源记录，不得复制旧仓代码或资产。
4. 科学逻辑只能放在 `src/easydesign/`；脚本、未来 CLI 和 UI 只是 adapter。
5. 不得扫描目录猜测阶段输出，只读取 manifest 明确声明的产物。
6. 不得静默切换后端、结构来源、模型或 filter profile。
7. run 和 attempt 不可变，禁止覆盖科学产物。
8. 测试、TODO 状态、契约和中英文文档必须同步更新。
9. 未经明确授权不得添加许可证、Git remote、模型权重、密钥或第三方资产。
10. 工程验证和科学验证必须分别报告。

See [English instructions](AGENTS.md).
