from __future__ import annotations

from datetime import UTC, datetime

from easydesign.core import ArtifactRef
from easydesign.filtering import (
    FullPredictionEvidence,
    build_multi_seed_consensus,
    evaluate_sequence_prefilter,
    final_prediction_decisions,
    final_prediction_metrics,
    lazy_greedy_select,
    score_full_prediction_evidence,
)
from easydesign.filtering.structure_metrics import InterfaceMetricValues
from easydesign.stages.s04_pilot_generation import CandidateRecord
from easydesign.stages.s07_final_filtering_and_selection import (
    DevelopabilityRisk,
    FinalPredictionRecord,
    SeedPairConsistency,
    TnpCandidateRecord,
)

NOW = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)


def _artifact(identifier: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=identifier,
        role="fixture",
        relative_path=f"fixture/{identifier}.cif",
        file_format="mmcif",
        size_bytes=1,
        sha256="a" * 64,
        producer_stage="06-scale-generation-and-refolding",
        producer_attempt="attempt-0001",
    )


def _candidate(identifier: str, sequence: str, ordinal: int) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=identifier,
        backend_candidate_id=identifier,
        strategy_id="generic-strategy",
        task_id="scale-generic-strategy",
        task_attempt_number=1,
        ordinal_within_strategy=ordinal,
        original_structure=_artifact(f"{identifier}-original"),
        refolded_structure=_artifact(f"{identifier}-refold"),
        design_mask_source=_artifact(f"{identifier}-mask"),
        designed_binder_residue_ids=(2,),
        pass_filters=True,
        metrics={
            "designed_chain_sequence": sequence,
            "designed_sequence": sequence[1:2],
            "design_to_target_iptm": 0.75,
            "min_design_to_target_pae": 5.0,
            "filter_rmsd": 1.0,
            "filter_rmsd_design": 1.0,
            "design_ptm": 0.85,
        },
    )


def _interface(*, bsa: float = 900.0) -> InterfaceMetricValues:
    return InterfaceMetricValues(
        target_ca_rmsd_angstrom=1.0,
        hotspot_coverage=0.75,
        contacted_hotspot_count=3,
        hotspot_count=4,
        binder_contact_coverage=0.60,
        cdr_dominance=0.80,
        cdr_utilization=0.70,
        residue_pair_contact_count=24,
        atom_contact_count=96,
        severe_clash_count=0,
        moderate_clash_count=1,
        hydrogen_bond_count=5,
        salt_bridge_count=2,
        polar_contact_fraction=0.40,
        interface_bsa_angstrom2=bsa,
        interface_bsa_missing_reason=None,
    )


def _evidence(candidate_id: str, seed: int, *, bsa: float = 900.0) -> FullPredictionEvidence:
    return FullPredictionEvidence(
        candidate_id=candidate_id,
        seed=seed,
        pairwise_iptm=0.75,
        minimum_interface_pae_angstrom=5.0,
        binder_ptm=0.80,
        binder_pose_rmsd_angstrom=1.0,
        target_ca_rmsd_angstrom=1.0,
        contacted_hotspot_residue_ids=(1, 2, 3),
        interface=_interface(bsa=bsa),
    )


def _prediction(
    candidate_id: str,
    seed: int,
    score: float,
) -> FinalPredictionRecord:
    evidence = _evidence(candidate_id, seed)
    seed101_decisions = final_prediction_decisions(evidence, consensus=False)
    consensus_decisions = final_prediction_decisions(evidence, consensus=True)
    return FinalPredictionRecord(
        candidate_id=candidate_id,
        seed=seed,  # type: ignore[arg-type]
        predicted_structure=_artifact(f"{candidate_id}-s{seed}-structure"),
        summary_confidence=_artifact(f"{candidate_id}-s{seed}-summary"),
        full_confidence=_artifact(f"{candidate_id}-s{seed}-full"),
        pairwise_iptm=evidence.pairwise_iptm,
        minimum_interface_pae_angstrom=evidence.minimum_interface_pae_angstrom,
        binder_ptm=evidence.binder_ptm,
        binder_pose_rmsd_angstrom=evidence.binder_pose_rmsd_angstrom,
        target_ca_rmsd_angstrom=evidence.target_ca_rmsd_angstrom,
        hotspot_coverage=evidence.interface.hotspot_coverage,
        contacted_hotspot_residue_ids=evidence.contacted_hotspot_residue_ids,
        severe_clash_count=0,
        moderate_clash_count=1,
        metrics=final_prediction_metrics(evidence),
        seed101_gate_decisions=seed101_decisions,
        seed101_gate_pass=True,
        consensus_gate_decisions=consensus_decisions,
        consensus_seed_pass=True,
        score_full=score,
    )


