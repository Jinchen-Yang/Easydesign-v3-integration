#!/usr/bin/env python3
"""Collect read-only Figure 2 Harness metrics from an EasyDesign Agent SQLite trace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from easydesign.agent.benchmark_trace import collect_trace_metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--thread", required=True)
    parser.add_argument("--execution-id")
    parser.add_argument("--after-seq", type=int, default=0)
    parser.add_argument("--before-seq", type=int)
    parser.add_argument("--source-label")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = collect_trace_metrics(
        arguments.database,
        thread=arguments.thread,
        execution_id=arguments.execution_id,
        after_seq=arguments.after_seq,
        before_seq=arguments.before_seq,
        source_label=arguments.source_label,
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
