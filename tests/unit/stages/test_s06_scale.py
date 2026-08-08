from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from easydesign.core import ArtifactRef, ManifestStateError
from easydesign.orchestration.config import Stage06Config
from easydesign.orchestration.stage06 import (
    _resolve_multi_strategy_authorization,
    _resolve_strategy_authorization,
    build_scale_plan,
)
from easydesign.stages.s05_pilot_filtering import (
    Stage05BundleV0_2,
    StrategyPromotionRecord,
)
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


def _promotion(rank: int) -> StrategyPromotionRecord:
    return StrategyPromotionRecord(
        strategy_id=f"strategy-{rank}",
        promotion_rank=rank,
        score_yaml=0.5 - rank / 100,
        pilot_candidate_count=40,
        unique_sequence_count=40,
        boltzgen_hard_pass_count=6,
        final_gate_pass_count=5,
        final_gate_pass_rate=5 / 40,
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
        total_candidate_count=limit,
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
            total_candidate_count=50_000,
            strategy_id="strategy-one",
            strategy_bundle_sha256=SHA256,
            stage05_bundle_sha256=SHA256,
            design_specification=_artifact("design-specification"),
            resource_report=_artifact("resource-report"),
            devices=(0, 1),
            preauthorized_candidate_limit=1_000,
            generated_at=NOW,
        )


def test_user_defined_scale_count_builds_final_remainder_shard() -> None:
    plan = build_scale_plan(
        profile=ScaleProfile.USER_DEFINED_V1,
        total_candidate_count=5_001,
        strategy_id="strategy-one",
        strategy_bundle_sha256=SHA256,
        stage05_bundle_sha256=SHA256,
        design_specification=_artifact("design-specification"),
        resource_report=_artifact("resource-report"),
        devices=(0, 1),
        preauthorized_candidate_limit=5_001,
        generated_at=NOW,
    )

    assert [item.requested_candidates for item in plan.shards] == [2_500, 2_500, 1]
    assert plan.shards[-1].ordinal_end == 5_001


def test_stage06_config_defaults_to_recommended_user_budget_and_reads_dev34() -> None:
    current = Stage06Config()
    assert current.scale_profile == "user-defined-v1"
    assert current.total_candidate_count == 50_000
    assert current.authorized_candidate_limit == 50_000

    legacy = Stage06Config.model_validate(
        {"scale_profile": "smoke-1000", "preauthorized_candidate_limit": 1_000}
    )
    assert legacy.total_candidate_count == 1_000
    assert legacy.authorized_candidate_limit == 1_000


def test_stage06_config_accepts_arbitrary_positive_user_count() -> None:
    config = Stage06Config.model_validate(
        {"scale_profile": "user-defined-v1", "total_candidate_count": 37}
    )
    assert config.total_candidate_count == 37
    assert config.authorized_candidate_limit == 37


def test_manual_scale_authorization_requires_two_explicit_acknowledgements() -> None:
    payload = {
        "scale_profile": "production-50000",
        "preauthorized_candidate_limit": 50_000,
        "manual_strategy_authorization": {
            "strategy_id": "tier-a-strategy",
            "authorized_by": "principal-investigator",
            "reason": "Run this strategy as an explicitly exploratory production-scale test.",
            "source_stage05_bundle_sha256": SHA256,
        },
    }
    with pytest.raises(ValidationError, match="acknowledge"):
        Stage06Config.model_validate(payload)

    payload["manual_strategy_authorization"].update(
        {
            "acknowledge_stage05_scientific_stop": True,
            "acknowledge_not_scientifically_eligible": True,
        }
    )
    config = Stage06Config.model_validate(payload)
    assert config.manual_strategy_authorization is not None
    assert config.manual_strategy_authorization.strategy_id == "tier-a-strategy"


def test_manual_scale_authorization_only_accepts_stage05_expanded_tier_a() -> None:
    config = Stage06Config.model_validate(
        {
            "scale_profile": "production-50000",
            "preauthorized_candidate_limit": 50_000,
            "manual_strategy_authorization": {
                "strategy_id": "tier-a-strategy",
                "authorized_by": "principal-investigator",
                "reason": ("Run this strategy as an explicitly exploratory production-scale test."),
                "source_stage05_bundle_sha256": SHA256,
                "acknowledge_stage05_scientific_stop": True,
                "acknowledge_not_scientifically_eligible": True,
            },
        }
    )
    upstream = SimpleNamespace(
        stage05_bundle=SimpleNamespace(
            status="stopped-no-scale-winner",
            winner_strategy_id=None,
        ),
        stage05_bundle_ref=SimpleNamespace(sha256=SHA256),
        pilot_filter_report=SimpleNamespace(
            selected_strategy_ids=("tier-a-strategy",),
        ),
        strategy_bundle=SimpleNamespace(
            strategies=(SimpleNamespace(strategy_id="tier-a-strategy"),),
        ),
    )

    authorization = _resolve_strategy_authorization(
        upstream=upstream,  # type: ignore[arg-type]
        config=config,
        authorized_at=NOW,
    )

    assert authorization.mode == "manual-stage05-stop-override"
    assert authorization.strategy_id == "tier-a-strategy"
    with pytest.raises(ManifestStateError, match="已扩展"):
        _resolve_strategy_authorization(
            upstream=SimpleNamespace(
                **{
                    **upstream.__dict__,
                    "pilot_filter_report": SimpleNamespace(selected_strategy_ids=()),
                }
            ),  # type: ignore[arg-type]
            config=config,
            authorized_at=NOW,
        )


def test_human_promotion_receipt_limits_scale_to_selected_tier_a_subset() -> None:
    stage05_bundle = Stage05BundleV0_2.model_construct(
        status="strategies-promoted",
        promoted_strategy_ids=("strategy-1", "strategy-2"),
        promotion_rank=(_promotion(1), _promotion(2)),
    )
    upstream = SimpleNamespace(
        stage05_bundle=stage05_bundle,
        stage05_bundle_ref=SimpleNamespace(sha256=SHA256),
    )
    config = Stage06Config(
        total_candidate_count=50_000,
        allocation_policy="equal-across-promoted-v1",
        human_promoted_strategy_ids=("strategy-2",),
        human_promotion_receipt_sha256="b" * 64,
    )

    authorization = _resolve_multi_strategy_authorization(
        upstream=upstream,  # type: ignore[arg-type]
        profile=ScaleProfile.PRODUCTION_50000,
        config=config,
        authorized_at=NOW,
    )

    assert authorization.mode == "human-promotion-receipt"
    assert authorization.promoted_strategy_ids == ("strategy-2",)
    assert authorization.human_promotion_receipt_sha256 == "b" * 64

    invalid = config.model_copy(update={"human_promoted_strategy_ids": ("strategy-missing",)})
    with pytest.raises(ManifestStateError, match="合法 Tier A"):
        _resolve_multi_strategy_authorization(
            upstream=upstream,  # type: ignore[arg-type]
            profile=ScaleProfile.PRODUCTION_50000,
            config=invalid,
            authorized_at=NOW,
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
