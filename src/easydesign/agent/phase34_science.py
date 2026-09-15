"""Compact trusted working sets and deterministic binding of downstream opinions."""

from __future__ import annotations

import statistics
from typing import Any

from easydesign.core import canonical_model_sha256

from .contracts import AgentBoundaryError
from .phase3 import build_pilot_diagnosis
from .phase34_contracts import (
    ExecutionMode,
    FinalCandidateDossier,
    FinalSelectionProposal,
    Gate4Recommendation,
    PilotDiagnosis,
    PilotDiagnosisHypothesis,
    PilotMeasurement,
)
from .phase34_opinions import FinalSelectionOpinion, PilotDiagnosisOpinion
from .phase34_plan import PilotArmIntent
from .session_store import identity


def compact_arm_intent(arm: PilotArmIntent) -> dict[str, Any]:
    """Losslessly factor repeated compiled settings; immutable source DTO stays intact."""
    payload = arm.model_dump(mode="json")
    records = payload["compiled_settings"]
    common = {
        key: value
        for key, value in records[0].items()
        if key not in {"strategy_id", "scaffold_id"}
        and all(key in record and record[key] == value for record in records)
    }
    payload["compiled_settings"] = {
        "common": common,
        "strategies": [
            {key: value for key, value in record.items() if key not in common} for record in records
        ],
        "semantics": "Each strategy inherits every common field; merge common with its "
        "strategy fields to recover the exact compiled configuration.",
    }
    return payload


def pilot_working_set(
    measurement: PilotMeasurement, arms: tuple[PilotArmIntent, ...]
) -> dict[str, Any]:
    """Summarize all measured rows, retaining denominator and missingness semantics."""
    if measurement.native_evidence is not None:
        from .phase3_ranking import compact_native_packet

        return compact_native_packet(measurement, arms)
    facts: dict[str, Any] = {}
    target_contexts: dict[str, Any] = {}
    for arm in arms:
        context_id = "context-" + identity(arm.target_context)[:24]
        intent = compact_arm_intent(arm)
        target_contexts[context_id] = intent["target_context"]
        intent["target_context"] = {"shared_context_id": context_id}
        candidates = [
            c for c in measurement.candidates if c.lineage.strategy_id in arm.strategy_ids
        ]
        denominators = [d for d in measurement.arms if d.strategy_id in arm.strategy_ids]
        metric_names = sorted({m.metric_id for c in candidates for m in c.metrics})
        summaries = {}
        for name in metric_names:
            metrics = [m for c in candidates for m in c.metrics if m.metric_id == name]
            values = [
                float(m.value)
                for m in metrics
                if m.available
                and isinstance(m.value, (int, float))
                and not isinstance(m.value, bool)
            ]
            summaries[name] = {
                "available": sum(m.available for m in metrics),
                "missing": len(candidates) - sum(m.available for m in metrics),
                "missing_reasons": sorted({m.missing_reason for m in metrics if m.missing_reason}),
                "units": sorted({m.unit for m in metrics if m.unit is not None}),
                "median": statistics.median(values) if values else None,
                "minimum": min(values) if values else None,
                "maximum": max(values) if values else None,
            }
        facts[arm.arm_id] = {
            "design_intent": intent,
            "denominators": [d.model_dump(mode="json") for d in denominators],
            "metrics": summaries,
            "candidate_count": len(candidates),
            "unmeasured_candidate_ids": [
                c.candidate_id
                for c in measurement.unmeasured_candidates
                if c.strategy_id in arm.strategy_ids
            ],
            "representative_candidate_ids": [
                c.lineage.candidate_id
                for c in sorted(candidates, key=lambda c: c.development_rank_global)[:5]
            ],
        }
    return {
        "measurement_sha256": canonical_model_sha256(measurement),
        "execution": measurement.execution.model_dump(mode="json"),
        "facts": facts,
        "shared_target_contexts": target_contexts,
        "interpretation_limits": [
            "Legacy thresholds are audit annotations, not calibrated v3 scientific truth.",
            "Development scores are engineering ordering, not biological fitness.",
            "validation-micro is INCONCLUSIVE; zero pass does not establish "
            "Site or Design failure.",
            "Unreported metrics are missing data, not measured zero values.",
        ],
    }


