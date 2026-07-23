# Coding Agent 工作规则

1. 开始前阅读 `PROJECT_CHARTER.md`、`TODO.md`、`TODO_NOW.md` 和相关阶段 README。
2. 阶段 README 中的输入、输出、不变量和完成门槛就是阶段边界。
3. 未经明确迁移任务和来源审查，不得复制旧仓代码或资产。
4. 科学逻辑只放在 `src/easydesign/`；脚本、未来 CLI 和 UI 只能调用 API。
5. 不得扫描目录猜测输出，不得静默切换后端、结构来源、模型或 filter profile。
6. run 和 attempt 不可变，禁止覆盖科学产物。
7. 同步更新代码、测试、阶段说明、`TODO` 和 `TODO_NOW`。
8. 未经授权不得添加许可证、remote、权重、密钥或第三方资产。
9. 工程验证与科学验证必须分别报告。
