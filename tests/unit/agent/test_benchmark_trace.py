import json
import sqlite3
from pathlib import Path

from easydesign.agent.benchmark_trace import collect_trace_metrics


def test_collect_trace_metrics_keeps_summary_cost_separate(tmp_path: Path) -> None:
    database = tmp_path / "agent.sqlite"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE events(seq INTEGER PRIMARY KEY, thread TEXT, kind TEXT, payload TEXT)"
    )
    rows = [
        (1, "t", "model-call", {"role": "site", "execution_id": "e"}),
        (
            2,
            "t",
            "model-context",
            {
                "execution_id": "e",
                "input_chars_with_schemas": 42000,
                "estimated_input_tokens": 10500,
                "soft_target_exceeded": False,
            },
        ),
        (
            3,
            "t",
            "model-response",
            {
                "execution_id": "e",
                "role": "site",
                "site_stage": "research",
                "latency_seconds": 4.5,
                "responses": [
                    {
                        "usage": {
                            "input_tokens": 100,
                            "output_tokens": 20,
                            "total_tokens": 120,
                        }
                    }
                ],
            },
        ),
        (4, "t", "auxiliary-model-call", {"role": "site", "execution_id": "e"}),
        (5, "t", "framework-summary-call", {"role": "site", "execution_id": "e"}),
        (
            6,
            "t",
            "framework-summary-response",
            {
                "execution_id": "e",
                "role": "site",
                "latency_seconds": 2.0,
                "usage": [
                    {
                        "input_tokens": 80,
                        "output_tokens": 30,
                        "total_tokens": 110,
                    }
                ],
            },
        ),
        (
            7,
            "t",
            "tool",
            {"role": "site", "name": "read_evidence_result", "execution_id": "e"},
        ),
        (8, "t", "submission-preflight-passed", {"role": "site", "execution_id": "e"}),
        (9, "other", "model-call", {"role": "judge", "execution_id": "foreign"}),
    ]
    connection.executemany(
        "INSERT INTO events(seq,thread,kind,payload) VALUES(?,?,?,?)",
        [(seq, thread, kind, json.dumps(payload)) for seq, thread, kind, payload in rows],
    )
    connection.commit()
    connection.close()

    result = collect_trace_metrics(
        database, thread="t", execution_id="e", source_label="nk2r-attempt005"
    )
    assert result["source"]["database"] == "nk2r-attempt005"
    assert len(result["source"]["event_digest_sha256"]) == 64
    assert result["source"]["first_seq"] == 1
    assert result["model_calls"]["total"] == 1
    assert result["model_calls"]["by_role"] == {"site": 1}
    assert result["model_calls"]["usage"]["total_tokens"] == 120
    assert result["framework_summaries"]["calls"] == 1
    assert result["framework_summaries"]["reserved_calls"] == 1
    assert result["framework_summaries"]["usage"]["output_tokens"] == 30
    assert result["provider_calls"] == {
        "total": 2,
        "scientific": 1,
        "auxiliary": 1,
        "usage": {"input_tokens": 180, "output_tokens": 50, "total_tokens": 230},
    }
    assert result["site_timing"]["research_model_wall_seconds"]["sum"] == 4.5
    assert result["site_timing"]["auxiliary_summary_wall_seconds"]["sum"] == 2.0
    assert result["site_timing"]["observed_provider_wall_seconds"] == 6.5
    assert result["tools"]["by_name"] == {"read_evidence_result": 1}
    assert result["context"]["input_chars_with_schemas"]["max"] == 42000
    assert result["quality_control"]["submission_preflight_passed"] == 1
