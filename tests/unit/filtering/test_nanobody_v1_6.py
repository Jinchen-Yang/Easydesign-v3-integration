from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from easydesign.core import ArtifactRef, ManifestStateError
from easydesign.filtering import (
    PROFILE_SOURCE_SHA256_V1_6,
    build_advisory_validation_report,
    evaluate_pilot_candidates_v1_6,
    promotion_records,
)
from easydesign.filtering.structure_metrics import InterfaceMetricValues
from easydesign.stages.s04_pilot_generation import CandidateRecord
from easydesign.stages.s05_pilot_filtering import (
    ExpansionCandidateRecord,
    FilterDecision,
    FullTargetPredictionRecord,
    StrategyTier,
)

NOW = datetime(2026, 7, 31, 8, 0, tzinfo=UTC)


def _artifact(identifier: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=identifier,
        role="candidate-structure",
        relative_path=f"candidates/{identifier}.cif",
        file_format="mmcif",
        size_bytes=10,
        sha256="a" * 64,
        producer_stage="04-pilot-generation",
        producer_attempt="attempt-0001",
    )


def _candidate(
    strategy_number: int,
    ordinal: int,
    *,
    final_gate_pass: bool,
) -> CandidateRecord:
    strategy_id = f"strategy-{strategy_number:02d}"
    candidate_id = f"{strategy_id}-{ordinal:02d}"
    sequence = (
        "ACDEFGHIKLMNPQRSTVWY"
        if ordinal == 1
        else "YWVTSRQPNMLKIHGFEDCA"
    )
    return CandidateRecord(
        candidate_id=candidate_id,
        backend_candidate_id=candidate_id,
        strategy_id=strategy_id,
        task_id=f"pilot-{strategy_id}",
        task_attempt_number=1,
        ordinal_within_strategy=ordinal,
        original_structure=_artifact(f"{candidate_id}-original"),
        refolded_structure=_artifact(f"{candidate_id}-refold"),
        pass_filters=True,
        metrics={
            "pass_filters": True,
            "designed_chain_sequence": sequence,
            "design_to_target_iptm": 0.75 if final_gate_pass else 0.40,
            "min_design_to_target_pae": 6.0 if final_gate_pass else 12.0,
            "filter_rmsd": 1.0,
            "filter_rmsd_design": 1.0,
            "design_ptm": 0.85,
            "delta_sasa_refolded": 800.0,
        },
    )


def _structure() -> InterfaceMetricValues:
    return InterfaceMetricValues(
        target_ca_rmsd_angstrom=1.0,
        hotspot_coverage=0.8,
        contacted_hotspot_count=2,
        hotspot_count=3,
        binder_contact_coverage=0.4,
        cdr_dominance=0.7,
        cdr_utilization=0.5,
        residue_pair_contact_count=20,
        atom_contact_count=80,
        severe_clash_count=0,
        moderate_clash_count=1,
        hydrogen_bond_count=4,
        salt_bridge_count=1,
        polar_contact_fraction=0.3,
        interface_bsa_angstrom2=900.0,
        interface_bsa_missing_reason=None,
    )


@pytest.mark.parametrize(
    ("tier_a_count", "expected_promoted"),
    (
        (0, 0),
        (1, 1),
        (2, 2),
        (3, 3),
        (4, 3),
    ),
)
def test_v1_6_promotes_only_top_three_tier_a(
    tier_a_count: int,
    expected_promoted: int,
) -> None:
    candidates = tuple(
        _candidate(
            strategy_number,
            ordinal,
            final_gate_pass=strategy_number <= tier_a_count,
        )
        for strategy_number in range(1, 5)
        for ordinal in (1, 2)
    )
    report = evaluate_pilot_candidates_v1_6(
        candidates=candidates,
        structural_metrics={
            candidate.candidate_id: _structure() for candidate in candidates
        },
        candidate_index_sha256="f" * 64,
        maximum_tier_a_strategies=3,
        generated_at=NOW,
    )

    assert len(report.promoted_strategy_ids) == expected_promoted
    assert report.status == (
        "strategies-promoted" if expected_promoted else "stopped-no-tier-a"
    )
    assert all(
        summary.tier is StrategyTier.A
        for summary in report.strategy_summaries
        if summary.strategy_id in report.promoted_strategy_ids
    )
    assert not any(
        summary.selected_for_expansion and summary.tier is not StrategyTier.A
        for summary in report.strategy_summaries
    )


def _decision(*, passed: bool) -> tuple[FilterDecision, ...]:
    return (
        FilterDecision(
            rule_id="structure-gate",
            metric_id="binder-pose-rmsd",
            operator="le",
            threshold=3.0,
            observed=18.0 if not passed else 2.0,
            passed=passed,
            reason="fixture",
        ),
    )


