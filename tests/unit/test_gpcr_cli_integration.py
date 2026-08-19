from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from easydesign import cli
from easydesign.core import sha256_file
from easydesign.orchestration.gpcr_site import (
    AnalysisWorkflowError,
    GpcrSiteRequest,
    gpcr_selection_to_stage02_config,
    publish_gpcr_analysis,
    validate_gpcr_analysis_bundle,
)

PDB = """\
ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00 20.00           N
ATOM      2  CA  ALA A   1       1.450   0.000   0.000  1.00 20.00           C
ATOM      3  C   ALA A   1       2.050   1.400   0.000  1.00 20.00           C
ATOM      4  O   ALA A   1       1.400   2.400   0.000  1.00 20.00           O
TER
END
"""


def test_gpcr_cli_parser_exposes_provider_and_batch_contract() -> None:
    parsed = cli._parser().parse_args(
        [
            "site",
            "scan",
            "project",
            "--method",
            "both",
            "--provider",
            "auto",
            "--context",
            "context.yaml",
            "--offline",
        ]
    )
    assert parsed.provider == "auto"
    assert parsed.context == Path("context.yaml")
    assert parsed.offline is True
    batch = cli._parser().parse_args(
        ["gpcr", "batch-review", "--input", "batch.yaml", "--output-dir", "review"]
    )
    assert batch.gpcr_command == "batch-review"


def test_standalone_gpcr_bundle_is_immutable_and_validated(tmp_path: Path) -> None:
    structure = tmp_path / "target.pdb"
    structure.write_text(PDB, encoding="ascii")
    output = tmp_path / "bundle"
    published = publish_gpcr_analysis(
        GpcrSiteRequest(
            evidence_dir=tmp_path / "unused",
            structure=structure,
            gpcr_entry="adrb2_human",
            receptor_chain="A",
            cache_mode="offline",
            cache_root=tmp_path / "empty-cache",
        ),
        output,
    )
    manifest = validate_gpcr_analysis_bundle(published.analysis_root)
    assert manifest["approval_status"] == "awaiting_human_review"
    analysis = json.loads(published.analysis_path.read_text(encoding="utf-8"))
    assert analysis["analysis_notes"]["no_fused_score"] is True
    assert analysis["candidates"]["inhibit"]
    assert not (output / "analysis-r000001" / "analysis-manifest.json").is_symlink()


def _project_bundle_with_selectable_candidate(tmp_path: Path) -> tuple[Path, Path, str]:
    project = tmp_path / "project"
    project.mkdir()
    structure = tmp_path / "target.pdb"
    structure.write_text(PDB, encoding="ascii")
    published = publish_gpcr_analysis(
        GpcrSiteRequest(
            evidence_dir=tmp_path / "unused",
            structure=structure,
            gpcr_entry="adrb2_human",
            receptor_chain="A",
            cache_mode="offline",
            cache_root=tmp_path / "empty-cache",
        ),
        project / "gpcr-site",
        project_root=project,
    )
    analysis = json.loads(published.analysis_path.read_text(encoding="utf-8"))
    candidate = analysis["candidates"]["inhibit"][0]
    candidate["classification"] = "backup"
    candidate["residues"] = [
        {
            "key": "1|A|ATOM|1|A:1",
            "model_id": "1",
            "chain_id": "A",
            "auth_asym_id": "A",
            "auth_seq_id": 1,
            "insertion_code": "",
            "hetero_flag": "ATOM",
            "label_chain_id": "A",
            "label_asym_id": "A",
            "label_seq_id": 1,
            "sequence_index": 1,
            "amino_acid": "A",
        }
    ]
    published.analysis_path.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = json.loads(published.manifest_path.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        if item["path"] == "gpcr-hotspot-analysis.json":
            item["sha256"] = sha256_file(published.analysis_path)
            item["size_bytes"] = published.analysis_path.stat().st_size
    published.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    selection = yaml.safe_load(published.selection_path.read_text(encoding="utf-8"))
    selection["analysis_manifest_sha256"] = sha256_file(published.manifest_path)
    selection["candidate_ids"] = [candidate["id"]]
    published.selection_path.write_text(
        yaml.safe_dump(selection, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return project, published.selection_path, candidate["id"]


def test_gpcr_selection_projects_only_verified_candidate_to_label_region(
    tmp_path: Path,
) -> None:
    project, selection_path, _ = _project_bundle_with_selectable_candidate(tmp_path)

    config = gpcr_selection_to_stage02_config(project, selection_path)

    assert config.mode.value == "user-provided"
    assert config.user_regions is not None
    source = config.user_regions.source
    assert source.type == "residue-list"
    assert source.regions[0].id == "A"
    assert source.regions[0].residues == ("1",)


def test_gpcr_selection_rejects_avoid_or_unresolved_candidate(tmp_path: Path) -> None:
    project, selection_path, candidate_id = _project_bundle_with_selectable_candidate(tmp_path)
    manifest_path = next((project / "gpcr-site").glob("analysis-r*/analysis-manifest.json"))
    analysis_path = manifest_path.parent / "gpcr-hotspot-analysis.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    analysis["candidates"]["inhibit"][0]["classification"] = "unresolved"
    analysis_path.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        if item["path"] == "gpcr-hotspot-analysis.json":
            item["sha256"] = sha256_file(analysis_path)
            item["size_bytes"] = analysis_path.stat().st_size
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    selection = yaml.safe_load(selection_path.read_text(encoding="utf-8"))
    selection["analysis_manifest_sha256"] = sha256_file(manifest_path)
    selection["candidate_ids"] = [candidate_id]
    selection_path.write_text(
        yaml.safe_dump(selection, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(AnalysisWorkflowError, match="only primary/backup"):
        gpcr_selection_to_stage02_config(project, selection_path)
