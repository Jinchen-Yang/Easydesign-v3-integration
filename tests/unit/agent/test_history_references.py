"""Large completed histories retain every value via local exact-value references."""

import copy
import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from easydesign.agent.evidence_output import fit_site_working_view, reasoning_working_view
from easydesign.agent.session_store import compact
from tests.unit.agent.test_receptor_display import receptor


def expand_history(root: dict[str, Any]) -> dict[str, Any]:
    def read(item: Any) -> Any:
        if isinstance(item, dict) and set(item) == {"history_value_same_as"}:
            node: Any = root
            for part in item["history_value_same_as"].split("/")[1:]:
                part = part.replace("~1", "/").replace("~0", "~")
                node = node[int(part)] if isinstance(node, list) else node[part]
            return read(node)
        if isinstance(item, dict):
            return {key: read(value) for key, value in item.items() if key != "history_encoding"}
        if isinstance(item, list):
            return [read(value) for value in item]
        return item

    return read(root)


def test_late_context_keeps_all_arguments_failures_and_latest_science() -> None:
    messages: list[Any] = [HumanMessage(content="Immutable user goal " + "u" * 18000)]
    diagnostic = {
        "error_code": "INVALID_FIELD_PROJECTION",
        "message": "A scalar count is not a list. " * 50,
        "unknown_occupancy": None,
    }
    for n in range(24):
        call = {
            "id": f"request-{n}",
            "name": "read_evidence_result",
            "args": {"path": ["count", 0]},
        }
        messages.extend(
            [
                AIMessage(content="", tool_calls=[call]),
                ToolMessage(
                    content=compact(diagnostic),
                    tool_call_id=call["id"],
                    name=call["name"],
                    status="error",
                ),
            ]
        )
    messages.extend(
        [
            AIMessage(
                content="A hypothesis, not approved science.",
                tool_calls=[
                    {"id": "new", "name": "read_site_evidence", "args": {"label_seq_ids": [17, 23]}}
                ],
            ),
            ToolMessage(
                content=compact(
                    {"full_result": "/result-abcd.json", "candidate_evidence": receptor()}
                ),
                tool_call_id="new",
                name="read_site_evidence",
            ),
        ]
    )
    original = [m.model_dump() for m in messages]
    plain = reasoning_working_view(messages)
    assert 15000 + sum(len(str(m.content)) for m in plain) > 60000
    view, archived = fit_site_working_view(
        messages, reasoning=True, system_chars=15000, max_chars=60000, suffix=[]
    )
    assert not archived  # Repeated small diagnostics have no offloaded scientific artifact.
    assert 15000 + sum(len(str(m.content)) for m in view) <= 60000
    assert view[0] == plain[0] == messages[0]
    encoded = json.loads(view[1].content)
    assert "history_encoding" in encoded
    assert expand_history(encoded) == json.loads(plain[1].content)
    assert [m.model_dump() for m in messages] == original


def test_existing_receptor_encoding_stays_in_its_own_tool_view() -> None:
    from easydesign.agent.evidence_output import receptor_display_projection

    receptor_view = receptor_display_projection(receptor())
    before = copy.deepcopy(receptor_view)
    messages = [
        HumanMessage(content="Original goal"),
        AIMessage(
            content="", tool_calls=[{"id": "a", "name": "analyze_receptor_context", "args": {}}]
        ),
        ToolMessage(
            content=compact(receptor_view), name="analyze_receptor_context", tool_call_id="a"
        ),
    ]
    output = reasoning_working_view(messages, share_exact_values=True)
    record = json.loads(output[1].content)["runtime_history"][-1]
    assert record["content"] == before
    assert receptor_view == before


def test_incomplete_tool_exchange_is_never_reencoded() -> None:
    messages = [
        HumanMessage(content="Keep this exact turn"),
        AIMessage(
            content="", tool_calls=[{"id": "pending", "name": "read_site_evidence", "args": {}}]
        ),
    ]
    assert reasoning_working_view(messages, share_exact_values=True) == messages
