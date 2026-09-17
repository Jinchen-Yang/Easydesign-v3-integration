"""Phase 4 global pooling and non-destructive review shortlisting."""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from typing import Literal

from easydesign.core import canonical_model_sha256
from easydesign.core.artifacts import SHA256_PATTERN
from easydesign.stages.s04_pilot_generation import CandidateIndex
from easydesign.stages.s05_pilot_filtering import FilterDecision
from easydesign.stages.s06_scale_generation_and_refolding import (
    MultiStrategyCandidateIndex,
)
from easydesign.stages.s07_final_filtering_and_selection import (
    FinalFilterReport,
    FinalPredictionRecord,
)

from .contracts import AgentBoundaryError, DecisionCard, ScientificStatus
from .phase34_contracts import (
    ExecutionMode,
    FinalCandidateDossier,
    FinalReviewDossier,
    FinalSelectionProposal,
    Gate5ApprovalAuthority,
    Gate5JudgeAssessment,
    GlobalCandidatePool,
    LegacyPolicyAnnotation,
    MetricObservation,
    ReviewShortlist,
    ReviewShortlistEntry,
    ScaleCampaignSpecification,
    ScaleCandidateLineageV3,
    ScaleCandidateObservation,
    ScaleCandidateValidity,
    ScientificContextReferences,
    WetLabHandoffItem,
    WetLabHandoffPackage,
)
from .session_store import identity


def _legacy_annotation(
    decision: FilterDecision,
    *,
    candidate_id: str,
    ordinal: int,
) -> LegacyPolicyAnnotation:
    return LegacyPolicyAnnotation(
        rule_id=f"stage07-rule-{identity({'candidate': candidate_id, 'ordinal': ordinal})[:16]}",
        metric_id=decision.metric_id,
        passed=decision.passed,
        reason=decision.reason,
    )


