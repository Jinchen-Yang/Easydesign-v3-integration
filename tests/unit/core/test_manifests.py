from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from easydesign.core import (
    ArtifactRef,
    CodeIdentity,
    CodeIdentitySource,
    EvidenceStatus,
    ExecutionStatus,
    ManifestStateError,
    RunManifest,
    RuntimeProfileRef,
    StageId,
    StageManifest,
    UndeclaredArtifactError,
    canonical_model_sha256,
)


def artifact(
    artifact_id: str,
    *,
    role: str | None = None,
    producer_stage: str | None = None,
    producer_attempt: str | None = None,
) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=artifact_id,
        role=artifact_id if role is None else role,
        relative_path=f"artifacts/{artifact_id}.json",
        file_format="json",
        sha256="a" * 64,
        size_bytes=10,
        producer_stage=producer_stage,
        producer_attempt=producer_attempt,
    )


def succeeded_stage(now, succeeded_attempt) -> StageManifest:
    return StageManifest(
        stage_id=StageId.TARGET_PREPARATION,
        contract_version="0.1",
        status=ExecutionStatus.SUCCEEDED,
        created_at=now,
        completed_at=now,
        input_artifacts=(artifact("request"),),
        output_artifacts=(
            artifact(
                "target-structure",
                producer_stage=str(StageId.TARGET_PREPARATION),
                producer_attempt=succeeded_attempt.attempt_id,
            ),
        ),
        attempts=(succeeded_attempt,),
        selected_attempt_id=succeeded_attempt.attempt_id,
    )


def test_succeeded_stage_requires_succeeded_selection(now, succeeded_attempt) -> None:
    stage = succeeded_stage(now, succeeded_attempt)
    assert stage.require_output("target-structure").artifact_id == "target-structure"

    with pytest.raises(UndeclaredArtifactError):
        stage.require_output("hotspots")


def test_succeeded_stage_rejects_missing_selection(now, succeeded_attempt) -> None:
    with pytest.raises(ValidationError, match="succeeded attempt"):
        StageManifest(
            stage_id=StageId.TARGET_PREPARATION,
            contract_version="0.1",
            status=ExecutionStatus.SUCCEEDED,
            created_at=now,
            completed_at=now,
            attempts=(succeeded_attempt,),
        )


def test_stage_rejects_duplicate_artifact_ids(now) -> None:
    duplicate = artifact("same")
    with pytest.raises(ValidationError, match="不能重复"):
        StageManifest(
            stage_id=StageId.TARGET_PREPARATION,
            contract_version="0.1",
            status=ExecutionStatus.PENDING,
            created_at=now,
            input_artifacts=(duplicate,),
            output_artifacts=(duplicate,),
        )


def test_stage_rejects_output_from_wrong_stage(now, succeeded_attempt) -> None:
    with pytest.raises(ValidationError, match="producer_stage"):
        StageManifest(
            stage_id=StageId.TARGET_PREPARATION,
            contract_version="0.1",
            status=ExecutionStatus.SUCCEEDED,
            created_at=now,
            completed_at=now,
            output_artifacts=(
                artifact(
                    "target-structure",
                    producer_stage=str(StageId.HOTSPOT_DISCOVERY),
                    producer_attempt=succeeded_attempt.attempt_id,
                ),
            ),
            attempts=(succeeded_attempt,),
            selected_attempt_id=succeeded_attempt.attempt_id,
        )


def test_stage_rejects_output_from_unselected_attempt(now, succeeded_attempt) -> None:
    other_attempt = succeeded_attempt.model_copy(
        update={"attempt_id": "attempt-0002"}
    )
    with pytest.raises(ValidationError, match="selected attempt"):
        StageManifest(
            stage_id=StageId.TARGET_PREPARATION,
            contract_version="0.1",
            status=ExecutionStatus.SUCCEEDED,
            created_at=now,
            completed_at=now,
            output_artifacts=(
                artifact(
                    "target-structure",
                    producer_stage=str(StageId.TARGET_PREPARATION),
                    producer_attempt=other_attempt.attempt_id,
                ),
            ),
            attempts=(succeeded_attempt, other_attempt),
            selected_attempt_id=succeeded_attempt.attempt_id,
        )


def test_downstream_accepts_only_declared_upstream_output(now, succeeded_attempt) -> None:
    upstream = succeeded_stage(now, succeeded_attempt)
    declared = upstream.require_output("target-structure")
    downstream = StageManifest(
        stage_id=StageId.HOTSPOT_DISCOVERY,
        contract_version="0.1",
        status=ExecutionStatus.PENDING,
        created_at=now,
        input_artifacts=(declared,),
    )
    assert downstream.validate_inputs_declared_by((upstream,)) is None

    forged = declared.model_copy(update={"sha256": "b" * 64})
    invalid_downstream = downstream.model_copy(update={"input_artifacts": (forged,)})
    with pytest.raises(UndeclaredArtifactError, match="不一致"):
        invalid_downstream.validate_inputs_declared_by((upstream,))


def test_downstream_rejects_undeclared_upstream_artifact(now, succeeded_attempt) -> None:
    undeclared = artifact(
        "undeclared-target",
        producer_stage=str(StageId.TARGET_PREPARATION),
        producer_attempt="attempt-0001",
    )
    downstream = StageManifest(
        stage_id=StageId.HOTSPOT_DISCOVERY,
        contract_version="0.1",
        status=ExecutionStatus.PENDING,
        created_at=now,
        input_artifacts=(undeclared,),
    )
    upstream = succeeded_stage(now, succeeded_attempt)
    with pytest.raises(UndeclaredArtifactError, match="未由上游声明"):
        downstream.validate_inputs_declared_by((upstream,))


