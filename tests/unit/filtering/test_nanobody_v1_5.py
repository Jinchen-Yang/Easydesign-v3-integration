from __future__ import annotations

from datetime import UTC, datetime

from easydesign.core import ArtifactRef
from easydesign.filtering import (
    PROFILE_SOURCE_SHA256,
    evaluate_expansion_candidates,
    evaluate_pilot_candidates,
    select_scale_strategy,
)
from easydesign.filtering.structure_metrics import InterfaceMetricValues
from easydesign.stages.s04_pilot_generation import CandidateRecord
from easydesign.stages.s05_pilot_filtering import (
    FilterDecision,
    FullTargetPredictionRecord,
    StrategyTier,
)

NOW = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)


def _artifact(identifier: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=identifier,
        role="candidate-structure",
        relative_path=f"candidates/{identifier}.cif",
        file_format="mmcif",
        size_bytes=10,
        sha256=(identifier[0] if identifier[0] in "abcdef" else "a") * 64,
        producer_stage="04-pilot-generation",
        producer_attempt="attempt-0001",
    )


def _candidate(
    identifier: str,
    strategy: str,
    sequence: str,
    *,
    pass_filters: bool,
    iptm: float,
    pae: float,
) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=identifier,
        backend_candidate_id=identifier,
        strategy_id=strategy,
        task_id=f"pilot-{strategy}",
        task_attempt_number=1,
        ordinal_within_strategy=int(identifier.rsplit("-", maxsplit=1)[-1]),
        original_structure=_artifact(f"{identifier}-original"),
        refolded_structure=_artifact(f"{identifier}-refold"),
        pass_filters=pass_filters,
        metrics={
            "pass_filters": pass_filters,
            "designed_chain_sequence": sequence,
            "design_to_target_iptm": iptm,
            "min_design_to_target_pae": pae,
            "filter_rmsd": 1.0,
            "filter_rmsd_design": 1.0,
            "design_ptm": 0.85,
            "delta_sasa_refolded": 800.0,
        },
    )


