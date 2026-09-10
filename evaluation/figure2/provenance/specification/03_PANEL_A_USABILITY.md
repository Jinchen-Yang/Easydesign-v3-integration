# Panel A/B — Usability and Operational Reliability Metric Bank

尽量全部收集，主文只选最稳定的。

## 时间
- time_to_valid_project_min
- time_to_first_valid_target_bundle
- time_to_first_valid_strategy
- time_to_executable_plan
- active_human_time_min
- compute_wait_time_min
- retry_time_min

## 完成
- task_completion_rate
- first_pass_validity_rate
- project_compile_success_rate
- plan_freeze_success_rate
- complete_artifact_rate

## 人工负担
- operational_intervention_count
- scientific_approval_count
- unnecessary_manual_edit_count
- correction_count
- command_repair_count
- schema_repair_count
- path_repair_count

## Agent 行为
- tool_call_count
- distinct_tool_count
- invalid_tool_call_rate
- redundant_tool_call_rate
- failed_tool_call_rate
- evaluation_actions_per_candidate
- number_of_candidates_explicitly_compared
- number_of_alternatives_discarded
- premature_termination_rate

最后几项参考 BioDesignBench 的行为评测思路：不只看会不会调工具，还看评估深度、候选比较与是否过早停止。

## 主文
time-to-valid-project
task completion
intervention count

## Extended Data
first-pass validity
invalid action rate
tool coverage
evaluation depth
premature termination
