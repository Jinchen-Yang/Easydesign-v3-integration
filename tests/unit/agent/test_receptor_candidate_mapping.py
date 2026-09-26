"""Synthetic nonuniform numbering, missingness and source-identity regression."""

import json
from copy import deepcopy
from typing import Any

import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.evidence_output import receptor_overview_projection
from easydesign.agent.site_evidence import receptor_candidate_mapping


def examples() -> tuple[dict[str, Any], dict[str, Any]]:
    rows = [
        {
            "canonical_position": canonical,
            "label_seq_id": design,
            "construct_position": construct,
            "author_chain_id": "A",
            "source_author_chain_id": "A",
            "canonical_residue": "N",
            "amino_acid": residue,
            "mapping_status": "ambiguous",
            "edit_type": "native" if residue == "N" else "substitution",
            "model_presence": ["1"] if present else [],
            "coordinate_present": present,
            "source_author_residue_id": None,
            "insertion_code": None,
        }
        for canonical, design, construct, residue, present in [
            (10, 10, 18, "N", True),
            (20, 148, 156, "E", True),
            (21, 149, 157, "N", False),
            (22, 150, 158, "N", True),
            (22, 151, 159, "N", False),
        ]
    ]
    facts = {
        "observed_facts": {"mapping": rows},
        "derived_metrics": {
            "sasa": {"residues": [{"residue": {"label_seq_id": n}} for n in [10, 148, 150]]}
        },
    }
    receptor = {
        "identity": {"accession": "SYNTHETIC", "receptor_chain": "A"},
        "candidates": {
            "inhibit": [
                {
                    "id": "synthetic-candidate",
                    "limitations": ["No functional evidence"],
                    "residues": [
                        {"gpcrdb_sequence_number": p, "label_seq_id": p + 8, "observed": True}
                        for p in [10, 20, 21, 22, 30]
                    ],
                }
            ],
            "activate": [],
        },
    }
    return facts, receptor


def test_approved_candidate_mapping_preserves_nonuniform_and_nonunique_rows() -> None:
    facts, receptor = examples()
    before = deepcopy((facts, receptor))
    mapping = receptor_candidate_mapping(
        facts, receptor, approved_accession="SYNTHETIC", approved_auth_chain="A"
    )
    assert (facts, receptor) == before
    assert [row["mapping"] for row in mapping["facts"]] == facts["observed_facts"]["mapping"]
    assert [row["coordinate_observed"] for row in mapping["facts"]] == [
        True,
        True,
        False,
        True,
        False,
    ]
    assert mapping["unmapped_canonical_positions"] == [30]
    assert mapping["facts"][1]["mapping"]["label_seq_id"] == 148
    assert mapping["facts"][1]["mapping"]["edit_type"] == "substitution"
    projected = receptor_overview_projection({**receptor, "approved_design_mapping": mapping})
    table = projected["approved_design_mapping"]["facts_table"]
    names = table["mapping_columns"]
    decoded = [dict(zip(names, row[: len(names)], strict=True)) for row in table["rows"]]
    assert decoded == facts["observed_facts"]["mapping"]
    source = projected["candidate_overview"]["inhibit"][0]["residue_table"]
    assert "source_label_seq_id" in source["columns"]
    assert source["rows"][1][source["columns"].index("source_label_seq_id")] == 28
    assert all(row["mapping_status"] == "ambiguous" for row in decoded)


@pytest.mark.parametrize("accession,chain", [("FOREIGN", "A"), ("SYNTHETIC", "B"), (None, "A")])
def test_candidate_mapping_rejects_foreign_or_unresolved_identity(
    accession: str | None, chain: str
) -> None:
    facts, receptor = examples()
    with pytest.raises(AgentBoundaryError, match="differs from the approved Target"):
        receptor_candidate_mapping(
            facts, receptor, approved_accession=accession, approved_auth_chain=chain
        )


