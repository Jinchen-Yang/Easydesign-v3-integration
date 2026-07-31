from __future__ import annotations

from types import SimpleNamespace

import pytest

from easydesign.core import ManifestStateError
from easydesign.stages.s06_scale_generation_and_refolding import (
    ScaleBundle,
    ScaleBundleV0_2,
    StrategyAllocation,
)
from easydesign.stages.s07_final_filtering_and_selection import (
    ScaleCandidateLineage,
    Stage07ScaleInput,
    Stage07StrategyAllocation,
    normalize_scale_bundle_for_stage07,
    summarize_selected_sources,
    validate_scale_candidate_lineage,
)

SHA256 = "a" * 64


def test_stage07_normalizes_legacy_single_strategy_scale_bundle() -> None:
    legacy = ScaleBundle.model_construct(
        requested_new_candidates=50_000,
        strategy_id="legacy-strategy",
    )
    normalized = normalize_scale_bundle_for_stage07(
        scale_bundle=legacy,
        scale_bundle_sha256=SHA256,
        candidate_index_sha256="b" * 64,
    )

    assert normalized.source_scale_bundle_schema == "0.1"
    assert normalized.allocation_policy == "legacy-single-strategy"
    assert normalized.total_candidate_budget == 50_000
    assert normalized.strategy_allocations[0].strategy_id == "legacy-strategy"


def test_stage07_normalizes_multi_strategy_allocations_without_losing_rank() -> None:
    current = ScaleBundleV0_2.model_construct(
        allocation_policy="equal-across-promoted-v1",
        total_candidate_budget=50_000,
        strategy_allocations=(
            StrategyAllocation(
                strategy_id="strategy-one",
                promotion_rank=1,
                score_yaml=0.5,
                requested_candidates=25_000,
            ),
            StrategyAllocation(
                strategy_id="strategy-two",
                promotion_rank=2,
                score_yaml=0.4,
                requested_candidates=25_000,
            ),
        ),
    )
    normalized = normalize_scale_bundle_for_stage07(
        scale_bundle=current,
        scale_bundle_sha256=SHA256,
        candidate_index_sha256="b" * 64,
    )

    assert normalized.source_scale_bundle_schema == "0.2"
    assert tuple(
        item.promotion_rank for item in normalized.strategy_allocations
    ) == (1, 2)
    assert sum(
        item.requested_candidates for item in normalized.strategy_allocations
    ) == 50_000


def _small_input() -> Stage07ScaleInput:
    return Stage07ScaleInput(
        source_scale_bundle_schema="0.2",
        source_scale_bundle_sha256=SHA256,
        candidate_index_sha256="b" * 64,
        allocation_policy="equal-across-promoted-v1",
        total_candidate_budget=4,
        strategy_allocations=(
            Stage07StrategyAllocation(
                strategy_id="strategy-one",
                requested_candidates=2,
                promotion_rank=1,
            ),
            Stage07StrategyAllocation(
                strategy_id="strategy-two",
                requested_candidates=2,
                promotion_rank=2,
            ),
        ),
    )


def _candidate(
    candidate_id: str,
    strategy_id: str,
    ordinal: int,
) -> ScaleCandidateLineage:
    return ScaleCandidateLineage(
        candidate_id=candidate_id,
        strategy_id=strategy_id,
        strategy_ordinal=ordinal,
        sequence_sha256=(candidate_id[0] if candidate_id[0] in "abcdef" else "c")
        * 64,
    )


def test_stage07_validates_exact_strategy_population() -> None:
    validate_scale_candidate_lineage(
        scale_input=_small_input(),
        candidates=(
            _candidate("a-one", "strategy-one", 1),
            _candidate("a-two", "strategy-one", 2),
            _candidate("b-one", "strategy-two", 1),
            _candidate("b-two", "strategy-two", 2),
        ),
    )


def test_stage07_rejects_per_strategy_ordinal_gap() -> None:
    with pytest.raises(ManifestStateError, match="ordinal"):
        validate_scale_candidate_lineage(
            scale_input=_small_input(),
            candidates=(
                _candidate("a-one", "strategy-one", 1),
                _candidate("a-three", "strategy-one", 3),
                _candidate("b-one", "strategy-two", 1),
                _candidate("b-two", "strategy-two", 2),
            ),
        )


def test_source_distribution_reports_global_selection_without_quota() -> None:
    primary = (
        SimpleNamespace(strategy_id="strategy-two"),
        SimpleNamespace(strategy_id="strategy-two"),
    )
    backup = (SimpleNamespace(strategy_id="strategy-one"),)

    distribution = summarize_selected_sources(
        primary=primary,  # type: ignore[arg-type]
        backup=backup,  # type: ignore[arg-type]
    )

    assert tuple(item.strategy_id for item in distribution) == (
        "strategy-one",
        "strategy-two",
    )
    assert distribution[0].backup_count == 1
    assert distribution[1].primary_count == 2
