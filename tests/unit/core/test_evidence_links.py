from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from easydesign.core import ArtifactRef
from easydesign.core.evidence_links import (
    RunEvidenceLink,
    ScaleEvidenceAdoptionRecord,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
SHA256 = "a" * 64


def _artifact() -> ArtifactRef:
    return ArtifactRef(
        artifact_id="scale-bundle",
        role="scale-bundle",
        relative_path="06-scale-generation/attempt-0001/artifacts/scale-bundle.json",
        file_format="json",
        size_bytes=1234,
        sha256=SHA256,
        producer_stage="06-scale-generation-and-refolding",
        producer_attempt="attempt-0001",
    )


def _link() -> RunEvidenceLink:
    return RunEvidenceLink(
        source_project_id="apoe-s02-006-pse",
        source_run_id="20260727-001-stage06-tier-a-50k-suzhou2",
        source_run_manifest_sha256="b" * 64,
        source_artifact=_artifact(),
        executor_id="suzhou2",
        artifact_sha256=SHA256,
        artifact_size_bytes=1234,
    )


def test_run_evidence_link_uses_relative_artifact_and_exact_identity() -> None:
    link = _link()
    assert not link.source_artifact.relative_path.startswith("/")
    assert link.artifact_sha256 == link.source_artifact.sha256


def test_run_evidence_link_rejects_mismatched_checksum() -> None:
    with pytest.raises(ValidationError, match="SHA-256"):
        RunEvidenceLink(
            **{
                **_link().model_dump(),
                "artifact_sha256": "c" * 64,
            }
        )


def test_scale_adoption_rejects_incomplete_historical_population() -> None:
    with pytest.raises(ValidationError, match="数量不完整"):
        ScaleEvidenceAdoptionRecord(
            generated_at=NOW,
            policy_reevaluation_sha256="d" * 64,
            source_scale_bundle=_link(),
            strategy_ids=("strategy-one",),
            shard_count=20,
            candidate_count=49_999,
            expected_candidate_count=50_000,
        )
