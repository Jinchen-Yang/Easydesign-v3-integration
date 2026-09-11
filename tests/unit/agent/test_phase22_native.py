"""Expert YAML uses the same trusted compiler/Judge/Gate 3, without rewriting source."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.design import DesignBridge
from easydesign.agent.native_strategy import import_native
from easydesign.core import sha256_file
from easydesign.orchestration.research import ResearchStrategy, StrategyVariant
from easydesign.stages.s03_boltzgen_configuration.compiler import (
    SCAFFOLD_IDS,
    _design_specification,
)
from tests.unit.agent.test_design_runtime import binder_intent, design_card, propose_design


def expert_input(bridge: Any, *, binding: tuple[int, ...] = (1, 2, 3)) -> Path:
    root = bridge.project / "inputs/expert"
    root.mkdir(parents=True)
    variants = []
    for scaffold in SCAFFOLD_IDS:
        path = root / f"{scaffold}.yaml"
        # This is a scientist fixture prepared before Agent invocation, not model-written YAML.
        path.write_text(
            "# Preserve expert annotation\n"
            + yaml.safe_dump(
                _design_specification(binding_label_seq_ids=binding, scaffold_id=scaffold),
                sort_keys=False,
            )
        )
        variants.append(
            StrategyVariant(
                id=f"expert-{scaffold}",
                scaffold_ids=(scaffold,),
                native_boltzgen_yaml=path.relative_to(bridge.project),
                native_boltzgen_sha256=sha256_file(path),
                hypothesis_id="expert-condition",
                hypothesis_statement="Explore scaffold tolerance at the approved site",
                role="baseline",
                evidence_refs=("approved:site",),
                changed_factors=("scaffold",),
                held_constant=("target and hotspot",),
                rationale="Use the reviewed expert constraints",
                expected_result="Later pilot evaluates tolerance",
                failure_interpretation="No binding inference from a failed micro smoke",
            )
        )
    strategy = ResearchStrategy(
        protocol_kind="first-pilot",
        foundation=bridge.approved_site()["run_id"],
        variants=tuple(variants),
    )
    path = root / "strategy.yaml"
    path.write_text(yaml.safe_dump(strategy.model_dump(mode="json"), sort_keys=False))
    return path


def test_native_import_judge_gate_and_project_shared_approval(design_bridge: Any) -> None:
    bridge = design_bridge
    path = expert_input(bridge)
    before = {p: p.read_bytes() for p in path.parent.glob("*.yaml")}
    import_native(bridge, path)
    intent = binder_intent().model_copy(update={"strategy_source": "expert-native", "arms": []})
    result = propose_design(bridge, intent)
    assert result["evaluation"]["status"] != "BLOCKED", result["evaluation"]
    assert result["evaluation"]["planned_candidates"] == 280
    assert result["native_specification"]["source_bytes"] == "preserved unchanged"
    assert not result["evaluation"]["generation_started"]
    card = design_card(bridge)
    bridge.store.respond(bridge.thread, card.card_id, "approve", "fixture-scientist")
    bridge.apply_decision(card)
    assert bridge.approved_design()
    for p, raw in before.items():
        assert p.read_bytes() == raw
    compiled = bridge.document(bridge.current_design()["compiled_ref"])
    native_yamls = [
        bridge.project / r["relative_path"]
        for r in compiled
        if r["relative_path"].endswith("/design.yaml")
    ]
    assert len(native_yamls) == 7
    assert {p.read_bytes() for p in native_yamls} == {
        raw for p, raw in before.items() if p.name != "strategy.yaml"
    }
    inherited = DesignBridge(bridge.project, "fresh-consumer", bridge.store)
    assert inherited.approved_design()


def test_native_wrong_hotspot_and_source_tamper_cannot_reach_gate(design_bridge: Any) -> None:
    bridge = design_bridge
    path = expert_input(bridge, binding=(4, 5, 6))
    with pytest.raises(AgentBoundaryError, match="approved hotspots"):
        import_native(bridge, path)
    assert bridge.current_design() is None


def test_native_preserves_input_and_blocks_unauthorized_rewrite(design_bridge: Any) -> None:
    bridge = design_bridge
    path = expert_input(bridge)
    import_native(bridge, path)
    with pytest.raises(AgentBoundaryError, match="Preserve scientist"):
        propose_design(bridge, binder_intent())
    yaml_path = path.parent / "7eow.yaml"
    yaml_path.write_text("entities: []\n")
    with pytest.raises(Exception, match="SHA|sha|checksum"):
        bridge.read_design_evidence()


def test_native_custom_scaffold_cannot_exclude_framework(design_bridge: Any) -> None:
    from importlib import resources

    from easydesign.stages.s03_boltzgen_configuration.compiler import ASSET_PACKAGE

    bridge = design_bridge
    strategy_path = expert_input(bridge)
    assets = resources.files(ASSET_PACKAGE)
    scaffold = strategy_path.parent / "custom-7eow.yaml"
    structure = scaffold.with_suffix(".cif")
    structure.write_bytes(assets.joinpath("7eow.cif").read_bytes())
    spec = yaml.safe_load(assets.joinpath("7eow.yaml").read_text())
    spec["path"] = str(structure)
    spec["exclude"].append({"chain": {"id": "B", "res_index": "1"}})
    scaffold.write_text(yaml.safe_dump(spec))
    native_path = strategy_path.parent / "7eow.yaml"
    native = yaml.safe_load(native_path.read_text())
    native["entities"][1]["file"]["path"] = str(scaffold)
    native_path.write_text(yaml.safe_dump(native))
    strategy = yaml.safe_load(strategy_path.read_text())
    for variant in strategy["variants"]:
        if variant["scaffold_ids"] == ["7eow"]:
            variant["native_boltzgen_sha256"] = sha256_file(native_path)
    strategy_path.write_text(yaml.safe_dump(strategy))
    with pytest.raises(AgentBoundaryError, match="cannot remove the VHH framework"):
        import_native(bridge, strategy_path)
    assert bridge.current_design() is None
