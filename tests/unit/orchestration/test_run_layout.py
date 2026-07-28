from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from easydesign.core import (
    ArtifactRef,
    Attempt,
    CodeIdentity,
    CodeIdentitySource,
    ExecutionStatus,
    RunManifest,
    RuntimeProfileRef,
    StageId,
    StageManifest,
    dump_model,
    load_model,
    sha256_file,
)
from easydesign.orchestration import (
    RunIndexEntry,
    continue_run_in_place,
    initialize_continuation_run,
    initialize_project,
    materialize_continuation_config,
    prune_archived_project_shells,
    replace_run_index_entries,
)
from easydesign.orchestration.workspace import initialize_run_workspace


def _identity(version: str, digit: str) -> CodeIdentity:
    return CodeIdentity(
        version=version,
        source=CodeIdentitySource.GIT,
        git_commit=digit * 40,
        dirty=False,
    )


def test_normal_next_stage_continues_same_run_without_copying_upstream(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input" / "target.pse"
    source.parent.mkdir()
    source.write_bytes(b"stable-pse-input")
    initialized = initialize_project(
        project_root=tmp_path / "project",
        target=source,
        stop_after_stage=1,
    )
    created = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
    profile = RuntimeProfileRef(profile_id="test-local", sha256="3" * 64)
    prepared = initialize_run_workspace(
        config_path=initialized.config_path,
        runs_root=tmp_path / "runs",
        easydesign_version="0.1.0.dev13",
        code_identity=_identity("0.1.0.dev13", "1"),
        runtime_profile=profile,
        run_id="one-coherent-run",
        created_at=created,
    )
    root = prepared.workspace.run_root
    stage_root = root / str(StageId.TARGET_PREPARATION) / "attempt-0001"
    stage_root.mkdir(parents=True)
    output_path = stage_root / "artifacts/target-placeholder.json"
    output_path.parent.mkdir()
    output_path.write_text("{}\n", encoding="utf-8")
    output_ref = ArtifactRef.from_file(
        run_root=root,
        relative_path=output_path.relative_to(root).as_posix(),
        artifact_id="target-placeholder",
        role="test-output",
        file_format="json",
        producer_stage=str(StageId.TARGET_PREPARATION),
        producer_attempt="attempt-0001",
    )
    attempt = Attempt(
        attempt_id="attempt-0001",
        status=ExecutionStatus.SUCCEEDED,
        created_at=created,
        started_at=created,
        ended_at=created + timedelta(seconds=1),
        backend_name="test-backend",
        backend_version="1",
        executor_name="test-executor",
    )
    stage_manifest_path = stage_root / "stage-manifest.json"
    stage_manifest = StageManifest(
        stage_id=StageId.TARGET_PREPARATION,
        contract_version="0.4",
        status=ExecutionStatus.SUCCEEDED,
        created_at=created,
        completed_at=created + timedelta(seconds=1),
        output_artifacts=(output_ref,),
        attempts=(attempt,),
        selected_attempt_id=attempt.attempt_id,
    )
    dump_model(stage_manifest, stage_manifest_path)
    stage_ref = ArtifactRef.from_file(
        run_root=root,
        relative_path=stage_manifest_path.relative_to(root).as_posix(),
        artifact_id="stage01-manifest",
        role="stage-manifest",
        file_format="json",
        producer_stage=str(StageId.TARGET_PREPARATION),
        producer_attempt="attempt-0001",
    )
    initial = load_model(prepared.workspace.run_manifest, RunManifest)
    running = initial.next_revision(
        updated_at=created + timedelta(seconds=1),
        status=ExecutionStatus.RUNNING,
    )
    succeeded = running.next_revision(
        updated_at=created + timedelta(seconds=2),
        status=ExecutionStatus.SUCCEEDED,
        completed_at=created + timedelta(seconds=2),
        stage_manifest_refs=(stage_ref,),
    )
    dump_model(running, root / "manifests/run-manifest.v0002.json")
    dump_model(succeeded, root / "manifests/run-manifest.v0003.json")
    (root / "manifests/LATEST").write_text(
        "run-manifest.v0003.json\n",
        encoding="utf-8",
    )
    stage_sha_before = sha256_file(stage_manifest_path)
    continuation_config = tmp_path / "project" / "stage02.yaml"
    materialize_continuation_config(
        source_run_root=root,
        destination=continuation_config,
        stage_number=2,
        execution_mode="review-gated",
        options={"mode": "automatic", "methods": ["sasa"]},
    )

    continued = continue_run_in_place(
        source_run_root=root,
        config_path=continuation_config,
        code_identity=_identity("0.1.0.dev17", "2"),
        runtime_profile=profile,
        continued_at=created + timedelta(seconds=3),
    )

    assert continued.workspace.run_root == root
    assert {
        path.name
        for path in (tmp_path / "runs" / prepared.workspace.project_id).iterdir()
    } == {"one-coherent-run", "PROJECT.json"}
    assert not (root / str(StageId.HOTSPOT_DISCOVERY)).exists()
    assert sha256_file(stage_manifest_path) == stage_sha_before
    assert (root / "config-snapshot/CURRENT").read_text(encoding="utf-8") == (
        "revisions/revision-0004/resolved-config.json\n"
    )
    latest = load_model(root / "manifests/run-manifest.v0004.json", RunManifest)
    assert latest.status is ExecutionStatus.RUNNING
    assert latest.run_id == "one-coherent-run"
    assert latest.stage_manifest_refs == (stage_ref,)
    assert latest.config_snapshot.verify(root) == (
        root / "config-snapshot/revisions/revision-0004/easydesign.yaml"
    )

    branch_config = tmp_path / "project" / "stage02-branch.yaml"
    materialize_continuation_config(
        source_run_root=root,
        destination=branch_config,
        stage_number=2,
        execution_mode="review-gated",
        continue_after_stage=1,
        options={"mode": "automatic", "methods": ["sasa"]},
    )
    branched = initialize_continuation_run(
        source_run_root=root,
        config_path=branch_config,
        runs_root=tmp_path / "runs",
        run_id="stage02-branch",
        code_identity=_identity("0.1.0.dev18", "3"),
        runtime_profile=profile,
        created_at=created + timedelta(seconds=4),
        copy_through_stage=1,
    )

    assert branched.workspace.run_root != root
    branch_manifest = load_model(branched.workspace.run_manifest, RunManifest)
    assert branch_manifest.status is ExecutionStatus.RUNNING
    assert branch_manifest.run_id == "stage02-branch"
    assert branch_manifest.stage_manifest_refs == (stage_ref,)
    assert sha256_file(stage_manifest_path) == stage_sha_before


def test_prune_only_removes_empty_shell_for_archived_project(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    (runs_root / "archived-target").mkdir(parents=True)
    (runs_root / "_archive/archived-target/run-001").mkdir(parents=True)
    (runs_root / "untracked-empty").mkdir()
    replace_run_index_entries(
        runs_root,
        (
            RunIndexEntry(
                category="archived-project-run",
                path="_archive/archived-target/run-001",
                layout_version="1",
                status="succeeded",
                project_id="archived-target",
                run_id="run-001",
            ),
        ),
        generated_at=datetime(2026, 7, 28, 9, 0, tzinfo=UTC),
    )

    removed = prune_archived_project_shells(runs_root)

    assert removed == ("archived-target",)
    assert not (runs_root / "archived-target").exists()
    assert (runs_root / "untracked-empty").is_dir()
