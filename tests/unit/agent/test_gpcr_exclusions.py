"""Default GPCR exclusions are evidence-bound and reach all compiled arms."""

from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace

import pytest
import yaml

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.design_contracts import BinderIntent
from easydesign.agent.design_evidence import resolve_design_intent
from easydesign.agent.design_exclusions import deposited_transducers, gpcr_design_exclusions
from tests.unit.agent.test_design_runtime import binder_intent, design_card, propose_design
from tests.unit.agent.test_gpcr_skill import compiled_designs, gpcr_context


def reference_case():
    sequence = "A" * 60
    ref = {"sha256": "reference", "file_format": "json"}
    feature = {
        "type": "Topological domain",
        "description": "Cytoplasmic",
        "location": {
            "start": {"value": 1, "modifier": "EXACT"},
            "end": {"value": 55, "modifier": "EXACT"},
        },
        "evidences": [{"evidenceCode": "ECO:0000255"}],
    }
    record = {"primaryAccession": "P12345", "sequence": {"value": sequence}, "features": [feature]}
    research = {
        "source_snapshot": {"queries": [{"cards": [{"provider": "UniProt", "source_refs": [ref]}]}]}
    }
    docs = {"snapshot": research, "reference": record}
    bridge = SimpleNamespace(document=lambda r: docs[r["sha256"]])
    target = {
        "evidence": {
            "identity": {
                "canonical": {
                    "accession": "P12345",
                    "sequence_sha256": sha256(sequence.encode()).hexdigest(),
                }
            }
        }
    }
    facts = {
        "declared_biology": {"target_kind": "gpcr", "required_site_compartment": "extracellular"},
        "observed_facts": {
            "mapping": [
                {"label_seq_id": n + 100, "canonical_position": n, "coordinate_present": n != 3}
                for n in range(1, 61)
            ]
        },
    }
    site = {"proposal": {"research_ref": {"sha256": "snapshot"}}}
    return bridge, target, facts, site, record


def test_canonical_exclusions_use_design_mapping_and_preserve_missing_coordinates():
    bridge, target, facts, site, _ = reference_case()
    result = gpcr_design_exclusions(bridge, target, facts, site)
    assert result["label_seq_ids"] == [n for n in range(101, 156) if n != 103]
    assert result["unobserved_label_seq_ids"] == [103]
    assert result["sources"][0]["feature"]["evidences"] == [{"evidenceCode": "ECO:0000255"}]
    intent = resolve_design_intent(
        binder_intent(),
        {
            "constraints": {"default_scaffold_template": "gpcr-vhh7-v1"},
            "approved_exclusions": [],
            "gpcr_exclusions": result,
        },
    )
    # More than forty exclusions must survive persisted intent and Gate reconstruction.
    assert (
        BinderIntent.model_validate(intent.model_dump()).arms[0].avoid_label_seq_ids
        == result["label_seq_ids"]
    )


@pytest.mark.parametrize(
    "kind,compartment", [("soluble", "extracellular"), ("gpcr", "intracellular"), ("gpcr", None)]
)
def test_other_modalities_do_not_gain_intracellular_exclusions(kind, compartment):
    bridge, target, facts, site, _ = reference_case()
    facts["declared_biology"].update(target_kind=kind, required_site_compartment=compartment)
    assert gpcr_design_exclusions(bridge, target, facts, site) is None


@pytest.mark.parametrize("change", ["foreign-accession", "foreign-sequence", "fuzzy", "ambiguous"])
def test_unverified_reference_cannot_invent_exclusions(change):
    bridge, target, facts, site, record = reference_case()
    if change == "foreign-accession":
        record["primaryAccession"] = "P99999"
    elif change == "foreign-sequence":
        record["sequence"]["value"] = "C" * 60
    elif change == "fuzzy":
        record["features"][0]["location"]["start"]["modifier"] = "UNSURE"
    else:
        facts["observed_facts"]["mapping"].append({"label_seq_id": 200, "canonical_position": 1})
    if change in {"foreign-sequence", "ambiguous"}:
        with pytest.raises(AgentBoundaryError):
            gpcr_design_exclusions(bridge, target, facts, site)
    else:
        result = gpcr_design_exclusions(bridge, target, facts, site)
        assert result["label_seq_ids"] == []
        assert result["status"] == "no-verified-residues"