def test_receptor_tool_persists_and_delivers_approved_correspondence(
    site_bridge: Any, monkeypatch: Any
) -> None:
    from langchain_core.messages import ToolMessage

    import easydesign.agent.evidence_research as module
    from easydesign.agent.evidence_output import output_message
    from easydesign.agent.evidence_research import EvidenceResearch, ReceptorAnalysis

    facts, receptor = examples()
    receptor["identity"]["entry_name"] = "synthetic"
    _, prepared_ref = site_bridge.prepared_structure()
    receptor["structure"] = {"sha256": prepared_ref.sha256}
    receptor.update(topology={}, membrane={}, state={}, chain_graph={}, warnings=[], avoid=[])
    context = site_bridge.persist(
        "synthetic-gpcr-source",
        {"identity": {"status": "resolved", "entry_name": "synthetic"}, "topology": {}},
    )
    fact_ref = site_bridge.persist("synthetic-site-facts", facts)
    target, _, _ = site_bridge.site_facts()
    target = deepcopy(target)
    target["evidence"]["hard_facts"].update(canonical_accession="SYNTHETIC", selected_chain="A")
    monkeypatch.setattr(site_bridge, "site_facts", lambda: (target, facts, fact_ref))
    analysis_calls = 0

    def analyze_structure(*args: Any) -> dict[str, Any]:
        nonlocal analysis_calls
        analysis_calls += 1
        return {}

    monkeypatch.setattr(module, "analyze_structure", analyze_structure)
    monkeypatch.setattr(module, "generate_candidates", lambda *args: deepcopy(receptor))
    worker = EvidenceResearch(site_bridge)
    monkeypatch.setattr(
        worker,
        "snapshot",
        lambda: {
            "queries": [
                {
                    "cards": [
                        {
                            "card_id": "synthetic-source",
                            "provider": "GPCRdb",
                            "context_ref": context,
                            "source_refs": [context],
                        }
                    ]
                }
            ]
        },
    )
    result = worker.analyze_receptor(
        ReceptorAnalysis(gpcrdb_card_id="synthetic-source", auth_chain="A")
    )
    stored = site_bridge.document(result["analysis_ref"])
    assert stored["candidates"] == receptor["candidates"]
    event = site_bridge.thread_latest("evidence-research")
    card = site_bridge.document(event["ref"])["cards"][0]
    assert fact_ref in card["source_refs"]
    assert not card["primary_eligible"]
    message = output_message(
        site_bridge,
        "site",
        "synthetic-receptor-execution",
        ToolMessage(
            name="analyze_receptor_context",
            tool_call_id="synthetic-receptor-tool",
            content=json.dumps({"analysis_ref": result["analysis_ref"]}),
        ),
    )
    supplied = json.loads(message.content)
    table = supplied["approved_design_mapping"]["facts_table"]
    assert table["row_count"] == 5
    assert table["rows"][1][table["mapping_columns"].index("label_seq_id")] == 148
    assert supplied["candidate_overview"]["inhibit"][0]["id"] == "synthetic-candidate"
    assert analysis_calls == 1

    # The model-facing kernel read must reuse the analysis atomically published by
    # acquisition instead of repeating structure/topology calculation.
    monkeypatch.setattr(
        worker,
        "snapshot",
        lambda: {
            "queries": [
                {
                    "cards": [
                        {
                            "card_id": "synthetic-source",
                            "provider": "GPCRdb",
                            "context_ref": context,
                            "source_refs": [context],
                        },
                        {
                            "card_id": result["card_id"],
                            "provider": "EasyDesign GPCR kernel",
                            "source_refs": [context, fact_ref, result["analysis_ref"]],
                        },
                    ]
                }
            ]
        },
    )
    reused = worker.analyze_receptor(
        ReceptorAnalysis(gpcrdb_card_id="synthetic-source", auth_chain="A")
    )
    assert reused["reused"] is True
    assert reused["analysis_ref"] == result["analysis_ref"]
    assert reused["card_id"] == result["card_id"]
    assert analysis_calls == 1