def _tnp(candidate_id: str, risk: DevelopabilityRisk) -> TnpCandidateRecord:
    medium = risk is DevelopabilityRisk.MEDIUM
    return TnpCandidateRecord(
        candidate_id=candidate_id,
        total_cdr_length=30,
        cdr3_length=12,
        cdr3_compactness=0.75,
        psh=0.2,
        ppc=0.1,
        pnc=0.1,
        flags={
            "L": "green",
            "L3": "green",
            "C": "green",
            "PSH": "amber" if medium else "green",
            "PPC": "amber" if medium else "green",
            "PNC": "green",
        },
        red_flag_count=0,
        amber_flag_count=2 if medium else 0,
        risk=risk,
    )


def test_sequence_prefilter_keeps_all_dispositions_and_one_duplicate_representative() -> None:
    candidates = (
        _candidate("candidate-good", "ACDEFG", 1),
        _candidate("candidate-duplicate", "ACDEFG", 2),
        _candidate("candidate-unknown", "ACXEFG", 3),
        _candidate("candidate-cys", "HIKLMN", 4),
    )
    records = evaluate_sequence_prefilter(
        candidates=candidates,
        unpaired_new_cysteines={
            "candidate-good": (),
            "candidate-duplicate": (),
            "candidate-unknown": (),
            "candidate-cys": (2,),
        },
    )
    by_id = {item.candidate_id: item for item in records}

    assert tuple(item.candidate_id for item in records) == tuple(
        item.candidate_id for item in candidates
    )
    duplicate_pair = (by_id["candidate-good"], by_id["candidate-duplicate"])
    assert sum(item.selected_for_deep for item in duplicate_pair) == 1
    assert sum(item.duplicate_of is not None for item in duplicate_pair) == 1
    assert by_id["candidate-unknown"].unknown_residue_count == 1
    assert by_id["candidate-cys"].unpaired_new_cysteine_residue_ids == (2,)


def test_seed101_empirical_reference_is_frozen_for_additional_seeds() -> None:
    initial = (
        _evidence("candidate-one", 101, bsa=800.0),
        _evidence("candidate-two", 101, bsa=1000.0),
    )
    initial_scores, reference = score_full_prediction_evidence(
        evidence=initial,
        score_refold_by_candidate={"candidate-one": 0.7, "candidate-two": 0.8},
    )
    additional_scores, reused = score_full_prediction_evidence(
        evidence=(
            _evidence("candidate-one", 202, bsa=900.0),
            _evidence("candidate-two", 303, bsa=1200.0),
        ),
        score_refold_by_candidate={"candidate-one": 0.7, "candidate-two": 0.8},
        seed101_reference=reference,
    )

    assert reference == reused
    assert set(reference) == {
        "interface_bsa",
        "residue_pair_contact_density",
        "atom_contact_density",
        "hydrogen_bond_density",
        "salt_bridge_density",
    }
    assert all(0.0 <= value <= 1.0 for value in initial_scores.values())
    assert all(0.0 <= value <= 1.0 for value in additional_scores.values())


