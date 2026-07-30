from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from easydesign.stages.s05_pilot_filtering import StrategyPromotionRecord
from easydesign.stages.s06_scale_generation_and_refolding import (
    ScaleCoverageReportV0_2,
    StrategyScaleCoverage,
    allocate_equal_candidate_budget,
    build_multi_strategy_shards,
    scale_candidate_id,
)

NOW = datetime(2026, 7, 31, 10, 0, tzinfo=UTC)


def _promotion(rank: int) -> StrategyPromotionRecord:
    return StrategyPromotionRecord(
        strategy_id=f"strategy-{rank}",
        promotion_rank=rank,
        score_yaml=0.50 - rank / 100,
        pilot_candidate_count=40,
        unique_sequence_count=40,
        boltzgen_hard_pass_count=6,
        final_gate_pass_count=5,
        final_gate_pass_rate=5 / 40,
    )


@pytest.mark.parametrize(
    ("strategy_count", "expected"),
    (
        (1, (50_000,)),
        (2, (25_000, 25_000)),
        (3, (16_667, 16_667, 16_666)),
    ),
)
def test_equal_budget_allocation_follows_promotion_rank(
    strategy_count: int,
    expected: tuple[int, ...],
) -> None:
    allocations = allocate_equal_candidate_budget(
        promoted_strategies=tuple(
            _promotion(rank) for rank in range(1, strategy_count + 1)
        ),
        total_candidate_budget=50_000,
    )

    assert tuple(item.requested_candidates for item in allocations) == expected
    assert tuple(item.promotion_rank for item in allocations) == tuple(
        range(1, strategy_count + 1)
    )


def test_allocation_rejects_more_than_three_promoted_strategies() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 3"):
        _promotion(4)


def test_multi_strategy_shards_allow_small_tail_and_preserve_local_ordinals() -> None:
    allocations = allocate_equal_candidate_budget(
        promoted_strategies=tuple(_promotion(rank) for rank in range(1, 4)),
        total_candidate_budget=50_000,
    )
    shards = build_multi_strategy_shards(
        strategy_allocations=allocations,
        shard_size=2_500,
    )

    assert len(shards) == 21
    assert sum(item.requested_candidates for item in shards) == 50_000
    tails = {
        item.strategy_id: item.requested_candidates
        for item in shards
        if item.strategy_ordinal_end
        == next(
            allocation.requested_candidates
            for allocation in allocations
            if allocation.strategy_id == item.strategy_id
        )
    }
    assert tails == {
        "strategy-1": 1_667,
        "strategy-2": 1_667,
        "strategy-3": 1_666,
    }
    for allocation in allocations:
        strategy_shards = [
            item for item in shards if item.strategy_id == allocation.strategy_id
        ]
        assert strategy_shards[0].strategy_ordinal_start == 1
        assert strategy_shards[-1].strategy_ordinal_end == (
            allocation.requested_candidates
        )


def test_candidate_identity_contains_strategy_and_local_ordinal() -> None:
    assert scale_candidate_id("strategy-one", 42) == (
        "strategy-one-scale-000042"
    )


def test_global_coverage_rejects_per_strategy_count_mismatch() -> None:
    with pytest.raises(ValidationError, match="requested 总数"):
        ScaleCoverageReportV0_2(
            total_requested_candidates=50_000,
            total_complete_candidates=50_000,
            global_candidate_ids_unique=True,
            strategy_coverage=(
                StrategyScaleCoverage(
                    strategy_id="strategy-one",
                    requested_candidates=25_000,
                    complete_candidates=25_000,
                    candidate_ids_unique=True,
                    ordinal_min=1,
                    ordinal_max=25_000,
                ),
            ),
        )
