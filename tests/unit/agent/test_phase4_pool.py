from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase4 import (
    build_candidate_dossiers,
    build_final_review_dossier,
    build_gate5_card,
    build_global_candidate_pool,
    build_review_shortlist,
    build_wet_lab_handoff,
)
from easydesign.agent.phase34_contracts import (
    DiversityContext,
    ExecutionProjection,
    FinalCandidateJudgeFinding,
    FinalSelectionProposal,
    Gate4PromotionAuthority,
    Gate5ApprovalAuthority,
    Gate5JudgeAssessment,
    ScaleCampaignSpecification,
    ScaleCandidateLineageV3,
    ScaleCandidateObservation,
    ScaleCandidateValidity,
    ScientificContextReferences,
)
from easydesign.core import ArtifactRef, canonical_model_sha256


def _campaign() -> ScaleCampaignSpecification:
    return ScaleCampaignSpecification(
        campaign_id="scale-validation-1",
        promotion_authority=Gate4PromotionAuthority(
            authority_id="gate4-test-authority",
            gate4_card_id="a" * 64,
            pilot_dossier_sha256="b" * 64,
            selected_strategy_ids=("arm-a", "arm-b"),
            requested_scale_candidates=50_000,
            production_strategy_allocations={"arm-a": 25_000, "arm-b": 25_000},
            authority_scope="test-only-control-flow",
            human_actor="validation-actor",
            authorizes_scientific_scale=False,
            authorizes_production_compute=False,
        ),
        execution=ExecutionProjection(
            mode="validation-micro",
            requested_production_candidates=50_000,
            execution_candidates=4,
            uses_real_generation_backend=False,
            uses_real_prediction_backend=False,
            purpose="Exercise Scale state and global ranking.",
        ),
        strategy_allocations={"arm-a": 2, "arm-b": 2},
        generation_backend="synthetic-replay",
        prediction_backend="synthetic-replay",
        allocation_policy="equal-validation-projection",
    )


def test_scale_campaign_cannot_change_gate4_production_intent() -> None:
    payload = _campaign().model_dump(mode="json")
    payload["execution"]["requested_production_candidates"] = 40_000
    with pytest.raises(ValidationError, match="production intent"):
        ScaleCampaignSpecification.model_validate(payload)


def _ref(candidate_id: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=f"{candidate_id}-structure",
        role="scientific-evidence",
        relative_path=f"artifacts/{candidate_id}.cif",
        file_format="cif",
        sha256="c" * 64,
        size_bytes=1,
        producer_stage="06-scale-generation-and-refolding",
        producer_attempt="attempt-0001",
    )


def _candidate(
    candidate_id: str,
    strategy: str,
    batch: str,
    ordinal: int,
    score: float | None,
    *,
    cluster: str | None = None,
    validity: ScaleCandidateValidity = ScaleCandidateValidity.VALID_EVALUATED,
) -> ScaleCandidateObservation:
    sequence = "ACDEFGHIK" if strategy == "arm-a" else "LMNPQRSTV"
    return ScaleCandidateObservation(
        lineage=ScaleCandidateLineageV3(
            campaign_id="scale-validation-1",
            batch_id=batch,
            shard_id=f"shard-{batch}",
            candidate_id=candidate_id,
            strategy_id=strategy,
            strategy_ordinal=ordinal,
            generation_task_id=f"task-{batch}",
            generation_attempt=1,
            backend_candidate_id=f"backend-{candidate_id}",
            prediction_id=f"prediction-{candidate_id}" if score is not None else None,
            prediction_seed=101 if score is not None else None,
            prediction_ids=(f"prediction-{candidate_id}",) if score is not None else (),
            prediction_seeds=(101,) if score is not None else (),
            sequence_sha256=hashlib.sha256(sequence.encode()).hexdigest(),
            artifact_refs=(_ref(candidate_id),),
        ),
        validity=validity,
        development_score=score,
        failure_reason=None if score is not None else "prediction artifact was not evaluable",
        diversity=DiversityContext(
            sequence_cluster_id=cluster,
            method="synthetic exact-sequence cluster" if cluster else None,
        ),
    )


