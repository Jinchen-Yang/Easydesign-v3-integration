from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from easydesign.backends.executors import (
    ManagedWorkerLayout,
    RemoteJobBundle,
    RemoteJobInput,
)
from easydesign.core import BackendContractError
from easydesign.orchestration.managed_worker_service import (
    resolve_managed_source_run,
)


def _managed_bundle(manifest_sha256: str) -> RemoteJobBundle:
    return RemoteJobBundle(
        job_id="job-stage06",
        controller_id="controller-a",
        controller_key_fingerprint="SHA256:controller-a",
        project_id="project-a",
        run_id="stage05-run",
        submitted_at=datetime(2026, 8, 1, tzinfo=UTC),
        stage_range=(6, 7),
        candidate_budget=50_000,
        easydesign_version="0.1.0.dev31",
        config_sha256="1" * 64,
        upstream_manifest_sha256=manifest_sha256,
        inputs=(
            RemoteJobInput(
                relative_path="easydesign.yaml",
                size_bytes=10,
                sha256="2" * 64,
                role="resolved-run-config",
            ),
        ),
        source_run_mode="managed-run",
        managed_source_run="runs/project-a/stage05-run",
    )


def test_managed_source_run_is_reused_in_place_by_manifest_identity(
    tmp_path: Path,
) -> None:
    layout = ManagedWorkerLayout(tmp_path / "managed-worker")
    source = layout.runs / "project-a" / "stage05-run"
    manifests = source / "manifests"
    manifests.mkdir(parents=True)
    manifest = manifests / "run-manifest-0002.json"
    manifest.write_text('{"status":"succeeded"}\n', encoding="utf-8")
    (manifests / "LATEST").write_text(manifest.name + "\n", encoding="utf-8")
    input_root = layout.jobs / "job-stage06" / "input"
    input_root.mkdir(parents=True)

    resolved = resolve_managed_source_run(
        layout=layout,
        bundle=_managed_bundle(hashlib.sha256(manifest.read_bytes()).hexdigest()),
        input_root=input_root,
    )

    assert resolved == source.resolve()


def test_managed_source_run_rejects_manifest_drift(tmp_path: Path) -> None:
    layout = ManagedWorkerLayout(tmp_path / "managed-worker")
    source = layout.runs / "project-a" / "stage05-run"
    manifests = source / "manifests"
    manifests.mkdir(parents=True)
    manifest = manifests / "run-manifest-0002.json"
    manifest.write_text('{"status":"succeeded"}\n', encoding="utf-8")
    (manifests / "LATEST").write_text(manifest.name + "\n", encoding="utf-8")
    input_root = layout.jobs / "job-stage06" / "input"
    input_root.mkdir(parents=True)

    with pytest.raises(BackendContractError, match="SHA-256"):
        resolve_managed_source_run(
            layout=layout,
            bundle=_managed_bundle("f" * 64),
            input_root=input_root,
        )