def _structure(*, hotspot: float, target_rmsd: float = 1.0) -> InterfaceMetricValues:
    return InterfaceMetricValues(
        target_ca_rmsd_angstrom=target_rmsd,
        hotspot_coverage=hotspot,
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


def test_pilot_filter_assigns_tier_a_and_does_not_fill_with_lower_tiers() -> None:
    candidates = (
        _candidate(
            "strategy-one-1",
            "strategy-one",
            "ACDEFG",
            pass_filters=True,
            iptm=0.7,
            pae=6.0,
        ),
        _candidate(
            "strategy-one-2",
            "strategy-one",
            "HIKLMN",
            pass_filters=True,
            iptm=0.8,
            pae=5.0,
        ),
        _candidate(
            "strategy-two-1",
            "strategy-two",
            "PQRSTV",
            pass_filters=True,
            iptm=0.4,
            pae=12.0,
        ),
        _candidate(
            "strategy-two-2",
            "strategy-two",
            "WYACDE",
            pass_filters=True,
            iptm=0.4,
            pae=12.0,
        ),
    )
    report = evaluate_pilot_candidates(
        candidates=candidates,
        structural_metrics={
            candidate.candidate_id: _structure(hotspot=0.8)
            for candidate in candidates
        },
        profile_sha256=PROFILE_SOURCE_SHA256,
        candidate_index_sha256="f" * 64,
        maximum_tier_a_strategies=3,
        generated_at=NOW,
    )

    assert report.status == "tier-a-selected"
    assert report.selected_strategy_ids == ("strategy-one",)
    assert report.strategy_summaries[0].tier is StrategyTier.A
    assert report.strategy_summaries[0].final_gate_pass_count == 2
    assert report.strategy_summaries[1].tier is StrategyTier.C
    assert report.strategy_summaries[1].boltzgen_hard_pass_count == 2
    assert not report.strategy_summaries[1].selected_for_expansion


def test_duplicate_sequence_is_not_counted_as_independent_pass() -> None:
    candidates = (
        _candidate(
            "strategy-one-1",
            "strategy-one",
            "ACDEFG",
            pass_filters=True,
            iptm=0.8,
            pae=5.0,
        ),
        _candidate(
            "strategy-one-2",
            "strategy-one",
            "ACDEFG",
            pass_filters=True,
            iptm=0.8,
            pae=5.0,
        ),
    )
    report = evaluate_pilot_candidates(
        candidates=candidates,
        structural_metrics={
            candidate.candidate_id: _structure(hotspot=0.8)
            for candidate in candidates
        },
        profile_sha256=PROFILE_SOURCE_SHA256,
        candidate_index_sha256="e" * 64,
        maximum_tier_a_strategies=3,
        generated_at=NOW,
    )

    assert report.status == "stopped-no-tier-a"
    assert report.strategy_summaries[0].tier is StrategyTier.B
    assert report.strategy_summaries[0].unique_sequence_count == 1
    duplicates = [record for record in report.candidate_records if record.duplicate_of]
    assert len(duplicates) == 1


def test_duplicate_representative_prefers_a_valid_conformation() -> None:
    candidates = (
        _candidate(
            "strategy-one-1",
            "strategy-one",
            "ACDEFG",
            pass_filters=False,
            iptm=0.85,
            pae=3.0,
        ),
        _candidate(
            "strategy-one-2",
            "strategy-one",
            "ACDEFG",
            pass_filters=True,
            iptm=0.50,
            pae=10.0,
        ),
    )
    report = evaluate_pilot_candidates(
        candidates=candidates,
        structural_metrics={
            candidate.candidate_id: _structure(hotspot=0.8)
            for candidate in candidates
        },
        profile_sha256=PROFILE_SOURCE_SHA256,
        candidate_index_sha256="d" * 64,
        maximum_tier_a_strategies=3,
        generated_at=NOW,
    )

    by_id = {record.candidate_id: record for record in report.candidate_records}
    assert by_id["strategy-one-2"].duplicate_of is None
    assert by_id["strategy-one-2"].eligible_unique_pass
    assert by_id["strategy-one-1"].duplicate_of == "strategy-one-2"


def _prediction(
    candidate_id: str,
    strategy_id: str,
    *,
    passed: bool,
    pose_rmsd: float,
) -> FullTargetPredictionRecord:
    decisions = (
        FilterDecision(
            rule_id="binder-pose",
            metric_id="binder-pose-rmsd",
            operator="le",
            threshold=3.0,
            observed=pose_rmsd,
            passed=passed,
            reason="fixture",
        ),
    )
    return FullTargetPredictionRecord(
        candidate_id=candidate_id,
        strategy_id=strategy_id,
        predicted_structure=_artifact(f"{candidate_id}-predicted"),
        summary_confidence=_artifact(f"{candidate_id}-summary"),
        full_confidence=_artifact(f"{candidate_id}-full"),
        pairwise_iptm=0.6,
        minimum_interface_pae_angstrom=8.0,
        binder_ptm=0.7,
        binder_pose_rmsd_angstrom=pose_rmsd,
        target_ca_rmsd_angstrom=1.0,
        severe_clash_count=0,
        moderate_clash_count=1,
        structure_gate_decisions=decisions,
        structure_gate_pass=passed,
        confidence_reference_pass=True,
        confidence_label="reference-supported",
    )


def test_expansion_selects_only_local_passes_and_one_scale_winner() -> None:
    candidates = (
        _candidate(
            "strategy-one-1",
            "strategy-one",
            "ACDEFG",
            pass_filters=True,
            iptm=0.8,
            pae=5.0,
        ),
        _candidate(
            "strategy-one-2",
            "strategy-one",
            "HIKLMN",
            pass_filters=True,
            iptm=0.7,
            pae=6.0,
        ),
        _candidate(
            "strategy-two-1",
            "strategy-two",
            "PQRSTV",
            pass_filters=True,
            iptm=0.8,
            pae=5.0,
        ),
        _candidate(
            "strategy-two-2",
            "strategy-two",
            "WYACDE",
            pass_filters=True,
            iptm=0.7,
            pae=6.0,
        ),
    )
    expanded = evaluate_expansion_candidates(
        candidates=candidates,
        structural_metrics={
            candidate.candidate_id: _structure(hotspot=0.8)
            for candidate in candidates
        },
        full_target_top_n=1,
    )
    selected = tuple(
        item for item in expanded if item.selected_for_full_target
    )
    assert len(selected) == 2

    report = select_scale_strategy(
        expanded_total_per_strategy=2,
        full_target_top_n=1,
        candidates=expanded,
        predictions=(
            _prediction(
                selected[0].candidate_id,
                selected[0].strategy_id,
                passed=True,
                pose_rmsd=1.5,
            ),
            _prediction(
                selected[1].candidate_id,
                selected[1].strategy_id,
                passed=False,
                pose_rmsd=4.0,
            ),
        ),
        generated_at=NOW,
    )

    assert report.status == "winner-selected"
    assert report.winner_strategy_id == selected[0].strategy_id


def test_expansion_stops_when_best_strategies_are_scientifically_tied() -> None:
    candidates = (
        _candidate(
            "strategy-one-1",
            "strategy-one",
            "ACDEFG",
            pass_filters=True,
            iptm=0.8,
            pae=5.0,
        ),
        _candidate(
            "strategy-two-1",
            "strategy-two",
            "HIKLMN",
            pass_filters=True,
            iptm=0.8,
            pae=5.0,
        ),
    )
    expanded = evaluate_expansion_candidates(
        candidates=candidates,
        structural_metrics={
            candidate.candidate_id: _structure(hotspot=0.8)
            for candidate in candidates
        },
        full_target_top_n=1,
    )
    report = select_scale_strategy(
        expanded_total_per_strategy=1,
        full_target_top_n=1,
        candidates=expanded,
        predictions=tuple(
            _prediction(
                item.candidate_id,
                item.strategy_id,
                passed=True,
                pose_rmsd=1.5,
            )
            for item in expanded
        ),
        generated_at=NOW,
    )

    assert report.status == "stopped-no-scale-winner"
    assert report.winner_strategy_id is None
    assert not any(item.winner for item in report.strategies)
