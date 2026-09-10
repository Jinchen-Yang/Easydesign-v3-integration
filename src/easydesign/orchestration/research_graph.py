"""Typed append-only scientific event graph and reconstructable project state."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from easydesign.core import (
    AssertionDomain,
    ClaimReceipt,
    ClaimStatus,
    ClaimType,
    ManifestStateError,
    dump_model,
    sha256_file,
)
from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN
from easydesign.safe_writes import append_pointer_revision


class ConfidenceCategory(StrEnum):
    UNASSESSED = "unassessed"
    UNSUPPORTED = "unsupported"
    WEAK = "weak"
    PLAUSIBLE = "plausible"
    SUPPORTED = "supported"
    STRONGLY_SUPPORTED = "strongly-supported"
    CONTRADICTED = "contradicted"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


class HypothesisStatus(StrEnum):
    """Discrete current state derived from immutable scientific events."""

    UNASSESSED = "unassessed"
    SUPPORTED = "supported"
    WEAKENED = "weakened"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


class _EventBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0", "1.1"] = "1.1"
    event_id: str = Field(pattern=ID_PATTERN)
    revision: int = Field(default=1, ge=1)
    predecessor_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    author_kind: Literal["deterministic-code", "agent-proposal", "human"]


class HypothesisEvent(_EventBase):
    event_type: Literal["hypothesis"] = "hypothesis"
    hypothesis_id: str = Field(pattern=ID_PATTERN)
    target_foundation_sha256: str = Field(pattern=SHA256_PATTERN)
    statement: str = Field(min_length=1)
    mechanism: str = Field(min_length=1)
    predictions: tuple[str, ...] = Field(min_length=1)
    falsifiers: tuple[str, ...] = Field(min_length=1)
    source_evidence_refs: tuple[str, ...] = ()
    status: ConfidenceCategory = ConfidenceCategory.UNASSESSED
    claim: ClaimReceipt

    @model_validator(mode="after")
    def validate_claim(self) -> Self:
        if self.claim.claim_type is not ClaimType.HYPOTHESIS:
            raise ValueError("HypothesisEvent 必须携带 hypothesis claim")
        if self.schema_version == "1.1" and self.status is not ConfidenceCategory.UNASSESSED:
            raise ValueError(
                "HypothesisEvent 1.1 必须以 unassessed 创建；当前状态只能由 Interpretation 派生"
            )
        return self


class ExperimentEvent(_EventBase):
    event_type: Literal["experiment"] = "experiment"
    experiment_id: str = Field(pattern=ID_PATTERN)
    hypothesis_ids: tuple[str, ...] = Field(min_length=1)
    strategy_revision_sha256: str = Field(pattern=SHA256_PATTERN)
    strategy_variant_ids: tuple[str, ...] = Field(min_length=1)
    changed_factors: tuple[str, ...] = Field(min_length=1)
    held_constant: tuple[str, ...] = Field(min_length=1)
    expected_observations: tuple[str, ...] = Field(min_length=1)
    protocol_identity: str = Field(min_length=1)
    plan_sha256: str = Field(pattern=SHA256_PATTERN)


class ObservationEvent(_EventBase):
    event_type: Literal["observation"] = "observation"
    observation_id: str = Field(pattern=ID_PATTERN)
    experiment_ids: tuple[str, ...] = ()
    run_id: str = Field(pattern=ID_PATTERN)
    run_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    backend_identity: str
    profile_identity: str
    denominator: int = Field(ge=0)
    passing_count: int = Field(ge=0)
    failure_or_missingness: tuple[str, ...] = ()
    claim: ClaimReceipt

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if self.passing_count > self.denominator:
            raise ValueError("observation passing_count 不能超过 denominator")
        if self.claim.claim_type is not ClaimType.OBSERVATION:
            raise ValueError("ObservationEvent 必须携带 observation claim")
        if self.claim.assertion_domain is not AssertionDomain.COMPUTATIONAL_METRIC:
            raise ValueError("deterministic pilot observation 只能声明真实 computational metric")
        return self


class InterpretationEvent(_EventBase):
    event_type: Literal["interpretation"] = "interpretation"
    interpretation_id: str = Field(pattern=ID_PATTERN)
    supports_hypothesis_ids: tuple[str, ...] = ()
    contradicts_hypothesis_ids: tuple[str, ...] = ()
    weakens_hypothesis_ids: tuple[str, ...] = ()
    rejects_hypothesis_ids: tuple[str, ...] = ()
    unresolved_hypothesis_ids: tuple[str, ...] = ()
    reasoning_summary: str = Field(min_length=1)
    evidence_event_ids: tuple[str, ...] = Field(min_length=1)
    alternative_explanations: tuple[str, ...] = Field(min_length=1)
    limitations: tuple[str, ...] = ()
    open_scientific_questions: tuple[str, ...] = ()
    suggested_next_step: str | None = Field(default=None, min_length=1)
    confidence: ConfidenceCategory
    approval_status: Literal["proposed", "human-approved"] = "proposed"
    claim: ClaimReceipt

    @model_validator(mode="after")
    def validate_interpretation(self) -> Self:
        if self.claim.claim_type is not ClaimType.INFERENCE:
            raise ValueError("InterpretationEvent 必须携带 inference claim")
        if self.author_kind == "agent-proposal" and self.approval_status != "proposed":
            raise ValueError("Agent interpretation 不得伪装 human-approved")
        groups = (
            self.supports_hypothesis_ids,
            self.contradicts_hypothesis_ids,
            self.weakens_hypothesis_ids,
            self.rejects_hypothesis_ids,
            self.unresolved_hypothesis_ids,
        )
        if any(len(group) != len(set(group)) for group in groups):
            raise ValueError("Interpretation hypothesis effect 不能包含重复 identity")
        flattened = [identifier for group in groups for identifier in group]
        if len(flattened) != len(set(flattened)):
            raise ValueError("同一 hypothesis 不能在一次 interpretation 中获得冲突状态")
        if self.schema_version == "1.1":
            if not flattened:
                raise ValueError("Interpretation 1.1 必须显式更新至少一个 hypothesis 状态")
            if not self.limitations:
                raise ValueError("Interpretation 1.1 必须记录 limitations")
            if self.suggested_next_step is None:
                raise ValueError("Interpretation 1.1 必须记录 suggested_next_step")
            if self.claim.statement != self.reasoning_summary:
                raise ValueError("Interpretation conclusion 必须与 inference claim 一致")
        return self


class DecisionEvent(_EventBase):
    event_type: Literal["decision"] = "decision"
    decision_id: str = Field(pattern=ID_PATTERN)
    action: Literal["continue", "revise", "stop", "promote", "test-next"]
    decision_record_sha256: str = Field(pattern=SHA256_PATTERN)
    approved_by: str = Field(min_length=1)
    resulting_refs: tuple[str, ...] = ()
    claim: ClaimReceipt

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        if self.author_kind != "human":
            raise ValueError("DecisionEvent 必须来自 human authority")
        if self.claim.claim_type is not ClaimType.HUMAN_DECISION:
            raise ValueError("DecisionEvent 必须携带 human_decision claim")
        if self.claim.status is not ClaimStatus.HUMAN_APPROVED:
            raise ValueError("DecisionEvent claim 必须是 human-approved")
        return self


ResearchEvent: TypeAlias = Annotated[
    HypothesisEvent | ExperimentEvent | ObservationEvent | InterpretationEvent | DecisionEvent,
    Field(discriminator="event_type"),
]
_EVENT_ADAPTER: TypeAdapter[ResearchEvent] = TypeAdapter(ResearchEvent)


class HypothesisState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hypothesis_id: str
    statement: str
    status: HypothesisStatus
    status_interpretation_id: str | None = None
    status_observation_ids: tuple[str, ...] = ()


class ObservationState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str
    run_id: str
    statement: str
    evidence_sha256: tuple[str, ...]


class InterpretationState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    interpretation_id: str
    conclusion: str
    observation_ids: tuple[str, ...]
    supports_hypothesis_ids: tuple[str, ...] = ()
    weakens_hypothesis_ids: tuple[str, ...] = ()
    rejects_hypothesis_ids: tuple[str, ...] = ()
    unresolved_hypothesis_ids: tuple[str, ...] = ()
    suggested_next_step: str | None = None


class ResearchStateSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0", "1.1"] = "1.1"
    status: Literal["not-yet-initialized", "active"]
    revision: int = Field(ge=0)
    active_hypotheses: tuple[HypothesisState, ...] = ()
    latest_observations: tuple[ObservationState, ...] = ()
    latest_interpretations: tuple[InterpretationState, ...] = ()
    open_scientific_questions: tuple[str, ...] = ()
    recommended_next_direction: str | None = None
    open_contradictions: tuple[str, ...] = ()
    pending_decisions: tuple[str, ...] = ()
    current_experiment_lineage: tuple[str, ...] = ()


def load_research_events(project_root: Path) -> tuple[ResearchEvent, ...]:
    root = project_root.resolve() / "research" / "events"
    if not root.is_dir():
        return ()
    events: list[ResearchEvent] = []
    previous_sha: str | None = None
    seen_ids: set[str] = set()
    for expected_revision, path in enumerate(sorted(root.glob("research-event-r*.json")), start=1):
        try:
            raw_json = path.read_text(encoding="utf-8")
            event = _EVENT_ADAPTER.validate_json(raw_json)
        except (OSError, ValueError) as error:
            raise ManifestStateError(f"Research Graph event 无法读取: {path}") from error
        if event.revision != expected_revision:
            raise ManifestStateError("Research Graph revision 不连续")
        if event.predecessor_sha256 != previous_sha:
            raise ManifestStateError("Research Graph predecessor SHA-256 drift")
        if event.event_id in seen_ids:
            raise ManifestStateError("Research Graph event_id 重复")
        seen_ids.add(event.event_id)
        events.append(event)
        previous_sha = _stored_event_sha256(raw_json)
    return tuple(events)


def _stored_event_sha256(raw_json: str) -> str:
    """Hash persisted JSON fields so schema defaults cannot rewrite historical identity."""

    try:
        payload = json.loads(raw_json)
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ManifestStateError("Research Graph event 无法规范化计算 SHA-256") from error
    return hashlib.sha256(canonical).hexdigest()


def research_state_summary(project_root: Path) -> ResearchStateSummary:
    events = load_research_events(project_root)
    if not events:
        return ResearchStateSummary(status="not-yet-initialized", revision=0)
    hypotheses: dict[str, HypothesisState] = {}
    observations: list[ObservationState] = []
    interpretations: list[InterpretationState] = []
    open_questions: list[str] = []
    recommended_next_direction: str | None = None
    experiments: list[str] = []
    for event in events:
        if isinstance(event, HypothesisEvent):
            hypotheses[event.hypothesis_id] = HypothesisState(
                hypothesis_id=event.hypothesis_id,
                statement=event.statement,
                status=_initial_hypothesis_status(event.status),
            )
        elif isinstance(event, ExperimentEvent):
            experiments.append(event.experiment_id)
        elif isinstance(event, ObservationEvent):
            observations.append(
                ObservationState(
                    observation_id=event.observation_id,
                    run_id=event.run_id,
                    statement=event.claim.statement,
                    evidence_sha256=tuple(
                        reference.sha256 for reference in event.claim.evidence_refs
                    ),
                )
            )
        elif isinstance(event, InterpretationEvent):
            rejected = tuple(
                dict.fromkeys((*event.contradicts_hypothesis_ids, *event.rejects_hypothesis_ids))
            )
            interpretations.append(
                InterpretationState(
                    interpretation_id=event.interpretation_id,
                    conclusion=event.reasoning_summary,
                    observation_ids=event.evidence_event_ids,
                    supports_hypothesis_ids=event.supports_hypothesis_ids,
                    weakens_hypothesis_ids=event.weakens_hypothesis_ids,
                    rejects_hypothesis_ids=rejected,
                    unresolved_hypothesis_ids=event.unresolved_hypothesis_ids,
                    suggested_next_step=event.suggested_next_step,
                )
            )
            _apply_hypothesis_status(
                hypotheses,
                event.supports_hypothesis_ids,
                HypothesisStatus.SUPPORTED,
                event,
            )
            _apply_hypothesis_status(
                hypotheses,
                event.weakens_hypothesis_ids,
                HypothesisStatus.WEAKENED,
                event,
            )
            _apply_hypothesis_status(
                hypotheses,
                rejected,
                HypothesisStatus.REJECTED,
                event,
            )
            _apply_hypothesis_status(
                hypotheses,
                event.unresolved_hypothesis_ids,
                HypothesisStatus.UNRESOLVED,
                event,
            )
            for question in event.open_scientific_questions:
                if question not in open_questions:
                    open_questions.append(question)
            if event.suggested_next_step is not None:
                recommended_next_direction = event.suggested_next_step
    return ResearchStateSummary(
        status="active",
        revision=len(events),
        active_hypotheses=tuple(hypotheses.values()),
        latest_observations=tuple(observations[-5:]),
        latest_interpretations=tuple(interpretations[-5:]),
        open_scientific_questions=tuple(open_questions[-10:]),
        recommended_next_direction=recommended_next_direction,
        open_contradictions=tuple(
            sorted(
                hypothesis_id
                for hypothesis_id, state in hypotheses.items()
                if state.status is HypothesisStatus.REJECTED
            )
        ),
        current_experiment_lineage=tuple(experiments[-5:]),
    )


def _initial_hypothesis_status(value: ConfidenceCategory) -> HypothesisStatus:
    if value in {ConfidenceCategory.SUPPORTED, ConfidenceCategory.STRONGLY_SUPPORTED}:
        return HypothesisStatus.SUPPORTED
    if value in {ConfidenceCategory.UNSUPPORTED, ConfidenceCategory.WEAK}:
        return HypothesisStatus.WEAKENED
    if value in {ConfidenceCategory.CONTRADICTED, ConfidenceCategory.REJECTED}:
        return HypothesisStatus.REJECTED
    if value is ConfidenceCategory.UNRESOLVED:
        return HypothesisStatus.UNRESOLVED
    return HypothesisStatus.UNASSESSED


def _apply_hypothesis_status(
    hypotheses: dict[str, HypothesisState],
    hypothesis_ids: tuple[str, ...],
    status: HypothesisStatus,
    interpretation: InterpretationEvent,
) -> None:
    for hypothesis_id in hypothesis_ids:
        current = hypotheses.get(hypothesis_id)
        if current is None:
            continue
        hypotheses[hypothesis_id] = current.model_copy(
            update={
                "status": status,
                "status_interpretation_id": interpretation.interpretation_id,
                "status_observation_ids": interpretation.evidence_event_ids,
            }
        )


def append_research_event(
    project_root: Path,
    event: ResearchEvent,
) -> tuple[ResearchEvent, Path]:
    """Append one immutable event after verifying evidence and chain identity."""

    root = project_root.resolve()
    events = load_research_events(root)
    if (
        isinstance(event, HypothesisEvent)
        and event.schema_version == "1.1"
        and event.status is not ConfidenceCategory.UNASSESSED
    ):
        raise ManifestStateError("HypothesisEvent 1.1 当前状态只能由 Interpretation 派生")
    if any(existing.event_id == event.event_id for existing in events):
        raise ManifestStateError(f"Research Graph event_id 已存在: {event.event_id}")
    if isinstance(event, HypothesisEvent) and any(
        isinstance(existing, HypothesisEvent) and existing.hypothesis_id == event.hypothesis_id
        for existing in events
    ):
        raise ManifestStateError(f"Research Graph hypothesis_id 已存在: {event.hypothesis_id}")
    previous_sha = None
    if events:
        previous_path = (
            root / "research" / "events" / f"research-event-r{events[-1].revision:06d}.json"
        )
        previous_sha = _stored_event_sha256(previous_path.read_text(encoding="utf-8"))
    event = event.model_copy(
        update={"revision": len(events) + 1, "predecessor_sha256": previous_sha}
    )
    if isinstance(event, ObservationEvent):
        known_experiments = {
            existing.experiment_id for existing in events if isinstance(existing, ExperimentEvent)
        }
        missing_experiments = set(event.experiment_ids) - known_experiments
        if missing_experiments:
            raise ManifestStateError(
                f"Observation 引用的 Experiment 不存在: {sorted(missing_experiments)}"
            )
        for reference in event.claim.evidence_refs:
            if reference.path is None:
                raise ManifestStateError("Observation evidence 必须有可定位 path")
            path = Path(reference.path).expanduser().resolve(strict=True)
            if sha256_file(path) != reference.sha256:
                raise ManifestStateError("Observation evidence checksum drift")
    elif isinstance(event, ExperimentEvent):
        known_hypotheses = {
            existing.hypothesis_id for existing in events if isinstance(existing, HypothesisEvent)
        }
        missing_hypotheses = set(event.hypothesis_ids) - known_hypotheses
        if missing_hypotheses:
            raise ManifestStateError(
                f"Experiment 引用的 Hypothesis 不存在: {sorted(missing_hypotheses)}"
            )
    elif isinstance(event, InterpretationEvent):
        observations_by_id = {
            existing.event_id: existing
            for existing in events
            if isinstance(existing, ObservationEvent)
        }
        missing_observations = set(event.evidence_event_ids) - set(observations_by_id)
        if missing_observations:
            raise ManifestStateError(
                f"Interpretation 引用的 Observation 不存在: {sorted(missing_observations)}"
            )
        known_hypotheses = {
            existing.hypothesis_id for existing in events if isinstance(existing, HypothesisEvent)
        }
        affected_hypotheses = {
            *event.supports_hypothesis_ids,
            *event.contradicts_hypothesis_ids,
            *event.weakens_hypothesis_ids,
            *event.rejects_hypothesis_ids,
            *event.unresolved_hypothesis_ids,
        }
        missing_hypotheses = affected_hypotheses - known_hypotheses
        if missing_hypotheses:
            raise ManifestStateError(
                f"Interpretation 引用的 Hypothesis 不存在: {sorted(missing_hypotheses)}"
            )
        if event.schema_version == "1.1":
            claim_evidence_ids = {reference.evidence_id for reference in event.claim.evidence_refs}
            if claim_evidence_ids != set(event.evidence_event_ids):
                raise ManifestStateError(
                    "Interpretation inference claim 必须精确引用 observation events"
                )
            for reference in event.claim.evidence_refs:
                if reference.path is None:
                    raise ManifestStateError(
                        "Interpretation observation evidence 必须有可定位 path"
                    )
                evidence_path = Path(reference.path).expanduser().resolve(strict=True)
                if sha256_file(evidence_path) != reference.sha256:
                    raise ManifestStateError("Interpretation observation checksum drift")
    path = root / "research" / "events" / f"research-event-r{event.revision:06d}.json"
    dump_model(event, path)
    summary = research_state_summary(root)
    snapshot = root / "research" / "snapshots" / f"research-state-r{event.revision:06d}.json"
    dump_model(summary, snapshot)
    append_pointer_revision(
        root / "RESEARCH_CURRENT",
        snapshot.relative_to(root).as_posix(),
    )
    return event, path


def find_research_event(project_root: Path, event_id: str) -> tuple[ResearchEvent, Path] | None:
    events = load_research_events(project_root)
    for event in events:
        if event.event_id == event_id:
            path = (
                project_root.resolve()
                / "research"
                / "events"
                / f"research-event-r{event.revision:06d}.json"
            )
            return event, path
    return None


__all__ = [
    "ConfidenceCategory",
    "DecisionEvent",
    "ExperimentEvent",
    "HypothesisEvent",
    "HypothesisStatus",
    "HypothesisState",
    "InterpretationEvent",
    "InterpretationState",
    "ObservationEvent",
    "ResearchEvent",
    "ResearchStateSummary",
    "append_research_event",
    "find_research_event",
    "load_research_events",
    "research_state_summary",
]
