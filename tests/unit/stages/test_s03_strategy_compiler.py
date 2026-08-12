from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from easydesign.core import ManifestStateError, sha256_file
from easydesign.stages.s02_hotspot_discovery import (
    AnnotationStatus,
    ApprovedHotspotSet,
    DesignGoal,
    EvidenceLevel,
    HotspotEvidence,
    HotspotsFile,
    PseColorRegionSource,
)
from easydesign.stages.s03_boltzgen_configuration import (
    BOLTZGEN_COMMIT,
    SCAFFOLD_IDS,
    CdrOverride,
    ExplicitStrategyVariant,
    NativeStrategyVariant,
    StrategyBundle,
    TargetCrop,
    compile_basic_vhh_matrix,
    compile_vhh_strategy_plan,
)

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def _hotspots(
    target: Path,
    region_ids: tuple[str, ...],
) -> HotspotsFile:
    sets = tuple(
        ApprovedHotspotSet(
            id=region_id,
            slug=f"region-{index}",
            source_region_id=f"source-{index}",
            design_goal=DesignGoal.EXPLORATORY,
            biological_rationale="User-approved test region.",
            structural_rationale="Coordinates and numbering were validated.",
            auth_residues=(str(index * 10 + 1), str(index * 10 + 2)),
            label_seq_ids=(index * 10 + 1, index * 10 + 2),
            label_ranges=f"{index * 10 + 1}..{index * 10 + 2}",
            evidence=(
                HotspotEvidence(
                    type="user-annotation",
                    source="test-fixture",
                    description="A deliberately generic approved region.",
                ),
            ),
        )
        for index, region_id in enumerate(region_ids)
    )
    return HotspotsFile(
        project_id="generic-project",
        run_id="generic-run",
        target_id="generic-target",
        target_structure_sha256=sha256_file(target),
        coordinate_model_ids=("1",),
        region_source=PseColorRegionSource(
            source_annotation_sha256="a" * 64,
        ),
        selection_basis=EvidenceLevel.STRUCTURAL_ONLY,
        annotation_status=AnnotationStatus.NOT_REQUESTED,
        approval_request_sha256="b" * 64,
        approved_by="fixture-author",
        hotspot_sets=sets,
    )


