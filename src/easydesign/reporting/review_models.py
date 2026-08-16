"""Versioned contracts for immutable Stage 05/07 review dashboards."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from easydesign.core import ArtifactRef, ErrorInfo, ExecutionStatus
from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN

REVIEW_DASHBOARD_GENERATOR_VERSION = "0.1"
THREEDMOL_VERSION = "2.5.5"
THREEDMOL_SHA256 = "f7cc78921ae72e7623e89cdd111434f58c2efddd2ffda1cd212644b406fb8016"
THREEDMOL_LICENSE = "BSD-3-Clause"
THREEDMOL_LICENSE_SHA256 = (
    "4c6eaaed856f3f28a3b1a98e74f4a8a71618de7d51ea4155c29f6f793bcef861"
)
THREEDMOL_NPM_INTEGRITY = (
    "sha512-kqNHouGqq3YfW58174tdERvm0XYTmP0tavQKOqIw1ouc2OJ7epkXEFrtEkVXV0cl"
    "BZT2Ze2xHRC/qxX0u0qCdw=="
)


class ReviewDashboardPresentationOverride(BaseModel):
    """Presentation-only customisation; scientific fields are intentionally absent."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=160)
    labels_zh: dict[str, str] = Field(default_factory=dict)
    metric_order: tuple[str, ...] = ()
    pinned_metric_cards: tuple[str, ...] = ()
    default_x_metric: str | None = Field(default=None, pattern=ID_PATTERN)
    default_y_metric: str | None = Field(default=None, pattern=ID_PATTERN)

    @model_validator(mode="after")
    def validate_keys(self) -> Self:
        for key, value in self.labels_zh.items():
            if not value.strip():
                raise ValueError(f"presentation label 不能为空: {key}")
        for values in (self.metric_order, self.pinned_metric_cards):
            if len(values) != len(set(values)):
                raise ValueError("presentation metric key 不能重复")
        return self


class ReviewStructureRoute(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    token: str = Field(pattern=r"^structure-[a-f0-9]{24}$")
    artifact: ArtifactRef
    mime_type: Literal[
        "chemical/x-mmcif",
        "chemical/x-pdb",
    ]


class ReviewStructureEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str = Field(min_length=1, max_length=128)
    route_token: str = Field(pattern=r"^structure-[a-f0-9]{24}$")
    scientific_mode: Literal[
        "source",
        "refolded",
        "de-novo",
        "target-conditioned",
    ]
    structure_sha256: str = Field(pattern=SHA256_PATTERN)
    backend_identity: str | None = None
    release_identity: dict[str, str] = Field(default_factory=dict)
    template_mode: Literal["disabled", "precomputed"] | None = None
    seed: int | None = Field(default=None, ge=0)
    sample_index: int | None = Field(default=None, ge=0)
    ranking_score: float | None = None


class ReviewMetricValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1, max_length=128)
    value: str | int | float | bool | None
    unit: str | None = Field(default=None, max_length=32)
    source_artifact_sha256: str = Field(pattern=SHA256_PATTERN)


class ReviewCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(pattern=ID_PATTERN)
    strategy_id: str = Field(pattern=ID_PATTERN)
    cohort: Literal["pilot", "expansion", "review"]
    current_display_order: int = Field(ge=1)
    authoritative_rank: int | None = Field(default=None, ge=1)
    metrics: tuple[ReviewMetricValue, ...]
    scientific_record: dict[str, JsonValue]
    structures: tuple[ReviewStructureEvidence, ...] = ()
    warnings: tuple[str, ...] = ()


class ReviewStrategy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1, max_length=160)
    promotion_rank: int | None = Field(default=None, ge=1)
    score: float | None = None
    denominator: int | None = Field(default=None, ge=0)
    scientific_record: dict[str, JsonValue]


