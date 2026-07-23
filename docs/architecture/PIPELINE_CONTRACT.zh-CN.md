# Pipeline 契约

[English](PIPELINE_CONTRACT.md)

## 身份

一个 run 有稳定 `project_id` 和 `run_id`；每个阶段有稳定编号 `stage_id`；每次执行
创建 `attempt_id`。Artifact 用逻辑角色加 checksum 定位，不能只依赖偶然文件路径。

## 状态

Run 和 stage 状态必须区分规划、执行、工程验证、科学结果、取消和失败。执行完整但
科学 filter 通过候选为零，是有效结果。

## 不可变与恢复

已接受 manifest 和 attempt artifact 不可变。恢复先验证上游 hash 和配置兼容性，
然后创建新 attempt，不修改失败或已完成的旧 attempt。

## Adapter 隔离

后端专属请求和结果字段留在 adapter 中。Core contract 只暴露能力与规范化证据，
使 BoltzGen、预测模型和 scheduler 可以替换而不重写阶段边界。