def intracellular_context(bridge, monkeypatch, labels=(6,)):
    gpcr_context(bridge, monkeypatch)
    original = bridge.site_facts

    def read():
        target, facts, ref = original()
        facts = deepcopy(facts)
        facts["declared_biology"] = {
            "target_kind": "gpcr",
            "required_site_compartment": "extracellular",
            "topology_source": "synthetic explicitly supplied topology",
            "topology": [{"label_seq_id": n, "segment": "ICL3"} for n in labels],
        }
        return target, facts, ref

    monkeypatch.setattr(bridge, "site_facts", read)


def test_all_21_yamls_inherit_default_and_arm_exclusions(design_bridge, monkeypatch):
    b = design_bridge
    original_site = deepcopy(b.approved_site())
    intracellular_context(b, monkeypatch)
    intent = binder_intent().model_copy(
        update={
            "arms": [
                binder_intent(name="all").arms[0],
                binder_intent(
                    name="subset", binding_label_seq_ids=[1], scaffold_template="official-vhh7-v1"
                ).arms[0],
                binder_intent(
                    name="avoid", binding_label_seq_ids=[1], avoid_label_seq_ids=[5]
                ).arms[0],
            ]
        }
    )
    result = propose_design(b, intent)
    assert result["evaluation"]["hard_constraints"] == "passed"
    paths = compiled_designs(b)
    assert len(paths) == 21
    for path in paths:
        chain = yaml.safe_load(path.read_text())["entities"][0]["file"]["binding_types"][0]["chain"]
        assert chain["not_binding"] == ("5,6" if path.parent.name.startswith("arm-3-") else "6")
    card = design_card(b)
    assert card.scientific_summary["gpcr_exclusions"]["label_seq_ids"] == [6]
    assert b.approved_site() == original_site
    assert b.store.response(b.thread, card.card_id) is None
    assert propose_design(b, intent)["request_identity"] == result["request_identity"]


@pytest.mark.parametrize(
    "changes", [{"binding_label_seq_ids": [1]}, {"target_crop": {"start": 1, "end": 4}}]
)
def test_default_binding_and_crop_conflicts_still_block(design_bridge, monkeypatch, changes):
    intracellular_context(
        design_bridge, monkeypatch, labels=(1,) if "binding_label_seq_ids" in changes else (6,)
    )
    result = propose_design(design_bridge, binder_intent(**changes))
    assert result["evaluation"]["status"] == "BLOCKED"
    assert "compiled_ref" not in design_bridge.current_design()


def test_policy_change_invalidates_old_gate_card(design_bridge, monkeypatch):
    b = design_bridge
    propose_design(b)
    old = design_card(b)
    intracellular_context(b, monkeypatch)
    assert b.current_design() is None
    b.store.respond(b.thread, old.card_id, "approve", "synthetic-scientist")
    with pytest.raises(AgentBoundaryError, match="current|stale|changed"):
        b.apply_decision(old)
    assert b.approved_design() is None


def test_deposited_roles_use_entity_membership_not_chain_letters(tmp_path):
    path = tmp_path / "complex.cif"
    path.write_text("""data_test
loop_
_entity.id
_entity.pdbx_description
1 'Guanine nucleotide-binding protein G(s) subunit alpha isoforms short'
2 'Beta-arrestin-2'
3 'Nanobody 35'
4 'Unknown protein'
loop_
_entity_poly.entity_id
_entity_poly.pdbx_strand_id
1 'Z,Y'
2 Q
3 A
4 B
""")
    roles = deposited_transducers(path)
    assert {k: v["role"] for k, v in roles.items()} == {
        "Z": "gprotein",
        "Y": "gprotein",
        "Q": "arrestin",
    }