def test_global_ranking_ignores_batch_boundaries_and_retains_invalid() -> None:
    candidates = (
        _candidate("candidate-a1", "arm-a", "batch-a", 1, 0.55, cluster="cluster-1"),
        _candidate("candidate-a2", "arm-a", "batch-a", 2, 0.50, cluster="cluster-1"),
        _candidate("candidate-b1", "arm-b", "batch-b", 1, 0.90, cluster="cluster-2"),
        _candidate(
            "candidate-b2",
            "arm-b",
            "batch-b",
            2,
            None,
            validity=ScaleCandidateValidity.UNEVALUABLE,
        ),
    )
    pool = build_global_candidate_pool(
        campaign=_campaign(),
        source_candidate_index_sha256="f" * 64,
        source_metric_report_sha256="0" * 64,
        planned_batches=3,
        completed_batch_ids=("batch-a", "batch-b"),
        failed_batch_ids=(),
        resumable_batch_ids=("batch-c",),
        candidates=candidates,
    )
    assert pool.global_ranking_candidate_ids == (
        "candidate-b1",
        "candidate-a1",
        "candidate-a2",
    )
    invalid = next(item for item in pool.candidates if item.lineage.candidate_id == "candidate-b2")
    assert invalid.global_development_rank is None
    assert len(pool.candidates) == 4
    assert pool.full_pool_preserved


def test_diversity_shortlist_is_advisory_and_non_destructive() -> None:
    pool = build_global_candidate_pool(
        campaign=_campaign(),
        source_candidate_index_sha256="f" * 64,
        source_metric_report_sha256="0" * 64,
        planned_batches=2,
        completed_batch_ids=("batch-a", "batch-b"),
        failed_batch_ids=(),
        resumable_batch_ids=(),
        candidates=(
            _candidate("candidate-a1", "arm-a", "batch-a", 1, 0.95, cluster="cluster-1"),
            _candidate("candidate-a2", "arm-a", "batch-a", 2, 0.90, cluster="cluster-1"),
            _candidate("candidate-b1", "arm-b", "batch-b", 1, 0.85, cluster="cluster-2"),
            _candidate("candidate-b2", "arm-b", "batch-b", 2, 0.80, cluster="cluster-3"),
        ),
    )
    shortlist = build_review_shortlist(
        pool=pool,
        requested_count=3,
        sequence_cluster_cap=1,
    )
    assert [item.candidate_id for item in shortlist.entries] == [
        "candidate-a1",
        "candidate-b1",
        "candidate-b2",
    ]
    assert shortlist.selection_semantics == "review-priority-not-scientific-hard-filter"
    assert len(pool.global_ranking_candidate_ids) == 4
    assert shortlist.full_ranked_pool_preserved


def test_shortlist_reports_honest_shortfall() -> None:
    pool = build_global_candidate_pool(
        campaign=_campaign(),
        source_candidate_index_sha256="f" * 64,
        source_metric_report_sha256="0" * 64,
        planned_batches=2,
        completed_batch_ids=("batch-a",),
        failed_batch_ids=(),
        resumable_batch_ids=("batch-b",),
        candidates=(
            _candidate("candidate-a1", "arm-a", "batch-a", 1, 0.9, cluster="cluster-1"),
            _candidate("candidate-a2", "arm-a", "batch-a", 2, 0.8, cluster="cluster-1"),
        ),
    )
    shortlist = build_review_shortlist(
        pool=pool,
        requested_count=2,
        sequence_cluster_cap=1,
    )
    assert len(shortlist.entries) == 1
    assert shortlist.shortfall_reason is not None


def _final_review():
    pool = build_global_candidate_pool(
        campaign=_campaign(),
        source_candidate_index_sha256="f" * 64,
        source_metric_report_sha256="0" * 64,
        planned_batches=2,
        completed_batch_ids=("batch-a", "batch-b"),
        failed_batch_ids=(),
        resumable_batch_ids=(),
        candidates=(
            _candidate("candidate-a1", "arm-a", "batch-a", 1, 0.95, cluster="cluster-1"),
            _candidate("candidate-a2", "arm-a", "batch-a", 2, 0.90, cluster="cluster-1"),
            _candidate("candidate-b1", "arm-b", "batch-b", 1, 0.85, cluster="cluster-2"),
            _candidate("candidate-b2", "arm-b", "batch-b", 2, 0.80, cluster="cluster-3"),
        ),
    )
    shortlist = build_review_shortlist(
        pool=pool,
        requested_count=3,
        sequence_cluster_cap=1,
    )
    ids = tuple(item.candidate_id for item in shortlist.entries)
    context = ScientificContextReferences(
        target_identity="UniProt:P00698",
        target_snapshot_sha256="1" * 64,
        site_intent_sha256="2" * 64,
        design_specification_sha256="3" * 64,
        pilot_dossier_sha256="4" * 64,
        evidence_refs=("target:1", "site:2", "design:3", "pilot:4"),
    )
    sequences = {
        candidate_id: "ACDEFGHIK" if "-a" in candidate_id else "LMNPQRSTV" for candidate_id in ids
    }
    dossiers = build_candidate_dossiers(
        pool=pool,
        shortlist=shortlist,
        context=context,
        sequences_by_candidate=sequences,
        concerns_by_candidate={
            candidate_id: ("Development metrics need experimental confirmation.",)
            for candidate_id in ids
        },
        uncertainties_by_candidate={
            candidate_id: ("Wet-lab binding and developability remain unknown.",)
            for candidate_id in ids
        },
        provenance_by_candidate={candidate_id: (f"scale:{candidate_id}",) for candidate_id in ids},
    )
    proposal = FinalSelectionProposal(
        primary_candidate_ids=ids[:2],
        backup_candidate_ids=ids[2:],
        requested_primary_count=2,
        requested_backup_count=1,
        rationale=("Review global rank together with advisory diversity and concerns.",),
    )
    review = build_final_review_dossier(
        project_id="soluble",
        pool=pool,
        shortlist=shortlist,
        candidate_dossiers=dossiers,
        proposed_selection=proposal,
        evidence_refs=("scale:global-pool", "scale:review-shortlist"),
    )
    return pool, shortlist, dossiers, review


