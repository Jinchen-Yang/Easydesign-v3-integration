"""Agent-authored interpretations grounded in immutable Research Graph observations."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Self

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from easydesign.core import (
    ClaimEvidenceRef,
    ClaimReceipt,
    ClaimStatus,
    ClaimType,
    ConfigurationError,
    EvidenceKind,
    sha256_file,
)
from easydesign.core.artifacts import ID_PATTERN

from .research_graph import (
    ConfidenceCategory,
    HypothesisEvent,
    InterpretationEvent,
    ObservationEvent,
    ResearchEvent,
    append_research_event,
    load_research_events,
)

ResearchId = Annotated[str, Field(pattern=ID_PATTERN)]


class InterpretationSubmission(BaseModel):
    """Typed Agent proposal that explains observations without rewriting facts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    interpretation_id: ResearchId
    observation_refs: tuple[ResearchId, ...] = Field(min_length=1)
    supports: tuple[ResearchId, ...] = ()
    weakens: tuple[ResearchId, ...] = ()
    rejects: tuple[ResearchId, ...] = ()
    unresolved: tuple[ResearchId, ...] = ()
    conclusion: str = Field(min_length=1, max_length=8192)
    alternative_explanations: tuple[str, ...] = Field(min_length=1)
    limitations: tuple[str, ...] = Field(min_length=1)
    open_scientific_questions: tuple[str, ...] = ()
    suggested_next_step: str = Field(min_length=1, max_length=4096)
    confidence: ConfidenceCategory = ConfidenceCategory.UNRESOLVED

    @model_validator(mode="after")
    def validate_effects(self) -> Self:
        groups = (self.supports, self.weakens, self.rejects, self.unresolved)
        if any(len(group) != len(set(group)) for group in groups):
            raise ValueError("interpretation hypothesis effect 不能包含重复 identity")
        effects = [identifier for group in groups for identifier in group]
        if not effects:
            raise ValueError("interpretation 必须显式更新至少一个 hypothesis 状态")
        if len(effects) != len(set(effects)):
            raise ValueError("同一 hypothesis 不能在一次 interpretation 中获得冲突状态")
        if len(self.observation_refs) != len(set(self.observation_refs)):
            raise ValueError("observation_refs 不能重复")
        return self


def load_interpretation_submission(
    project_root: Path,
    input_path: Path,
) -> tuple[InterpretationSubmission, Path]:
    """Load a project-local YAML proposal without mutating the source draft."""

    root = project_root.resolve()
    selected = input_path if input_path.is_absolute() else root / input_path
    try:
        selected = selected.resolve(strict=True)
    except OSError as error:
        raise ConfigurationError(f"interpretation input 无法读取: {selected}") from error
    if not selected.is_relative_to(root) or not selected.is_file():
        raise ConfigurationError("interpretation input 必须位于当前 project 内")
    try:
        payload = yaml.safe_load(selected.read_text(encoding="utf-8"))
        submission = InterpretationSubmission.model_validate(payload)
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ConfigurationError(f"interpretation input 无法解析或校验: {selected}") from error
    return submission, selected


def record_interpretation(
    project_root: Path,
    *,
    source_run_id: str,
    submission: InterpretationSubmission,
) -> tuple[InterpretationEvent, Path]:
    """Append one evidence-grounded Agent interpretation and preserve all history."""

    root = project_root.resolve()
    events = load_research_events(root)
    events_by_id = {event.event_id: event for event in events}
    observations: list[ObservationEvent] = []
    for event_id in submission.observation_refs:
        event = events_by_id.get(event_id)
        if not isinstance(event, ObservationEvent):
            raise ConfigurationError(
                f"interpretation observation_ref 不是已存在 ObservationEvent: {event_id}"
            )
        observations.append(event)
    if not any(observation.run_id == source_run_id for observation in observations):
        raise ConfigurationError("interpretation 必须至少引用一个属于 --run 的 ObservationEvent")

    known_hypotheses = {
        event.hypothesis_id for event in events if isinstance(event, HypothesisEvent)
    }
    affected = {
        *submission.supports,
        *submission.weakens,
        *submission.rejects,
        *submission.unresolved,
    }
    missing_hypotheses = affected - known_hypotheses
    if missing_hypotheses:
        raise ConfigurationError(
            f"interpretation 引用的 hypothesis 不存在: {sorted(missing_hypotheses)}"
        )

    evidence_refs: list[ClaimEvidenceRef] = []
    for observation in observations:
        event_path = _event_path(root, observation)
        evidence_refs.append(
            ClaimEvidenceRef(
                evidence_id=observation.event_id,
                sha256=sha256_file(event_path),
                kind=EvidenceKind.COMPUTATIONAL,
                path=str(event_path),
            )
        )
    source_run_ids = tuple(dict.fromkeys(observation.run_id for observation in observations))
    claim = ClaimReceipt(
        claim_id=f"claim-{submission.interpretation_id}",
        claim_type=ClaimType.INFERENCE,
        statement=submission.conclusion,
        scope=f"pilot-interpretation:{source_run_id}",
        evidence_refs=tuple(evidence_refs),
        source_run_ids=source_run_ids,
        analysis_identity="agent-interpretation-v1",
        limitations=submission.limitations,
        alternative_explanations=submission.alternative_explanations,
        status=ClaimStatus.PROPOSED,
    )
    event = InterpretationEvent(
        event_id=submission.interpretation_id,
        author_kind="agent-proposal",
        interpretation_id=submission.interpretation_id,
        supports_hypothesis_ids=submission.supports,
        weakens_hypothesis_ids=submission.weakens,
        rejects_hypothesis_ids=submission.rejects,
        unresolved_hypothesis_ids=submission.unresolved,
        reasoning_summary=submission.conclusion,
        evidence_event_ids=submission.observation_refs,
        alternative_explanations=submission.alternative_explanations,
        limitations=submission.limitations,
        open_scientific_questions=submission.open_scientific_questions,
        suggested_next_step=submission.suggested_next_step,
        confidence=submission.confidence,
        claim=claim,
    )
    recorded, path = append_research_event(root, event)
    assert isinstance(recorded, InterpretationEvent)
    return recorded, path


