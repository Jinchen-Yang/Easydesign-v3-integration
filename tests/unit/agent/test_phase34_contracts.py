from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase3 import (
    build_gate4_card,
    build_pilot_diagnosis,
    build_pilot_dossier,
    project_pilot_measurement,
)
from easydesign.agent.phase34_contracts import (
    AcceptedGate3Fixture,
    ExecutionProjection,
    Gate4Recommendation,
    PilotDiagnosisHypothesis,
    PilotJudgeAssessment,
    ValidationExecutionAuthority,
)
from easydesign.core import ArtifactRef, canonical_model_sha256
from easydesign.stages.s04_pilot_generation import CandidateIndex, CandidateRecord
from easydesign.stages.s05_pilot_filtering import (
    CandidateFilterRecord,
    FilterDecision,
    FilterMetric,
    PilotFilterReportV1_6,
    StrategyFilterSummary,
    StrategyTier,
)


def _ref(name: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=name,
        role="scientific-evidence",
        relative_path=f"artifacts/{name}.json",
        file_format="json",
        sha256="a" * 64,
        size_bytes=1,
        producer_stage="04-pilot-generation",
        producer_attempt="attempt-0001",
    )


def _candidate(candidate_id: str, strategy: str, ordinal: int) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=candidate_id,
        backend_candidate_id=f"backend-{candidate_id}",
        strategy_id=strategy,
        task_id=f"task-{strategy}",
        task_attempt_number=1,
        ordinal_within_strategy=ordinal,
        original_structure=_ref(f"{candidate_id}-original"),
        refolded_structure=_ref(f"{candidate_id}-refolded"),
        metrics={"source": "synthetic"},
    )


def _filter(candidate_id: str, strategy: str, score: float, passed: bool) -> CandidateFilterRecord:
    sequence = "ACDEFGHIK"
    return CandidateFilterRecord(
        candidate_id=candidate_id,
        strategy_id=strategy,
        sequence=sequence,
        sequence_sha256=hashlib.sha256(sequence.encode()).hexdigest(),
        metrics=(
            FilterMetric(
                metric_id="interface-confidence",
                value=score,
                source="derived",
                definition_version="synthetic-v1",
            ),
            FilterMetric(
                metric_id="optional-geometry",
                value=None,
                source="derived",
                definition_version="synthetic-v1",
                available=False,
                missing_reason="not computed in the fixture",
            ),
        ),
        hard_gate_decisions=(
            FilterDecision(
                rule_id="legacy-threshold",
                metric_id="interface-confidence",
                operator="ge",
                threshold=0.7,
                observed=score,
                passed=passed,
                reason="historical development threshold",
            ),
        ),
        hard_gate_pass=passed,
        eligible_unique_pass=passed,
        score_screen=score,
        normalization_group=strategy,
    )


def _report(index: CandidateIndex) -> PilotFilterReportV1_6:
    records = (
        _filter("candidate-a", "arm-a", 0.8, True),
        _filter("candidate-b", "arm-a", 0.6, False),
    )
    return PilotFilterReportV1_6(
        generated_at=datetime.now(UTC),
        profile_sha256="b" * 64,
        candidate_index_sha256=canonical_model_sha256(index),
        candidate_records=records,
        strategy_summaries=(
            StrategyFilterSummary(
                strategy_id="arm-a",
                candidate_count=2,
                unique_sequence_count=2,
                boltzgen_hard_pass_count=1,
                final_gate_pass_count=1,
                final_gate_pass_rate=0.5,
                score_screen_top_quartile_mean=0.8,
                score_screen_all_median=0.7,
                score_yaml=0.7,
                tier=StrategyTier.B,
            ),
        ),
        promoted_strategy_ids=(),
        status="stopped-no-tier-a",
    )


def test_accepted_gate3_fixtures_preserve_pending_authority() -> None:
    path = Path("tests/fixtures/agent/phase34_gate3_fixtures.json")
    payload = json.loads(path.read_text())
    fixtures = [AcceptedGate3Fixture.model_validate(item) for item in payload["fixtures"]]
    assert {item.case_id for item in fixtures} == {"case-4-standard", "case-5-native"}
    assert all(item.gate3_status == "awaiting-human-approval" for item in fixtures)
    assert all(not item.generation_started for item in fixtures)
    assert all("No " in item.acceptance_scope for item in fixtures)


