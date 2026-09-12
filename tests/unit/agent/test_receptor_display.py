"""Reference encoding preserves every supplied scientific value and source alias."""

import copy
import json
from typing import Any

import pytest
from langchain_core.messages import ToolMessage

from easydesign.agent.evidence_output import (
    output_message,
    receptor_display_projection,
    receptor_overview_projection,
    result_tool,
    verified_result,
)
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.session_store import compact


def expanded(view: dict[str, Any]) -> dict[str, Any]:
    def unpack(item: Any) -> Any:
        if isinstance(item, dict) and set(item) == {"value_same_as"}:
            node: Any = view
            for part in item["value_same_as"].split("/")[1:]:
                key = part.replace("~1", "/").replace("~0", "~")
                node = node[int(key)] if isinstance(node, list) else node[key]
            return unpack(node)
        if isinstance(item, dict):
            return {k: unpack(v) for k, v in item.items() if k != "value_encoding"}
        if isinstance(item, list):
            return [unpack(v) for v in item]
        return item

    return unpack(view)


def receptor() -> dict[str, Any]:
    evidence = {"scope": "s" * 200, "counterevidence": ["c" * 200], "occupancy": None}
    return {
        "state": {"assignment": "active", "counterstate": None},
        "membrane": {"status": "resolved", "reliable": True},
        "topology": {"mapping_status": "resolved", "residues": [{"id": n} for n in range(50)]},
        "candidates": {
            "inhibit": [
                {
                    "id": f"candidate-{n}",
                    "unique_warning": f"Unique limitation {n}",
                    "evidence": evidence,
                    "a/b~c": evidence,
                    "classification": "primary" if n == 0 else "backup",
                    "residues": [
                        {"gpcrdb_sequence_number": n * 10 + j, "amino_acid": "C", "observed": True}
                        for j in range(1, 5)
                    ],
                }
                for n in range(4)
            ]
        },
    }


@pytest.mark.asyncio
async def test_complete_display_expands_exactly_and_scoped_reads_stay_plain(bridge: Any) -> None:
    bridge = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = bridge.store.begin_execution(bridge.thread, "Inspect receptor")["execution_id"]
    source = receptor()
    before = copy.deepcopy(source)
    original = receptor_overview_projection(source)
    view = receptor_display_projection(source)
    assert "value_encoding" in view and len(compact(view)) < len(compact(original))
    assert expanded(view) == original
    assert source == before
    artifact = bridge.persist("display-test-analysis", source)
    result = output_message(
        bridge,
        "site",
        execution,
        ToolMessage(
            content=compact({"analysis_ref": artifact}),
            name="analyze_receptor_context",
            tool_call_id="complete-analysis",
        ),
    )
    shown = json.loads(result.content)
    assert shown["declared_scope_complete"] is True
    assert expanded(shown)["candidate_overview"] == original["candidate_overview"]
    assert verified_result(bridge, "site", shown["full_result"], execution_id=execution) == before
    read = result_tool(bridge, "site")
    for index in range(4):
        response = json.loads(
            await read.ainvoke(
                {"ref": shown["full_result"], "path": ["candidate_overview", "inhibit", index]}
            )
        )
        assert response["value"] == original["candidate_overview"]["inhibit"][index]
        assert "value_same_as" not in compact(response["value"])


def test_reserved_source_field_keeps_unencoded_view() -> None:
    source = receptor()
    source["state"]["value_same_as"] = "A source field, not an encoding reference"
    assert receptor_display_projection(source) == receptor_overview_projection(source)
