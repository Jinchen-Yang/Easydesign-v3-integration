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
""")
    before = source.read_bytes()
    value = deposited_polymer_metadata(source)
    assert value["status"] == "reported"
    assert value["entities"] == [
        {
            "entity_id": "1",
            "deposited_description": "Receptor, fusion partner",
            "deposited_source_segments": [],
            "polymer_type": "polypeptide(L)",
            "source_label_chain_ids": ["A", "C"],
            "source_auth_chain_ids": ["R", "S"],
        },
        {
            "entity_id": "2",
            "deposited_description": "Antibody fragment",
            "deposited_source_segments": [],
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
