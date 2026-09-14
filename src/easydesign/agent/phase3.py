"""Phase 3 projections over immutable Stage 04/05 outputs.

The legacy filter report is consumed as measurement evidence.  Its threshold
decisions remain visible but do not remove candidates or become v3 scientific
policy.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from typing import Literal

from easydesign.core import canonical_model_sha256
from easydesign.core.artifacts import SHA256_PATTERN
from easydesign.stages.s04_pilot_generation import CandidateIndex
from easydesign.stages.s05_pilot_filtering import (
    CandidateFilterRecord,
    PilotFilterReport,
    PilotFilterReportV1_6,
)

from .contracts import AgentBoundaryError, DecisionCard, ScientificStatus
from .phase34_contracts import (
    AcceptedGate3Fixture,
    ExecutionProjection,
    Gate4Recommendation,
    LegacyPolicyAnnotation,
    MetricObservation,
    PilotArmDenominator,
    PilotArmSummary,
    PilotCandidateLineage,
    PilotCandidateObservation,
    PilotDiagnosis,
    PilotDiagnosisHypothesis,
    PilotEvidenceDossier,
    PilotExecutionAuthority,
    PilotJudgeAssessment,
    PilotMeasurement,
)
from .session_store import identity

_GATE4_OPTIONS: tuple[tuple[str, str], ...] = (
    ("PROMOTE_TO_SCALE", "Promote the reviewed strategy set to a Scale campaign."),
    ("RUN_ANOTHER_PILOT", "Run another bounded, discriminating Pilot revision."),
    ("REVISE_DESIGN", "Return to Binder Strategy / Design Specification revision."),
    ("REVISE_SITE", "Return to Site / Mechanism revision while preserving Target authority."),
    ("STOP", "Stop the scientific campaign and preserve all evidence."),
)


def project_pilot_measurement(
    *,
    candidate_index: CandidateIndex,
    candidate_index_sha256: str,
    filter_report: PilotFilterReport | PilotFilterReportV1_6,
    filter_report_sha256: str,
    execution: ExecutionProjection,
    planned_by_strategy: dict[str, int] | None = None,
    operational_failures_by_strategy: dict[str, int] | None = None,
    generated_by_strategy: dict[str, int] | None = None,
    predicted_candidate_ids: frozenset[str] = frozenset(),
) -> PilotMeasurement:
    """Join published candidates to metrics and retain the complete valid population."""

    if (
        re.fullmatch(SHA256_PATTERN, candidate_index_sha256) is None
        or re.fullmatch(SHA256_PATTERN, filter_report_sha256) is None
    ):
        raise AgentBoundaryError("Pilot artifact identity must be an exact SHA-256")
    if filter_report.candidate_index_sha256 != candidate_index_sha256:
        raise AgentBoundaryError("Pilot filter report is not bound to this candidate index")
    candidates = {item.candidate_id: item for item in candidate_index.candidates}
    records = {item.candidate_id: item for item in filter_report.candidate_records}
    if set(candidates) != set(records):
        raise AgentBoundaryError("Pilot measurements must cover the exact candidate population")
    if not predicted_candidate_ids.issubset(candidates):
        raise AgentBoundaryError("Prediction evidence refers to an unknown Pilot candidate")
    planned = planned_by_strategy or (
        candidate_index.required_by_strategy
        or {
            strategy_id: candidate_index.required_per_strategy
            for strategy_id in {item.strategy_id for item in candidate_index.candidates}
        }
    )
    failures = operational_failures_by_strategy or {}
    if set(failures) - set(planned):
        raise AgentBoundaryError("Operational failures refer to an unknown pilot arm")

    ordered = sorted(
        records.values(),
        key=lambda item: (-item.score_screen, item.candidate_id),
    )
    global_rank = {item.candidate_id: rank for rank, item in enumerate(ordered, 1)}
    within: dict[str, list[CandidateFilterRecord]] = defaultdict(list)
    for item in ordered:
        within[item.strategy_id].append(item)
    strategy_rank = {
        item.candidate_id: rank for group in within.values() for rank, item in enumerate(group, 1)
    }

    observations: list[PilotCandidateObservation] = []
    missing: dict[str, Counter[str]] = defaultdict(Counter)
    unique_sequences: dict[str, set[str]] = defaultdict(set)
    pass_counts: Counter[str] = Counter()
    for candidate_id in sorted(candidates):
        candidate = candidates[candidate_id]
        record = records[candidate_id]
        if candidate.strategy_id != record.strategy_id:
            raise AgentBoundaryError("Candidate strategy lineage changed during filtering")
        unique_sequences[candidate.strategy_id].add(record.sequence_sha256)
        if record.hard_gate_pass:
            pass_counts[candidate.strategy_id] += 1
        metrics = tuple(
            MetricObservation(
                metric_id=item.metric_id,
                value=item.value,
                unit=item.unit,
                available=item.available,
                missing_reason=item.missing_reason,
                source=item.source,
                definition_version=item.definition_version,
            )
            for item in record.metrics
        )
        for metric in metrics:
            if not metric.available:
                missing[candidate.strategy_id][metric.metric_id] += 1
        annotations = tuple(
            LegacyPolicyAnnotation(
                rule_id=item.rule_id,
                metric_id=item.metric_id,
                passed=item.passed,
                reason=item.reason,
            )
            for item in record.hard_gate_decisions
        )
        observations.append(
            PilotCandidateObservation(
                lineage=PilotCandidateLineage(
                    candidate_id=candidate.candidate_id,
                    strategy_id=candidate.strategy_id,
                    task_id=candidate.task_id,
                    task_attempt_number=candidate.task_attempt_number,
                    ordinal_within_strategy=candidate.ordinal_within_strategy,
                    backend_candidate_id=candidate.backend_candidate_id,
                    sequence_sha256=record.sequence_sha256,
                    original_structure=candidate.original_structure,
                    refolded_structure=candidate.refolded_structure,
                    design_mask_source=candidate.design_mask_source,
                    designed_binder_residue_ids=candidate.designed_binder_residue_ids,
                ),
                metrics=metrics,
                legacy_policy_annotations=annotations,
                legacy_policy_pass=record.hard_gate_pass,
                development_score=record.score_screen,
                development_rank_global=global_rank[candidate_id],
                development_rank_within_strategy=strategy_rank[candidate_id],
            )
        )

    arms: list[PilotArmDenominator] = []
    for strategy_id in sorted(planned):
        group = [item for item in observations if item.lineage.strategy_id == strategy_id]
        valid = len(group)
        generated = (generated_by_strategy or {}).get(strategy_id, valid)
        failure_count = failures.get(strategy_id, 0)
        arms.append(
            PilotArmDenominator(
                strategy_id=strategy_id,
                planned_candidates=planned[strategy_id],
                generated_candidates=generated,
                valid_execution_products=valid,
                predicted_candidates=sum(
                    item.lineage.candidate_id in predicted_candidate_ids for item in group
                ),
                metric_evaluable_candidates=sum(
                    any(m.available for m in item.metrics) for item in group
                ),
                unique_sequences=len(unique_sequences[strategy_id]),
                legacy_policy_pass_count=pass_counts[strategy_id],
                operational_failure_count=failure_count,
                missing_by_metric=dict(sorted(missing[strategy_id].items())),
            )
        )
    return PilotMeasurement(
        execution=execution,
        source_candidate_index_sha256=candidate_index_sha256,
        source_filter_report_sha256=filter_report_sha256,
        candidates=tuple(observations),
        arms=tuple(arms),
    )


def build_pilot_dossier(
    *,
    project_id: str,
    pilot_run_id: str,
    upstream_fixture: AcceptedGate3Fixture,
    execution_authority: PilotExecutionAuthority,
    measurement: PilotMeasurement,
    diagnosis: PilotDiagnosis,
    proposed_interpretation: Gate4Recommendation,
    evidence_refs: tuple[str, ...],
) -> PilotEvidenceDossier:
    """Hydrate a Judge input without asking the model to recreate runtime facts."""

    return PilotEvidenceDossier(
        project_id=project_id,
        pilot_run_id=pilot_run_id,
        upstream_fixture=upstream_fixture,
        execution_authority=execution_authority,
        measurement=measurement,
        diagnosis=diagnosis,
        proposed_interpretation=proposed_interpretation,
        evidence_refs=tuple(dict.fromkeys((*upstream_fixture.evidence_refs, *evidence_refs))),
    )


def build_pilot_diagnosis(
    *,
    measurement: PilotMeasurement,
    hypotheses: tuple[PilotDiagnosisHypothesis, ...],
    conclusion: tuple[str, ...],
    uncertainties: tuple[str, ...],
    evidence_refs: tuple[str, ...],
    confidence: Literal["BOUNDED", "INCONCLUSIVE"],
) -> PilotDiagnosis:
    """Hydrate deterministic arm summaries around specialist diagnosis hypotheses."""

    candidates_by_strategy: dict[str, list[PilotCandidateObservation]] = defaultdict(list)
    for candidate in measurement.candidates:
        candidates_by_strategy[candidate.lineage.strategy_id].append(candidate)
    summaries: list[PilotArmSummary] = []
    for arm in measurement.arms:
        scores = sorted(item.development_score for item in candidates_by_strategy[arm.strategy_id])
        top_count = max(1, (len(scores) + 3) // 4) if scores else 0
        summaries.append(
            PilotArmSummary(
                strategy_id=arm.strategy_id,
                planned_candidates=arm.planned_candidates,
                valid_execution_products=arm.valid_execution_products,
                predicted_candidates=arm.predicted_candidates,
                unique_sequences=arm.unique_sequences,
                operational_failure_count=arm.operational_failure_count,
                legacy_policy_pass_count=arm.legacy_policy_pass_count,
                development_score_median=(statistics.median(scores) if scores else None),
                development_score_top_quartile_mean=(
                    statistics.fmean(scores[-top_count:]) if scores else None
                ),
                missing_by_metric=arm.missing_by_metric,
            )
        )
    return PilotDiagnosis(
        measurement_sha256=canonical_model_sha256(measurement),
        arm_summaries=tuple(summaries),
        hypotheses=hypotheses,
        conclusion=conclusion,
        uncertainties=uncertainties,
        evidence_refs=evidence_refs,
        confidence=confidence,
    )


def build_gate4_card(
    *,
    dossier: PilotEvidenceDossier,
    assessment: PilotJudgeAssessment,
) -> DecisionCard:
    """Create a Gate 4 card from one exact dossier and independent Judge result."""

    dossier_sha256 = canonical_model_sha256(dossier)
    if assessment.dossier_sha256 != dossier_sha256:
        raise AgentBoundaryError("Gate 4 Judge assessed a stale or different Pilot dossier")
    test_only = dossier.proposed_interpretation.test_only_control_flow_fixture
    if test_only and assessment.recommendation != "PROMOTE_TO_SCALE":
        raise AgentBoundaryError("The test-only integration fixture exercises PROMOTE_TO_SCALE")
    status: ScientificStatus = (
        "SUPPORTED"
        if assessment.verdict == "ready-to-ask"
        and assessment.recommendation == dossier.proposed_interpretation.outcome
        else "DISCOURAGED"
        if assessment.verdict == "ready-to-ask"
        else "BLOCKED"
    )
    warnings = list(assessment.critical_counterevidence)
    if test_only:
        warnings.insert(
            0,
            "TEST-ONLY CONTROL FLOW: this card is not a scientific promotion decision.",
        )
    if status == "DISCOURAGED" and not warnings:
        warnings.append("The independent Judge recommends a different Gate 4 route.")
    evidence_refs = list(dict.fromkeys((*dossier.evidence_refs, *assessment.evidence_refs)))
    request_identity = dossier_sha256
    card_id = identity(
        {
            "gate": "pilot-promotion",
            "dossier": dossier_sha256,
            "assessment": assessment.assessment_id,
            "option": assessment.recommendation,
        }
    )
    return DecisionCard(
        gate_type="pilot-promotion",
        owner_specialist="pilot-diagnosis",
        judge_status=status,
        warnings=warnings,
        alternative=(
            None
            if status == "SUPPORTED"
            else "Review the evidence and choose a bounded revision or stop route."
        ),
        card_id=card_id,
        assessment_id=assessment.assessment_id,
        project_id=dossier.project_id,
        run_id=dossier.pilot_run_id,
        request_identity=request_identity,
        evidence_id=dossier_sha256,
        question="What should the campaign do after this Pilot?",
        option_id=assessment.recommendation,
        options=[
            {
                "option_id": option,
                "label": option,
                "description": description,
                "eligible": status != "BLOCKED" or option != "PROMOTE_TO_SCALE",
                "judge_status": status if option == "PROMOTE_TO_SCALE" else "SUPPORTED",
            }
            for option, description in _GATE4_OPTIONS
        ],
        evidence_refs=evidence_refs,
        limitations=list(assessment.limitations),
        scientific_summary={
            "execution_mode": dossier.measurement.execution.mode,
            "requested_production_candidates": (
                dossier.measurement.execution.requested_production_candidates
            ),
            "execution_candidates": dossier.measurement.execution.execution_candidates,
            "arm_denominators": [item.model_dump(mode="json") for item in dossier.measurement.arms],
            "proposed_interpretation": dossier.proposed_interpretation.model_dump(mode="json"),
            "test_only_control_flow_fixture": test_only,
            "ranking_semantics": "development-ordering-not-biological-fitness",
        },
        action=(
            "Choose Scientist steering for this test-only integration card. No scientific "
            "promotion or production compute is authorized."
            if test_only
            else "Approve the reviewed Gate 4 route, revise it, reject it, or explicitly override "
            "a discouraged recommendation."
        ),
    )
