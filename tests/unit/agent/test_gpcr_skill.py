"""GPCR Skill templates reach executable YAML; no model or binding claims."""

from copy import deepcopy
from importlib import resources

import pytest
import yaml

from easydesign.agent.design_evidence import design_constraints, resolve_design_intent
from easydesign.agent.harness import site_research_prompt, site_synthesis_prompt
from easydesign.core import ManifestStateError
from easydesign.stages.s03_boltzgen_configuration.compiler import ASSET_PACKAGE, SCAFFOLD_IDS
from easydesign.stages.s03_boltzgen_configuration.scaffold_templates import (
    GPCR_TEMPLATE,
    gpcr_template,
)
from tests.unit.agent.test_design_runtime import binder_intent, design_card, propose_design


def gpcr_context(bridge, monkeypatch):
    original = bridge.read_site_evidence

    def read(query=None):
        result = deepcopy(original(query))
        result["biology"] = {**(result["biology"] or {}), "target_kind": "gpcr"}
        return result

    monkeypatch.setattr(bridge, "read_site_evidence", read)


def test_site_skill_prioritizes_reachable_orthosteric_gpcr_candidate() -> None:
    research = " ".join(site_research_prompt(domain_skills=True).split())
    synthesis = " ".join(site_synthesis_prompt().split())

    for prompt in (research, synthesis):
        assert "activating and inhibitory extracellular GPCR binder goals" in prompt
        assert "orthosteric ligand entrance or outer vestibule" in prompt
        assert "Peripheral ECL-only patches" in prompt
        assert "Pocket depth alone is insufficient" in prompt
        assert "Orthosteric engagement alone" in prompt
    assert "default-rank first" in synthesis
    assert "Runtime will display that first-ranked candidate as A" in synthesis
    assert "hard-invalid rather than merely later-ranked" in synthesis


def compiled_designs(bridge):
    proposal = bridge.current_design()
    refs = bridge.document(proposal["compiled_ref"])
    return [
        bridge.project / ref["relative_path"]
        for ref in refs
        if ref["relative_path"].endswith("/design.yaml")
    ]


def test_gpcr_defaults_compile_all_seven_supplied_templates(design_bridge, monkeypatch):
    bridge = design_bridge
    gpcr_context(bridge, monkeypatch)
    site = deepcopy(bridge.approved_site())
    evidence = bridge.read_design_evidence()
    assert evidence["constraints"]["default_scaffold_template"] == GPCR_TEMPLATE
    assert len(evidence["constraints"]["scaffolds"]) == 7
    result = propose_design(bridge)
    assert result["evaluation"]["hard_constraints"] == "passed"
    assert result["proposal"]["arms"][0]["scaffold_template"] == GPCR_TEMPLATE
    expected_insertions = dict(
        zip(
            SCAFFOLD_IDS,
            ("1..37", "1..46", "1..37", "1..42", "1..36", "1..43", "1..38"),
            strict=True,
        )
    )
    designs = compiled_designs(bridge)
    assert len(designs) == 7
    for path in designs:
        name = path.parent.name.removeprefix("arm-1-scaffold-")
        design = yaml.safe_load(path.read_text())
        assert design["entities"][1]["file"]["path"] == "scaffold.yaml"
        actual = yaml.safe_load((path.parent / "scaffold.yaml").read_text())
        expected, _ = gpcr_template(name)
        expected["path"] = f"../../assets/scaffolds/{name}.cif"
        # Whole-object comparison protects CDR1/2, exclusions, visibility and anchors too.
        assert actual == expected
        assert (
            actual["design_insertions"][2]["insertion"]["num_residues"] == expected_insertions[name]
        )
        assert (path.parent / actual["path"]).is_file()
        assert "not_binding" not in design["entities"][0]["file"]["binding_types"][0]["chain"]
    card = design_card(bridge)
    assert card.gate_type == "design-specification"
    assert bridge.store.response(bridge.thread, card.card_id) is None
    assert bridge.approved_site() == site
    assert propose_design(bridge)["request_identity"] == result["request_identity"]


@pytest.mark.parametrize("kind", ["soluble", "membrane", "unknown"])
def test_non_gpcr_default_stays_official(kind):
    evidence = {"constraints": design_constraints(kind), "approved_exclusions": []}
    resolved = resolve_design_intent(binder_intent(), evidence)
    assert resolved.arms[0].scaffold_template == "official-vhh7-v1"
    assert set(evidence["constraints"]["scaffold_templates"]) == {"official-vhh7-v1"}
    for scaffold in evidence["constraints"]["scaffolds"]:
        spec = yaml.safe_load(
            resources.files(ASSET_PACKAGE).joinpath(f"{scaffold['name']}.yaml").read_text()
        )
        assert scaffold["designed_residue_ranges"] == spec["design"][0]["chain"]["res_index"]


def test_non_gpcr_compilation_keeps_original_assets(design_bridge):
    propose_design(design_bridge)
    for path in compiled_designs(design_bridge):
        name = path.parent.name.removeprefix("arm-1-scaffold-")
        design = yaml.safe_load(path.read_text())
        assert design["entities"][1]["file"]["path"] == f"../../assets/scaffolds/{name}.yaml"
        assert not (path.parent / "scaffold.yaml").exists()
        assert (path.parent / design["entities"][1]["file"]["path"]).read_bytes() == (
            resources.files(ASSET_PACKAGE).joinpath(f"{name}.yaml").read_bytes()
        )


