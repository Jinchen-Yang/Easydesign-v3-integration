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
| EasyDesign 1.0 验收 | `planned` | VHH 七阶段、两条真实端到端基准和 Stage 01 六类入口测试通过。 |

### 七阶段实时摘要

下表由各 Stage `STATUS.md` 的“顶层摘要”自动生成；不得手工维护。

<!-- BEGIN AUTO-GENERATED STAGE ROLLUP -->
| Stage | 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新 | 详情 |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 01 | `planned` | sequence/FASTA、单 Target PSE 与 APOE MSA-backed backend smoke 已跑通，其余四类入口待实现。 | 将显式 MSA provider、endpoint 和 ticket 溯源接入正式 adapter 与 Target Bundle。 | 正式 adapter 尚未记录 resolved endpoint/ticket；Protenix 官方 MSA 端点持续 `PENDING`。 | 2026-07-24 | [STATUS](workflow/01-target-preparation/STATUS.md) |
| Stage 02 | `planned` | SASA 与 ScanNet CPU 双方法已在 APOE 正式 run 发布 Top 3 和比较报告。 | 人工审阅两套区域并建立批准区域到 Stage 03 的交接。 | 人工批准契约尚未实现；GPU 在 RTX 4080 上不兼容旧运行栈。 | 2026-07-24 | [STATUS](workflow/02-hotspot-discovery/STATUS.md) |
| Stage 03 | `planned` | 尚未实现；1.0 将先生成并校验 VHH BoltzGen 配置。 | 等待 Stage 02 人工批准区域后定义 YAML 与策略 manifest。 | Stage 02 handoff 未建立，VHH scaffold 权利待审查。 | 2026-07-24 | [STATUS](workflow/03-boltzgen-configuration/STATUS.md) |
| Stage 04 | `planned` | 尚未实现；clean 仓还没有真实 BoltzGen pilot。 | Stage 03 稳定后定义 pilot request/result 与执行器边界。 | 依赖已校验的 Stage 03 策略 bundle。 | 2026-07-24 | [STATUS](workflow/04-pilot-generation/STATUS.md) |
| Stage 05 | `planned` | 尚未实现；filter profile、逐规则审计和 shortlist 均待开发。 | Stage 04 候选契约稳定后建立可版本化 filter engine。 | 依赖 Stage 04 规范候选与原始 artifact。 | 2026-07-24 | [STATUS](workflow/05-pilot-filtering/STATUS.md) |
| Stage 06 | `planned` | 通用预测接口已在 Stage 01 实现，放大生成和复合物 refold 尚未开始。 | 复用 Protenix-v2 adapter，等待 Stage 05 shortlist 后定义 scale 契约。 | 依赖 Stage 05 入选策略和复合物预测验证。 | 2026-07-24 | [STATUS](workflow/06-scale-generation-and-refolding/STATUS.md) |
| Stage 07 | `planned` | 尚未实现；最终规则、聚类、多样性和 Top N 审核包均待开发。 | Stage 06 输出稳定后定义 final decision 与人工批准包。 | 依赖 Stage 06 完整预测与覆盖报告。 | 2026-07-24 | [STATUS](workflow/07-final-filtering-and-selection/STATUS.md) |
<!-- END AUTO-GENERATED STAGE ROLLUP -->

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