def test_multi_seed_consensus_requires_a_passing_consistent_pair() -> None:
    predictions = tuple(
        _prediction("candidate-one", seed, score)
        for seed, score in ((101, 0.80), (202, 0.78), (303, 0.76))
    )
    passed = build_multi_seed_consensus(
        candidate_id="candidate-one",
        predictions=predictions,
        score_deep=0.70,
        pair_metrics=(
            SeedPairConsistency(
                first_seed=101,
                second_seed=202,
                binder_ca_rmsd_angstrom=1.5,
                hotspot_contact_jaccard=0.8,
                passed=True,
            ),
        ),
    )
    failed = build_multi_seed_consensus(
        candidate_id="candidate-one",
        predictions=predictions[:1],
        score_deep=0.70,
        pair_metrics=(),
    )

    assert passed.consensus_pass
    assert passed.consensus_seed_ids == (101, 202)
    assert passed.score_final is not None
    assert not failed.consensus_pass
    assert failed.score_final is None


def test_openfold3_consensus_requires_three_individually_passing_consistent_seeds() -> None:
    predictions = tuple(
        _prediction("candidate-one", seed, score)
        for seed, score in (
            (101, 0.82),
            (202, 0.80),
            (303, 0.78),
            (404, 0.76),
            (505, 0.74),
        )
    )
    pair_101_202 = SeedPairConsistency(
        first_seed=101,
        second_seed=202,
        binder_ca_rmsd_angstrom=1.0,
        hotspot_contact_jaccard=0.8,
        passed=True,
    )
    insufficient = build_multi_seed_consensus(
        candidate_id="candidate-one",
        predictions=predictions,
        score_deep=0.70,
        pair_metrics=(pair_101_202,),
        required_individually_passing_seeds=3,
    )
    sufficient = build_multi_seed_consensus(
        candidate_id="candidate-one",
        predictions=predictions,
        score_deep=0.70,
        pair_metrics=(
            pair_101_202,
            SeedPairConsistency(
                first_seed=202,
                second_seed=303,
                binder_ca_rmsd_angstrom=1.2,
                hotspot_contact_jaccard=0.7,
                passed=True,
            ),
        ),
        required_individually_passing_seeds=3,
    )

    assert not insufficient.consensus_pass
    assert insufficient.required_individually_passing_seeds == 3
    assert sufficient.consensus_pass
    assert sufficient.consensus_seed_ids == (101, 202, 303)


def test_lazy_greedy_selection_is_quality_first_and_never_fills_past_available() -> None:
    first = build_multi_seed_consensus(
        candidate_id="candidate-one",
        predictions=tuple(
            _prediction("candidate-one", seed, score)
            for seed, score in ((101, 0.85), (202, 0.83), (303, 0.81))
        ),
        score_deep=0.80,
        pair_metrics=(
            SeedPairConsistency(
                first_seed=101,
                second_seed=202,
                binder_ca_rmsd_angstrom=1.0,
                hotspot_contact_jaccard=1.0,
                passed=True,
            ),
        ),
    )
    second = build_multi_seed_consensus(
        candidate_id="candidate-two",
        predictions=tuple(
            _prediction("candidate-two", seed, score)
            for seed, score in ((101, 0.70), (202, 0.69), (303, 0.68))
        ),
        score_deep=0.70,
        pair_metrics=(
            SeedPairConsistency(
                first_seed=101,
                second_seed=202,
                binder_ca_rmsd_angstrom=1.0,
                hotspot_contact_jaccard=1.0,
                passed=True,
            ),
        ),
    )
    selected = lazy_greedy_select(
        consensus=(first, second),
        tnp=(
            _tnp("candidate-one", DevelopabilityRisk.LOW),
            _tnp("candidate-two", DevelopabilityRisk.MEDIUM),
        ),
        design_sequences={
            "candidate-one": "ACDEFG",
            "candidate-two": "HIKLMN",
        },
        primary_count=20,
        backup_count=20,
    )

    assert len(selected) == 2
    assert selected[0].candidate_id == "candidate-one"
    assert all(item.selection_class == "primary" for item in selected)