def bind_pilot_opinion(
    measurement: PilotMeasurement,
    arms: tuple[PilotArmIntent, ...],
    opinion: PilotDiagnosisOpinion,
    *,
    evidence_refs: tuple[str, ...],
) -> tuple[PilotDiagnosis, Gate4Recommendation]:
    if {f.arm_id for f in opinion.arm_findings} != {a.arm_id for a in arms}:
        raise AgentBoundaryError("Pilot diagnosis must interpret each approved Design arm")
    ranked = None
    if measurement.native_evidence is not None:
        from .phase3_ranking import bind_native_ranking

        ranked = bind_native_ranking(measurement, arms, opinion)
    strategies = {a.strategy_id for a in measurement.arms}
    if set(opinion.selected_strategy_ids) - strategies:
        raise AgentBoundaryError("Pilot diagnosis recommends an unmeasured strategy")
    candidates = {c.lineage.candidate_id for c in measurement.candidates}
    if len(opinion.supporting_candidate_ids) != len(set(opinion.supporting_candidate_ids)) or (
        set(opinion.supporting_candidate_ids) - candidates
    ):
        raise AgentBoundaryError("Pilot scientific support cites a foreign or duplicate candidate")
    micro = measurement.execution.mode is ExecutionMode.VALIDATION_MICRO
    inconclusive = micro or not opinion.supporting_candidate_ids
    if inconclusive and opinion.recommended_action == "PROMOTE_TO_SCALE":
        raise AgentBoundaryError("Insufficient/micro evidence cannot authorize scientific Scale")
    hypothesis = PilotDiagnosisHypothesis(
        category="insufficient-evidence" if inconclusive else "prediction-uncertainty",
        status="UNRESOLVED" if inconclusive else "PLAUSIBLE",
        observations=tuple(opinion.key_observations),
        implications=(opinion.rationale,),
        evidence_refs=evidence_refs,
    )
    diagnosis = build_pilot_diagnosis(
        measurement=measurement,
        hypotheses=(hypothesis,),
        conclusion=tuple(opinion.key_observations),
        uncertainties=tuple(opinion.uncertainty),
        evidence_refs=evidence_refs,
        confidence="INCONCLUSIVE" if inconclusive else "BOUNDED",
    ).model_copy(
        update={
            "design_arms": arms,
            "ranked_pilot": ranked,
            "arm_comparisons": tuple(opinion.arm_comparisons),
            "alternative_explanations": tuple(
                f.alternative_explanation for f in opinion.arm_findings
            ),
            "operational_confounders": tuple(opinion.operational_confounders),
            "next_discriminating_experiment": tuple(opinion.next_discriminating_experiment),
            "arm_hypothesis_findings": tuple(
                f.model_dump(mode="json") for f in opinion.arm_findings
            ),
        }
    )
    recommendation = Gate4Recommendation(
        outcome=opinion.recommended_action,
        selected_strategy_ids=tuple(opinion.selected_strategy_ids),
        requested_scale_candidates=sum(opinion.scale_allocations.values()) or None,
        production_strategy_allocations=opinion.scale_allocations,
        evidence_sufficiency="INCONCLUSIVE" if inconclusive else "SUFFICIENT_FOR_STEERING",
        scientific_supporting_candidate_count=0 if micro else len(opinion.supporting_candidate_ids),
        observations=tuple(opinion.key_observations),
        interpretations=(opinion.rationale,),
        alternative_explanations=diagnosis.alternative_explanations,
        uncertainties=tuple(opinion.uncertainty),
        falsifiers_or_next_measurements=tuple(opinion.next_discriminating_experiment),
        evidence_refs=evidence_refs,
    )
    return diagnosis, recommendation


def selection_working_set(
    dossiers: tuple[FinalCandidateDossier, ...],
    *,
    primary_count: int,
    backup_count: int,
) -> dict[str, Any]:
    if not dossiers:
        raise AgentBoundaryError("Final selection needs a nonempty evaluated shortlist")
    return {
        "requested_primary_count": primary_count,
        "requested_backup_count": backup_count,
        "global_pool_sha256": dossiers[0].global_pool_sha256,
        "facts": {
            d.candidate.lineage.candidate_id: {
                "strategy_id": d.candidate.lineage.strategy_id,
                "sequence": d.sequence,
                "metrics": [m.model_dump(mode="json") for m in d.candidate.metrics],
                "diversity": d.candidate.diversity.model_dump(mode="json"),
                "development_rank": d.candidate.global_development_rank,
                "risks": d.known_concerns,
                "uncertainties": d.uncertainties,
                "scientific_claim_scope": d.scientific_claim_scope,
            }
            for d in dossiers
        },
        "interpretation_limits": "Choose a panel using quality, risk, diversity and hypothesis "
        "coverage. Development rank is not biological fitness. Missing data is not negative data. "
        "No selection output grants approval or authorizes an experiment.",
    }


def bind_selection_opinion(
    opinion: FinalSelectionOpinion,
    dossiers: tuple[FinalCandidateDossier, ...],
    *,
    primary_count: int,
    backup_count: int,
) -> FinalSelectionProposal:
    ids = {d.candidate.lineage.candidate_id for d in dossiers}
    if (set(opinion.primary_candidate_ids) | set(opinion.backup_candidate_ids)) - ids:
        raise AgentBoundaryError("Final selection cites a candidate outside the trusted shortlist")
    return FinalSelectionProposal(
        primary_candidate_ids=tuple(opinion.primary_candidate_ids),
        backup_candidate_ids=tuple(opinion.backup_candidate_ids),
        requested_primary_count=primary_count,
        requested_backup_count=backup_count,
        rationale=tuple(opinion.selection_rationale),
        selection_gap_reason=opinion.selection_gap_reason,
        major_risks=tuple(opinion.major_risks),
        diversity_coverage=tuple(opinion.diversity_coverage),
        unresolved_questions=tuple(opinion.unresolved_questions),
    )
