# EasyDesign 七阶段工作流

`workflow/` 是阶段职责面向人的事实来源。编号目录名是稳定工作流标识；Python
实现使用 `s01_` 至 `s07_`，运行目录镜像相同编号。

每个阶段只维护一个中文 `README.md`，其中同时包含用途、边界、输入、输出、
不变量、失败状态、溯源和完成门槛。当前不冻结 JSON Schema；首次实现验证后通过
ADR 引入机器 schema。

## 交接规则

阶段只能读取已接受的上游 manifest 中声明的 artifact。每个阶段输出新的不可变
manifest，至少记录阶段与契约版本、状态、输入输出、checksum、配置、代码版本、
后端/模型身份、attempt、警告、失败和时间。扫描目录不是接口。

```text
runs/<project_id>/<run_id>/
├── input-snapshot/
├── config-snapshot/
├── manifests/
├── 01-target-preparation/
├── 02-hotspot-discovery/
├── 03-boltzgen-configuration/
├── 04-pilot-generation/
├── 05-pilot-filtering/
├── 06-scale-generation-and-refolding/
├── 07-final-filtering-and-selection/
└── results/
```

Stage 内部直接使用 `attempt-0001/`，不再增加 `attempts/` 中间层。开发 smoke 和外部服务
诊断进入 `runs/_development/`，不能混入正式项目 run。

恢复执行必须先验证上游 hash 和配置兼容性，再建立新 attempt；不得改写旧 attempt。
