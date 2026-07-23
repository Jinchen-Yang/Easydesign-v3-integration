# EasyDesign 宏观路线图

状态定义见 `PROJECT_CHARTER.md`。本文件只维护宏观状态；阶段内部任务、验证和历史进入各自
`STATUS.md`。

| 里程碑 | 状态 | 完成门槛或阶段索引 |
| --- | --- | --- |
| M0 仓库基础 | `implemented` | 全新私有 Git 仓库、中文治理、七阶段契约、包骨架和基础检查完成。 |
| M1 统一运行契约 | `implemented` | 类型化 manifest、不可变 attempt、规范 JSON、SHA-256 和契约测试完成。 |
| Stage 01 Target 准备 | `planned` | [状态与任务](workflow/01-target-preparation/STATUS.md)：六类入口生成合格 Target Bundle。 |
| Stage 02 Hotspot 识别 | `planned` | [状态与任务](workflow/02-hotspot-discovery/STATUS.md)：输出可比较、有来源的候选。 |
| Stage 03 BoltzGen 配置 | `planned` | [状态与任务](workflow/03-boltzgen-configuration/STATUS.md)：生成并校验 VHH 策略矩阵。 |
| Stage 04 Pilot 生成 | `planned` | [状态与任务](workflow/04-pilot-generation/STATUS.md)：真实小批量 BoltzGen pilot 完成。 |
| Stage 05 Pilot 筛选 | `planned` | [状态与任务](workflow/05-pilot-filtering/STATUS.md)：输出可审计的策略 shortlist。 |
| Stage 06 放大与复折叠 | `planned` | [状态与任务](workflow/06-scale-generation-and-refolding/STATUS.md)：通用预测后端完成 smoke。 |
| Stage 07 终筛与选择 | `planned` | [状态与任务](workflow/07-final-filtering-and-selection/STATUS.md)：生成供人工批准的 Top N 包。 |
| EasyDesign 1.0 | `planned` | 两条真实端到端基准和 Stage 01 六类入口测试通过。 |
| CLI 与 release | `planned` | 稳定 Python API、薄 CLI、英文文档、授权、安全和引用审查完成。 |
| UI 与产品能力 | `planned` | UI 调用同一 API，不复制科学逻辑。 |

当前跨阶段重点见 `TODO_NOW.md`。
