"""Bounded display excerpts. Full declared review documents remain available."""

from __future__ import annotations

import json
from typing import Any


def excerpt(value: Any, budget: int = 14000) -> Any:
    if len(json.dumps(value, ensure_ascii=False)) <= budget:
        return value
    if isinstance(value, dict):
        priority = (
            "pilot_scope",
            "scale_execution_intent",
            "proposed_interpretation",
            "primary_candidate_ids",
            "backup_candidate_ids",
            "independent_review",
        )
        keys = [k for k in priority if k in value] + [k for k in value if k not in priority]
        chosen: dict[str, Any] = {}
        remaining = budget - 100
        for key in keys:
            if remaining < 250:
                break
            # Allocate bounded space while making omitted details explicit.
            part = excerpt(value[key], min(remaining - len(key) - 20, max(500, budget // 3)))
            chosen[key] = part
            remaining -= len(json.dumps({key: part}, ensure_ascii=False))
        chosen["display_excerpt"] = "See the complete review document for all details."
        return chosen
    if isinstance(value, list):
        sample: list[Any] = []
        remaining = budget - 150
        for item in value:
            if remaining < 250:
                break
            part = excerpt(item, min(remaining, max(200, budget // 4)))
            sample.append(part)
            remaining -= len(json.dumps(part, ensure_ascii=False)) + 2
        return {
            "total_items": len(value),
            "preview": sample,
            "display_excerpt": "Complete list is retained in the review document.",
        }
    return str(value)[: max(0, budget - 80)] + " [display excerpt; see complete document]"
