# EasyDesign 项目宪章与开发规则

本文档是项目战略、1.0 边界和开发制度的统一事实来源。发布阶段再拆分英文 README、
CONTRIBUTING、CHANGELOG、LICENSE、CITATION 和第三方声明。

## 1. 使命

EasyDesign 要把 binder 设计研究流程变成可追溯、可复现、可扩展并能够产品化的
系统，同时推进三条路线：

- **科研：** 保存方法、基准、负结果和 claim-to-evidence 链接，支撑正刊论文。
- **软件：** 先完成稳定 Python API，再做薄 CLI，最后做调用同一 API 的 UI。
- **商业：** 保护知识产权和资产权利，支持私有部署及未来商业产品。

开发速度来自清楚的契约、证据和模块边界，不来自隐藏失败或堆叠临时脚本。

## 2. EasyDesign 1.0

1.0 实现完整七阶段 VHH 主线，可以使用小规模预算和基线模型，不承诺 binder
准确率。发布门槛是：

1. 七个阶段均调用真实工具，不使用伪造科学结果通过验收；
2. 一条实验结构输入的端到端基准通过；
3. 一条无合适现成结构的 sequence/UniProt 端到端基准通过；
4. Stage 01 六类输入入口分别通过集成测试；
5. 运行可安全恢复，保留溯源且不覆盖已完成产物；
6. 软件成功与科学筛选结果分别报告。

其他 binder 类型在 1.0 只允许保留 adapter 接口，不列入实现承诺。

## 3. 不可妥协的工程规则

1. 一个概念只能有一个实现和一个事实来源。
2. 阶段只读取上游 manifest 声明的 artifact，并输出不可变 manifest。
3. 禁止静默 fallback、伪造成功、错误后端命名和吞掉异常。
4. 每次运行保存输入 hash、配置快照、代码版本、随机种子、后端/模型版本和环境。
5. CLI、UI、notebook 和 shell 脚本不得包含科学业务逻辑。
6. filter、scaffold、预测器和 executor 都必须是带能力声明的可替换 adapter。
7. 启发式必须明确标注；没有证据时不得描述成能量学或实验验证方法。
8. run 和 attempt 只追加不覆盖；恢复执行创建新 attempt。
9. 密钥、权重、缓存、大型运行结果和未经审查资产不得提交。
10. 第三方代码、模型、数据和 scaffold 引入前必须完成来源与权利审查。
11. 代码、测试、阶段说明和 TODO 状态必须在同一变更中保持一致。
12. 阶段契约、架构、证据标准和兼容性发生重大变化时记录 ADR。

## 4. 状态与证据

项目只使用以下状态：

- `planned`：已经规范，尚未实现；
- `implemented`：代码存在并通过工程检查；
- `smoke-validated`：真实小规模运行完成；
- `scientifically-validated`：预定义科学基准通过；
- `production-ready`：运行、支持、安全和发布门槛全部通过。

高等级状态必须链接当前等级及所有更低等级的证据。一次完整运行没有候选通过
filter，是有效的科学负结果，不代表软件失败，也不能包装为 binder 成功。

## 5. 开发与评审流程

- 采用 trunk-based 开发；`main` 保持可验证，工作使用短期分支和 Conventional Commits。
- 修改前阅读相关阶段 `README.md`、`TODO.md` 和 `TODO_NOW.md`。
- 领域逻辑只放在 `src/easydesign/`；脚本只能调用 API。
- 按风险补充 unit、adapter integration 和 end-to-end 测试。
- 合并前运行 `make check`、`make test`；打包变更再运行 `make build`。
- 重型后端可以使用独立环境，不能在包导入时强制加载可选重型依赖。
- 核心逻辑不得硬编码 SMART、服务器路径、用户名或密钥。

评审必须拒绝重复逻辑、读取未声明文件、覆盖产物、隐藏 fallback、错误科学标签、
站点路径泄漏和来源不明资产。

## 6. 文档制度

- `README.md`：项目入口与当前状态。
- `PROJECT_CHARTER.md`：战略、1.0 边界和开发规则。
- `TODO.md`：宏观里程碑、七阶段状态和阶段状态索引。
- `TODO_NOW.md`：跨阶段的 Now/Next/Blocked 和项目历史索引，不复制阶段任务。
- 每个 workflow 阶段维护一个稳定的中文 `README.md`，同时承担说明和契约。
- 每个 workflow 阶段维护一个动态 `STATUS.md`，记录功能矩阵、Now/Next/Blocked、
  验证证据和只追加工作日志。
- 阶段历史每月归档到该阶段的 `history/YYYY-MM.md`；跨阶段历史归档到
  `docs/history/YYYY-MM/`。
- Git commit 记录代码差异；历史文档只记录决策理由、验证证据、run/attempt 身份、
  失败和结论更正，不能复制流水账。
- 当前开发期只维护中文；公开发行前再建立英文发布文档并进行逐项校对。

## 7. 知识产权与第三方资产

当前没有 `LICENSE` 是刻意选择，所有权利保留。当前只使用项目所有者批准的私有远程
托管；公开授权、公开 release 和论文引用信息必须经过明确的 IP/release 决策。第三方
资产使用前登记到
`resources/provenance/ASSET_REGISTER.tsv`，记录来源、不可变版本或 checksum、
许可证、用途、再分发权和审查结论。能够下载不代表拥有使用权。
