from __future__ import annotations

import pytest

from easydesign.core import ConfigurationError
from easydesign.orchestration.research_protocols import (
    DEFAULT_SCALE_CANDIDATE_COUNT,
    ExperimentalCondition,
    scale_protocol_summary,
    validate_first_pilot_protocol,
)
from easydesign.stages.s03_boltzgen_configuration import SCAFFOLD_IDS


@pytest.mark.parametrize(("condition_count", "expected"), ((1, 280), (2, 560), (6, 1680)))
def test_first_pilot_is_exactly_seven_by_forty_by_x(
    condition_count: int,
    expected: int,
) -> None:
    summary = validate_first_pilot_protocol(
        conditions=tuple(
            ExperimentalCondition(
                condition_id=f"condition-{index}",
                scaffold_ids=SCAFFOLD_IDS,
                candidates_per_scaffold=40,
            )
            for index in range(condition_count)
        ),
        official_scaffold_ids=SCAFFOLD_IDS,
    )

    assert summary.experimental_condition_count == condition_count
    assert summary.scaffold_count_per_condition == 7
    assert summary.candidates_per_scaffold == 40
    assert summary.candidates_per_condition == 280
    assert summary.total_candidates == expected


def test_every_first_pilot_condition_must_independently_be_complete() -> None:
    valid = ExperimentalCondition(
        condition_id="baseline",
        scaffold_ids=SCAFFOLD_IDS,
        candidates_per_scaffold=40,
    )
    missing = valid.model_copy(
        update={"condition_id": "diagnostic", "scaffold_ids": SCAFFOLD_IDS[:-1]}
    )
    reduced = valid.model_copy(update={"condition_id": "diagnostic", "candidates_per_scaffold": 39})

    with pytest.raises(ConfigurationError, match="condition=diagnostic"):
        validate_first_pilot_protocol(
            conditions=(valid, missing),
            official_scaffold_ids=SCAFFOLD_IDS,
        )
    with pytest.raises(ConfigurationError, match="生成 40"):
        validate_first_pilot_protocol(
            conditions=(valid, reduced),
            official_scaffold_ids=SCAFFOLD_IDS,
        )


def test_first_pilot_counts_only_explicit_conditions_without_cartesian_expansion() -> None:
    explicitly_admitted = (
        ExperimentalCondition(
            condition_id="hotspot-a-cdr3-12",
            scaffold_ids=SCAFFOLD_IDS,
            candidates_per_scaffold=40,
        ),
        ExperimentalCondition(
            condition_id="hotspot-b-cdr3-14",
            scaffold_ids=SCAFFOLD_IDS,
            candidates_per_scaffold=40,
        ),
    )

    summary = validate_first_pilot_protocol(
        conditions=explicitly_admitted,
        official_scaffold_ids=SCAFFOLD_IDS,
    )

    assert summary.experimental_condition_count == 2
    assert summary.total_candidates == 2 * 7 * 40


@pytest.mark.parametrize("count", (10_000, 20_000, 50_000, 100_000, 37_129))
def test_scale_accepts_exact_positive_user_counts(count: int) -> None:
    summary = scale_protocol_summary(
        total_candidate_count=count,
        strategy_ids=("s1", "s2", "s3"),
    )

    assert summary.default_candidate_count == DEFAULT_SCALE_CANDIDATE_COUNT == 50_000
    assert summary.total_candidate_count == count
    assert sum(item.candidate_count for item in summary.allocation) == count
    assert summary.shard_size == 2_500
    assert summary.total_shards == sum(item.shard_count for item in summary.allocation)


@pytest.mark.parametrize("count", (0, -1))
def test_scale_rejects_non_positive_count(count: int) -> None:
    with pytest.raises(ConfigurationError, match="正整数"):
        scale_protocol_summary(total_candidate_count=count, strategy_ids=("s1",))
