from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from easydesign.core import ArtifactRef
from easydesign.core.evidence_links import (
    AdoptedDeviceExecutionSummary,
    AdoptedScaleExecutionSummary,
    PolicyReevaluationRecord,
    ProjectScaleEvidenceContinuation,
    ReevaluatedStrategy,
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


def _policy() -> PolicyReevaluationRecord:
    return PolicyReevaluationRecord(
        generated_at=NOW,
        source_stage05_bundle=RunEvidenceLink(
            **{
                **_link().model_dump(),
                "source_run_id": "20260726-004-stage05-pilot-filter",
                "source_artifact": ArtifactRef(
                    **{
                        **_artifact().model_dump(),
                        "artifact_id": "stage05-bundle",
                        "role": "stage05-bundle",
                        "producer_stage": "05-pilot-filtering",
                    }
                ),
                "artifact_sha256": SHA256,
                "artifact_size_bytes": 1234,
            }
        ),
        source_stage05_status="stopped-no-scale-winner",
        strategies=(
            ReevaluatedStrategy(
                strategy_id="strategy-one",
                tier="tier-a",
                score_yaml=0.75,
                old_selected_for_expansion=True,
                new_promoted=True,
                promotion_rank=1,
            ),
            ReevaluatedStrategy(
                strategy_id="strategy-two",
                tier="tier-b",
                score_yaml=0.5,
                old_selected_for_expansion=False,
                new_promoted=False,
            ),
        ),
        promoted_strategy_ids=("strategy-one",),
        status="strategies-promoted",
    )


def _continuation() -> ProjectScaleEvidenceContinuation:
    policy = _policy()
    adoption = ScaleEvidenceAdoptionRecord(
        generated_at=NOW,
        policy_reevaluation_sha256="d" * 64,
        source_scale_bundle=_link(),
        strategy_ids=("strategy-one",),
        shard_count=20,
        candidate_count=50_000,
        expected_candidate_count=50_000,
    )
    return ProjectScaleEvidenceContinuation(
        continuation_id="apoe-v16-scale-evidence",
        generated_at=NOW,
        project_id="apoe-s02-006-pse",
        source_local_run_id="20260726-004-stage05-pilot-filter",
        source_local_run_manifest_sha256="b" * 64,
        policy_reevaluation=policy,
        scale_evidence_adoption=adoption,
        source_stage06_manifest=_link(),
        source_scale_plan=_link(),
        source_scale_progress=_link(),
        source_candidate_index=_link(),
        execution=AdoptedScaleExecutionSummary(
            executor_id="suzhou2",
            strategy_ids=("strategy-one",),
            strategy_candidate_counts={"strategy-one": 50_000},
            strategy_shard_counts={"strategy-one": 20},
            devices=(0, 1, 2, 3, 4, 5, 6, 7),
            shard_count=20,
            succeeded_task_count=20,
            failed_task_count=0,
            candidate_count=50_000,
            elapsed_seconds=192_410,
            completed_at=NOW,
        ),
        device_execution=tuple(
            AdoptedDeviceExecutionSummary(
                device=device,
                task_count=3 if device < 4 else 2,
                attempt_count=3 if device < 4 else 2,
                failed_attempt_count=0,
                candidate_count=7_500 if device < 4 else 5_000,
                busy_seconds=24_000,
            )
            for device in range(8)
        ),
    )


def test_project_scale_evidence_continuation_preserves_two_run_identities() -> None:
    continuation = _continuation()
    assert continuation.policy_reevaluation.source_stage05_status == (
        "stopped-no-scale-winner"
    )
    assert continuation.scale_evidence_adoption.status == "adopted"
    assert continuation.execution.candidate_count == 50_000


def test_project_scale_evidence_continuation_rejects_strategy_mismatch() -> None:
    continuation = _continuation()
    with pytest.raises(ValidationError, match="policy promotion"):
        ProjectScaleEvidenceContinuation.model_validate(
            {
                **continuation.model_dump(),
                "scale_evidence_adoption": {
                    **continuation.scale_evidence_adoption.model_dump(),
                    "strategy_ids": ("strategy-two",),
                },
            }
        )
