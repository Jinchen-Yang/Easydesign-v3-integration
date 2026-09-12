"""Plain receptor views preserve scientific values and existing scoped source access."""

import copy
import json
from typing import Any

import pytest
from langchain_core.messages import ToolMessage

from easydesign.agent.evidence_output import (
    output_message,
    receptor_overview_projection,
    result_tool,
    verified_result,
)
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.session_store import compact


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
                        {
                            "gpcrdb_sequence_number": n * 10 + j,
                            "amino_acid": "C",
                            "observed": True,
                            "auth_seq_id": n * 10 + j,
                            "label_seq_id": n * 10 + j + 8,
                        }
                        for j in range(1, 5)
                    ],
                }
                for n in range(4)
            ]
        },
    }


@pytest.mark.asyncio
async def test_complete_display_and_scoped_reads_preserve_plain_scientific_values(
    bridge: Any,
) -> None:
    bridge = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = bridge.store.begin_execution(bridge.thread, "Inspect receptor")["execution_id"]
    source = receptor()
    before = copy.deepcopy(source)
    original = receptor_overview_projection(source)
    assert source == before
    table = original["candidate_overview"]["inhibit"][0]["residue_table"]
    assert "label_seq_id" not in table["columns"]
    first = dict(zip(table["columns"], table["rows"][0], strict=True))
    assert first["gpcrdb_sequence_number"] == first["source_auth_seq_id"] == 1
    assert first["source_label_seq_id"] == 9
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
    assert shown["candidate_overview"] == original["candidate_overview"]
    assert "value_encoding" not in shown and "value_same_as" not in compact(shown)
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


def test_source_fields_are_not_interpreted_as_custom_reference_syntax() -> None:
    source = receptor()
    source["state"]["value_same_as"] = "A source field, not an encoding reference"
    assert receptor_overview_projection(source)["state"] == source["state"]
