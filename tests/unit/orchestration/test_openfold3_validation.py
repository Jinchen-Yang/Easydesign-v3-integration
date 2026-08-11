from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from easydesign.core import ConfigurationError, sha256_file
from easydesign.orchestration.openfold3_validation import (
    OpenFold3ApprovalReceipt,
    OpenFold3ValidationReport,
    approve_openfold3_validation_report,
    generate_openfold3_validation_report,
)


def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "0.1",
                "workspace_id": "validation-test",
                "runtime_root": "runtime",
                "projects_root": "workspace/projects",
                "runs_root": "workspace/runs",
                "archives_root": "workspace/archives",
                "upload_warning_bytes": 1024,
                "upload_blocking_bytes": 2048,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))


def _files(tmp_path: Path) -> tuple[Path, Path, Path]:
    structure = tmp_path / "prediction.cif"
    structure.write_text("data_prediction\n", encoding="utf-8")
    panel = tmp_path / "panel.yaml"
    panel.write_text(
        yaml.safe_dump(
            {
                "schema_version": "0.2",
                "panel_id": "afo-release-comparison-v2",
                "cases": [
                    {
                        "case_id": "case-one",
                        "case_class": "boundary-negative",
                        "source_uri": "fixture://case-one",
                        "chain_annotations": {"A": "target", "B": "binder"},
                        "required_backends": [
                            "openfold3-af3-jax",
                            "protenix-v2",
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    file_ref = {
        "path": str(structure),
        "size_bytes": structure.stat().st_size,
        "sha256": sha256_file(structure),
    }
    evidence = tmp_path / "evidence.json"
    release_identity = {
        "release_id": "afo-3-1-4-of3-p2-155k",
        "backend_id": "openfold3-af3-jax",
        "backend_version": "3.1.4",
        "model_id": "of3-p2-155k",
        "adapter_contract_version": "openfold3-af3-jax-cli-v1",
        "release_manifest_sha256": "a" * 64,
        "conversion_receipt_sha256": "b" * 64,
        "raw_checkpoint_sha256": "c" * 64,
        "converted_weight_sha256": "d" * 64,
        "wheel_sha256": "e" * 64,
        "environment_lock_sha256": "f" * 64,
        "runner_commit": "bc32b22ff5902e3daffd5d1f7203d7f2ab6cb997",
        "runner_tree_sha256": "1" * 64,
    }
    observations = []
    for backend, iptm in (
        ("openfold3-af3-jax", 0.65),
        ("protenix-v2", 0.55),
    ):
        observations.append(
            {
                "case_id": "case-one",
                "backend": backend,
                "backend_identity": f"{backend}@fixture",
                "model_identity": (
                    "of3-p2-155k" if backend == "openfold3-af3-jax" else backend
                ),
                "structure": file_ref,
                "chain_ids": ["A", "B"],
                "chain_complete": True,
                "pairwise_iptm": iptm,
                "ptm": 0.7,
                "binder_ptm": 0.7,
                "minimum_interface_pae_angstrom": 8.0,
                "target_ca_rmsd_angstrom": 2.0,
                "has_clash": False,
                "gpde": None if backend == "openfold3-af3-jax" else 0.2,
                "native_metrics": (
                    release_identity if backend == "openfold3-af3-jax" else {}
                ),
            }
        )
    evidence.write_text(
        json.dumps(
            {
                "schema_version": "0.2",
                "afo_release": release_identity,
                "observations": observations,
            }
        ),
        encoding="utf-8",
    )
    return panel, evidence, structure


def test_report_has_no_automatic_gate_and_approval_does_not_switch_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path, monkeypatch)
    panel, evidence, _ = _files(tmp_path)

    report_path = generate_openfold3_validation_report(
        panel_path=panel,
        evidence_path=evidence,
    )
    report = OpenFold3ValidationReport.model_validate_json(report_path.read_text())
    approval_path = approve_openfold3_validation_report(
        report_path=report_path,
        reviewer="researcher-one",
        decision="approve-stable-promotion",
        confirm=True,
    )
    approval = OpenFold3ApprovalReceipt.model_validate_json(
        approval_path.read_text()
    )

    assert report.automatic_acceptance_threshold is None
    assert not report.default_backend_changed
    assert report.metric_drift[0].threshold_decision_changed
    assert not approval.default_backend_changed
    assert approval.afo_release.release_id == "afo-3-1-4-of3-p2-155k"
    assert not (tmp_path / "runtime/profile.yaml").exists()


def test_report_fails_closed_for_missing_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path, monkeypatch)
    panel, evidence, _ = _files(tmp_path)
    payload = json.loads(evidence.read_text())
    payload["observations"] = payload["observations"][:1]
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="不完整"):
        generate_openfold3_validation_report(
            panel_path=panel,
            evidence_path=evidence,
        )


def test_approval_requires_explicit_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path, monkeypatch)
    panel, evidence, _ = _files(tmp_path)
    report = generate_openfold3_validation_report(
        panel_path=panel,
        evidence_path=evidence,
    )

    with pytest.raises(ConfigurationError, match="--confirm"):
        approve_openfold3_validation_report(
            report_path=report,
            reviewer="researcher-one",
            decision="approve-stable-promotion",
            confirm=False,
        )