def project_scale_observations(
    *,
    campaign: ScaleCampaignSpecification,
    candidate_index: CandidateIndex | MultiStrategyCandidateIndex,
    candidate_index_sha256: str,
    final_filter_report: FinalFilterReport,
    final_filter_report_sha256: str,
) -> tuple[ScaleCandidateObservation, ...]:
    """Project Stage 06/07 evidence without applying Stage 07 legacy selection gates."""

    if (
        re.fullmatch(SHA256_PATTERN, candidate_index_sha256) is None
        or re.fullmatch(SHA256_PATTERN, final_filter_report_sha256) is None
    ):
        raise AgentBoundaryError("Scale artifact identity must be an exact SHA-256")
    if final_filter_report.scale_candidate_index_sha256 != candidate_index_sha256:
        raise AgentBoundaryError("Stage 07 metrics are bound to a different Scale index")
    indexed = {item.candidate_id: item for item in candidate_index.candidates}
    prefilters = {item.candidate_id: item for item in final_filter_report.sequence_prefilter}
    if set(indexed) != set(prefilters):
        raise AgentBoundaryError("Stage 07 prefilter must cover the exact Scale population")
    deep = {item.candidate_id: item for item in final_filter_report.deep_filter}
    consensus = {item.candidate_id: item for item in final_filter_report.consensus}
    predictions: dict[str, list[FinalPredictionRecord]] = defaultdict(list)
    for prediction in final_filter_report.predictions:
        predictions[prediction.candidate_id].append(prediction)
    observations: list[ScaleCandidateObservation] = []
    for candidate_id in sorted(indexed):
        candidate = indexed[candidate_id]
        prefilter = prefilters[candidate_id]
        if candidate.strategy_id != prefilter.strategy_id:
            raise AgentBoundaryError("Scale candidate strategy changed during Stage 07")
        if hashlib.sha256(prefilter.sequence.encode()).hexdigest() != prefilter.sequence_sha256:
            raise AgentBoundaryError("Stage 07 sequence hash does not match its sequence")
        candidate_predictions = sorted(
            predictions[candidate_id],
            key=lambda item: (-item.score_full, item.seed, item.sample_index),
        )
        deep_record = deep.get(candidate_id)
        consensus_record = consensus.get(candidate_id)
        if consensus_record is not None and consensus_record.score_final is not None:
            score = consensus_record.score_final
            evaluation_level: Literal["refold", "deep", "multi-seed", "unavailable"] = "multi-seed"
        elif deep_record is not None:
            score = deep_record.score_deep
            evaluation_level = "deep"
        else:
            score = prefilter.score_refold
            evaluation_level = "refold"
        standard_sequence = all(residue in "ACDEFGHIKLMNPQRSTVWY" for residue in prefilter.sequence)
        validity = (
            ScaleCandidateValidity.VALID_EVALUATED
            if standard_sequence
            else ScaleCandidateValidity.INVALID_EXECUTION_PRODUCT
        )
        decisions = list(prefilter.decisions)
        if deep_record is not None:
            decisions.extend(deep_record.decisions)
        for prediction in candidate_predictions:
            decisions.extend(prediction.seed101_gate_decisions)
            decisions.extend(prediction.consensus_gate_decisions)
        prediction_ids = tuple(
            "prediction-"
            + identity(
                {
                    "candidate": candidate_id,
                    "seed": item.seed,
                    "sample": item.sample_index,
                }
            )[:24]
            for item in candidate_predictions
        )
        artifact_refs = [candidate.original_structure, candidate.refolded_structure]
        if candidate.design_mask_source is not None:
            artifact_refs.append(candidate.design_mask_source)
        for prediction in candidate_predictions:
            artifact_refs.extend(
                (
                    prediction.predicted_structure,
                    prediction.summary_confidence,
                    prediction.full_confidence,
                )
            )
        metrics = (
            MetricObservation(
                metric_id="score-refold",
                value=prefilter.score_refold,
                available=True,
                source="stage07-final-filter-report",
                definition_version="legacy-stage07-observed-v1",
            ),
            MetricObservation(
                metric_id="score-deep",
                value=None if deep_record is None else deep_record.score_deep,
                available=deep_record is not None,
                missing_reason=None if deep_record is not None else "not evaluated by Stage 07",
                source="stage07-final-filter-report",
                definition_version="legacy-stage07-observed-v1",
            ),
            MetricObservation(
                metric_id="score-final-consensus",
                value=(None if consensus_record is None else consensus_record.score_final),
                available=(
                    consensus_record is not None and consensus_record.score_final is not None
                ),
                missing_reason=(
                    None
                    if consensus_record is not None and consensus_record.score_final is not None
                    else "no passing multi-seed consensus score"
                ),
                source="stage07-final-filter-report",
                definition_version="legacy-stage07-observed-v1",
            ),
            MetricObservation(
                metric_id="prediction-count",
                value=len(candidate_predictions),
                available=True,
                source="stage07-final-filter-report",
                definition_version="phase4-lineage-v1",
            ),
        )
        annotations = tuple(
            _legacy_annotation(decision, candidate_id=candidate_id, ordinal=ordinal)
            for ordinal, decision in enumerate(decisions, 1)
        )
        observations.append(
            ScaleCandidateObservation(
                lineage=ScaleCandidateLineageV3(
                    campaign_id=campaign.campaign_id,
                    batch_id=candidate.task_id,
                    shard_id=candidate.task_id,
                    candidate_id=candidate_id,
                    strategy_id=candidate.strategy_id,
                    strategy_ordinal=candidate.ordinal_within_strategy,
                    generation_task_id=candidate.task_id,
                    generation_attempt=candidate.task_attempt_number,
                    backend_candidate_id=candidate.backend_candidate_id,
                    prediction_id=prediction_ids[0] if prediction_ids else None,
                    prediction_seed=(
                        candidate_predictions[0].seed if candidate_predictions else None
                    ),
                    prediction_ids=prediction_ids,
                    prediction_seeds=tuple(item.seed for item in candidate_predictions),
                    sequence_sha256=prefilter.sequence_sha256,
                    artifact_refs=tuple(
                        {(item.relative_path, item.sha256): item for item in artifact_refs}.values()
                    ),
                ),
                validity=validity,
                metrics=metrics,
                legacy_policy_annotations=annotations,
                legacy_policy_pass=all(item.passed for item in decisions),
                development_score=score if standard_sequence else None,
                failure_reason=(
                    None if standard_sequence else "sequence contains a non-standard residue"
                ),
                evaluation_level=evaluation_level if standard_sequence else "unavailable",
            )
        )
    return tuple(observations)