def latest_observation_for_run(
    project_root: Path,
    run_id: str,
) -> ObservationEvent | None:
    return next(
        (
            event
            for event in reversed(load_research_events(project_root))
            if isinstance(event, ObservationEvent) and event.run_id == run_id
        ),
        None,
    )


def latest_interpretation_for_observation(
    project_root: Path,
    observation_event_id: str,
) -> InterpretationEvent | None:
    return next(
        (
            event
            for event in reversed(load_research_events(project_root))
            if isinstance(event, InterpretationEvent)
            and observation_event_id in event.evidence_event_ids
        ),
        None,
    )


def follow_up_research_event_ids(
    project_root: Path,
    *,
    source_run_id: str,
) -> tuple[str, ...]:
    """Return the minimal H→O→I lineage required by a new Strategy 1.3 draft."""

    events = load_research_events(project_root)
    observation = next(
        (
            event
            for event in reversed(events)
            if isinstance(event, ObservationEvent) and event.run_id == source_run_id
        ),
        None,
    )
    if observation is None:
        raise ConfigurationError("--from-pilot 尚无 ObservationEvent；请先运行 pilot review")
    interpretation = next(
        (
            event
            for event in reversed(events)
            if isinstance(event, InterpretationEvent)
            and observation.event_id in event.evidence_event_ids
        ),
        None,
    )
    if interpretation is None:
        raise ConfigurationError(
            "--from-pilot 尚无 evidence-grounded InterpretationEvent；请先运行 pilot interpret"
        )
    affected_hypotheses = {
        *interpretation.supports_hypothesis_ids,
        *interpretation.contradicts_hypothesis_ids,
        *interpretation.weakens_hypothesis_ids,
        *interpretation.rejects_hypothesis_ids,
        *interpretation.unresolved_hypothesis_ids,
    }
    hypothesis_event_ids = tuple(
        event.event_id
        for event in events
        if isinstance(event, HypothesisEvent) and event.hypothesis_id in affected_hypotheses
    )
    return tuple(
        dict.fromkeys(
            (
                *hypothesis_event_ids,
                *interpretation.evidence_event_ids,
                interpretation.event_id,
            )
        )
    )


def validate_follow_up_research_refs(
    project_root: Path,
    event_ids: tuple[str, ...],
) -> tuple[ResearchEvent, ...]:
    """Validate that Strategy 1.3 references a connected H→O→I lineage."""

    if len(event_ids) != len(set(event_ids)):
        raise ConfigurationError("prior_research_event_ids 不能重复")
    events_by_id = {event.event_id: event for event in load_research_events(project_root)}
    missing = [event_id for event_id in event_ids if event_id not in events_by_id]
    if missing:
        raise ConfigurationError(f"follow-up 引用的 research event 不存在: {missing}")
    selected = tuple(events_by_id[event_id] for event_id in event_ids)
    hypotheses = {event.hypothesis_id for event in selected if isinstance(event, HypothesisEvent)}
    observations = {event.event_id for event in selected if isinstance(event, ObservationEvent)}
    interpretations = [event for event in selected if isinstance(event, InterpretationEvent)]
    if not hypotheses or not observations or not interpretations:
        raise ConfigurationError(
            "Strategy 1.3 follow-up 必须引用 Hypothesis、Observation 与 Interpretation"
        )
    connected = any(
        observations.intersection(interpretation.evidence_event_ids)
        and hypotheses.intersection(
            {
                *interpretation.supports_hypothesis_ids,
                *interpretation.contradicts_hypothesis_ids,
                *interpretation.weakens_hypothesis_ids,
                *interpretation.rejects_hypothesis_ids,
                *interpretation.unresolved_hypothesis_ids,
            }
        )
        for interpretation in interpretations
    )
    if not connected:
        raise ConfigurationError(
            "Strategy 1.3 prior refs 未形成可追溯 Hypothesis→Observation→Interpretation"
        )
    return selected


def _event_path(project_root: Path, event: ResearchEvent) -> Path:
    return (
        project_root.resolve()
        / "research"
        / "events"
        / f"research-event-r{event.revision:06d}.json"
    )


__all__ = [
    "InterpretationSubmission",
    "follow_up_research_event_ids",
    "latest_interpretation_for_observation",
    "latest_observation_for_run",
    "load_interpretation_submission",
    "record_interpretation",
    "validate_follow_up_research_refs",
]
