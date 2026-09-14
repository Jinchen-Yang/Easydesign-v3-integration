"""Current Gate 3 scientific intent and bounded execution plans, without authority."""

from __future__ import annotations

import json
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core import ArtifactRef, canonical_model_sha256
from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN
from easydesign.orchestration.config import LocalMultiGpuExecutorConfig, PredictionBackend
from easydesign.orchestration.research import ResearchStrategy
from easydesign.stages.s03_boltzgen_configuration.models import StrategyRecord

from .contracts import AgentBoundaryError


class PlanContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class PilotArmIntent(PlanContract):
    """A scientific arm can expand into several scaffold-specific strategies."""

    arm_id: str = Field(pattern=ID_PATTERN)
    strategy_ids: tuple[str, ...] = Field(min_length=1)
    hypothesis: str | None
    rationale: str
    changed_factors: tuple[str, ...]
    held_constant: tuple[str, ...]
    expected_result: str
    failure_interpretation: str | None
    role: str | None
    # These are compiled, runtime-verified values, including expert-native YAML.
    compiled_settings: tuple[dict[str, Any], ...] = Field(min_length=1)
    target_context: dict[str, Any]
    evidence_refs: tuple[str, ...]


class BoundPilotPlan(PlanContract):
    """The exact execution scope shown at Gate 3, never model-authored permission."""

    project_id: str = Field(pattern=ID_PATTERN)
    project_binding: str = Field(pattern=SHA256_PATTERN)
    target_binding: str = Field(pattern=SHA256_PATTERN)
    hotspot_sha256: str = Field(pattern=SHA256_PATTERN)
    design_proposal_id: str = Field(pattern=SHA256_PATTERN)
    design_snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    strategy_sha256: str = Field(pattern=SHA256_PATTERN)
    compiled_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    prediction_backend: PredictionBackend
    runtime_policy_sha256: str = Field(pattern=SHA256_PATTERN)
    executor: LocalMultiGpuExecutorConfig = LocalMultiGpuExecutorConfig()
    mode: Literal["formal-pilot", "validation-micro"]
    production_allocations: dict[str, int]
    execution_allocations: dict[str, int]
    prediction_selection: Literal["all-execution-candidates"] = "all-execution-candidates"
    additional_generation: Literal[0] = 0
    arms: tuple[PilotArmIntent, ...] = Field(min_length=1)
    parent_gate4_card_id: str | None = Field(default=None, pattern=SHA256_PATTERN)
    validation_only: bool

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        all_ids = [s for arm in self.arms for s in arm.strategy_ids]
        if len(all_ids) != len(set(all_ids)) or set(all_ids) != set(self.production_allocations):
            raise ValueError("Pilot arm lineage must cover each compiled strategy exactly once")
        if not self.execution_allocations or set(self.execution_allocations) - set(all_ids):
            raise ValueError("Pilot execution selects an unknown or empty strategy set")
        if any(n < 1 for n in self.production_allocations.values()) or any(
            n < 1 or n > self.production_allocations[s]
            for s, n in self.execution_allocations.items()
        ):
            raise ValueError("Pilot allocation must be positive and within the approved intent")
        if self.mode == "formal-pilot":
            if self.validation_only or self.execution_allocations != self.production_allocations:
                raise ValueError("Formal Pilot must execute the exact approved plan")
        elif not self.validation_only or sum(self.execution_allocations.values()) > 6:
            raise ValueError("validation-micro is validation-only and bounded to six candidates")
        return self


