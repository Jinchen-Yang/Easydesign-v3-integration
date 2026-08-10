from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import easydesign.orchestration.research as research_module
from easydesign.core import ConfigurationError
from easydesign.orchestration.application import RunSummary
from easydesign.orchestration.local_project import (
    STAGE_FILENAMES,
)
from easydesign.orchestration.project import initialize_project
from easydesign.orchestration.research import (
    ResearchStrategy,
    _site_fragment_from_file,
    initialize_research_project,
    pilot_review,
    project_status,
)


def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        'schema_version: "0.1"\nworkspace_id: local-research-test\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))
    return tmp_path


def test_agent_native_project_is_compact_and_status_is_the_resume_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workspace(tmp_path, monkeypatch)
    target = root / "target.fasta"
    target.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    project = root / "workspace/projects/agent-native"

    initialized = initialize_research_project(project_root=project, target=target)
    status = project_status(project)

    assert initialized.status == "initialized"
    assert initialized.phase == "prepare"
    assert status.status == "target-not-started"
    assert status.phase == "prepare"
    assert {item.name for item in project.iterdir()} >= {
        "PROJECT.yaml",
        "DECISIONS.md",
        "strategy-draft.yaml",
        "inputs",
        "strategies",
        "config-revisions",
        "CONFIG_CURRENT",
    }
    assert all(not (project / name).exists() for name in STAGE_FILENAMES.values())
    assert status.next_actions[0].command.startswith("easydesign target prepare")
    assert "step" not in status.model_dump_json()


def test_legacy_seven_yaml_project_is_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workspace(tmp_path, monkeypatch)
    target = root / "target.fasta"
    target.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    project = root / "workspace/projects/legacy"
    initialize_project(project_root=project, target=target)
    (project / "CONFIG_CURRENT").write_text("easydesign.yaml\n", encoding="utf-8")
    for filename in STAGE_FILENAMES.values():
        (project / filename).write_text("legacy: true\n", encoding="utf-8")

    status = project_status(project)

    assert status.status == "legacy-stage-project"
    assert "只读" in status.warnings[0]
    assert all((project / name).is_file() for name in STAGE_FILENAMES.values())


def test_strategy_schema_supports_explicit_variants_and_native_identity() -> None:
    native = "entities: []\n"
    strategy = ResearchStrategy.model_validate(
        {
            "schema_version": "1.0",
            "foundation": "current",
            "variants": [
                {
                    "id": "cropped-cdr3",
                    "hotspot_set_id": "A",
                    "binding_label_seq_ids": [10, 11],
                    "scaffold_ids": ["7eow", "7xl0"],
                    "target_crop": {"start": 5, "end": 80},
                    "cdr_overrides": [
                        {
                            "cdr": 3,
                            "design_res_index": "98..116",
                            "insertion_num_residues": "3..12",
                        }
                    ],
                    "candidates": 40,
                    "rationale": "test explicit experiment",
                    "expected_result": "compare two scaffolds",
                },
                {
                    "id": "expert-native",
                    "scaffold_ids": ["7eow"],
                    "native_boltzgen_yaml": "inputs/native.yaml",
                    "native_boltzgen_sha256": hashlib.sha256(native.encode("utf-8")).hexdigest(),
                    "candidates": 40,
                    "rationale": "expert controlled design",
                    "expected_result": "backend validation",
                },
            ],
        }
    )

    assert strategy.variants[0].target_crop is not None
    assert strategy.variants[0].cdr_overrides[0].cdr == 3
    assert strategy.variants[1].native_boltzgen_sha256 is not None


