"""Frozen Stage 07 review-cohort and dual-mode comparison contracts."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core import ArtifactRef, ManifestStateError
from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN
from easydesign.filtering.structure_metrics import compare_dual_mode_structures
from easydesign.stages.s04_pilot_generation import CandidateRecord

from .models import DeepFilterRecord, RawFinalPrediction


class Stage07ReviewCohortEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    review_rank: int = Field(ge=1)
    candidate_id: str = Field(pattern=ID_PATTERN)
    strategy_id: str = Field(pattern=ID_PATTERN)
    score_deep: float = Field(ge=0, le=1)
    absolute_gate_pass: Literal[True] = True
    selected_for_seed101: Literal[True] = True
    source_refolded_structure: ArtifactRef


class Stage07ReviewCohortIndex(BaseModel):
    """At most N deep-gate passers, frozen before final selection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    requested_size: int = Field(default=200, ge=1, le=400)
    actual_size: int = Field(ge=0, le=400)
    ordering: Literal[
        "absolute-gate-pass-then-score-deep-desc-candidate-id-asc"
    ] = "absolute-gate-pass-then-score-deep-desc-candidate-id-asc"
    deep_filter_profile_sha256: str = Field(pattern=SHA256_PATTERN)
    scale_candidate_index_sha256: str = Field(pattern=SHA256_PATTERN)
    entries: tuple[Stage07ReviewCohortEntry, ...] = ()

    @model_validator(mode="after")
    def validate_entries(self) -> Self:
        if self.actual_size != len(self.entries):
            raise ValueError("review cohort actual_size 与 entries 不一致")
        if self.actual_size > self.requested_size:
            raise ValueError("review cohort 超过 requested_size")
        identities = [item.candidate_id for item in self.entries]
        if len(identities) != len(set(identities)):
            raise ValueError("review cohort candidate_id 不能重复")
        if tuple(item.review_rank for item in self.entries) != tuple(
            range(1, len(self.entries) + 1)
        ):
            raise ValueError("review cohort rank 必须连续且从 1 开始")
        ordered = tuple(
            sorted(self.entries, key=lambda item: (-item.score_deep, item.candidate_id))
        )
        if ordered != self.entries:
            raise ValueError("review cohort 未遵循冻结排序")
        return self


