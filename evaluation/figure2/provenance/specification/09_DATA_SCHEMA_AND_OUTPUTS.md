# Data Schema and Required Outputs

## FIGURE2_DATA_LONG.csv
每行：
target × method × campaign × metric

建议字段：
benchmark_version
repository_commit
method
model_id
reasoning_mode
target_id
target_family
task_id
benchmark_mode
campaign_id
replicate_id
condition_id
x_conditions
scaffold_count
candidates_per_scaffold
candidates_expected
candidates_generated
evaluator_profile
evaluator_profile_sha256
metric_name
metric_value
metric_unit
numerator
denominator
status
failure_reason
start_time
end_time
wall_time_s
gpu_hours
cpu_hours
hardware
target_input_sha256
plan_sha256
artifact_manifest_sha256
provenance_complete
data_origin

## Required files
- EVAL_MANIFEST.json
- TARGET_MANIFEST.csv
- RUN_MANIFEST.csv
- METRIC_DICTIONARY.csv
- FIGURE2_DATA_LONG.csv
- FIGURE2_SUMMARY.csv
- FAILURE_EVENTS.csv
- CLAIM_EVENTS.csv
- PROVENANCE_MANIFEST.csv

data_origin 只允许真实来源：
real_run / real_fixture_fault_test / manual_expert / wet_lab

synthetic fixture 可测代码，但 mock 数值不得进入主结果。
