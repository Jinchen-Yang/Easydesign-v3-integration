from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from easydesign.core import ArtifactRef
from easydesign.orchestration.stage06 import build_scale_plan
from easydesign.stages.s06_scale_generation_and_refolding import (
    ScaleCoverageReport,
    ScaleProfile,
)

NOW = datetime(2026, 7, 26, 4, 0, tzinfo=UTC)
SHA256 = "a" * 64


def _artifact(artifact_id: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=artifact_id,
        role="test-input",
        relative_path=f"inputs/{artifact_id}.json",
        file_format="json",
        sha256=SHA256,
        size_bytes=1,
        producer_stage="05-pilot-filtering",
        producer_attempt="attempt-0001",
    )


@pytest.mark.parametrize(
    ("profile", "limit", "shard_count", "shard_size"),
    (
        (ScaleProfile.SMOKE_1000, 1_000, 2, 500),
        (ScaleProfile.PRODUCTION_50000, 50_000, 20, 2_500),
    ),
)
def test_scale_profiles_build_contiguous_authorized_shards(
    profile: ScaleProfile,
    limit: int,
    shard_count: int,
    shard_size: int,
) -> None:
    plan = build_scale_plan(
        profile=profile,
        strategy_id="strategy-one",
        strategy_bundle_sha256=SHA256,
        stage05_bundle_sha256=SHA256,
        design_specification=_artifact("design-specification"),
        resource_report=_artifact("resource-report"),
        devices=(0, 1),
        preauthorized_candidate_limit=limit,
        generated_at=NOW,
    )

    assert len(plan.shards) == shard_count
    assert {item.requested_candidates for item in plan.shards} == {shard_size}
    assert plan.shards[0].ordinal_start == 1
    assert plan.shards[-1].ordinal_end == limit


def test_scale_plan_rejects_candidate_budget_above_authorization() -> None:
    with pytest.raises(ValidationError, match="预授权"):
        build_scale_plan(
            profile=ScaleProfile.PRODUCTION_50000,
            strategy_id="strategy-one",
            strategy_bundle_sha256=SHA256,
            stage05_bundle_sha256=SHA256,
            design_specification=_artifact("design-specification"),
            resource_report=_artifact("resource-report"),
            devices=(0, 1),
            preauthorized_candidate_limit=1_000,
            generated_at=NOW,
        )


def test_scale_coverage_rejects_gaps_or_duplicate_identity() -> None:
    with pytest.raises(ValidationError, match="identity"):
        ScaleCoverageReport(
            strategy_id="strategy-one",
            requested_new_candidates=1_000,
            complete_new_candidates=1_000,
            candidate_ids_unique=False,
            ordinal_min=1,
            ordinal_max=1_000,
        )
    with pytest.raises(ValidationError, match="缺口"):
        ScaleCoverageReport(
            strategy_id="strategy-one",
            requested_new_candidates=1_000,
            complete_new_candidates=1_000,
            candidate_ids_unique=True,
            ordinal_min=1,
            ordinal_max=1_000,
            ordinal_gaps=(502,),
        )
