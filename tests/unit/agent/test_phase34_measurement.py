from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase34_measurement import incomplete_prediction_evidence
from easydesign.core import (
    ArtifactIntegrityError,
    ArtifactRef,
    ManifestStateError,
    ProgressSnapshot,
    TaskRecord,
    TaskStatus,
    dump_model,
)
from easydesign.stages.s05_pilot_filtering import (
    FullTargetExecutionState,
    FullTargetPredictionRecord,
)


def test_partial_prediction_preserves_success_missingness_and_hard_boundaries(tmp_path):
    runtime, artifacts = tmp_path / "runtime", tmp_path / "artifacts"
    runtime.mkdir()
    artifacts.mkdir()
    structure = artifacts / "verified-test-structure.cif"
    structure.write_text("# synthetic verified structure for projection testing\n")
    ref = ArtifactRef.from_file(
        run_root=tmp_path,
        relative_path="artifacts/verified-test-structure.cif",
        artifact_id="test-structure",
        role="synthetic-test",
        file_format="cif",
    )
    prediction = FullTargetPredictionRecord(
        candidate_id="candidate-a",
        strategy_id="arm-a",
        predicted_structure=ref,
        summary_confidence=ref,
        full_confidence=ref,
        pairwise_iptm=0.4,
        minimum_interface_pae_angstrom=8.0,
        binder_ptm=0.5,
        binder_pose_rmsd_angstrom=3.0,
        target_ca_rmsd_angstrom=2.0,
        severe_clash_count=0,
        moderate_clash_count=1,
        structure_gate_decisions=(),
        structure_gate_pass=True,
        confidence_reference_pass=False,
        confidence_label="low-confidence",
    )
    now = datetime.now(UTC)
    state = FullTargetExecutionState(
        created_at=now,
        updated_at=now,
        target_msa_sha256="a" * 64,
        selected_candidate_ids=("candidate-a", "candidate-b"),
        tasks=(
            TaskRecord(
                task_id="predict-a",
                strategy_id="candidate-a",
                requested_candidates=1,
                status=TaskStatus.SUCCEEDED,
                collected_candidates=1,
                candidate_ids=("candidate-a",),
                attempts=(
                    {
                        "attempt_number": 1,
                        "status": "succeeded",
                        "requested_candidates": 1,
                        "collected_candidates": 1,
                        "device": 0,
                        "command_sha256": "c" * 64,
                        "output_relative_path": "work/a",
                        "started_at": now,
                        "ended_at": now,
                        "return_code": 0,
                    },
                ),
            ),
            TaskRecord(
                task_id="predict-b",
                strategy_id="candidate-b",
                requested_candidates=1,
                status=TaskStatus.FAILED,
                attempts=(
                    {
                        "attempt_number": 1,
                        "status": "failed",
                        "requested_candidates": 1,
                        "device": 0,
                        "command_sha256": "d" * 64,
                        "output_relative_path": "work/b",
                        "started_at": now,
                        "ended_at": now,
                        "return_code": 1,
                        "error": {
                            "code": "backend-failure",
                            "message": "Synthetic failure",
                            "retryable": True,
                        },
                    },
                ),
            ),
        ),
        predictions=(prediction,),
        progress=ProgressSnapshot(
            stage_id="05-pilot-filtering",
            updated_at=now,
            status="incomplete",
            total_tasks=2,
            pending_tasks=0,
            waiting_tasks=0,
            running_tasks=0,
            succeeded_tasks=1,
            failed_tasks=1,
            planned_candidates=2,
            collected_candidates=1,
        ),
    )
    dump_model(state, runtime / "full-target-state.json")
    index = SimpleNamespace(
        candidates=tuple(
            SimpleNamespace(candidate_id="candidate-" + x, strategy_id="arm-" + x)
            for x in ("a", "b")
        )
    )
    kwargs = dict(
        root=tmp_path,
        runtime=runtime,
        artifacts=artifacts,
        authority_id="validation-authority",
        index=index,
        index_sha256="b" * 64,
        error=ManifestStateError(
            "Stage 05 Protenix full-target tasks 未全部完成，可使用 runs resume"
        ),
    )
    evidence = incomplete_prediction_evidence(**kwargs)
    assert evidence.predictions == (prediction,)
    assert evidence.operational_failure is not None
    assert all(r.verify(tmp_path).exists() for r in evidence.evidence_refs)
    assert incomplete_prediction_evidence(**kwargs) == evidence
    with pytest.raises(ManifestStateError, match="checksum mismatch"):
        incomplete_prediction_evidence(
            **{**kwargs, "error": ManifestStateError("checksum mismatch")}
        )
    foreign = SimpleNamespace(candidates=index.candidates[:1])
    with pytest.raises(AgentBoundaryError, match="foreign population"):
        incomplete_prediction_evidence(**{**kwargs, "index": foreign})
    structure.write_text("changed synthetic artifact\n")
    with pytest.raises(ArtifactIntegrityError):
        incomplete_prediction_evidence(**kwargs)