def test_strategy_schema_rejects_unknown_scaffold_and_ambiguous_native() -> None:
    with pytest.raises(ValueError, match="未知 scaffold"):
        ResearchStrategy.model_validate(
            {
                "variants": [
                    {
                        "id": "bad",
                        "hotspot_set_id": "A",
                        "scaffold_ids": ["unknown"],
                        "rationale": "invalid",
                        "expected_result": "reject",
                    }
                ]
            }
        )
    with pytest.raises(ValueError, match="provenance scaffold"):
        ResearchStrategy.model_validate(
            {
                "variants": [
                    {
                        "id": "bad-native",
                        "scaffold_ids": ["7eow", "7xl0"],
                        "native_boltzgen_yaml": "inputs/native.yaml",
                        "native_boltzgen_sha256": "a" * 64,
                        "rationale": "invalid",
                        "expected_result": "reject",
                    }
                ]
            }
        )


def test_site_proposal_cannot_embed_or_bypass_human_approval(tmp_path: Path) -> None:
    config = tmp_path / "site.yaml"
    config.write_text(
        """mode: user-provided
methods: []
automatic: null
annotations:
  uniprot: if_available
user_regions:
  source:
    type: residue-list
    numbering: label
    regions:
      - id: A
        residues: ['10']
  approval:
    approved_by: researcher
    acknowledge_user_provided_regions: true
    acknowledge_evidence_limitations: true
    selections:
      - id: A
        design_goal: exploratory
        biological_rationale: known test rationale
        structural_rationale: known test structure
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="site approve --confirm"):
        _site_fragment_from_file(config)


def test_project_status_recovers_an_incomplete_pilot_without_stage_language(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workspace(tmp_path, monkeypatch)
    target = root / "target.fasta"
    target.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    project = root / "workspace/projects/agent-native"
    initialize_research_project(project_root=project, target=target)
    summary = RunSummary(
        project_id="agent-native",
        run_id="pilot-20260808-000000-example",
        path=root / "workspace/runs/agent-native/pilot-20260808-000000-example",
        status="running",
        latest_manifest=root / "manifest.json",
        manifest_revision=4,
        completed_stages=("01-target-preparation", "02-hotspot-discovery", "03-config"),
    )
    monkeypatch.setattr(research_module, "_runs", lambda _project: (summary,))
    monkeypatch.setattr(research_module, "_semantic_evidence", lambda _project: ())
    monkeypatch.setattr(research_module, "_latest_foundation", lambda _project: None)
    monkeypatch.setattr(
        research_module,
        "_has_internal_stage",
        lambda _summary, number: number in {1, 2, 3, 4},
    )

    status = project_status(project)

    assert status.status == "pilot-resume-ready"
    assert status.phase == "pilot"
    assert status.next_actions[0].command.startswith("easydesign job resume")
    assert "Stage" not in status.model_dump_json()


def test_negative_pilot_review_does_not_offer_illegal_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = tmp_path / "pilot-filter-report.json"
    report.write_text(
        json.dumps(
            {
                "status": "stopped-no-tier-a",
                "candidate_records": [],
                "strategy_summaries": [],
                "promoted_strategy_ids": [],
            }
        ),
        encoding="utf-8",
    )
    run = RunSummary(
        project_id="example",
        run_id="pilot-negative",
        path=tmp_path / "run",
        status="succeeded",
        latest_manifest=tmp_path / "manifest.json",
        manifest_revision=5,
        completed_stages=("05-pilot-filtering",),
    )
    monkeypatch.setattr(
        research_module,
        "resolve_project_path",
        lambda path, *, must_exist: path.resolve(),
    )
    monkeypatch.setattr(research_module, "_run_by_id", lambda _root, _run_id: run)
    monkeypatch.setattr(research_module, "_has_internal_stage", lambda _run, number: number == 5)

    def artifact(_root: Path, artifact_id: str) -> tuple[object, Path]:
        if artifact_id == "pilot-filter-report":
            return SimpleNamespace(sha256="a" * 64), report
        raise ConfigurationError("missing fixture artifact")

    monkeypatch.setattr(research_module, "_artifact", artifact)

    result = pilot_review(tmp_path, run_id=run.run_id)

    assert [action.command for action in result.next_actions] == [
        f"easydesign strategy draft {tmp_path.resolve()} --from-pilot {run.run_id}"
    ]