def _prediction(
    candidate_id: str,
    strategy_id: str,
    *,
    passed: bool,
) -> FullTargetPredictionRecord:
    return FullTargetPredictionRecord(
        candidate_id=candidate_id,
        strategy_id=strategy_id,
        predicted_structure=_artifact(f"{candidate_id}-predicted"),
        summary_confidence=_artifact(f"{candidate_id}-summary"),
        full_confidence=_artifact(f"{candidate_id}-confidence"),
        pairwise_iptm=0.30,
        minimum_interface_pae_angstrom=18.0,
        binder_ptm=0.60,
        binder_pose_rmsd_angstrom=18.0 if not passed else 2.0,
        target_ca_rmsd_angstrom=1.0,
        severe_clash_count=0,
        moderate_clash_count=1,
        structure_gate_decisions=_decision(passed=passed),
        structure_gate_pass=passed,
        confidence_reference_pass=False,
        confidence_label="low-confidence",
    )


def test_full_target_evidence_does_not_gate_features_by_scientific_label() -> None:
    payload = _prediction(
        "candidate-configured",
        "strategy-configured",
        passed=True,
    ).model_dump()
    payload.update(
        template_mode="precomputed",
        binder_unpaired_msa_mode="remote",
        target_template_data_sha256="a" * 64,
        binder_template_data_sha256="b" * 64,
    )

    record = FullTargetPredictionRecord.model_validate(payload)

    assert record.scientific_mode == "de-novo"
    assert record.template_mode == "precomputed"
    assert record.binder_unpaired_msa_mode == "remote"


def test_full_target_zero_pass_is_warning_and_does_not_revoke_promotion() -> None:
    pilot_candidates = tuple(
        _candidate(1, ordinal, final_gate_pass=True) for ordinal in (1, 2)
    )
    pilot_report = evaluate_pilot_candidates_v1_6(
        candidates=pilot_candidates,
        structural_metrics={
            candidate.candidate_id: _structure() for candidate in pilot_candidates
        },
        candidate_index_sha256="e" * 64,
        maximum_tier_a_strategies=3,
        generated_at=NOW,
    )
    promotions = promotion_records(pilot_report)
    expanded = (
        ExpansionCandidateRecord(
            candidate_id="expanded-01",
            strategy_id=promotions[0].strategy_id,
            sequence="ACDEFGHIKLMN",
            sequence_sha256=hashlib.sha256(b"ACDEFGHIKLMN").hexdigest(),
            local_gate_decisions=_decision(passed=True),
            local_gate_pass=True,
            score_expand_structure=0.8,
            selected_for_full_target=True,
        ),
    )
    report = build_advisory_validation_report(
        promoted_strategies=promotions,
        expanded_total_per_strategy=1,
        full_target_top_n=1,
        candidates=expanded,
        predictions=(
            _prediction(
                "expanded-01",
                promotions[0].strategy_id,
                passed=False,
            ),
        ),
        generated_at=NOW,
    )

    assert report.status == "diagnostics-complete"
    assert report.promoted_strategies == promotions
    assert report.strategies[0].advisory_status == "advisory-warning"
    assert report.strategies[0].full_target_structure_pass_count == 0
    assert {
        warning.code for warning in report.warnings
    } == {
        "full-target-structure-gate-zero-pass",
        "full-target-confidence-low",
    }


def test_missing_diagnostic_candidate_is_operational_failure() -> None:
    pilot_candidates = tuple(
        _candidate(1, ordinal, final_gate_pass=True) for ordinal in (1, 2)
    )
    pilot_report = evaluate_pilot_candidates_v1_6(
        candidates=pilot_candidates,
        structural_metrics={
            candidate.candidate_id: _structure() for candidate in pilot_candidates
        },
        candidate_index_sha256="d" * 64,
        maximum_tier_a_strategies=3,
        generated_at=NOW,
    )
    with pytest.raises(ManifestStateError, match="未达到 100"):
        build_advisory_validation_report(
            promoted_strategies=promotion_records(pilot_report),
            expanded_total_per_strategy=100,
            full_target_top_n=10,
            candidates=(),
            predictions=(),
            generated_at=NOW,
        )


def test_v1_6_profile_records_exact_method_document_hash() -> None:
    repository_root = Path(__file__).parents[3]
    method_path = (
        repository_root / "docs/NANOBODY_FILTER_STANDARD_V1.6.md"
    )
    assert hashlib.sha256(method_path.read_bytes()).hexdigest() == (
        PROFILE_SOURCE_SHA256_V1_6
    )
