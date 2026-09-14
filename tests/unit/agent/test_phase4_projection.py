from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from easydesign.agent.phase4 import (
    build_global_candidate_pool,
    project_scale_observations,
)
from easydesign.agent.phase34_contracts import (
    ExecutionProjection,
    Gate4PromotionAuthority,
    ScaleCampaignSpecification,
)
from easydesign.core import ArtifactRef, canonical_model_sha256
from easydesign.stages.s04_pilot_generation import CandidateIndex, CandidateRecord
from easydesign.stages.s05_pilot_filtering import FilterDecision
from easydesign.stages.s07_final_filtering_and_selection import (
    FinalFilterReport,
    SequencePrefilterRecord,
)


def _ref(name: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=name,
        role="scientific-evidence",
        relative_path=f"artifacts/{name}.cif",
        file_format="cif",
        sha256=hashlib.sha256(name.encode()).hexdigest(),
        size_bytes=1,
        producer_stage="06-scale-generation-and-refolding",
        producer_attempt="attempt-0001",
    )


def test_stage07_legacy_failure_remains_rankable_measurement() -> None:
    candidate = CandidateRecord(
        candidate_id="candidate-a",
        backend_candidate_id="backend-a",
        strategy_id="arm-a",
        task_id="scale-arm-a-shard-0001",
        task_attempt_number=2,
        ordinal_within_strategy=1,
        original_structure=_ref("candidate-a-original"),
        refolded_structure=_ref("candidate-a-refolded"),
        metrics={"source": "deterministic-test"},
    )
    index = CandidateIndex(
        generated_at=datetime.now(UTC),
        strategy_bundle_sha256="a" * 64,
        required_per_strategy=1,
        candidates=(candidate,),
    )
    index_sha256 = canonical_model_sha256(index)
    sequence = "ACDEFGHIK"
    report = FinalFilterReport(
        generated_at=datetime.now(UTC),
        profile_sha256="b" * 64,
        scale_candidate_index_sha256=index_sha256,
        sequence_prefilter=(
            SequencePrefilterRecord(
                candidate_id="candidate-a",
                strategy_id="arm-a",
                sequence=sequence,
                sequence_sha256=hashlib.sha256(sequence.encode()).hexdigest(),
                design_sequence=sequence,
                unknown_residue_count=0,
                decisions=(
                    FilterDecision(
                        rule_id="legacy-score-threshold",
                        metric_id="score-refold",
                        operator="ge",
                        threshold=0.7,
                        observed=0.6,
                        passed=False,
                        reason="Historical provisional threshold.",
                    ),
                ),
                hard_pass=False,
                score_refold=0.6,
            ),
        ),
        deep_filter=(),
        predictions=(),
        consensus=(),
        selections=(),
        status="stopped-no-final-candidate",
    )
    campaign = ScaleCampaignSpecification(
        campaign_id="scale-projection-test",
        promotion_authority=Gate4PromotionAuthority(
            authority_id="test-gate4-authority",
            gate4_card_id="c" * 64,
            pilot_dossier_sha256="d" * 64,
            selected_strategy_ids=("arm-a",),
            requested_scale_candidates=50_000,
            production_strategy_allocations={"arm-a": 50_000},
            authority_scope="test-only-control-flow",
            human_actor="validation-actor",
            authorizes_scientific_scale=False,
            authorizes_production_compute=False,
        ),
        execution=ExecutionProjection(
            mode="validation-micro",
            requested_production_candidates=50_000,
            execution_candidates=1,
            uses_real_generation_backend=False,
            uses_real_prediction_backend=False,
            purpose="Test Stage 06/07 projection.",
        ),
        strategy_allocations={"arm-a": 1},
        generation_backend="deterministic-test",
        prediction_backend="deterministic-test",
        allocation_policy="single-validation-projection",
    )
    report_sha256 = canonical_model_sha256(report)
    observations = project_scale_observations(
        campaign=campaign,
        candidate_index=index,
        candidate_index_sha256=index_sha256,
        final_filter_report=report,
        final_filter_report_sha256=report_sha256,
    )
    assert len(observations) == 1
    observation = observations[0]
    assert observation.legacy_policy_pass is False
    assert observation.development_score == 0.6
    assert observation.evaluation_level == "refold"
    assert all(
        not item.governing_v3_scientific_policy for item in observation.legacy_policy_annotations
    )
    pool = build_global_candidate_pool(
        campaign=campaign,
        source_candidate_index_sha256=index_sha256,
        source_metric_report_sha256=report_sha256,
        planned_batches=1,
        completed_batch_ids=("scale-arm-a-shard-0001",),
        failed_batch_ids=(),
        resumable_batch_ids=(),
        candidates=observations,
    )
    assert pool.global_ranking_candidate_ids == ("candidate-a",)
