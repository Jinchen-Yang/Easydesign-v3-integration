"""Native BoltzGen evidence, separate from historical EasyDesign screening policy."""

from __future__ import annotations

import math
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from easydesign.core import ArtifactRef, canonical_model_sha256
from easydesign.core.artifacts import SHA256_PATTERN

from .phase34_plan import PlanContract


class NativeFilterRule(PlanContract):
    feature: str
    lower_is_better: bool
    threshold: float


class NativeFilterProfile(PlanContract):
    backend: Literal["boltzgen-0.3.2"] = "boltzgen-0.3.2"
    source_commit: Literal["a3149cf18eeb58648d1abbb27539bd73f746cdda"] = (
        "a3149cf18eeb58648d1abbb27539bd73f746cdda"
    )
    filter_source_sha256: Literal[
        "b8aecfbb54a187125a9668239e813cf5e1454a6934b94292fc0fa82c7a29fdb1"
    ] = "b8aecfbb54a187125a9668239e813cf5e1454a6934b94292fc0fa82c7a29fdb1"
    configuration: dict[str, Any]
    configuration_ref: ArtifactRef
    rules: tuple[NativeFilterRule, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_rules(self) -> Self:
        if len({r.feature for r in self.rules}) != len(self.rules):
            raise ValueError("Native filter features must be unique")
        return self


class NativeFilterDecision(PlanContract):
    feature: str
    threshold: float
    lower_is_better: bool
    value: float | bool | None
    passed: bool | None
    missing_reason: str | None = None


class NativeCandidateEvidence(PlanContract):
    candidate_id: str
    profile_sha256: str = Field(pattern=SHA256_PATTERN)
    native_pass: bool | None
    decisions: tuple[NativeFilterDecision, ...]
    # Original column names are retained, including names containing '<' and other symbols.
    metrics: dict[str, bool | int | float | str | None]
    additional_metrics: dict[str, bool | int | float | str | None] = Field(default_factory=dict)
    metric_sources: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent_partition(self) -> Self:
        for value in (*self.metrics.values(), *self.additional_metrics.values()):
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Non-finite measurements must be represented as missing")
        decisions = [d.passed for d in self.decisions]
        expected = None if not decisions or None in decisions else all(decisions)
        if self.native_pass != expected:
            raise ValueError("Native partition contradicts its per-rule observations")
        return self


class NativePilotEvidence(PlanContract):
    version: Literal["native-boltz2-pilot-v1"] = "native-boltz2-pilot-v1"
    profiles: dict[str, NativeFilterProfile]
    candidates: tuple[NativeCandidateEvidence, ...]
    source_refs: tuple[ArtifactRef, ...] = ()
    metric_reference: Literal["boltzgen-pilot-metrics-v1"] = "boltzgen-pilot-metrics-v1"

    @model_validator(mode="after")
    def verify_profiles(self) -> Self:
        if any(key != canonical_model_sha256(p) for key, p in self.profiles.items()):
            raise ValueError("Native profile identity changed")
        if len({c.candidate_id for c in self.candidates}) != len(self.candidates):
            raise ValueError("Duplicate native candidate evidence")
        for candidate in self.candidates:
            profile = self.profiles.get(candidate.profile_sha256)
            if profile is None or [
                (d.feature, d.threshold, d.lower_is_better) for d in candidate.decisions
            ] != [(r.feature, r.threshold, r.lower_is_better) for r in profile.rules]:
                raise ValueError("Native decisions differ from the active run profile")
        return self