def native_ordering_key(candidate: ScaleCandidateObservation) -> tuple[float, float, str]:
    """Refold consistency orders review effort; missing metrics sort last, never fail."""
    evidence = candidate.native_evidence
    assert evidence is not None

    def numeric(name: str) -> float:
        value = evidence.metrics.get(name)
        return float(value) if isinstance(value, (int, float)) else float("inf")

    return numeric("bb_rmsd_design"), numeric("bb_rmsd"), candidate.lineage.candidate_id


def build_global_candidate_pool(
    *,
    campaign: ScaleCampaignSpecification,
    source_candidate_index_sha256: str,
    source_metric_report_sha256: str,
    planned_batches: int,
    completed_batch_ids: tuple[str, ...],
    failed_batch_ids: tuple[str, ...],
    resumable_batch_ids: tuple[str, ...],
    candidates: tuple[ScaleCandidateObservation, ...],
) -> GlobalCandidatePool:
    """Rank every valid evaluated candidate together, independent of batch boundaries."""

    if any(item.lineage.campaign_id != campaign.campaign_id for item in candidates):
        raise AgentBoundaryError("Scale candidate belongs to a different campaign")
    if any(item.global_development_rank is not None for item in candidates):
        raise AgentBoundaryError("Input candidates must not supply their own global rank")
    eligible = [item for item in candidates if item.competition_eligible]
    if campaign.evidence_policy == "boltzgen-native-v1":
        if any(item.native_evidence is None for item in candidates):
            raise AgentBoundaryError("Native Scale campaign requires native evidence for every row")
        rankable = sorted(eligible, key=native_ordering_key)
    else:
        rankable = sorted(
            eligible, key=lambda item: (-(item.development_score or 0.0), item.lineage.candidate_id)
        )
    rank_by_id = {item.lineage.candidate_id: rank for rank, item in enumerate(rankable, 1)}
    hydrated = tuple(
        item.model_copy(
            update={
                "global_development_rank": rank_by_id.get(item.lineage.candidate_id),
            }
        )
        for item in candidates
    )
    return GlobalCandidatePool(
        campaign=campaign,
        source_candidate_index_sha256=source_candidate_index_sha256,
        source_metric_report_sha256=source_metric_report_sha256,
        planned_batches=planned_batches,
        completed_batch_ids=completed_batch_ids,
        failed_batch_ids=failed_batch_ids,
        resumable_batch_ids=resumable_batch_ids,
        candidates=hydrated,
        global_ranking_candidate_ids=tuple(item.lineage.candidate_id for item in rankable),
    )


def build_review_shortlist(
    *,
    pool: GlobalCandidatePool,
    requested_count: int,
    sequence_cluster_cap: int | None = None,
    strategy_groups: dict[str, str] | None = None,
) -> ReviewShortlist:
    """Prioritize global candidates for review while preserving the complete pool."""

    by_id = {item.lineage.candidate_id: item for item in pool.candidates}
    selected: list[ReviewShortlistEntry] = []
    cluster_counts: Counter[str] = Counter()
    review_order = list(pool.global_ranking_candidate_ids)
    arm_representatives: set[str] = set()
    if pool.campaign.evidence_policy == "boltzgen-native-v1" and strategy_groups:
        # Reserve review visibility for available Arms before filling by global rank.
        # This is shortlist coverage, not a per-Arm final selection quota.
        representatives: dict[str, str] = {}
        representative_clusters: Counter[str] = Counter()
        for cid in review_order:
            candidate = by_id[cid]
            group = strategy_groups.get(candidate.lineage.strategy_id)
            cluster = candidate.diversity.sequence_cluster_id or cid
            if group is None or group in representatives:
                continue
            if sequence_cluster_cap is not None and (
                representative_clusters[cluster] >= sequence_cluster_cap
            ):
                continue
            representatives[group] = cid
            representative_clusters[cluster] += 1
        first = list(representatives.values())
        arm_representatives = set(first)
        review_order = first + [cid for cid in review_order if cid not in arm_representatives]
    for candidate_id in review_order:
        candidate = by_id[candidate_id]
        rank = candidate.global_development_rank
        if rank is None:
            raise AgentBoundaryError("global ranking points to an unranked candidate")
        cluster = candidate.diversity.sequence_cluster_id or candidate_id
        if sequence_cluster_cap is not None and cluster_counts[cluster] >= sequence_cluster_cap:
            continue
        cluster_counts[cluster] += 1
        role: Literal["ranked-lead", "diversity-representative"] = (
            "diversity-representative" if sequence_cluster_cap is not None else "ranked-lead"
        )
        selected.append(
            ReviewShortlistEntry(
                candidate_id=candidate_id,
                global_development_rank=rank,
                review_role=role,
                reason=(
                    "Best available nonduplicate representative for Arm review coverage; "
                    "global engineering rank is retained, with no final panel quota."
                    if candidate_id in arm_representatives
                    else "Highest remaining development rank within the advisory "
                    "sequence-cluster cap."
                    if sequence_cluster_cap is not None
                    else "Selected by deterministic global development ordering."
                ),
            )
        )
        if len(selected) == requested_count:
            break
    shortfall = None
    if len(selected) < requested_count:
        shortfall = (
            "The valid evaluated global pool and advisory diversity cap provide only "
            f"{len(selected)} of {requested_count} requested review candidates."
        )
    return ReviewShortlist(
        global_pool_sha256=canonical_model_sha256(pool),
        requested_count=requested_count,
        entries=tuple(selected),
        sequence_cluster_cap=sequence_cluster_cap,
        shortfall_reason=shortfall,
    )


