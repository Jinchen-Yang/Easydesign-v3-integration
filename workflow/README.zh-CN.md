# 工作流规范

[English](README.md)

`workflow/` 是阶段职责面向人的事实来源。带编号的目录名是稳定工作流标识；
Python 模块使用合法的 `s01_` 到 `s07_` 前缀，运行输出镜像相同的编号名称。

每个阶段都有说明 README、规范性 CONTRACT 和 examples 占位。当前契约只在概念层
描述 artifact，不冻结 JSON Schema。

## 交接规则

一个阶段只能读取已接受的上游 manifest 中声明的 artifact。每个阶段输出新的不可变
manifest，包含阶段标识、契约版本、状态、输入、输出、溯源、attempt、警告、失败、
时间和 checksum。扫描目录不是接口。

运行目录：

```text
runs/<project_id>/<run_id>/
├── run-manifest.json
├── config-snapshot/
├── 01-target-preparation/
├── 02-hotspot-discovery/
├── 03-boltzgen-configuration/
├── 04-pilot-generation/
├── 05-pilot-filtering/
├── 06-scale-generation-and-refolding/
└── 07-final-filtering-and-selection/
```

恢复阶段时创建新的 attempt，绝不能重写旧 attempt。
