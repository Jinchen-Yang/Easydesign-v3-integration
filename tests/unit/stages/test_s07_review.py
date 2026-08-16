from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import gemmi

from easydesign.core import ArtifactRef
from easydesign.stages.s04_pilot_generation import CandidateRecord
from easydesign.stages.s07_final_filtering_and_selection import (
    DeepFilterRecord,
    RawFinalPrediction,
    Stage07AdvisoryComparisonProfile,
    build_stage07_prediction_comparison_report,
    build_stage07_review_cohort,
)


def _pdb_line(
    serial: int,
    *,
    chain: str,
    residue: int,
    x: float,
    y: float,
    z: float,
) -> str:
    return (
        f"ATOM  {serial:5d}  CA  ALA {chain}{residue:4d}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00 20.00           C  \n"
    )


def _complex(root: Path, name: str, binder_offset: float = 0.0) -> ArtifactRef:
    pdb = root / f"{name}.pdb"
    pdb.write_text(
        "".join(
            (
                _pdb_line(1, chain="A", residue=1, x=0, y=0, z=0),
                _pdb_line(2, chain="A", residue=2, x=10, y=0, z=0),
                _pdb_line(3, chain="A", residue=3, x=20, y=0, z=0),
                _pdb_line(4, chain="B", residue=1, x=0, y=4 + binder_offset, z=0),
                _pdb_line(5, chain="B", residue=2, x=10, y=4 + binder_offset, z=0),
                _pdb_line(6, chain="B", residue=3, x=20, y=4 + binder_offset, z=0),
                "TER\n",
                "END\n",
            )
        ),
        encoding="ascii",
    )
    structure = gemmi.read_structure(str(pdb))
    for chain in structure[0]:
        for label_seq_id, residue in enumerate(chain, start=1):
            residue.label_seq = label_seq_id
    cif = root / f"{name}.cif"
    structure.make_mmcif_document().write_file(str(cif))
    return ArtifactRef.from_file(
        run_root=root,
        relative_path=cif.name,
        artifact_id=f"{name}-structure",
        role="test-structure",
        file_format="mmcif",
    )


def _candidate(candidate_id: str, structure: ArtifactRef) -> CandidateRecord:
    return CandidateRecord.model_construct(
        candidate_id=candidate_id,
        strategy_id="strategy-a",
        refolded_structure=structure,
    )


def _deep(candidate_id: str, score: float) -> DeepFilterRecord:
    return DeepFilterRecord(
        candidate_id=candidate_id,
        metrics=(),
        decisions=(),
        absolute_gate_pass=True,
        score_deep=score,
        selected_for_seed101=True,
    )


def _prediction(
    candidate_id: str,
    *,
    mode: str,
    seed: int,
    sample_index: int,
    ranking_score: float,
    structure: ArtifactRef,
    backend_identity: str = "test-backend@1",
) -> RawFinalPrediction:
    return RawFinalPrediction.model_construct(
        candidate_id=candidate_id,
        scientific_mode=mode,
        seed=seed,
        sample_index=sample_index,
        ranking_score=ranking_score,
        is_seed_representative=True,
        backend_identity=backend_identity,
        model_identity="test-model",
        release_identity={},
        template_mode="disabled" if mode == "de-novo" else "precomputed",
        target_condition_sha256=None if mode == "de-novo" else "a" * 64,
        predicted_structure=structure,
        contacted_hotspot_residue_ids=(1, 2),
    )


def test_review_cohort_is_deterministic_and_never_pads(tmp_path: Path) -> None:
    structure = _complex(tmp_path, "source")
    candidates = {
        item: _candidate(item, structure) for item in ("candidate-a", "candidate-b")
    }
    cohort = build_stage07_review_cohort(
        deep_records=(
            _deep("candidate-b", 0.8),
            _deep("candidate-a", 0.8),
        ),
        candidates=candidates,
        requested_size=200,
        profile_sha256="1" * 64,
        candidate_index_sha256="2" * 64,
        generated_at=datetime.now(UTC),
    )

    assert cohort.actual_size == 2
    assert tuple(item.candidate_id for item in cohort.entries) == (
        "candidate-a",
        "candidate-b",
    )
    assert tuple(item.review_rank for item in cohort.entries) == (1, 2)


