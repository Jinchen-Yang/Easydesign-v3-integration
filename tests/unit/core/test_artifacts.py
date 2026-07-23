from __future__ import annotations

import shutil

import pytest
from pydantic import ValidationError

from easydesign.core import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactRef,
    PathPolicyError,
)


def test_artifact_from_file_and_verify(tmp_path) -> None:
    run_root = tmp_path / "run"
    path = run_root / "01-target-preparation" / "target.cif"
    path.parent.mkdir(parents=True)
    path.write_text("data_target\n", encoding="utf-8")

    artifact = ArtifactRef.from_file(
        run_root=run_root,
        relative_path="01-target-preparation/target.cif",
        artifact_id="target-structure",
        role="canonical-target-structure",
        file_format="mmcif",
        producer_stage="01-target-preparation",
        producer_attempt="attempt-0001",
    )

    assert artifact.verify(run_root) == path.resolve()
    assert artifact.size_bytes == path.stat().st_size


@pytest.mark.parametrize(
    "relative_path",
    (
        "/absolute/target.cif",
        "../escape.cif",
        "stage/../escape.cif",
        "stage//target.cif",
        "stage\\target.cif",
        "./target.cif",
    ),
)
def test_artifact_rejects_unsafe_relative_paths(relative_path: str) -> None:
    with pytest.raises(ValidationError):
        ArtifactRef(
            artifact_id="target",
            role="target",
            relative_path=relative_path,
            file_format="mmcif",
            sha256="a" * 64,
            size_bytes=1,
        )


def test_artifact_rejects_symlink_escape(tmp_path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (run_root / "linked").symlink_to(outside, target_is_directory=True)

    artifact = ArtifactRef(
        artifact_id="target",
        role="target",
        relative_path="linked/target.cif",
        file_format="mmcif",
        sha256="a" * 64,
        size_bytes=1,
    )
    with pytest.raises(PathPolicyError):
        artifact.resolve(run_root)


def test_artifact_detects_size_change_before_hash(tmp_path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    path = run_root / "target.cif"
    path.write_text("initial", encoding="utf-8")
    artifact = ArtifactRef.from_file(
        run_root=run_root,
        relative_path="target.cif",
        artifact_id="target",
        role="target",
        file_format="mmcif",
    )
    path.write_text("changed-size", encoding="utf-8")

    with pytest.raises(ArtifactIntegrityError, match="大小"):
        artifact.verify(run_root)


def test_artifact_detects_same_size_content_change(tmp_path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    path = run_root / "target.cif"
    path.write_bytes(b"aaaa")
    artifact = ArtifactRef.from_file(
        run_root=run_root,
        relative_path="target.cif",
        artifact_id="target",
        role="target",
        file_format="mmcif",
    )
    path.write_bytes(b"bbbb")

    with pytest.raises(ArtifactIntegrityError, match="SHA-256"):
        artifact.verify(run_root)


def test_artifact_resolves_after_run_tree_moves(tmp_path) -> None:
    original_root = tmp_path / "original"
    path = original_root / "inputs" / "target.cif"
    path.parent.mkdir(parents=True)
    path.write_text("portable", encoding="utf-8")
    artifact = ArtifactRef.from_file(
        run_root=original_root,
        relative_path="inputs/target.cif",
        artifact_id="target",
        role="target",
        file_format="mmcif",
    )

    moved_root = tmp_path / "moved"
    shutil.copytree(original_root, moved_root)
    assert artifact.verify(moved_root) == (moved_root / "inputs/target.cif").resolve()


def test_artifact_requires_producer_pair() -> None:
    with pytest.raises(ValidationError, match="producer"):
        ArtifactRef(
            artifact_id="target",
            role="target",
            relative_path="target.cif",
            file_format="mmcif",
            sha256="a" * 64,
            size_bytes=1,
            producer_stage="01-target-preparation",
        )


def test_artifact_from_file_rejects_missing_file(tmp_path) -> None:
    with pytest.raises(ArtifactNotFoundError):
        ArtifactRef.from_file(
            run_root=tmp_path,
            relative_path="missing.cif",
            artifact_id="target",
            role="target",
            file_format="mmcif",
        )
