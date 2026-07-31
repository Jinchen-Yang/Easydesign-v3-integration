"""Nanobody Filter Standard v1.6 promotion and advisory diagnostics."""

from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Literal

from easydesign.core import ManifestStateError
from easydesign.filtering.nanobody_v1_5 import (
    PROFILE_SOURCE_SHA256 as PROFILE_SOURCE_SHA256_V1_5,
)
from easydesign.filtering.nanobody_v1_5 import (
    evaluate_pilot_candidates,
)
from easydesign.filtering.structure_metrics import InterfaceMetricValues
from easydesign.stages.s04_pilot_generation import CandidateRecord
from easydesign.stages.s05_pilot_filtering.models import (
    AdvisoryStrategySummary,
    AdvisoryValidationReport,
    ExpansionCandidateRecord,
    FullTargetPredictionRecord,
    PilotFilterReportV1_6,
    Stage05Warning,
    StrategyPromotionRecord,
    StrategyTier,
)

PROFILE_ID_V1_6 = "nanobody-filter-standard-v1.6"
PROFILE_SOURCE_SHA256_V1_6 = (
    "7fd2d11eba6fe634095bb8cb1e902f39ca59d837cd601c393e978424a4848cfb"
)


def evaluate_pilot_candidates_v1_6(
    *,
    candidates: tuple[CandidateRecord, ...],
    structural_metrics: dict[str, InterfaceMetricValues],
    candidate_index_sha256: str,
    maximum_tier_a_strategies: int,
    generated_at: datetime,
) -> PilotFilterReportV1_6:
    """Reuse the frozen v1.5 gates while publishing v1.6 promotion semantics."""

    legacy_report = evaluate_pilot_candidates(
        candidates=candidates,
        structural_metrics=structural_metrics,
        # v1.6 intentionally reuses the frozen v1.5 pilot gates.  The legacy
        # implementation validates its own source identity before evaluating;
        # the resulting records are then republished under the v1.6 profile.
        profile_sha256=PROFILE_SOURCE_SHA256_V1_5,
        candidate_index_sha256=candidate_index_sha256,
        maximum_tier_a_strategies=maximum_tier_a_strategies,
        generated_at=generated_at,
    )
    promoted = tuple(
        summary.strategy_id
        for summary in sorted(
            (
                summary
                for summary in legacy_report.strategy_summaries
                if summary.selected_for_expansion
            ),
            key=lambda summary: (-summary.score_yaml, summary.strategy_id),
        )
    )
    return PilotFilterReportV1_6(
        generated_at=generated_at,
        profile_sha256=PROFILE_SOURCE_SHA256_V1_6,
        candidate_index_sha256=candidate_index_sha256,
        candidate_records=legacy_report.candidate_records,
        strategy_summaries=legacy_report.strategy_summaries,
        promoted_strategy_ids=promoted,
        status=("strategies-promoted" if promoted else "stopped-no-tier-a"),
    )


def promotion_records(
    report: PilotFilterReportV1_6,
) -> tuple[StrategyPromotionRecord, ...]:
    """Create the immutable F_YAML ranking used by Stage 06 allocation."""

    summaries = {item.strategy_id: item for item in report.strategy_summaries}
    records: list[StrategyPromotionRecord] = []
    for rank, strategy_id in enumerate(report.promoted_strategy_ids, start=1):
        summary = summaries[strategy_id]
        if summary.tier is not StrategyTier.A:
            raise ManifestStateError("v1.6 promotion 只接受 Tier A strategy")
        records.append(
            StrategyPromotionRecord(
                strategy_id=strategy_id,
                promotion_rank=rank,
                score_yaml=summary.score_yaml,
                pilot_candidate_count=summary.candidate_count,
                unique_sequence_count=summary.unique_sequence_count,
                boltzgen_hard_pass_count=summary.boltzgen_hard_pass_count,
                final_gate_pass_count=summary.final_gate_pass_count,
                final_gate_pass_rate=summary.final_gate_pass_rate,
            )
        )
    return tuple(records)


