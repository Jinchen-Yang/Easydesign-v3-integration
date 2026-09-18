import importlib.util
from pathlib import Path


def _module():
    path = Path(__file__).parents[3] / "evaluation/figure2_v3_ab/runners/validate_harness_trace.py"
    spec = importlib.util.spec_from_file_location("validate_harness_trace", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_trace_validation_reports_each_threshold_without_scientific_claims() -> None:
    trace = {
        "source": {"event_digest_sha256": "a" * 64},
        "model_calls": {"total": 9, "by_role": {"site": 7}},
        "framework_summaries": {"calls": 1, "usage": {"output_tokens": 400}},
        "tools": {"total": 12, "by_name": {"read_file": 2}},
        "context": {
            "input_chars_with_schemas": {"max": 42000},
            "hard_guard_events": 0,
        },
    }
    acceptance = {
        "efficiency_targets_per_successful_run": {
            "total_model_calls_max": 8,
            "site_research_model_calls_max": 8,
            "framework_summary_calls_max": 2,
            "framework_summary_output_tokens_max": 1024,
            "tool_calls_max": 20,
            "read_file_calls_max": 4,
            "read_evidence_result_calls_max": 3,
            "max_input_chars_with_schemas": 50000,
            "hard_context_guard_events": 0,
        }
    }
    result = _module().evaluate(trace, acceptance)
    assert result["status"] == "FAIL"
    assert result["scientific_checks"] == "SEPARATE_REQUIRED_INPUT"
    failed = [row["metric"] for row in result["efficiency_checks"] if row["status"] == "FAIL"]
    assert failed == ["total_model_calls_max"]