def test_candidate_dossiers_cover_shortlist_and_preserve_context() -> None:
    pool, shortlist, dossiers, review = _final_review()
    assert len(dossiers) == len(shortlist.entries)
    assert all(item.scientific_claim_scope == "development-evidence-only" for item in dossiers)
    assert review.full_ranked_pool_preserved
    assert review.global_pool_sha256 == canonical_model_sha256(pool)


def test_gate5_and_validation_handoff_remain_non_scientific() -> None:
    _, _, dossiers, review = _final_review()
    assessment = Gate5JudgeAssessment(
        assessment_id="gate5-judge-1",
        final_review_dossier_sha256=canonical_model_sha256(review),
        verdict="ready-to-ask",
        recommendation="APPROVE_WET_LAB_HANDOFF",
        candidate_findings=tuple(
            FinalCandidateJudgeFinding(
                candidate_id=item.candidate.lineage.candidate_id,
                status="SUPPORTED",
                reasons=("Lineage and development measurements are internally consistent.",),
                concerns=("No experimental validation is present.",),
            )
            for item in dossiers
        ),
        reasons=("The proposed panel is auditable for control-flow validation.",),
        limitations=("This development fixture supports no biological claim.",),
        evidence_refs=("validation:final-review",),
    )
    card = build_gate5_card(dossier=review, assessment=assessment)
    assert card.gate_type == "wet-lab-handoff"
    assert card.judge_status == "SUPPORTED"
    assert "cannot authorize experiments" in card.warnings[0]
    authority = Gate5ApprovalAuthority(
        authority_id="gate5-validation-authority",
        gate5_card_id=card.card_id,
        final_review_dossier_sha256=canonical_model_sha256(review),
        primary_candidate_ids=review.proposed_selection.primary_candidate_ids,
        backup_candidate_ids=review.proposed_selection.backup_candidate_ids,
        authority_scope="test-only-control-flow",
        human_actor="validation-actor",
        authorizes_wet_lab_handoff=False,
    )
    handoff = build_wet_lab_handoff(
        dossier=review,
        gate5_card=card,
        authority=authority,
    )
    assert handoff.handoff_status == "validation-only-not-authorized-for-experiment"
    assert handoff.ordering_status == "not-ordered"
    assert [item.selection_class for item in handoff.candidates] == [
        "primary",
        "primary",
        "backup",
    ]


def test_gate5_requires_exact_judge_coverage() -> None:
    _, _, dossiers, review = _final_review()
    assessment = Gate5JudgeAssessment(
        assessment_id="gate5-judge-incomplete",
        final_review_dossier_sha256=canonical_model_sha256(review),
        verdict="ready-to-ask",
        recommendation="REVISE_FINAL_SELECTION",
        candidate_findings=(
            FinalCandidateJudgeFinding(
                candidate_id=dossiers[0].candidate.lineage.candidate_id,
                status="DISCOURAGED",
                reasons=("Only one candidate was reviewed.",),
                concerns=("Panel coverage is incomplete.",),
            ),
        ),
        reasons=("Review coverage is incomplete.",),
        limitations=("Other candidate dossiers were not assessed.",),
        evidence_refs=("validation:partial-review",),
    )
    with pytest.raises(AgentBoundaryError, match="exactly cover"):
        build_gate5_card(dossier=review, assessment=assessment)


def test_test_only_gate5_authority_cannot_authorize_experiments() -> None:
    with pytest.raises(ValidationError):
        Gate5ApprovalAuthority(
            authority_id="invalid-test-authority",
            gate5_card_id="a" * 64,
            final_review_dossier_sha256="b" * 64,
            primary_candidate_ids=("candidate-a",),
            authority_scope="test-only-control-flow",
            human_actor="validation-actor",
            authorizes_wet_lab_handoff=True,
        )
