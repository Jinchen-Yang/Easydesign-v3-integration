# EasyDesign 宏观路线图

状态定义见 `PROJECT_CHARTER.md`。本文件按产品时间尺度维护宏观方向；它不保存正在编码的
细节，也不承诺日期。阶段内部任务、验证和历史进入各自 `STATUS.md`，当前跨阶段重点见
`TODO_NOW.md`。

## 短期目标：EasyDesign 1.0

目标是以 VHH 为首个参考 binder，把七阶段真实跑通并形成稳定 Python API。功能完整优先于
设计准确率，任何模型失败和科学负结果必须如实报告。

| 里程碑 | 状态 | 完成门槛或阶段索引 |
| --- | --- | --- |
| M0 仓库基础 | `implemented` | 私有 Git 仓库、中文治理、七阶段契约、包骨架和基础检查完成。 |
| M1 统一运行契约 | `implemented` | 类型化 manifest、不可变 attempt、规范 JSON、SHA-256 和契约测试完成。 |
| Stage 01 Target 准备 | `planned` | [状态与任务](workflow/01-target-preparation/STATUS.md)：六类入口生成合格 Target Bundle。 |
| Stage 02 候选区域发现 | `planned` | [状态与任务](workflow/02-hotspot-discovery/STATUS.md)：输出可比较、有来源的候选区域。 |
| Stage 03 设计配置 | `planned` | [状态与任务](workflow/03-boltzgen-configuration/STATUS.md)：1.0 生成并校验 VHH BoltzGen 策略。 |
| Stage 04 Pilot 生成 | `planned` | [状态与任务](workflow/04-pilot-generation/STATUS.md)：真实小批量 BoltzGen pilot 完成。 |
| Stage 05 Pilot 筛选 | `planned` | [状态与任务](workflow/05-pilot-filtering/STATUS.md)：输出可审计的策略 shortlist。 |
| Stage 06 放大与复折叠 | `planned` | [状态与任务](workflow/06-scale-generation-and-refolding/STATUS.md)：通用预测后端完成 smoke。 |
| Stage 07 终筛与选择 | `planned` | [状态与任务](workflow/07-final-filtering-and-selection/STATUS.md)：生成供人工批准的 Top N 包。 |
| EasyDesign 1.0 验收 | `planned` | VHH 七阶段、两条真实端到端基准和 Stage 01 六类入口测试通过。 |

## 中期目标：多 binder 与正式开发者产品

| 里程碑 | 状态 | 完成门槛 |
| --- | --- | --- |
| 通用 binder profile | `planned` | 分子表示、约束、生成后端、filter 和输出包均有稳定 adapter 契约，不复制 pipeline。 |
| 蛋白 binder 主线 | `planned` | 至少一条真实小规模端到端基准通过，并与 VHH 共用运行契约。 |
| 肽 binder 主线 | `planned` | 至少一条真实小规模端到端基准通过，明确线性/环肽表示与筛选边界。 |
| 方法 benchmark | `planned` | 按 binder 类型建立预注册数据集、基线、负结果和科学验证报告。 |
| CLI 与公开 release | `planned` | 稳定 Python API、薄 CLI、英文文档、授权、安全、引用和第三方资产审查完成。 |
| 多执行环境 | `planned` | local、Slurm/SMART 和可移植容器使用相同请求/结果契约。 |

## 长期目标：一键式平台、科研与商业产品

| 里程碑 | 状态 | 完成门槛 |
| --- | --- | --- |
| EasyDesign UI | `planned` | UI 调用同一 Python API，可创建、恢复、审阅和比较完整 run，不复制科学逻辑。 |
| 多 binder 设计平台 | `planned` | VHH、蛋白、肽及后续类型通过能力声明接入，用户用一次配置运行完整流程。 |
| 科研成果 | `planned` | 方法、benchmark、失败分析和真实实验结果形成可审计论文证据链。 |
| 商业产品 | `planned` | 完成 IP、许可证、安全、部署、支持、审计和质量体系，形成可持续产品。 |
| 数据与模型闭环 | `planned` | 经授权的实验反馈能够版本化回流，用于评估和改进而不污染历史证据。 |

长期目标不改变 1.0 的范围：当前首先把 VHH 主线真实跑通；蛋白和肽不会被包装成已经实现。