def build_advisory_validation_report(
    *,
    promoted_strategies: tuple[StrategyPromotionRecord, ...],
    expanded_total_per_strategy: int,
    full_target_top_n: int,
    candidates: tuple[ExpansionCandidateRecord, ...],
    predictions: tuple[FullTargetPredictionRecord, ...],
    generated_at: datetime,
) -> AdvisoryValidationReport:
    """Validate diagnostic completeness without turning a scientific negative into a stop."""

    if not promoted_strategies:
        raise ManifestStateError("没有 Tier A strategy 时不能生成 advisory report")
    promoted_ids = tuple(item.strategy_id for item in promoted_strategies)
    if len(promoted_ids) != len(set(promoted_ids)):
        raise ManifestStateError("promoted strategy_id 不能重复")
    if len(promoted_ids) > 3:
        raise ManifestStateError("v1.6 最多晋级三个 Tier A strategy")

    candidate_by_id = {item.candidate_id: item for item in candidates}
    if len(candidate_by_id) != len(candidates):
        raise ManifestStateError("expansion candidate_id 不能重复")
    selected_ids = {
        item.candidate_id for item in candidates if item.selected_for_full_target
    }
    prediction_by_id = {item.candidate_id: item for item in predictions}
    if len(prediction_by_id) != len(predictions):
        raise ManifestStateError("full-target prediction candidate_id 不能重复")
    if set(prediction_by_id) != selected_ids:
        raise ManifestStateError(
            "full-target prediction 必须覆盖全部且仅覆盖 selected candidate"
        )
    for candidate_id, prediction in prediction_by_id.items():
        if prediction.strategy_id != candidate_by_id[candidate_id].strategy_id:
            raise ManifestStateError("full-target prediction strategy identity 不一致")

    candidate_groups: dict[str, list[ExpansionCandidateRecord]] = {
        strategy_id: [] for strategy_id in promoted_ids
    }
    prediction_groups: dict[str, list[FullTargetPredictionRecord]] = {
        strategy_id: [] for strategy_id in promoted_ids
    }
    for candidate in candidates:
        if candidate.strategy_id not in candidate_groups:
            raise ManifestStateError("expansion candidate 来自未晋级 strategy")
        candidate_groups[candidate.strategy_id].append(candidate)
    for prediction in predictions:
        if prediction.strategy_id not in prediction_groups:
            raise ManifestStateError("full-target prediction 来自未晋级 strategy")
        prediction_groups[prediction.strategy_id].append(prediction)

    summaries: list[AdvisoryStrategySummary] = []
    warnings: list[Stage05Warning] = []
    for promotion in promoted_strategies:
        strategy_id = promotion.strategy_id
        group = candidate_groups[strategy_id]
        if len(group) != expanded_total_per_strategy:
            raise ManifestStateError(
                f"strategy={strategy_id} expansion 未达到 "
                f"{expanded_total_per_strategy}"
            )
        selected_group = [item for item in group if item.selected_for_full_target]
        if len(selected_group) > full_target_top_n:
            raise ManifestStateError("selected full-target 数超过配置上限")
        predicted_group = prediction_groups[strategy_id]
        passing = [item for item in predicted_group if item.structure_gate_pass]
        pose_values = [item.binder_pose_rmsd_angstrom for item in predicted_group]
        mean_score = (
            sum(item.score_expand_structure for item in selected_group)
            / len(selected_group)
            if selected_group
            else 0.0
        )
        advisory_status: Literal["advisory-supported", "advisory-warning"] = (
            "advisory-supported" if passing else "advisory-warning"
        )
        summaries.append(
            AdvisoryStrategySummary(
                strategy_id=strategy_id,
                promotion_rank=promotion.promotion_rank,
                score_yaml=promotion.score_yaml,
                complete_candidate_count=len(group),
                local_gate_pass_count=sum(item.local_gate_pass for item in group),
                selected_for_full_target_count=len(selected_group),
                full_target_prediction_count=len(predicted_group),
                full_target_structure_pass_count=len(passing),
                full_target_structure_pass_rate=(
                    len(passing) / len(predicted_group) if predicted_group else 0.0
                ),
                minimum_binder_pose_rmsd_angstrom=(
                    min(pose_values) if pose_values else None
                ),
                median_binder_pose_rmsd_angstrom=(
                    float(median(pose_values)) if pose_values else None
                ),
                mean_selected_score_expand_structure=mean_score,
                advisory_status=advisory_status,
            )
        )
        if not passing:
            warnings.append(
                Stage05Warning(
                    warning_id=(
                        f"full-target-zero-pass-{promotion.promotion_rank:02d}"
                    ),
                    strategy_id=strategy_id,
                    code="full-target-structure-gate-zero-pass",
                    message=(
                        "诊断性 full-target 复核没有结构门通过者；"
                        "该证据需要人工关注，但不撤销 Tier A 晋级。"
                    ),
                    evidence_candidate_ids=tuple(
                        item.candidate_id for item in predicted_group
                    ),
                )
            )
        if predicted_group and not any(
            item.confidence_reference_pass for item in predicted_group
        ):
            warnings.append(
                Stage05Warning(
                    warning_id=(
                        f"full-target-low-confidence-"
                        f"{promotion.promotion_rank:02d}"
                    ),
                    strategy_id=strategy_id,
                    code="full-target-confidence-low",
                    message=(
                        "诊断性 full-target 复核的 iPTM、PAE 与 binder pTM "
                        "参考线均未提供支持；仅作 warning。"
                    ),
                    evidence_candidate_ids=tuple(
                        item.candidate_id for item in predicted_group
                    ),
                )
            )

    return AdvisoryValidationReport(
        generated_at=generated_at,
        expanded_total_per_strategy=expanded_total_per_strategy,
        full_target_refold_top_n=full_target_top_n,
        promoted_strategies=promoted_strategies,
        candidates=candidates,
        predictions=predictions,
        strategies=tuple(summaries),
        warnings=tuple(warnings),
    )
