from __future__ import annotations

import json
from pathlib import Path

import pytest

from easydesign.core import ConfigurationError, sha256_file
from easydesign.orchestration.runtime_components import (
    install_openfold3_component,
    load_openfold3_bundle,
)

REQUIRED_ROLES = (
    "alphafold-wheel",
    "environment-requirements",
    "converted-weight",
    "runner-script",
    "license",
    "notice",
    "model-card",
    "conversion-manifest",
    "checksums",
    "smoke-input",
    "validation-receipt",
)


def _bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    records: list[dict[str, object]] = []
    for index, role in enumerate(REQUIRED_ROLES):
        if role == "runner-script":
            relative = Path("runner/run_alphafold.py")
        elif role == "alphafold-wheel":
            relative = Path("wheelhouse/alphafold3_open-3.1.3.whl")
        elif role == "environment-requirements":
            relative = Path("environment/requirements.txt")
        elif role == "converted-weight":
            relative = Path("model/of3_ported_weights.bin.zst")
        else:
            relative = Path("metadata") / f"{index:02d}-{role}.txt"
        path = bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{role}\n", encoding="utf-8")
        records.append(
            {
                "relative_path": relative.as_posix(),
                "role": role,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    by_role = {str(item["role"]): item for item in records}
    manifest = {
        "schema_version": "0.1",
        "component_id": "openfold3-p2-af3-jax",
        "backend_id": "openfold3-af3-jax",
        "backend_version": "3.1.3",
        "model_id": "of3-p2-155k",
        "python_version": "3.12",
        "code_license": "Apache-2.0",
        "template_mode": "disabled",
        "raw_checkpoint_sha256": "a" * 64,
        "converted_weight_sha256": by_role["converted-weight"]["sha256"],
        "wheel_sha256": by_role["alphafold-wheel"]["sha256"],
        "runner_commit": "b811498",
        "environment_lock_sha256": by_role["environment-requirements"]["sha256"],
        "files": records,
    }
    (bundle / "release-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return bundle


def test_load_bundle_verifies_complete_inventory(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)

    selected, manifest = load_openfold3_bundle(bundle)

    assert selected == bundle
    assert manifest.runner_commit == "b811498"
    assert len(manifest.files) == len(REQUIRED_ROLES)


def test_load_bundle_fails_closed_after_file_corruption(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    (bundle / "model/of3_ported_weights.bin.zst").write_text(
        "corrupted\n", encoding="utf-8"
    )

    with pytest.raises(ConfigurationError, match="大小不一致|SHA-256"):
        load_openfold3_bundle(bundle)


def test_load_bundle_rejects_missing_required_role(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    manifest_path = bundle / "release-manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["files"] = [
        item for item in payload["files"] if item["role"] != "license"
    ]
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="无法校验"):
        load_openfold3_bundle(bundle)


def test_install_preflight_failure_records_quarantine_without_profile_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        "\n".join(
            (
                'schema_version: "0.1"',
                "workspace_id: runtime-component-test",
                "runtime_root: runtime",
                "projects_root: workspace/projects",
                "runs_root: workspace/runs",
                "archives_root: workspace/archives",
                "",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))
    bundle = _bundle(tmp_path)
    (bundle / "model/of3_ported_weights.bin.zst").write_text(
        "corrupted\n", encoding="utf-8"
    )

    with pytest.raises(ConfigurationError, match="大小不一致|SHA-256"):
        install_openfold3_component(bundle)

    receipts = tuple((tmp_path / "runtime/quarantine").glob("*.json"))
    assert len(receipts) == 1
    assert not (tmp_path / "runtime/profile.yaml").exists()
