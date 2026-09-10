"""Capture final CPU-only validation; the expected GPU gate outcome is blocked."""
import json
import sys
from run_cpu import ROOT, EVAL, put, run_cmd


def main():
    commands = [
        ("source-freeze", [sys.executable, "evaluation/figure2/runners/run_cpu.py", "verify"], 0),
        ("evaluation-tests", [sys.executable, "-m", "pytest", "evaluation/figure2/metrics/test_evaluation.py", "-q", "-o", "addopts=", "-o", "cache_dir=runtime/cache/figure2/math-tests-final"], 0),
        ("gpu-gate", [sys.executable, "evaluation/figure2/runners/gpu_gate.py", "--queue", "evaluation/figure2/manifests/GPU_TASK_QUEUE.json"], 2),
        ("diff-check", ["git", "diff", "--check"], 0),
    ]
    records = []
    for name, command, expected in commands:
        receipt, _ = run_cmd(command, EVAL / "provenance/final-validation" / name, timeout=120)
        records.append({"check": name, "expected_returncode": expected, "passed": receipt["returncode"] == expected, **receipt})
    put(EVAL / "provenance/final-validation/summary.json", {"status": "passed" if all(r["passed"] for r in records) else "failed", "checks": records})
    print(json.dumps({r["check"]: r["passed"] for r in records}))
    if not all(r["passed"] for r in records):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