class PredictionRepresentative(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scientific_mode: Literal["de-novo", "target-conditioned"]
    seed: Literal[101, 202, 303, 404, 505]
    sample_index: int = Field(ge=0)
    ranking_score: float
    is_seed_representative: bool
    backend_identity: str = Field(min_length=1)
    model_identity: str = Field(min_length=1)
    release_identity: dict[str, str]
    template_mode: Literal["disabled", "precomputed"]
    target_condition_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    predicted_structure: ArtifactRef


class Stage07PredictionComparison(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(pattern=ID_PATTERN)
    pair_id: str = Field(pattern=ID_PATTERN)
    pair_kind: Literal["best-ranked", "matched-seed-representative"]
    de_novo: PredictionRepresentative
    target_conditioned: PredictionRepresentative
    matched_seed: bool
    target_aligned_binder_rmsd_angstrom: float = Field(ge=0)
    binder_internal_rmsd_angstrom: float = Field(ge=0)
    target_rmsd_angstrom: float = Field(ge=0)
    hotspot_contact_recovery: float = Field(ge=0, le=1)
    hotspot_contact_jaccard: float = Field(ge=0, le=1)
    binder_centroid_displacement_angstrom: float = Field(ge=0)
    selection_authority: Literal["descriptive-only"] = "descriptive-only"

    @model_validator(mode="after")
    def validate_pair(self) -> Self:
        if self.de_novo.scientific_mode != "de-novo":
            raise ValueError("comparison 左侧必须为 de-novo")
        if self.target_conditioned.scientific_mode != "target-conditioned":
            raise ValueError("comparison 右侧必须为 target-conditioned")
        if self.matched_seed != (self.de_novo.seed == self.target_conditioned.seed):
            raise ValueError("matched_seed 与 sample seed 不一致")
        if self.pair_kind == "matched-seed-representative" and not self.matched_seed:
            raise ValueError("matched-seed pair 必须使用同一 seed")
        return self


class Stage07AdvisoryComparisonProfile(BaseModel):
    """Optional independent rules; never changes selection or promotion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    profile_id: str = Field(pattern=ID_PATTERN)
    maximum_target_aligned_binder_rmsd_angstrom: float = Field(gt=0)
    minimum_hotspot_contact_jaccard: float = Field(ge=0, le=1)


class Stage07AdvisoryComparisonVerdict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(pattern=ID_PATTERN)
    pair_id: str = Field(pattern=ID_PATTERN)
    rule_results: dict[str, bool]
    verdict: Literal["支持", "不支持"]
    selection_authority: Literal["advisory-only"] = "advisory-only"

    @model_validator(mode="after")
    def validate_verdict(self) -> Self:
        expected = "支持" if all(self.rule_results.values()) else "不支持"
        if not self.rule_results or self.verdict != expected:
            raise ValueError("advisory verdict 与 rule results 不一致")
        return self


class Stage07PredictionComparisonReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    review_cohort_sha256: str = Field(pattern=SHA256_PATTERN)
    default_pair_policy: Literal[
        "highest-ranking-score-then-seed-then-sample-index"
    ] = "highest-ranking-score-then-seed-then-sample-index"
    comparisons: tuple[Stage07PredictionComparison, ...] = ()
    advisory_profile: ArtifactRef | None = None
    verdict_authority: Literal["metrics-only", "advisory-only"] = "metrics-only"
    advisory_verdicts: tuple[Stage07AdvisoryComparisonVerdict, ...] = ()

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if (self.advisory_profile is None) != (self.verdict_authority == "metrics-only"):
            raise ValueError("advisory profile 与 verdict authority 不一致")
        if self.advisory_profile is None and self.advisory_verdicts:
            raise ValueError("没有 advisory profile 时不能存在 verdict records")
        best = [item.candidate_id for item in self.comparisons if item.pair_kind == "best-ranked"]
        if len(best) != len(set(best)):
            raise ValueError("每个候选只能有一个默认 best-ranked pair")
        return self


def build_stage07_review_cohort(
    *,
    deep_records: tuple[DeepFilterRecord, ...],
    candidates: Mapping[str, CandidateRecord],
    requested_size: int,
    profile_sha256: str,
    candidate_index_sha256: str,
    generated_at: datetime,
) -> Stage07ReviewCohortIndex:
    if requested_size > 400:
        raise ManifestStateError("review cohort 不能超过 seed-101 Top 400")
    selected = tuple(
        sorted(
            (item for item in deep_records if item.absolute_gate_pass),
            key=lambda item: (-item.score_deep, item.candidate_id),
        )[:requested_size]
    )
    if any(not item.selected_for_seed101 for item in selected):
        raise ManifestStateError("review cohort 必须完全属于 seed-101 Top 400")
    entries = tuple(
        Stage07ReviewCohortEntry(
            review_rank=index,
            candidate_id=record.candidate_id,
            strategy_id=candidates[record.candidate_id].strategy_id,
            score_deep=record.score_deep,
            source_refolded_structure=candidates[record.candidate_id].refolded_structure,
        )
        for index, record in enumerate(selected, start=1)
    )
    return Stage07ReviewCohortIndex(
        generated_at=generated_at,
        requested_size=requested_size,
        actual_size=len(entries),
        deep_filter_profile_sha256=profile_sha256,
        scale_candidate_index_sha256=candidate_index_sha256,
        entries=entries,
    )


def _best_prediction(items: list[RawFinalPrediction]) -> RawFinalPrediction:
    return sorted(items, key=lambda item: (-item.ranking_score, item.seed, item.sample_index))[0]


def _representative(item: RawFinalPrediction) -> PredictionRepresentative:
    return PredictionRepresentative(
        scientific_mode=item.scientific_mode,
        seed=item.seed,
        sample_index=item.sample_index,
        ranking_score=item.ranking_score,
        is_seed_representative=item.is_seed_representative,
        backend_identity=item.backend_identity,
        model_identity=item.model_identity,
        release_identity=item.release_identity,
        template_mode=item.template_mode,
        target_condition_sha256=item.target_condition_sha256,
        predicted_structure=item.predicted_structure,
    )


def build_stage07_prediction_comparison_report(
    *,
    root: Path,
    cohort: Stage07ReviewCohortIndex,
    cohort_sha256: str,
    de_novo_predictions: tuple[RawFinalPrediction, ...],
    target_conditioned_predictions: tuple[RawFinalPrediction, ...],
    generated_at: datetime,
    advisory_profile: Stage07AdvisoryComparisonProfile | None = None,
    advisory_profile_ref: ArtifactRef | None = None,
) -> Stage07PredictionComparisonReport:
    if (advisory_profile is None) != (advisory_profile_ref is None):
        raise ManifestStateError("advisory profile 与 frozen ArtifactRef 必须同时提供")
    cohort_ids = {item.candidate_id for item in cohort.entries}
    by_mode: dict[tuple[str, str], list[RawFinalPrediction]] = defaultdict(list)
    for prediction in (*de_novo_predictions, *target_conditioned_predictions):
        if prediction.candidate_id in cohort_ids:
            by_mode[(prediction.candidate_id, prediction.scientific_mode)].append(prediction)
    comparisons: list[Stage07PredictionComparison] = []
    for entry in cohort.entries:
        de_novo = by_mode[(entry.candidate_id, "de-novo")]
        conditioned = by_mode[(entry.candidate_id, "target-conditioned")]
        if not de_novo or not conditioned:
            raise ManifestStateError(
                f"review cohort 缺少双模式 prediction: {entry.candidate_id}"
            )
        if not any(item.seed == 101 for item in de_novo) or not any(
            item.seed == 101 for item in conditioned
        ):
            raise ManifestStateError(
                f"review cohort 缺少双模式 seed-101: {entry.candidate_id}"
            )
        pairs: list[
            tuple[
                Literal["best-ranked", "matched-seed-representative"],
                RawFinalPrediction,
                RawFinalPrediction,
            ]
        ] = [
            ("best-ranked", _best_prediction(de_novo), _best_prediction(conditioned))
        ]
        de_reps = {
            seed: _best_prediction(
                [item for item in de_novo if item.seed == seed and item.is_seed_representative]
            )
            for seed in sorted({item.seed for item in de_novo if item.is_seed_representative})
        }
        conditioned_reps = {
            seed: _best_prediction(
                [
                    item
                    for item in conditioned
                    if item.seed == seed and item.is_seed_representative
                ]
            )
            for seed in sorted(
                {item.seed for item in conditioned if item.is_seed_representative}
            )
        }
        for seed in sorted(set(de_reps) & set(conditioned_reps)):
            left = de_reps[seed]
            right = conditioned_reps[seed]
            if (left.seed, left.sample_index, right.seed, right.sample_index) == (
                pairs[0][1].seed,
                pairs[0][1].sample_index,
                pairs[0][2].seed,
                pairs[0][2].sample_index,
            ):
                continue
            pairs.append(("matched-seed-representative", left, right))
        for ordinal, (kind, left, right) in enumerate(pairs, start=1):
            geometry = compare_dual_mode_structures(
                reference_complex=left.predicted_structure.verify(root),
                comparison_complex=right.predicted_structure.verify(root),
            )
            left_contacts = set(left.contacted_hotspot_residue_ids)
            right_contacts = set(right.contacted_hotspot_residue_ids)
            union = left_contacts | right_contacts
            comparisons.append(
                Stage07PredictionComparison(
                    candidate_id=entry.candidate_id,
                    pair_id=f"{entry.candidate_id}-{kind}-{ordinal:02d}",
                    pair_kind=kind,
                    de_novo=_representative(left),
                    target_conditioned=_representative(right),
                    matched_seed=left.seed == right.seed,
                    target_aligned_binder_rmsd_angstrom=(
                        geometry.target_aligned_binder_rmsd_angstrom
                    ),
                    binder_internal_rmsd_angstrom=geometry.binder_internal_rmsd_angstrom,
                    target_rmsd_angstrom=geometry.target_rmsd_angstrom,
                    hotspot_contact_recovery=(
                        len(left_contacts & right_contacts) / len(left_contacts)
                        if left_contacts
                        else (1.0 if not right_contacts else 0.0)
                    ),
                    hotspot_contact_jaccard=(
                        len(left_contacts & right_contacts) / len(union) if union else 1.0
                    ),
                    binder_centroid_displacement_angstrom=(
                        geometry.binder_centroid_displacement_angstrom
                    ),
                )
            )
    verdicts = tuple(
        Stage07AdvisoryComparisonVerdict(
            candidate_id=item.candidate_id,
            pair_id=item.pair_id,
            rule_results={
                "target-aligned-binder-rmsd": (
                    item.target_aligned_binder_rmsd_angstrom
                    <= advisory_profile.maximum_target_aligned_binder_rmsd_angstrom
                ),
                "hotspot-contact-jaccard": (
                    item.hotspot_contact_jaccard
                    >= advisory_profile.minimum_hotspot_contact_jaccard
                ),
            },
            verdict=(
                "支持"
                if (
                    item.target_aligned_binder_rmsd_angstrom
                    <= advisory_profile.maximum_target_aligned_binder_rmsd_angstrom
                    and item.hotspot_contact_jaccard
                    >= advisory_profile.minimum_hotspot_contact_jaccard
                )
                else "不支持"
            ),
        )
        for item in comparisons
        if item.pair_kind == "best-ranked" and advisory_profile is not None
    )
    return Stage07PredictionComparisonReport(
        generated_at=generated_at,
        review_cohort_sha256=cohort_sha256,
        comparisons=tuple(comparisons),
        advisory_profile=advisory_profile_ref,
        verdict_authority=(
            "metrics-only" if advisory_profile is None else "advisory-only"
        ),
        advisory_verdicts=verdicts,
    )