def build_candidate_dossiers(
    *,
    pool: GlobalCandidatePool,
    shortlist: ReviewShortlist,
    context: ScientificContextReferences,
    sequences_by_candidate: dict[str, str],
    concerns_by_candidate: dict[str, tuple[str, ...]],
    uncertainties_by_candidate: dict[str, tuple[str, ...]],
    provenance_by_candidate: dict[str, tuple[str, ...]],
) -> tuple[FinalCandidateDossier, ...]:
    """Project every shortlisted candidate into a traceable, bounded review dossier."""

    pool_sha256 = canonical_model_sha256(pool)
    if shortlist.global_pool_sha256 != pool_sha256:
        raise AgentBoundaryError("review shortlist is bound to a different global pool")
    shortlist_sha256 = canonical_model_sha256(shortlist)
    by_id = {item.lineage.candidate_id: item for item in pool.candidates}
    shortlisted_ids = tuple(item.candidate_id for item in shortlist.entries)
    supplied_maps = (
        sequences_by_candidate,
        concerns_by_candidate,
        uncertainties_by_candidate,
        provenance_by_candidate,
    )
    if any(set(mapping) != set(shortlisted_ids) for mapping in supplied_maps):
        raise AgentBoundaryError("candidate dossier inputs must exactly cover the review shortlist")
    scientific_scope: Literal["development-evidence-only", "scientist-approved-scale-evidence"] = (
        "development-evidence-only"
        if pool.campaign.promotion_authority.authority_scope == "test-only-control-flow"
        or pool.campaign.execution.mode is not ExecutionMode.PRODUCTION
        else "scientist-approved-scale-evidence"
    )
    return tuple(
        FinalCandidateDossier(
            global_pool_sha256=pool_sha256,
            review_shortlist_sha256=shortlist_sha256,
            context=context,
            candidate=by_id[candidate_id],
            sequence=sequences_by_candidate[candidate_id],
            known_concerns=concerns_by_candidate[candidate_id],
            uncertainties=uncertainties_by_candidate[candidate_id],
            provenance_refs=provenance_by_candidate[candidate_id],
            scientific_claim_scope=scientific_scope,
        )
        for candidate_id in shortlisted_ids
    )


