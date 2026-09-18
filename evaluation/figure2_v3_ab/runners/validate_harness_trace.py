#!/usr/bin/env python3
"""Evaluate one collected Harness trace against the frozen efficiency thresholds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _metric(trace: dict[str, Any], name: str) -> int | float:
    paths = {
        "total_model_calls_max": ("model_calls", "total"),
        "site_research_model_calls_max": ("model_calls", "by_role", "site"),
        "framework_summary_calls_max": ("framework_summaries", "calls"),
        "framework_summary_output_tokens_max": (
            "framework_summaries",
            "usage",
            "output_tokens",
        ),
        "tool_calls_max": ("tools", "total"),
        "read_file_calls_max": ("tools", "by_name", "read_file"),
        "read_evidence_result_calls_max": (
            "tools",
            "by_name",
            "read_evidence_result",
        ),
        "max_input_chars_with_schemas": (
            "context",
            "input_chars_with_schemas",
            "max",
        ),
        "hard_context_guard_events": ("context", "hard_guard_events"),
    }
    value: Any = trace
    for key in paths[name]:
        if not isinstance(value, dict) or key not in value:
            return 0
        value = value[key]
    return 0 if value is None else value


def evaluate(trace: dict[str, Any], acceptance: dict[str, Any]) -> dict[str, Any]:
    checks = []
    for name, threshold in acceptance["efficiency_targets_per_successful_run"].items():
        observed = _metric(trace, name)
        # All currently frozen targets are upper bounds, including an exact zero guard target.
        checks.append(
            {
                "metric": name,
                "observed": observed,
                "maximum": threshold,
                "status": "PASS" if observed <= threshold else "FAIL",
            }
        )
    return {
        "schema_version": "figure2-v3-harness-trace-evaluation-v1",
        "trace_digest_sha256": trace["source"]["event_digest_sha256"],
        "status": "PASS" if all(row["status"] == "PASS" for row in checks) else "FAIL",
        "efficiency_checks": checks,
        "scientific_checks": "SEPARATE_REQUIRED_INPUT",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = evaluate(
        json.loads(arguments.trace.read_text()),
        json.loads(arguments.acceptance.read_text()),
    )
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        print(encoded, end="")
        return
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("x") as handle:
        handle.write(encoded)


if __name__ == "__main__":
    main()
