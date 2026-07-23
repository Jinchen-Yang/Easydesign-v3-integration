from __future__ import annotations

import json

import pytest

from easydesign.core import (
    ArtifactRef,
    ManifestStateError,
    SerializationError,
    canonical_json_bytes,
    canonical_model_sha256,
    dump_model,
    load_model,
)


def example_artifact() -> ArtifactRef:
    return ArtifactRef(
        artifact_id="target",
        role="canonical-target",
        relative_path="01-target-preparation/target.cif",
        file_format="mmcif",
        sha256="a" * 64,
        size_bytes=42,
        producer_stage="01-target-preparation",
        producer_attempt="attempt-0001",
    )


def test_json_round_trip(tmp_path) -> None:
    artifact = example_artifact()
    path = tmp_path / "artifact.json"

    dump_model(artifact, path)
    restored = load_model(path, ArtifactRef)

    assert restored == artifact


def test_dump_refuses_overwrite(tmp_path) -> None:
    path = tmp_path / "artifact.json"
    dump_model(example_artifact(), path)

    with pytest.raises(ManifestStateError, match="不可覆盖"):
        dump_model(example_artifact(), path)


def test_canonical_json_and_hash_are_stable() -> None:
    artifact = example_artifact()
    first = canonical_json_bytes(artifact)
    second = canonical_json_bytes(ArtifactRef.model_validate(artifact.model_dump()))

    assert first == second
    assert canonical_model_sha256(artifact) == canonical_model_sha256(artifact)
    assert first.endswith(b"}")
    assert b"\n" not in first


def test_load_rejects_extra_fields(tmp_path) -> None:
    payload = example_artifact().model_dump(mode="json")
    payload["unexpected"] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SerializationError, match="模型校验失败"):
        load_model(path, ArtifactRef)


def test_load_rejects_invalid_json(tmp_path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(SerializationError, match="JSON 读取失败"):
        load_model(path, ArtifactRef)