class ApprovedGate3Context(PlanContract):
    """Live product input; historical accepted development fixtures remain separate."""

    context_kind: Literal["current-approved-gate3"] = "current-approved-gate3"
    project_id: str = Field(pattern=ID_PATTERN)
    gate3_card_id: str = Field(pattern=SHA256_PATTERN)
    gate3_outcome_sha256: str = Field(pattern=SHA256_PATTERN)
    target_identity: str
    target_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    site_intent_sha256: str = Field(pattern=SHA256_PATTERN)
    strategy_sha256: str = Field(pattern=SHA256_PATTERN)
    compiled_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    execution_plan_sha256: str = Field(pattern=SHA256_PATTERN)
    planned_candidates: int = Field(ge=1)
    plan: BoundPilotPlan
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        if self.execution_plan_sha256 != canonical_model_sha256(self.plan):
            raise ValueError("Approved Pilot context references a different plan")
        if self.project_id != self.plan.project_id or (
            self.strategy_sha256 != self.plan.strategy_sha256
            or self.compiled_manifest_sha256 != self.plan.compiled_manifest_sha256
            or self.planned_candidates != sum(self.plan.production_allocations.values())
        ):
            raise ValueError("Approved Pilot context differs from the reviewed Design")
        return self


class ValidatedDesignContext(ApprovedGate3Context):
    """Engineering input only: the Design has no fabricated Scientist approval."""

    context_kind: Literal["validation-design"] = "validation-design"  # type: ignore[assignment]
    gate3_card_id: None = None  # type: ignore[assignment]
    gate3_outcome_sha256: None = None  # type: ignore[assignment]

    @model_validator(mode="after")
    def validation_scope(self) -> Self:
        if not self.plan.validation_only:
            raise ValueError("Validation context cannot authorize formal Pilot")
        return self


def project_arm_intents(
    strategy: ResearchStrategy,
    records: tuple[StrategyRecord, ...],
    *,
    target_context: dict[str, Any],
) -> tuple[PilotArmIntent, ...]:
    """Use compiler region IDs; never infer arm membership from metric names."""
    variants = {v.id: v for v in strategy.variants}
    if {r.region_id for r in records} != set(variants):
        raise AgentBoundaryError("Compiled strategies do not cover the exact Design arms")
    arms = []
    for arm_id, variant in variants.items():
        group = tuple(r for r in records if r.region_id == arm_id)
        arms.append(
            PilotArmIntent(
                arm_id=arm_id,
                strategy_ids=tuple(r.strategy_id for r in group),
                hypothesis=variant.hypothesis_statement,
                rationale=variant.rationale,
                changed_factors=variant.changed_factors,
                held_constant=variant.held_constant,
                expected_result=variant.expected_result,
                failure_interpretation=variant.failure_interpretation,
                role=variant.role,
                compiled_settings=tuple(
                    {
                        **r.model_dump(mode="json"),
                        "cdr_overrides": [c.model_dump(mode="json") for c in variant.cdr_overrides],
                        "target_crop": variant.target_crop.model_dump(mode="json")
                        if variant.target_crop
                        else None,
                    }
                    for r in group
                ),
                target_context=target_context,
                evidence_refs=variant.evidence_refs,
            )
        )
    return tuple(arms)


def compiled_records(bridge: Any, proposal: dict[str, Any]) -> tuple[StrategyRecord, ...]:
    """Only read compiler outputs explicitly declared by the verified receipt."""
    records = []
    for raw in bridge.document(proposal["compiled_ref"]):
        ref = ArtifactRef.model_validate(raw)
        if ref.relative_path.endswith("/strategy-manifest.json"):
            payload = json.loads(ref.verify(bridge.project).read_text())
            if payload.get("compilation_status") != "compiled":
                raise AgentBoundaryError("Strategy manifest is not a compiled product")
            metadata = {
                "schema_version",
                "compilation_status",
                "strategy_profile",
                "scaffold_registry",
            }
            records.append(
                StrategyRecord.model_validate(
                    {key: value for key, value in payload.items() if key not in metadata}
                )
            )
    if not records or len({r.strategy_id for r in records}) != len(records):
        raise AgentBoundaryError("Design has no unique compiled strategy population")
    return tuple(sorted(records, key=lambda r: r.strategy_id))