def build_final_review_dossier(
    *,
    project_id: str,
    pool: GlobalCandidatePool,
    shortlist: ReviewShortlist,
    candidate_dossiers: tuple[FinalCandidateDossier, ...],
    proposed_selection: FinalSelectionProposal,
    evidence_refs: tuple[str, ...],
    selection_revision_id: str | None = None,
) -> FinalReviewDossier:
    """Bind the full review set and proposed panel for independent final review."""

    pool_sha256 = canonical_model_sha256(pool)
    shortlist_sha256 = canonical_model_sha256(shortlist)
    if shortlist.global_pool_sha256 != pool_sha256:
        raise AgentBoundaryError("final review shortlist is stale")
    expected_ids = tuple(item.candidate_id for item in shortlist.entries)
    observed_ids = tuple(item.candidate.lineage.candidate_id for item in candidate_dossiers)
    if observed_ids != expected_ids:
        raise AgentBoundaryError("final review dossiers must preserve shortlist order and coverage")
    return FinalReviewDossier(
        filtering_policy="boltzgen-native-profile-v1"
        if pool.campaign.evidence_policy == "boltzgen-native-v1"
        else "calibration-pending",
        selection_revision_id=selection_revision_id,
        project_id=project_id,
        campaign_id=pool.campaign.campaign_id,
        global_pool_sha256=pool_sha256,
        review_shortlist_sha256=shortlist_sha256,
        candidate_dossiers=candidate_dossiers,
        proposed_selection=proposed_selection,
        evidence_refs=evidence_refs,
    )


def build_gate5_card(
    *,
    dossier: FinalReviewDossier,
    assessment: Gate5JudgeAssessment,
) -> DecisionCard:
    """Create a Gate 5 Scientist decision bound to one independently reviewed panel."""

    dossier_sha256 = canonical_model_sha256(dossier)
    if assessment.final_review_dossier_sha256 != dossier_sha256:
        raise AgentBoundaryError("Gate 5 Judge assessed a stale final review dossier")
    dossier_ids = {item.candidate.lineage.candidate_id for item in dossier.candidate_dossiers}
    finding_ids = {item.candidate_id for item in assessment.candidate_findings}
    if finding_ids != dossier_ids:
        raise AgentBoundaryError("Gate 5 Judge findings must exactly cover final review")
    proposal = dossier.proposed_selection
    selected = set(proposal.primary_candidate_ids) | set(proposal.backup_candidate_ids)
    finding_by_id = {item.candidate_id: item for item in assessment.candidate_findings}
    selected_blocked = any(finding_by_id[item].status == "BLOCKED" for item in selected)
    selected_discouraged = any(finding_by_id[item].status == "DISCOURAGED" for item in selected)
    recommendation_matches = assessment.recommendation == "APPROVE_WET_LAB_HANDOFF"
    status: ScientificStatus = (
        "SUPPORTED"
        if assessment.verdict == "ready-to-ask"
        and recommendation_matches
        and not selected_blocked
        and not selected_discouraged
        else "DISCOURAGED"
        if assessment.verdict == "ready-to-ask" and not selected_blocked
        else "BLOCKED"
    )
    test_only = all(
        item.scientific_claim_scope == "development-evidence-only"
        for item in dossier.candidate_dossiers
    )
    warnings = list(assessment.critical_counterevidence)
    if test_only:
        warnings.insert(
            0,
            "TEST-ONLY CONTROL FLOW: approval cannot authorize experiments or ordering.",
        )
    if status == "DISCOURAGED" and not warnings:
        warnings.append("The independent Judge recommends revision or stop.")
    card_id = identity(
        {
            "gate": "wet-lab-handoff",
            "dossier": dossier_sha256,
            "assessment": assessment.assessment_id,
            "primary": proposal.primary_candidate_ids,
            "backup": proposal.backup_candidate_ids,
        }
    )
    return DecisionCard(
        gate_type="wet-lab-handoff",
        owner_specialist="final-selection",
        judge_status=status,
        warnings=warnings,
        alternative=(
            None
            if status == "SUPPORTED"
            else "Revise the candidate panel or stop while preserving the full ranked pool."
        ),
        card_id=card_id,
        assessment_id=assessment.assessment_id,
        project_id=dossier.project_id,
        run_id=dossier.campaign_id,
        request_identity=dossier_sha256,
        evidence_id=dossier_sha256,
        question="Should this reviewed candidate panel proceed to Wet-lab Handoff?",
        option_id="wet-lab-panel",
        options=[
            {
                "option_id": "wet-lab-panel",
                "label": "Approve reviewed panel",
                "description": "Approve the exact primary and backup panel shown here.",
                "primary_candidate_ids": list(proposal.primary_candidate_ids),
                "backup_candidate_ids": list(proposal.backup_candidate_ids),
                "eligible": status != "BLOCKED",
                "judge_status": status,
            },
            {
                "option_id": "revise-final-selection",
                "label": "Revise final selection",
                "description": "Return the candidate panel for evidence-bound revision.",
                "eligible": True,
                "judge_status": "SUPPORTED",
            },
            {
                "option_id": "stop",
                "label": "Stop",
                "description": "Stop without creating an experimental handoff.",
                "eligible": True,
                "judge_status": "SUPPORTED",
            },
        ],
        evidence_refs=list(dict.fromkeys((*dossier.evidence_refs, *assessment.evidence_refs))),
        limitations=list(assessment.limitations),
        scientific_summary={
            "proposed_selection": proposal.model_dump(mode="json"),
            "candidate_findings": [
                item.model_dump(mode="json") for item in assessment.candidate_findings
            ],
            "test_only_control_flow_fixture": test_only,
            "ranking_semantics": "development-ordering-not-biological-fitness",
            "filtering_policy": dossier.filtering_policy,
        },
        action=(
            "Exercise the validation-only Gate 5 route; no experiment or order is authorized."
            if test_only
            else "Approve the reviewed panel, request a revision, reject it, or explicitly "
            "override a discouraged recommendation."
        ),
    )