def test_three_arms_preserve_template_choices_hotspots_and_approved_avoid(
    design_bridge, monkeypatch
):
    bridge = design_bridge
    gpcr_context(bridge, monkeypatch)
    site = deepcopy(bridge.approved_site())
    site["proposal"]["intent"]["avoid_label_seq_ids"] = [5]
    monkeypatch.setattr(bridge, "approved_site", lambda: site)
    approved = list(site["hotspots"]["hotspot_sets"][0]["label_seq_ids"])
    intent = binder_intent()
    intent = intent.model_copy(
        update={
            "arms": [
                intent.arms[0],
                binder_intent(
                    name="shorter",
                    role="diagnostic",
                    binding_label_seq_ids=approved[:1],
                    cdr_overrides=[{"cdr": 3, "insertion_num_residues": "3..20"}],
                    changed_factors=["CDR3 insertion range", "conditioning subset"],
                ).arms[0],
                binder_intent(
                    name="official",
                    role="integrated-alternative",
                    scaffold_template="official-vhh7-v1",
                    rationale="Compare the original loop settings as an alternative.",
                    changed_factors=["scaffold template configuration"],
                ).arms[0],
            ]
        }
    )
    result = propose_design(bridge, intent)
    assert result["evaluation"]["hard_constraints"] == "passed", result["evaluation"]
    assert result["evaluation"]["planned_candidates"] == 840
    assert [a["scaffold_template"] for a in result["proposal"]["arms"]] == [
        GPCR_TEMPLATE,
        GPCR_TEMPLATE,
        "official-vhh7-v1",
    ]
    designs = compiled_designs(bridge)
    assert len(designs) == 21
    for path in designs:
        design = yaml.safe_load(path.read_text())
        chain = design["entities"][0]["file"]["binding_types"][0]["chain"]
        assert chain["not_binding"] == "5"
        expected_binding = approved[:1] if path.parent.name.startswith("arm-2-") else approved
        assert chain["binding"] == ",".join(map(str, expected_binding))
        if path.parent.name.startswith("arm-2-"):
            name = path.parent.name.removeprefix("arm-2-scaffold-")
            actual = yaml.safe_load((path.parent / "scaffold.yaml").read_text())
            expected, _ = gpcr_template(name)
            expected["path"] = f"../../assets/scaffolds/{name}.cif"
            expected["design_insertions"][2]["insertion"]["num_residues"] = "3..20"
            assert actual == expected
        elif path.parent.name.startswith("arm-3-"):
            assert not (path.parent / "scaffold.yaml").exists()
    assert bridge.approved_site() == site


@pytest.mark.parametrize(
    "changes",
    [
        {"binding_label_seq_ids": [999]},
        {"avoid_label_seq_ids": [999]},
        {"avoid_label_seq_ids": [1, 2, 3, 4]},
    ],
)
def test_gpcr_template_cannot_bypass_binding_constraints(design_bridge, monkeypatch, changes):
    gpcr_context(design_bridge, monkeypatch)
    result = propose_design(design_bridge, binder_intent(**changes))
    assert result["evaluation"]["status"] == "BLOCKED"
    assert "compiled_ref" not in design_bridge.current_design()


def test_gpcr_manifest_integrity_is_checked(monkeypatch):
    from easydesign.stages.s03_boltzgen_configuration import scaffold_templates

    monkeypatch.setattr(scaffold_templates, "GPCR_MANIFEST_SHA256", "0" * 64)
    with pytest.raises(ManifestStateError, match="manifest checksum"):
        gpcr_template("7eow")


def test_template_and_avoid_survive_strategy_matrix_export(tmp_path):
    import csv
    import json

    from easydesign.stages.s03_boltzgen_configuration import (
        ExplicitStrategyVariant,
        compile_vhh_strategy_plan,
    )
    from easydesign.stages.s03_boltzgen_configuration.compiler import write_design_matrix
    from tests.unit.stages.test_s03_strategy_compiler import _hotspots, _write_target

    target = tmp_path / "target.cif"
    _write_target(target)
    _, records = compile_vhh_strategy_plan(
        target_cif=target,
        hotspots=_hotspots(target, ("approved",)),
        artifacts_root=tmp_path / "compiled",
        variants=(
            ExplicitStrategyVariant(
                variant_id="gpcr-arm",
                hotspot_set_id="approved",
                scaffold_ids=SCAFFOLD_IDS,
                scaffold_template=GPCR_TEMPLATE,
                avoid_label_seq_ids=(5,),
            ),
        ),
    )
    write_design_matrix(
        records, json_path=tmp_path / "matrix.json", tsv_path=tmp_path / "matrix.tsv"
    )
    rows = json.loads((tmp_path / "matrix.json").read_text())["strategies"]
    assert len(rows) == 7 and all(r["scaffold_template"] == GPCR_TEMPLATE for r in rows)
    with (tmp_path / "matrix.tsv").open() as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(rows) == 7
    assert all(r["avoid_label_seq_ids"] == "5" for r in rows)
    assert all(r["scaffold_template"] == GPCR_TEMPLATE for r in rows)


def test_old_frozen_design_without_template_field_still_renders(design_bridge, monkeypatch):
    bridge = design_bridge
    propose_design(bridge)
    card = design_card(bridge)
    bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-scientist")
    bridge.apply_decision(card)
    old = deepcopy(bridge.approved_design())
    for arm in old["proposal"]["intent"]["arms"]:
        arm.pop("scaffold_template")
    monkeypatch.setattr(bridge, "approved_design", lambda: old)
    result = bridge.scientific_state()
    assert result["frozen_design"]["arms"][0]["scaffold_template"] == "official-vhh7-v1"
