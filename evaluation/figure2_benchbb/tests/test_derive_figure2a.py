import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "runners/derive_figure2a.py"
S = importlib.util.spec_from_file_location("d", P)
M = importlib.util.module_from_spec(S)
S.loader.exec_module(M)


class MetricsTest(unittest.TestCase):
    def test_usage(self):
        rows = [
            {"kind": "model-call", "payload": {}},
            {
                "kind": "model-context",
                "payload": {"input_chars_with_schemas": 900, "repair_attempt": 0},
            },
            {
                "kind": "model-response",
                "payload": {
                    "latency_seconds": 1,
                    "responses": [
                        {
                            "invalid_tool_names": [],
                            "stop_reason": "end_turn",
                            "usage": {"input_tokens": 100, "output_tokens": 20},
                        }
                    ],
                },
            },
            {"kind": "tool", "payload": {}},
            {"kind": "agent-terminal", "payload": {"status": "finished"}},
        ]
        r = M.runtime_summary(rows)
        self.assertEqual(
            (
                r["model_calls"],
                r["tool_calls"],
                r["input_tokens"],
                r["output_tokens"],
                r["peak_chars"],
            ),
            (1, 1, 100, 20, 900),
        )

    def test_missing_sentinel(self):
        self.assertEqual(M.NA, "not_available")


if __name__ == "__main__":
    unittest.main()
