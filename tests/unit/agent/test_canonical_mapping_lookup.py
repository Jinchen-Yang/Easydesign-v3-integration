"""Explicit SYNTHETIC mapping lookup regressions; no new alignments or approvals."""

import json
from copy import deepcopy
from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from pydantic import ValidationError

from easydesign.agent.evidence_output import output_message, verified_result
from easydesign.agent.phase2_tools import PHASE2_ALLOWED, phase2_tools
from easydesign.agent.site_contracts import CanonicalMappingQuery
from easydesign.agent.site_evidence import canonical_mapping_rows


def synthetic_facts() -> dict[str, Any]:
    rows = [
        {
            "label_seq_id": 35,
            "canonical_position": 53,
            "mapping_status": "review-required",
            "source_author_chain_id": "L",
            "source_author_residue_id": "35",
            "model_presence": ["1"],
        },
        {
            "label_seq_id": 427,
            "canonical_position": 299,
            "mapping_status": "ambiguous",
            "source_author_chain_id": "A",
            "source_author_residue_id": "299",
            "model_presence": ["1"],
        },
        {
            "label_seq_id": 900,
            "canonical_position": 299,
            "mapping_status": "ambiguous",
            "source_author_chain_id": "B",
            "source_author_residue_id": "299",
            "model_presence": ["2"],
        },
        {
            "label_seq_id": 128,
            "canonical_position": 146,
            "mapping_status": "review-required",
            "coordinate_present": False,
            "model_presence": [],
            "source_author_residue_id": None,
        },
        {
            "label_seq_id": 999,
            "canonical_position": None,
            "mapping_status": "unmapped",
            "model_presence": ["1"],
        },
    ]
    return {
        "observed_facts": {"mapping": rows},
        "derived_metrics": {
            "sasa": {"residues": [{"residue": {"label_seq_id": n}} for n in [35, 427, 900, 999]]}
        },
    }


def test_lookup_retains_all_qualified_rows_and_distinguishes_missing_states() -> None:
    facts = synthetic_facts()
    before = deepcopy(facts)
    result = canonical_mapping_rows(
        facts, CanonicalMappingQuery(canonical_positions=[53, 299, 146, 18])
    )
    matches = result["matches"]
    assert [m["canonical_position"] for m in matches] == [53, 299, 146, 18]
    assert matches[0]["observed_design_labels"] == [35]
    assert matches[1]["mapping_rows"] == facts["observed_facts"]["mapping"][1:3]
    assert matches[1]["observed_design_labels"] == [427, 900]
    assert matches[2]["mapping_rows"] == [facts["observed_facts"]["mapping"][3]]
    assert matches[2]["status"] == "mapped" and matches[2]["observed_design_labels"] == []
    assert matches[3]["status"] == "no-approved-correspondence" and matches[3]["mapping_rows"] == []
    assert facts == before


@pytest.mark.parametrize("positions", [[], [0], [-1], [True], [53, 53], list(range(1, 8))])
def test_lookup_rejects_invalid_or_unbounded_position_queries(positions: list[Any]) -> None:
    with pytest.raises(ValidationError):
        CanonicalMappingQuery(canonical_positions=positions)


@pytest.mark.asyncio
async def test_lookup_tool_uses_bound_target_and_preserves_full_output(
    site_bridge: Any, monkeypatch: Any
) -> None:
    bridge = site_bridge
    target, _, ref = bridge.site_facts()
    binding = target["binding"]
    jobs = len(bridge.controller.list(project_id=bridge.project_id))
    tool = next(t for t in phase2_tools(bridge, "site") if t.name == "read_canonical_mapping")
    # The real synthetic prepared target has no verified canonical reference: never infer identity.
    unknown = json.loads(await tool.ainvoke({"canonical_positions": [1]}))
    assert unknown["matches"][0]["status"] == "no-approved-correspondence"
    facts = synthetic_facts()
    monkeypatch.setattr(bridge, "site_facts", lambda: (target, facts, ref))
    payload = bridge.read_canonical_mapping(
        CanonicalMappingQuery(canonical_positions=[53, 299, 146, 18])
    )
    execution = bridge.store.begin_execution(bridge.thread, "Synthetic canonical lookup")
    projected = output_message(
        bridge,
        "site",
        execution["execution_id"],
        ToolMessage(
            content=json.dumps(payload), name="read_canonical_mapping", tool_call_id="mapping"
        ),
    )
    value = json.loads(projected.content)
    assert value["matches"] == payload["matches"]
    assert value["limitations"] == payload["limitations"]
    assert value["scientific_content_complete"] is True
    stored = verified_result(
        bridge, "site", value["full_result"], execution_id=execution["execution_id"]
    )
    assert stored["matches"] == payload["matches"]
    assert bridge.target_state()["binding"] == binding
    assert len(bridge.controller.list(project_id=bridge.project_id)) == jobs
    assert bridge.current_site() is None and bridge.approved_site() is None
    assert all(
        "read_canonical_mapping" not in names
        for role, names in PHASE2_ALLOWED.items()
        if role != "site"
    )