def test_best_ranked_and_matched_seed_pairs_are_separate(tmp_path: Path) -> None:
    source = _complex(tmp_path, "source")
    de_novo = _complex(tmp_path, "de-novo")
    conditioned = _complex(tmp_path, "conditioned", binder_offset=1.0)
    cohort = build_stage07_review_cohort(
        deep_records=(_deep("candidate-a", 0.9),),
        candidates={"candidate-a": _candidate("candidate-a", source)},
        requested_size=200,
        profile_sha256="1" * 64,
        candidate_index_sha256="2" * 64,
        generated_at=datetime.now(UTC),
    )
    report = build_stage07_prediction_comparison_report(
        root=tmp_path,
        cohort=cohort,
        cohort_sha256="3" * 64,
        de_novo_predictions=(
            _prediction(
                "candidate-a",
                mode="de-novo",
                seed=101,
                sample_index=0,
                ranking_score=0.9,
                structure=de_novo,
            ),
            _prediction(
                "candidate-a",
                mode="de-novo",
                seed=202,
                sample_index=1,
                ranking_score=0.9,
                structure=de_novo,
            ),
        ),
        target_conditioned_predictions=(
            _prediction(
                "candidate-a",
                mode="target-conditioned",
                seed=101,
                sample_index=0,
                ranking_score=0.7,
                structure=conditioned,
                backend_identity="openfold3-af3-jax@afo-test",
            ),
            _prediction(
                "candidate-a",
                mode="target-conditioned",
                seed=202,
                sample_index=1,
                ranking_score=0.95,
                structure=conditioned,
                backend_identity="openfold3-af3-jax@afo-test",
            ),
        ),
        generated_at=datetime.now(UTC),
    )

    default = next(item for item in report.comparisons if item.pair_kind == "best-ranked")
    matched = [
        item
        for item in report.comparisons
        if item.pair_kind == "matched-seed-representative"
    ]
    assert (default.de_novo.seed, default.target_conditioned.seed) == (101, 202)
    assert default.matched_seed is False
    assert default.de_novo.backend_identity == "test-backend@1"
    assert default.target_conditioned.backend_identity == "openfold3-af3-jax@afo-test"
    assert {item.de_novo.seed for item in matched} == {101, 202}
    assert all(item.matched_seed for item in matched)


def test_optional_profile_is_advisory_only(tmp_path: Path) -> None:
    source = _complex(tmp_path, "source")
    predicted = _complex(tmp_path, "predicted")
    cohort = build_stage07_review_cohort(
        deep_records=(_deep("candidate-a", 0.9),),
        candidates={"candidate-a": _candidate("candidate-a", source)},
        requested_size=1,
        profile_sha256="1" * 64,
        candidate_index_sha256="2" * 64,
        generated_at=datetime.now(UTC),
    )
    profile_path = tmp_path / "profile.json"
    profile_path.write_text("{}", encoding="utf-8")
    profile_ref = ArtifactRef.from_file(
        run_root=tmp_path,
        relative_path="profile.json",
        artifact_id="advisory-profile",
        role="advisory-only",
        file_format="json",
    )
    prediction = _prediction(
        "candidate-a",
        mode="de-novo",
        seed=101,
        sample_index=0,
        ranking_score=0.9,
        structure=predicted,
    )
    conditioned = _prediction(
        "candidate-a",
        mode="target-conditioned",
        seed=101,
        sample_index=0,
        ranking_score=0.9,
        structure=predicted,
    )
    report = build_stage07_prediction_comparison_report(
        root=tmp_path,
        cohort=cohort,
        cohort_sha256="3" * 64,
        de_novo_predictions=(prediction,),
        target_conditioned_predictions=(conditioned,),
        generated_at=datetime.now(UTC),
        advisory_profile=Stage07AdvisoryComparisonProfile(
            profile_id="comparison-sanity-v1",
            maximum_target_aligned_binder_rmsd_angstrom=2.0,
            minimum_hotspot_contact_jaccard=0.5,
        ),
        advisory_profile_ref=profile_ref,
    )

    assert report.verdict_authority == "advisory-only"
    assert report.advisory_verdicts[0].verdict == "支持"
    assert report.advisory_verdicts[0].selection_authority == "advisory-only"
