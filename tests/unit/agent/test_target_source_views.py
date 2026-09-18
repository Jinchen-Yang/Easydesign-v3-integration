"""Read-only depositor metadata and current canonical source-view prerequisites."""

from pathlib import Path
from typing import Any

from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.session_store import identity
from easydesign.agent.target_identity import (
    deposited_polymer_metadata,
    pending_canonical_source_read,
)


def test_deposited_entity_projection_preserves_original_chain_names(tmp_path: Path) -> None:
    source = tmp_path / "target.cif"
    source.write_text("""data_target
loop_
_entity.id
_entity.type
_entity.pdbx_description
1 polymer 'Receptor, fusion partner'
2 polymer 'Antibody fragment'
3 non-polymer LIG
loop_
_entity_poly.entity_id
_entity_poly.type
_entity_poly.pdbx_strand_id
1 'polypeptide(L)' 'R, S'
2 'polypeptide(L)' N
loop_
_struct_asym.id
_struct_asym.entity_id
A 1
B 2
C 1
D 3
loop_
_struct_ref.id
_struct_ref.db_name
_struct_ref.db_code
_struct_ref.pdbx_db_accession
_struct_ref.pdbx_db_isoform
_struct_ref.entity_id
1 UNP RECEPTOR_HUMAN P12345 ? 1
""")
    before = source.read_bytes()
    value = deposited_polymer_metadata(source)
    assert value["status"] == "reported"
    assert value["entities"] == [
        {
            "entity_id": "1",
            "deposited_description": "Receptor, fusion partner",
            "deposited_source_segments": [],
            "deposited_database_references": [
                {
                    "database_name": "UNP",
                    "database_code": "RECEPTOR_HUMAN",
                    "accession": "P12345",
                    "isoform": None,
                }
            ],
            "polymer_type": "polypeptide(L)",
            "source_label_chain_ids": ["A", "C"],
            "source_auth_chain_ids": ["R", "S"],
        },
        {
            "entity_id": "2",
            "deposited_description": "Antibody fragment",
            "deposited_source_segments": [],
            "deposited_database_references": [],
            "polymer_type": "polypeptide(L)",
            "source_label_chain_ids": ["B"],
            "source_auth_chain_ids": ["N"],
        },
    ]
    assert source.read_bytes() == before and "not proof" in value["authority"]
    assert (
        deposited_polymer_metadata(tmp_path / "unannotated.pdb")["status"]
        == "not-reported-in-input"
    )


def test_canonical_view_prerequisite_needs_current_binding_and_identity_scope(bridge: Any) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    assert pending_canonical_source_read(b) is None
    b.store.event(b.thread, "canonical-reference-proposal", {"accession": "P00698"})
    assert pending_canonical_source_read(b) == "UniProt:P00698"

    def view(need: str, binding: str, source: str = "UniProt:P00698") -> None:
        ref = b.persist(
            "evidence-view",
            {
                "need": need,
                "cards": [{"source_id": source, "binding_context": {"current_binding": binding}}],
            },
        )
        b.store.event(b.thread, "evidence-view", {"ref": ref})

    view("TARGET_IDENTITY", "old-binding")
    current = identity(b.binding())
    view("FUNCTIONAL_MECHANISM", current)
    view("TARGET_IDENTITY", current, "UniProt:P07550")
    assert pending_canonical_source_read(b) == "UniProt:P00698"
    view("TARGET_IDENTITY", current)
    assert pending_canonical_source_read(b) is None
    assert not b._jobs()


def test_target_preview_keeps_all_deposited_segments(bridge: Any) -> None:
    import json

    from langchain_core.messages import ToolMessage

    from easydesign.agent.evidence_output import output_message
    from easydesign.agent.session_store import compact

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = b.store.begin_execution(b.thread, "Inspect a multi-origin construct")
    segments = [
        {"begin": 9, "end": 238, "organism": "human"},
        {"begin": 399, "end": 501, "organism": "human"},
        {"begin": 239, "end": 398, "organism": "phage T4"},
    ]
    metadata = {"entities": [{"source_segments": segments}], "authority": "depositor"}
    value = {"deposited_entities": metadata, "large_mapping": list(range(2000))}
    result = json.loads(
        output_message(
            b,
            "target",
            execution["execution_id"],
            ToolMessage(name="read_target_evidence", tool_call_id="target", content=compact(value)),
        ).content
    )
    assert result["partial"] and len(compact(result)) < 6600
    assert result["deposited_entities"] == metadata
    assert result["deposited_entities"]["entities"][0]["source_segments"][2] == segments[2]


def test_target_gate_receives_one_complete_bounded_decision_view(bridge: Any) -> None:
    import json

    from langchain_core.messages import ToolMessage

    from easydesign.agent.evidence_output import output_message
    from easydesign.agent.session_store import compact

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = b.store.begin_execution(b.thread, "Review a multi-chain target gate")
    missing = list(range(1, 31)) + list(range(236, 402))
    options = [
        {
            "option_id": f"chain-{chain.lower()}",
            "label": f"chain {chain}",
            "eligible": True,
            "description": "Scientist selection required",
        }
        for chain in ("G", "R", "A", "N", "B", "C")
    ]
    chains = [
        {
            "auth_chain": option["label"].split()[-1],
            "construct_length": 406,
            "observed_length": 297,
            "missing_construct_positions": missing,
        }
        for option in options
    ]
    value = {
        "status": "awaiting-human-approval",
        "decision_kind": "chain-selection",
        "question": "Choose the receptor chain.",
        "options": options,
        "chains": chains,
        "hard_facts": {"canonical_accession": "P21452", "chains": chains},
        "identity_evidence": {
            "construct_comparisons": chains,
            "decision_context": "x" * 6500,
        },
        "limitations": ["Identity does not establish function."],
    }
    rendered = json.loads(
        output_message(
            b,
            "target",
            execution["execution_id"],
            ToolMessage(content=compact(value), name="read_target_evidence", tool_call_id="gate"),
        ).content
    )
    assert rendered["projection_scope"] == "target-gate-decision"
    assert rendered["declared_scope_complete"]
    assert rendered["scientific_content_complete"] and not rendered["partial"]
    assert rendered["options"] == options
    encoded = rendered["hard_facts"]["chains"][0]
    assert encoded["missing_construct_position_count"] == len(missing)
    assert [
        position
        for start, end in encoded["missing_construct_position_ranges_inclusive"]
        for position in range(start, end + 1)
    ] == missing
    assert len(compact(rendered)) < 30000


def test_target_position_ranges_are_lossless_and_distinct_from_alignment_deletions() -> None:
    from easydesign.agent.evidence_output import target_page_projection

    positions = list(range(1, 31)) + list(range(236, 402)) + list(range(481, 502))
    value = {"chains": [{"missing_construct_positions": positions, "deletions": 48}]}
    projected = target_page_projection(value)["chains"][0]
    assert projected["deletions"] == 48
    assert projected["missing_construct_position_count"] == len(positions) == 217
    ranges = projected["missing_construct_position_ranges_inclusive"]
    assert [p for start, end in ranges for p in range(start, end + 1)] == positions
    assert value["chains"][0]["missing_construct_positions"] == positions
    small = {"missing_construct_positions": [128, 129]}
    assert target_page_projection(small) == small