def build_wet_lab_handoff(
    *,
    dossier: FinalReviewDossier,
    gate5_card: DecisionCard,
    authority: Gate5ApprovalAuthority,
) -> WetLabHandoffPackage:
    """Assemble the exact approved panel without copying large scientific artifacts."""

    dossier_sha256 = canonical_model_sha256(dossier)
    if gate5_card.gate_type != "wet-lab-handoff":
        raise AgentBoundaryError("Wet-lab Handoff requires a Gate 5 card")
    if authority.gate5_card_id != gate5_card.card_id:
        raise AgentBoundaryError("Gate 5 authority belongs to a different decision card")
    if authority.final_review_dossier_sha256 != dossier_sha256:
        raise AgentBoundaryError("Gate 5 authority belongs to a different final review")
    proposal = dossier.proposed_selection
    if authority.primary_candidate_ids != proposal.primary_candidate_ids or (
        authority.backup_candidate_ids != proposal.backup_candidate_ids
    ):
        raise AgentBoundaryError("Gate 5 authority changed the independently reviewed panel")
    by_id = {item.candidate.lineage.candidate_id: item for item in dossier.candidate_dossiers}
    items: list[WetLabHandoffItem] = []
    selection_class: Literal["primary", "backup"]
    for selection_class, candidate_ids in (
        ("primary", authority.primary_candidate_ids),
        ("backup", authority.backup_candidate_ids),
    ):
        for rank, candidate_id in enumerate(candidate_ids, 1):
            candidate_dossier = by_id[candidate_id]
            candidate_rank = candidate_dossier.candidate.global_development_rank
            if candidate_rank is None:
                raise AgentBoundaryError("Wet-lab candidate lacks a global rank")
            items.append(
                WetLabHandoffItem(
                    candidate_id=candidate_id,
                    selection_class=selection_class,
                    selection_rank=rank,
                    sequence=candidate_dossier.sequence,
                    candidate_dossier_sha256=canonical_model_sha256(candidate_dossier),
                    global_development_rank=candidate_rank,
                    metrics=candidate_dossier.candidate.metrics,
                    artifact_refs=candidate_dossier.candidate.lineage.artifact_refs,
                    known_concerns=candidate_dossier.known_concerns,
                    uncertainties=candidate_dossier.uncertainties,
                )
            )
    return WetLabHandoffPackage(
        project_id=dossier.project_id,
        campaign_id=dossier.campaign_id,
        final_review_dossier_sha256=dossier_sha256,
        approval_authority=authority,
        context=dossier.candidate_dossiers[0].context,
        candidates=tuple(items),
        evidence_refs=tuple(
            dict.fromkeys(
                (
                    *dossier.evidence_refs,
                    *(ref for item in dossier.candidate_dossiers for ref in item.provenance_refs),
                )
            )
        ),
        handoff_status=(
            "ready-for-downstream-experimental-planning"
            if authority.authorizes_wet_lab_handoff
            else "validation-only-not-authorized-for-experiment"
        ),
    )