@pytest.mark.parametrize("role", ["gprotein", "arrestin", "other_protein"])
@pytest.mark.parametrize("matching_model", [True, False])
def test_only_identified_receptor_contacts_use_exact_source_mapping(role, matching_model):
    from pathlib import Path

    bridge, target, facts, site, _ = reference_case()
    original = bridge.document
    research = original(site["proposal"]["research_ref"])
    ref = {"artifact_id": "research-receptor-analysis", "sha256": "kernel"}
    research["source_snapshot"]["queries"].append(
        {"cards": [{"provider": "EasyDesign GPCR kernel", "source_refs": [ref]}]}
    )
    target["binding"] = "target"
    target["evidence"]["hard_facts"] = {"canonical_accession": "P12345", "selected_chain": "R"}
    # Different canonical, source and design numbers; the source model also matters.
    row = facts["observed_facts"]["mapping"][-1]
    row.update(source_author_chain_id="R", source_author_residue_id="999", model_presence=["2"])
    for other in facts["observed_facts"]["mapping"][:-1]:
        other["model_presence"] = ["2"]
    contact = {
        "residue_b": {
            "auth_asym_id": "R",
            "auth_seq_id": 999,
            "model_id": "2" if matching_model else "1",
            "hetero_flag": "ATOM",
        }
    }
    analysis = {
        "approved_design_mapping": {"target_binding": "target"},
        "identity": {"accession": "P12345", "receptor_chain": "R"},
        "structure": {"sha256": "structure"},
        "chain_graph": {
            "contact_cutoff": 5.0,
            "edges": [
                {
                    "chain_a": "Z",
                    "chain_b": "R",
                    "interface_type": role,
                    "geometry_observed": True,
                    "contacts": [contact, contact],
                }
            ],
        },
    }
    bridge.document = lambda r: analysis if r["sha256"] == "kernel" else original(r)
    bridge.binding = lambda: {"source_sha": "structure"}
    bridge.validate_project = lambda: SimpleNamespace(source_path=Path("synthetic.pdb"))
    bridge.prepared_structure = lambda: (
        Path("synthetic.pdb"),
        SimpleNamespace(sha256="structure"),
    )
    bridge.prepared_structure_path = lambda: Path("synthetic.pdb")
    result = gpcr_design_exclusions(bridge, target, facts, site)
    assert (160 in result["label_seq_ids"]) == (role != "other_protein" and matching_model)
    assert 999 not in result["label_seq_ids"]
    analysis["membrane"] = {"reliable": True}
    analysis["residue_regions"] = [
        {"region": "intracellular_tm_surface", "residue": contact["residue_b"]}
    ]
    signed = gpcr_design_exclusions(bridge, target, facts, site)
    assert (160 in signed["label_seq_ids"]) == matching_model
    analysis["approved_design_mapping"]["target_binding"] = "foreign"
    with pytest.raises(AgentBoundaryError, match="stale Target"):
        gpcr_design_exclusions(bridge, target, facts, site)


@pytest.mark.parametrize("includes_default", [True, False])
def test_expert_yaml_must_contain_default_without_runtime_rewriting(
    design_bridge, monkeypatch, includes_default
):
    from easydesign.agent.native_strategy import import_native
    from easydesign.core import sha256_file
    from tests.unit.agent.test_phase22_native import expert_input

    b = design_bridge
    intracellular_context(b, monkeypatch)
    path = expert_input(b)
    strategy = yaml.safe_load(path.read_text())
    if includes_default:
        for variant in strategy["variants"]:
            native_path = b.project / variant["native_boltzgen_yaml"]
            value = yaml.safe_load(native_path.read_text())
            value["entities"][0]["file"]["binding_types"][0]["chain"]["not_binding"] = "6"
            native_path.write_text(yaml.safe_dump(value))
            variant["native_boltzgen_sha256"] = sha256_file(native_path)
        path.write_text(yaml.safe_dump(strategy))
    before = {p: p.read_bytes() for p in path.parent.glob("*.yaml")}
    import_native(b, path)
    intent = binder_intent().model_copy(update={"strategy_source": "expert-native", "arms": []})
    result = propose_design(b, intent)
    assert (result["evaluation"]["status"] != "BLOCKED") == includes_default
    assert {p: p.read_bytes() for p in before} == before
    if includes_default:
        assert len(compiled_designs(b)) == 7
    else:
        assert "compiled_ref" not in b.current_design()