def test_validation_authority_cannot_become_scientific_or_production() -> None:
    authority = ValidationExecutionAuthority(
        authority_id="validation-overlay-1",
        fixture_id="accepted-standard-gate3-live162",
        reason="Exercise downstream state transitions with bounded compute.",
    )
    assert not authority.authorizes_scientific_pilot
    with pytest.raises(ValidationError):
        ValidationExecutionAuthority(
            authority_id="invalid-overlay",
            fixture_id=authority.fixture_id,
            authorizes_production_compute=True,
            reason="must fail",
        )


def test_execution_projection_preserves_production_intent() -> None:
    projection = ExecutionProjection(
        mode="validation-micro",
        requested_production_candidates=280,
        execution_candidates=2,
        uses_real_generation_backend=True,
        uses_real_prediction_backend=True,
        purpose="Minimal real backend validation.",
    )
    assert projection.requested_production_candidates == 280
    assert projection.execution_candidates == 2
    with pytest.raises(ValidationError):
        ExecutionProjection(
            mode="production",
            requested_production_candidates=280,
            execution_candidates=2,
            uses_real_generation_backend=True,
            uses_real_prediction_backend=True,
            purpose="invalid",
        )


def test_measurement_retains_legacy_failure_and_missingness() -> None:
    index = CandidateIndex(
        generated_at=datetime.now(UTC),
        strategy_bundle_sha256="c" * 64,
        required_per_strategy=2,
        candidates=(
            _candidate("candidate-a", "arm-a", 1),
            _candidate("candidate-b", "arm-a", 2),
        ),
    )
    report = _report(index)
    result = project_pilot_measurement(
        candidate_index=index,
        candidate_index_sha256=canonical_model_sha256(index),
        filter_report=report,
        filter_report_sha256=canonical_model_sha256(report),
        execution=ExecutionProjection(
            mode="validation-micro",
            requested_production_candidates=280,
            execution_candidates=2,
            uses_real_generation_backend=False,
            uses_real_prediction_backend=False,
            purpose="Synthetic contract test.",
        ),
    )
    assert len(result.candidates) == 2
    failed = next(item for item in result.candidates if item.lineage.candidate_id == "candidate-b")
    assert not failed.legacy_policy_pass
    assert failed.development_rank_global == 2
    assert all(not item.governing_v3_scientific_policy for item in failed.legacy_policy_annotations)
    assert result.arms[0].missing_by_metric == {"optional-geometry": 2}
    assert result.scientific_policy == "measure-and-rank-first-filter-calibration-pending"


def test_measurement_rejects_unbound_filter_report() -> None:
    index = CandidateIndex(
        generated_at=datetime.now(UTC),
        strategy_bundle_sha256="c" * 64,
        required_per_strategy=2,
        candidates=(
            _candidate("candidate-a", "arm-a", 1),
            _candidate("candidate-b", "arm-a", 2),
        ),
    )
    report = _report(index).model_copy(update={"candidate_index_sha256": "d" * 64})
    with pytest.raises(AgentBoundaryError, match="not bound"):
        project_pilot_measurement(
            candidate_index=index,
            candidate_index_sha256=canonical_model_sha256(index),
            filter_report=report,
            filter_report_sha256=canonical_model_sha256(report),
            execution=ExecutionProjection(
                mode="validation-micro",
                requested_production_candidates=280,
                execution_candidates=2,
                uses_real_generation_backend=False,
                uses_real_prediction_backend=False,
                purpose="Synthetic contract test.",
            ),
        )


def test_zero_support_cannot_be_scientific_promotion() -> None:
    common = {
        "outcome": "PROMOTE_TO_SCALE",
        "selected_strategy_ids": ("arm-a",),
        "requested_scale_candidates": 50_000,
        "production_strategy_allocations": {"arm-a": 50_000},
        "evidence_sufficiency": "INCONCLUSIVE",
        "scientific_supporting_candidate_count": 0,
        "observations": ("No supporting candidate was observed.",),
        "interpretations": ("The micro result is underpowered.",),
        "alternative_explanations": ("Sampling may be insufficient.",),
        "uncertainties": ("Candidate yield is unknown at production scale.",),
        "falsifiers_or_next_measurements": ("Run a discriminating follow-up Pilot.",),
        "evidence_refs": ("synthetic:pilot-measurement",),
    }
    with pytest.raises(ValidationError):
        Gate4Recommendation(**common)
    fixture = Gate4Recommendation(**common, test_only_control_flow_fixture=True)
    assert fixture.test_only_control_flow_fixture

    with pytest.raises(ValidationError):
        Gate4Recommendation(
            **{
                **common,
                "outcome": "STOP",
                "selected_strategy_ids": ("arm-a",),
            },
            test_only_control_flow_fixture=False,
        )