class ReviewDashboardReport(BaseModel):
    """Browser payload. It contains display material, never new scientific decisions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    report_kind: Literal["stage05", "stage07"]
    project_id: str = Field(pattern=ID_PATTERN)
    run_id: str = Field(pattern=ID_PATTERN)
    stage_id: Literal[
        "05-pilot-filtering",
        "07-final-filtering-and-selection",
    ]
    generated_at: datetime
    title: str = Field(min_length=1, max_length=160)
    tabs: tuple[str, ...] = Field(min_length=2, max_length=3)
    source_run_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    source_stage_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    source_profile_id: str = Field(min_length=1)
    source_profile_sha256: str = Field(pattern=SHA256_PATTERN)
    selection_authority: Literal["upstream-artifacts-only"] = (
        "upstream-artifacts-only"
    )
    requested_review_cohort_size: int | None = Field(default=None, ge=1)
    actual_review_cohort_size: int | None = Field(default=None, ge=0)
    candidates: tuple[ReviewCandidate, ...]
    strategies: tuple[ReviewStrategy, ...]
    comparisons: tuple[dict[str, JsonValue], ...] = ()
    comparison_advisory_verdicts: tuple[dict[str, JsonValue], ...] = ()
    presentation: ReviewDashboardPresentationOverride = (
        ReviewDashboardPresentationOverride()
    )
    structure_routes: tuple[ReviewStructureRoute, ...] = ()
    source_artifacts: tuple[ArtifactRef, ...]
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if self.report_kind == "stage07":
            if (
                self.requested_review_cohort_size is None
                or self.actual_review_cohort_size is None
            ):
                raise ValueError("Stage 07 dashboard 必须声明真实 N/requested cohort")
            if self.actual_review_cohort_size > self.requested_review_cohort_size:
                raise ValueError("Stage 07 actual cohort 不能超过 requested")
        elif (
            self.requested_review_cohort_size is not None
            or self.actual_review_cohort_size is not None
        ):
            raise ValueError("Stage 05 dashboard 不声明 Stage 07 cohort")
        tokens = [item.token for item in self.structure_routes]
        if len(tokens) != len(set(tokens)):
            raise ValueError("structure route token 不能重复")
        available = set(tokens)
        used = {
            structure.route_token
            for candidate in self.candidates
            for structure in candidate.structures
        }
        if not used.issubset(available):
            raise ValueError("candidate structure 引用了未声明 route")
        return self


class ReviewDashboardManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    report_id: Literal[
        "stage05-review-dashboard",
        "stage07-review-dashboard",
    ]
    revision: int = Field(ge=1)
    status: ExecutionStatus
    created_at: datetime
    completed_at: datetime
    generator_version: Literal["0.1"] = "0.1"
    source_run_manifest_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    source_stage_manifest_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    source_identity_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    threedmol_version: Literal["2.5.5"] = "2.5.5"
    threedmol_sha256: Literal[
        "f7cc78921ae72e7623e89cdd111434f58c2efddd2ffda1cd212644b406fb8016"
    ] = "f7cc78921ae72e7623e89cdd111434f58c2efddd2ffda1cd212644b406fb8016"
    threedmol_license: Literal["BSD-3-Clause"] = "BSD-3-Clause"
    threedmol_license_sha256: Literal[
        "4c6eaaed856f3f28a3b1a98e74f4a8a71618de7d51ea4155c29f6f793bcef861"
    ] = "4c6eaaed856f3f28a3b1a98e74f4a8a71618de7d51ea4155c29f6f793bcef861"
    threedmol_npm_integrity: str = THREEDMOL_NPM_INTEGRITY
    output_artifacts: tuple[ArtifactRef, ...] = ()
    warnings: tuple[str, ...] = ()
    error: ErrorInfo | None = None

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        if self.status not in {ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED}:
            raise ValueError("dashboard manifest 必须为终态")
        if self.completed_at < self.created_at:
            raise ValueError("dashboard 完成时间不能早于开始时间")
        sources = (
            self.source_run_manifest_sha256,
            self.source_stage_manifest_sha256,
            self.source_identity_sha256,
        )
        if self.status is ExecutionStatus.SUCCEEDED:
            if any(value is None for value in sources):
                raise ValueError("成功 dashboard 必须有完整 source identity")
            if self.error is not None or not self.output_artifacts:
                raise ValueError("成功 dashboard 必须发布输出且不能带 error")
        elif self.error is None or self.output_artifacts:
            raise ValueError("失败 dashboard 必须只记录 error")
        return self


class ReviewDashboardOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ExecutionStatus
    report_root: Path
    manifest_path: Path
    entrypoint: Path | None = None
    error: ErrorInfo | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        succeeded = self.status is ExecutionStatus.SUCCEEDED
        if succeeded != (self.entrypoint is not None and self.error is None):
            raise ValueError("dashboard outcome 状态不一致")
        if not succeeded and (
            self.status is not ExecutionStatus.FAILED or self.error is None
        ):
            raise ValueError("dashboard outcome 必须为 succeeded/failed")
        return self


class ReviewDashboardExportManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    created_at: datetime
    source_report_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    report_kind: Literal["stage05", "stage07"]
    copied_structures: tuple[ArtifactRef, ...]
    output_artifacts: tuple[ArtifactRef, ...]
