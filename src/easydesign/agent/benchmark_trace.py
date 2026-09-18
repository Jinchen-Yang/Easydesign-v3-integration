"""Read-only, deterministic metrics for a persisted Agent execution trace."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import statistics
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def _usage_totals(value: Any) -> Counter[str]:
    totals: Counter[str] = Counter()
    records = value if isinstance(value, list) else [value]
    for record in records:
        if not isinstance(record, dict):
            continue
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            number = record.get(key)
            if isinstance(number, int):
                totals[key] += number
    return totals


def collect_trace_metrics(
    database: Path,
    *,
    thread: str,
    execution_id: str | None = None,
    after_seq: int = 0,
    before_seq: int | None = None,
    source_label: str | None = None,
) -> dict[str, Any]:
    """Aggregate one immutable event range without modifying its SQLite store."""
    database = database.resolve(strict=True)
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        query = "SELECT seq,kind,payload FROM events WHERE thread=? AND seq>?"
        arguments: list[Any] = [thread, after_seq]
        if before_seq is not None:
            query += " AND seq<=?"
            arguments.append(before_seq)
        query += " ORDER BY seq"
        rows = connection.execute(query, arguments).fetchall()
    finally:
        connection.close()

    events: list[tuple[int, str, dict[str, Any]]] = []
    for seq, kind, raw in rows:
        payload = json.loads(raw)
        if execution_id is not None and payload.get("execution_id") not in {
            execution_id,
            None,
        }:
            continue
        events.append((seq, kind, payload))

    kinds = Counter(kind for _, kind, _ in events)
    roles: Counter[str] = Counter()
    tools: Counter[str] = Counter()
    tools_by_role: Counter[str] = Counter()
    model_latency: list[float] = []
    summary_latency: list[float] = []
    model_usage: Counter[str] = Counter()
    summary_usage: Counter[str] = Counter()
    context_chars: list[int] = []
    context_tokens: list[int] = []
    soft_target_exceeded = 0

    for _, kind, payload in events:
        if kind == "model-call":
            roles[str(payload.get("role", "unknown"))] += 1
        elif kind == "tool":
            role = str(payload.get("role", "unknown"))
            name = str(payload.get("name", "unknown"))
            tools[name] += 1
            tools_by_role[f"{role}:{name}"] += 1
        elif kind == "model-response":
            latency = payload.get("latency_seconds")
            if isinstance(latency, (int, float)):
                model_latency.append(float(latency))
            for response in payload.get("responses", []):
                model_usage.update(_usage_totals(response.get("usage")))
        elif kind == "framework-summary-response":
            latency = payload.get("latency_seconds")
            if isinstance(latency, (int, float)):
                summary_latency.append(float(latency))
            summary_usage.update(_usage_totals(payload.get("usage")))
        elif kind == "model-context":
            chars = payload.get("input_chars_with_schemas")
            tokens = payload.get("estimated_input_tokens")
            if isinstance(chars, int):
                context_chars.append(chars)
            if isinstance(tokens, int):
                context_tokens.append(tokens)
            soft_target_exceeded += bool(payload.get("soft_target_exceeded"))

    def distribution(values: Sequence[float | int]) -> dict[str, float | int | None]:
        if not values:
            return {"count": 0, "sum": 0, "median": None, "max": None}
        return {
            "count": len(values),
            "sum": sum(values),
            "median": statistics.median(values),
            "max": max(values),
        }

    sequence = [seq for seq, _, _ in events]
    event_digest = hashlib.sha256(
        json.dumps(events, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schema_version": "figure2-trace-metrics-v1",
        "source": {
            "database": source_label or str(database),
            "event_digest_sha256": event_digest,
            "thread": thread,
            "execution_id": execution_id,
            "after_seq": after_seq,
            "before_seq": before_seq,
            "first_seq": min(sequence) if sequence else None,
            "last_seq": max(sequence) if sequence else None,
        },
        "events": {"total": len(events), "by_kind": dict(sorted(kinds.items()))},
        "model_calls": {
            "total": kinds["model-call"],
            "by_role": dict(sorted(roles.items())),
            "response_latency_seconds": distribution(model_latency),
            "usage": dict(sorted(model_usage.items())),
        },
        "framework_summaries": {
            "calls": kinds["framework-summary-call"],
            "responses": kinds["framework-summary-response"],
            "latency_seconds": distribution(summary_latency),
            "usage": dict(sorted(summary_usage.items())),
        },
        "tools": {
            "total": kinds["tool"],
            "by_name": dict(sorted(tools.items())),
            "by_role_and_name": dict(sorted(tools_by_role.items())),
        },
        "context": {
            "input_chars_with_schemas": distribution(context_chars),
            "estimated_input_tokens": distribution(context_tokens),
            "soft_target_exceeded_calls": soft_target_exceeded,
            "hard_guard_events": kinds["hard-context-guard"],
        },
        "quality_control": {
            "rejected_submissions": kinds["rejected-submission"],
            "contract_repairs": kinds["contract-repair"],
            "submission_preflight_passed": kinds["submission-preflight-passed"],
            "scientific_consistency_findings": kinds["scientific-consistency-finding"],
            "research_reservations": kinds["research-reservation"],
            "decision_cards": kinds["decision-card"],
        },
    }