def test_pilot_dossier_hydrates_test_only_gate4_card() -> None:
    fixture_payload = json.loads(
        Path("tests/fixtures/agent/phase34_gate3_fixtures.json").read_text()
    )["fixtures"][0]
    fixture = AcceptedGate3Fixture.model_validate(fixture_payload)
    index = CandidateIndex(
        generated_at=datetime.now(UTC),
        strategy_bundle_sha256="c" * 64,
        required_per_strategy=2,
        candidates=(
            _candidate("candidate-a", "arm-a", 1),
            _candidate("candidate-b", "arm-a", 2),
        ),
    )
    report = _report(index)
    measurement = project_pilot_measurement(
        candidate_index=index,
        candidate_index_sha256=canonical_model_sha256(index),
        filter_report=report,
        filter_report_sha256=canonical_model_sha256(report),
        execution=ExecutionProjection(
            mode="validation-micro",
            requested_production_candidates=280,
            execution_candidates=2,
            uses_real_generation_backend=False,
            uses_real_prediction_backend=False,
            purpose="Gate 4 integration fixture.",
        ),
    )
    recommendation = Gate4Recommendation(
        outcome="PROMOTE_TO_SCALE",
        selected_strategy_ids=("arm-a",),
        requested_scale_candidates=50_000,
        production_strategy_allocations={"arm-a": 50_000},
        evidence_sufficiency="INCONCLUSIVE",
        scientific_supporting_candidate_count=0,
        observations=("The bounded path produced measurable candidates.",),
        interpretations=("No biological promotion can be inferred.",),
        alternative_explanations=("The development sample is underpowered.",),
        uncertainties=("Scientific candidate quality remains unresolved.",),
        falsifiers_or_next_measurements=("Run a formally approved Pilot after Phase 2 freeze.",),
        evidence_refs=("synthetic:pilot-measurement",),
        test_only_control_flow_fixture=True,
    )
    diagnosis = build_pilot_diagnosis(
        measurement=measurement,
        hypotheses=(
            PilotDiagnosisHypothesis(
                category="insufficient-evidence",
                status="SUPPORTED",
                observations=("Only two validation candidates were measured.",),
                implications=("No scientific promotion can be inferred.",),
                evidence_refs=("synthetic:pilot-measurement",),
            ),
        ),
        conclusion=("The validation Pilot is scientifically inconclusive.",),
        uncertainties=("Production candidate behavior is unknown.",),
        evidence_refs=("synthetic:pilot-measurement",),
        confidence="INCONCLUSIVE",
    )
    assert diagnosis.arm_summaries[0].development_score_median == 0.7
    assert diagnosis.arm_summaries[0].development_score_top_quartile_mean == 0.8
    dossier = build_pilot_dossier(
        project_id="soluble",
        pilot_run_id="pilot-validation-1",
        upstream_fixture=fixture,
        execution_authority=ValidationExecutionAuthority(
            authority_id="validation-overlay-1",
            fixture_id=fixture.fixture_id,
            reason="Exercise downstream state transitions with bounded compute.",
        ),
        measurement=measurement,
        diagnosis=diagnosis,
        proposed_interpretation=recommendation,
        evidence_refs=("project:pilot-measurement.json#sha256=" + "e" * 64,),
    )
    assessment = PilotJudgeAssessment(
        assessment_id="pilot-judge-1",
        dossier_sha256=canonical_model_sha256(dossier),
        verdict="ready-to-ask",
        recommendation="PROMOTE_TO_SCALE",
        reasons=("Control-flow evidence is internally consistent.",),
        limitations=("No scientific promotion evidence exists.",),
        evidence_refs=("project:pilot-dossier.json#sha256=" + "f" * 64,),
    )
    card = build_gate4_card(dossier=dossier, assessment=assessment)
    assert card.gate_type == "pilot-promotion"
    assert card.option_id == "PROMOTE_TO_SCALE"
    assert card.judge_status == "SUPPORTED"
    assert card.scientific_summary["test_only_control_flow_fixture"] is True
    assert "not a scientific promotion" in card.warnings[0]


def test_gate4_card_rejects_stale_judge_binding() -> None:
    with pytest.raises(ValidationError):
        PilotJudgeAssessment(
            assessment_id="judge",
            dossier_sha256="a" * 64,
            verdict="insufficient",
            recommendation="PROMOTE_TO_SCALE",
            reasons=("Evidence is insufficient.",),
            limitations=("No complete Pilot.",),
            evidence_refs=("synthetic:evidence",),
        )