def test_downstream_rejects_unsuccessful_upstream(now) -> None:
    downstream = StageManifest(
        stage_id=StageId.HOTSPOT_DISCOVERY,
        contract_version="0.1",
        status=ExecutionStatus.PENDING,
        created_at=now,
    )
    upstream = StageManifest(
        stage_id=StageId.TARGET_PREPARATION,
        contract_version="0.1",
        status=ExecutionStatus.PENDING,
        created_at=now,
    )
    with pytest.raises(UndeclaredArtifactError, match="尚未成功"):
        downstream.validate_inputs_declared_by((upstream,))


def test_stage_rejects_future_manifest_as_upstream(now) -> None:
    current = StageManifest(
        stage_id=StageId.HOTSPOT_DISCOVERY,
        contract_version="0.1",
        status=ExecutionStatus.PENDING,
        created_at=now,
    )
    future = StageManifest(
        stage_id=StageId.BOLTZGEN_CONFIGURATION,
        contract_version="0.1",
        status=ExecutionStatus.FAILED,
        created_at=now,
        completed_at=now,
    )
    with pytest.raises(UndeclaredArtifactError, match="不是.*上游"):
        current.validate_inputs_declared_by((future,))


def test_run_manifest_revision_chain(now) -> None:
    run = RunManifest(
        revision=1,
        project_id="apoe-vhh",
        run_id="run-20260724-001",
        easydesign_version="0.1.0.dev0",
        code_commit="dd652f4",
        status=ExecutionStatus.RUNNING,
        evidence_status=EvidenceStatus.IMPLEMENTED,
        created_at=now,
        updated_at=now,
        config_snapshot=artifact("config-snapshot"),
    )
    next_run = run.next_revision(updated_at=now + timedelta(minutes=1))

    assert next_run.revision == 2
    assert next_run.previous_manifest_sha256 == canonical_model_sha256(run)
    assert run.revision == 1


def test_run_manifest_rejects_non_monotonic_revision_time(now) -> None:
    run = RunManifest(
        revision=1,
        project_id="apoe-vhh",
        run_id="run-001",
        easydesign_version="0.1.0.dev0",
        code_commit="dd652f4",
        status=ExecutionStatus.RUNNING,
        evidence_status=EvidenceStatus.IMPLEMENTED,
        created_at=now,
        updated_at=now,
        config_snapshot=artifact("config-snapshot"),
    )
    with pytest.raises(ManifestStateError, match="updated_at"):
        run.next_revision(updated_at=now)


def test_run_manifest_revision_one_rejects_previous_hash(now) -> None:
    with pytest.raises(ValidationError, match="revision 1"):
        RunManifest(
            revision=1,
            previous_manifest_sha256="a" * 64,
            project_id="apoe-vhh",
            run_id="run-001",
            easydesign_version="0.1.0.dev0",
            code_commit="dd652f4",
            status=ExecutionStatus.PENDING,
            evidence_status=EvidenceStatus.IMPLEMENTED,
            created_at=now,
            updated_at=now,
            config_snapshot=artifact("config-snapshot"),
        )


def test_run_manifest_is_frozen(now) -> None:
    run = RunManifest(
        revision=1,
        project_id="apoe-vhh",
        run_id="run-001",
        easydesign_version="0.1.0.dev0",
        code_commit="dd652f4",
        status=ExecutionStatus.PENDING,
        evidence_status=EvidenceStatus.IMPLEMENTED,
        created_at=now,
        updated_at=now,
        config_snapshot=artifact("config-snapshot"),
    )
    with pytest.raises(ValidationError, match="frozen"):
        run.revision = 2


def test_run_manifest_11_preserves_structured_code_identity(now) -> None:
    identity = CodeIdentity(
        version="0.1.0.dev1",
        source=CodeIdentitySource.WORKING_TREE,
        git_commit="1" * 40,
        dirty=True,
        content_sha256="2" * 64,
    )
    profile = RuntimeProfileRef(profile_id="server-local", sha256="3" * 64)
    run = RunManifest(
        schema_version="1.1",
        revision=1,
        project_id="apoe",
        run_id="run-001",
        easydesign_version="0.1.0.dev1",
        code_identity=identity,
        runtime_profile=profile,
        status=ExecutionStatus.RUNNING,
        evidence_status=EvidenceStatus.IMPLEMENTED,
        created_at=now,
        updated_at=now,
        config_snapshot=artifact("config-snapshot"),
    )

    revised = run.next_revision(updated_at=now + timedelta(seconds=1))

    assert revised.code_identity == identity
    assert revised.runtime_profile == profile
    assert revised.code_commit is None


def test_run_manifest_11_rejects_legacy_code_commit(now) -> None:
    with pytest.raises(ValidationError, match="不得.*code_commit"):
        RunManifest(
            schema_version="1.1",
            revision=1,
            project_id="apoe",
            run_id="run-001",
            easydesign_version="0.1.0.dev1",
            code_commit="dd652f4",
            code_identity=CodeIdentity(
                version="0.1.0.dev1",
                source=CodeIdentitySource.GIT,
                git_commit="1" * 40,
                dirty=False,
            ),
            status=ExecutionStatus.PENDING,
            evidence_status=EvidenceStatus.IMPLEMENTED,
            created_at=now,
            updated_at=now,
            config_snapshot=artifact("config-snapshot"),
        )