@pytest.mark.parametrize(
    "region_ids",
    (
        ("A",),
        ("A", "B"),
        ("north", "equator", "south"),
    ),
)
def test_compiler_builds_complete_region_scaffold_matrix_without_negative_sites(
    tmp_path: Path,
    region_ids: tuple[str, ...],
) -> None:
    target = tmp_path / "target.cif"
    target.write_text("data_target\n#\n", encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    scaffold_assets, strategies = compile_basic_vhh_matrix(
        target_cif=target,
        hotspots=_hotspots(target, region_ids),
        artifacts_root=artifacts,
        candidates_per_strategy=17,
    )

    assert len(scaffold_assets) == len(SCAFFOLD_IDS)
    assert len(strategies) == len(region_ids) * len(SCAFFOLD_IDS)
    assert {(strategy.source_hotspot_set_id, strategy.scaffold_id) for strategy in strategies} == {
        (region_id, scaffold_id) for region_id in region_ids for scaffold_id in SCAFFOLD_IDS
    }
    for strategy in strategies:
        path = artifacts / strategy.design_specification_path
        text = path.read_text(encoding="utf-8")
        document = yaml.safe_load(text)
        target_entity = document["entities"][0]["file"]
        binding = target_entity["binding_types"]
        assert "not_binding" not in text
        assert binding == [
            {
                "chain": {
                    "id": "A",
                    "binding": ",".join(str(value) for value in strategy.binding_label_seq_ids),
                }
            }
        ]
        assert strategy.candidates_per_strategy == 17
        assert strategy.crop_enabled is False
        assert strategy.neutral_residue_policy == "unmarked"


def test_strategy_bundle_records_complete_registry_and_upstream_identity(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.cif"
    target.write_text("data_target\n#\n", encoding="utf-8")
    hotspots = _hotspots(target, ("A", "B", "C"))
    scaffold_assets, strategies = compile_basic_vhh_matrix(
        target_cif=target,
        hotspots=hotspots,
        artifacts_root=tmp_path / "artifacts",
        candidates_per_strategy=40,
    )

    bundle = StrategyBundle(
        generated_at=NOW,
        project_id=hotspots.project_id,
        run_id=hotspots.run_id,
        target_id=hotspots.target_id,
        target_structure_sha256=hotspots.target_structure_sha256,
        target_bundle_sha256="c" * 64,
        hotspots_sha256="d" * 64,
        source_stage02_manifest_sha256="e" * 64,
        validation_report_sha256="f" * 64,
        scaffold_assets=scaffold_assets,
        strategies=strategies,
    )

    assert len(bundle.strategies) == 21
    assert bundle.boltzgen_commit == BOLTZGEN_COMMIT
    assert bundle.random_seed_status == "unsupported-by-boltzgen-0.3.2"


def test_compiler_allows_explicit_official_scaffold_subset_for_backend_probe(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.cif"
    target.write_text("data_target\n#\n", encoding="utf-8")

    scaffold_assets, strategies = compile_basic_vhh_matrix(
        target_cif=target,
        hotspots=_hotspots(target, ("probe-region",)),
        artifacts_root=tmp_path / "artifacts",
        candidates_per_strategy=1,
        scaffold_ids=("7eow",),
    )

    assert [asset.scaffold_id for asset in scaffold_assets] == ["7eow"]
    assert [strategy.scaffold_id for strategy in strategies] == ["7eow"]
    assert strategies[0].candidates_per_strategy == 1


def test_compiler_rejects_target_checksum_mismatch_and_overwrite(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.cif"
    target.write_text("data_target\n#\n", encoding="utf-8")
    hotspots = _hotspots(target, ("A",))
    artifacts = tmp_path / "artifacts"

    with pytest.raises(ManifestStateError, match="SHA|不一致"):
        compile_basic_vhh_matrix(
            target_cif=target,
            hotspots=hotspots.model_copy(update={"target_structure_sha256": "f" * 64}),
            artifacts_root=artifacts,
            candidates_per_strategy=40,
        )

    compile_basic_vhh_matrix(
        target_cif=target,
        hotspots=hotspots,
        artifacts_root=artifacts,
        candidates_per_strategy=40,
    )
    with pytest.raises(ManifestStateError, match="必须为空"):
        compile_basic_vhh_matrix(
            target_cif=target,
            hotspots=hotspots,
            artifacts_root=artifacts,
            candidates_per_strategy=40,
        )


def test_explicit_plan_avoids_global_cartesian_and_compiles_crop_and_cdr(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.cif"
    target.write_text("data_target\n#\n", encoding="utf-8")
    artifacts = tmp_path / "artifacts"

    assets, strategies = compile_vhh_strategy_plan(
        target_cif=target,
        hotspots=_hotspots(target, ("A", "B", "C")),
        artifacts_root=artifacts,
        variants=(
            ExplicitStrategyVariant(
                variant_id="focused-cdr3",
                hotspot_set_id="A",
                binding_label_seq_ids=(1, 2),
                scaffold_ids=("7eow", "7xl0"),
                target_crop=TargetCrop(start=1, end=80),
                cdr_overrides=(
                    CdrOverride(
                        cdr=3,
                        design_res_index="98..116",
                        insertion_num_residues="3..12",
                    ),
                ),
                candidates_per_strategy=17,
                hypothesis_id="h-focused-cdr3",
                role="diagnostic",
                evidence_refs=("site:approved-a",),
                changed_factors=("cdr3-design",),
                held_constant=("target", "site", "crop"),
                rationale="test CDR3 reach while holding the site constant",
                expected_result="more CDR-mediated approved-site contacts",
                failure_interpretation="failure may reflect scaffold-loop incompatibility",
            ),
        ),
    )

    assert [item.scaffold_id for item in assets] == ["7eow", "7xl0"]
    assert len(strategies) == 2
    assert {item.region_id for item in strategies} == {"focused-cdr3"}
    assert all(item.crop_enabled for item in strategies)
    assert all(item.candidates_per_strategy == 17 for item in strategies)
    assert {item.hypothesis_id for item in strategies} == {"h-focused-cdr3"}
    assert {item.role for item in strategies} == {"diagnostic"}
    assert all(item.changed_factors == ("cdr3-design",) for item in strategies)
    for item in strategies:
        design = yaml.safe_load(
            (artifacts / item.design_specification_path).read_text(encoding="utf-8")
        )
        assert design["entities"][0]["file"]["include"] == [
            {"chain": {"id": "A", "res_index": "1..80"}}
        ]
        assert design["entities"][1]["file"]["path"] == "scaffold.yaml"
        assert item.variant_scaffold_path is not None
        scaffold = yaml.safe_load(
            (artifacts / item.variant_scaffold_path).read_text(encoding="utf-8")
        )
        assert scaffold["design"][0]["chain"]["res_index"].endswith("98..116")
        assert scaffold["design_insertions"][2]["insertion"]["num_residues"] == "3..12"

    bundle = StrategyBundle(
        schema_version="0.3",
        generated_at=NOW,
        project_id="generic-project",
        run_id="generic-run",
        target_id="generic-target",
        target_structure_sha256="a" * 64,
        target_bundle_sha256="b" * 64,
        hotspots_sha256="c" * 64,
        source_stage02_manifest_sha256="d" * 64,
        validation_report_sha256="e" * 64,
        scaffold_assets=assets,
        strategies=strategies,
    )
    assert bundle.schema_version == "0.3"


def test_explicit_plan_rejects_unapproved_binding_and_preserves_native_bytes(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.cif"
    target.write_text("data_target\n#\n", encoding="utf-8")
    hotspots = _hotspots(target, ("A",))
    with pytest.raises(ManifestStateError, match="approved hotspots"):
        compile_vhh_strategy_plan(
            target_cif=target,
            hotspots=hotspots,
            artifacts_root=tmp_path / "bad-artifacts",
            variants=(
                ExplicitStrategyVariant(
                    variant_id="bad-binding",
                    binding_label_seq_ids=(999,),
                    scaffold_ids=("7eow",),
                ),
            ),
        )

    native_text = "entities: []\n"
    _, records = compile_vhh_strategy_plan(
        target_cif=target,
        hotspots=hotspots,
        artifacts_root=tmp_path / "native-artifacts",
        variants=(),
        native_variants=(
            NativeStrategyVariant(
                variant_id="expert-native",
                scaffold_id="7eow",
                yaml_text=native_text,
                source_sha256=__import__("hashlib").sha256(native_text.encode("utf-8")).hexdigest(),
            ),
        ),
    )
    path = tmp_path / "native-artifacts" / records[0].design_specification_path
    assert path.read_bytes() == native_text.encode("utf-8")
    assert records[0].native_source_sha256 is not None
