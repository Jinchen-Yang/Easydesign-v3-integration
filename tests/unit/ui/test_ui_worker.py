from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from easydesign.core import (
    ArtifactRef,
    ConfigurationError,
    EvidenceStatus,
    ExecutionStatus,
    RunManifest,
    dump_model,
    load_model,
)
from easydesign.orchestration import ProjectNavigation, RunIndex
from easydesign.ui import jobs, worker
from easydesign.ui.jobs import UiJobController
from easydesign.ui.models import UiJobRecord
from easydesign.ui.security import UiRunRegistry
from easydesign.ui.sessions import DesignSessionStore


def _minimal_run(
    run_root: Path,
    *,
    project_id: str,
    run_id: str,
    created_at: datetime,
) -> None:
    config_path = run_root / "config-snapshot" / "resolved-config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('{"schema_version": "0.7"}\n', encoding="utf-8")
    config = ArtifactRef.from_file(
        run_root=run_root,
        relative_path="config-snapshot/resolved-config.json",
        artifact_id="resolved-config",
        role="resolved-config",
        file_format="json",
    )
    manifest = RunManifest(
        schema_version="1.0",
        revision=1,
        project_id=project_id,
        run_id=run_id,
        easydesign_version="0.1.0.test",
        code_commit="a" * 40,
        status=ExecutionStatus.SUCCEEDED,
        evidence_status=EvidenceStatus.IMPLEMENTED,
        created_at=created_at,
        updated_at=created_at,
        completed_at=created_at,
        config_snapshot=config,
    )
    manifest_path = run_root / "manifests" / "run-manifest-0001.json"
    dump_model(manifest, manifest_path)
    (run_root / "manifests" / "LATEST").write_text(
        "run-manifest-0001.json\n",
        encoding="utf-8",
    )


def test_worker_attaches_continuation_run_to_design_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sessions = DesignSessionStore(tmp_path / "sessions")
    session = sessions.create(
        project_id="sample-project",
        design_mode="stepwise",
        execution_mode="review-gated",
    )
    run_root = tmp_path / "runs" / "sample-project" / "stage02-run"
    config = tmp_path / "stage02.yaml"
    config.write_text("schema_version: '0.7'\n", encoding="utf-8")
    now = datetime.now(tz=UTC)
    _minimal_run(
        run_root,
        project_id="sample-project",
        run_id=run_root.name,
        created_at=now,
    )
    record_path = tmp_path / "job.json"
    dump_model(
        UiJobRecord(
            job_id="job-worker-session",
            operation="run",
            status="running",
            config_path=str(config),
            run_id=run_root.name,
            session_id=session.session_id,
            stage_number=2,
            created_at=now,
            updated_at=now,
        ),
        record_path,
    )
    monkeypatch.setattr(
        worker,
        "execute_pipeline",
        lambda *args, **kwargs: SimpleNamespace(
            status="awaiting-human-approval",
            run_root=run_root,
            plan=SimpleNamespace(project_id="sample-project"),
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "easydesign.ui.worker",
            "--job-record",
            str(record_path),
            "--operation",
            "run",
            "--drain-file",
            str(tmp_path / "job.drain"),
            "--config",
            str(config),
            "--runs-root",
            str(tmp_path / "runs"),
            "--run-id",
            run_root.name,
            "--continue-after-stage",
            "1",
            "--session-root",
            str(sessions.root),
        ],
    )

    assert worker.main() == 0
    expected_key = UiRunRegistry(tmp_path / "runs").register(run_root)
    updated_job = load_model(record_path, UiJobRecord)
    updated_session = sessions.load(session.session_id)
    assert updated_job.run_key == expected_key
    assert updated_session.run_lineage == (expected_key,)
    assert updated_session.current_stage == 2
    assert updated_session.status == "awaiting-human-approval"
    assert updated_job.error is None
    index = load_model(tmp_path / "runs" / "run-index.json", RunIndex)
    entry = next(item for item in index.entries if item.project_id == "sample-project")
    assert entry.run_id == "stage02-run"
    assert entry.status == "awaiting-human-approval"
    assert entry.is_project_primary is True
    navigation = load_model(
        tmp_path / "runs" / "sample-project" / "PROJECT.json",
        ProjectNavigation,
    )
    assert navigation.primary_run_id == "stage02-run"
    assert navigation.runs[0].relative_path == "sample-project/stage02-run"


def test_self_test_run_skips_product_project_navigation(tmp_path: Path) -> None:
    now = datetime.now(tz=UTC)
    run_root = tmp_path / "runs" / "_selftests" / "fixture" / "stage01"
    _minimal_run(
        run_root,
        project_id="developer-backend-selftest",
        run_id="stage01",
        created_at=now,
    )
    record = UiJobRecord(
        job_id="job-self-test-stage01",
        operation="run",
        status="running",
        run_id="stage01",
        self_test_id="selftest-20260801t000000z-fixture",
        stage_number=1,
        created_at=now,
        updated_at=now,
    )

    error = worker._publish_product_run_navigation(
        record=record,
        run_root=run_root,
        runs_root=tmp_path / "runs",
        project_id="developer-backend-selftest",
        status="succeeded",
    )

    assert error is None
    assert not (tmp_path / "runs" / "run-index.json").exists()
    assert not (
        tmp_path / "runs" / "developer-backend-selftest" / "PROJECT.json"
    ).exists()


def test_external_submission_persists_stage_acceptance(tmp_path: Path) -> None:
    controller = UiJobController(tmp_path / "jobs")

    record = controller.accept_external(
        operation="remote-run",
        project_id="sample-project",
        stage_number=4,
        external_job_id="remote-job-0001",
        run_id="remote-run-0001",
        session_id="session-0001",
        status="submitted",
    )

    restored = controller.load(record.job_id)
    assert restored.project_id == "sample-project"
    assert restored.stage_number == 4
    assert restored.external_job_id == "remote-job-0001"
    assert restored.status == "submitted"


def test_legacy_external_continuation_is_rebound_to_source_run(tmp_path: Path) -> None:
    controller = UiJobController(tmp_path / "jobs")
    record = controller.accept_external(
        operation="managed-remote-run",
        project_id="sample-project",
        stage_number=4,
        external_job_id="managed-job-legacy",
        run_id="managed-run-legacy",
        status="running",
    )

    recovered = controller.latest_continuation(
        run_key="source-run-key",
        project_id="sample-project",
        stage_number=4,
    )
    assert recovered is not None
    assert recovered.job_id == record.job_id

    rebound = controller.bind_continuation(
        recovered.job_id,
        accepted_run_key="source-run-key",
        status="running",
        execution_target="managed-ssh",
    )
    assert rebound.accepted_run_key == "source-run-key"
    assert rebound.execution_target == "managed-ssh"
    assert controller.latest_continuation(
        run_key="source-run-key",
        project_id="sample-project",
        stage_number=4,
    ).job_id == record.job_id


def test_terminal_legacy_job_is_not_attached_to_new_run(tmp_path: Path) -> None:
    controller = UiJobController(tmp_path / "jobs")
    controller.accept_external(
        operation="managed-remote-run",
        project_id="sample-project",
        stage_number=4,
        external_job_id="managed-job-old",
        run_id="managed-run-old",
        status="succeeded",
    )

    assert controller.latest_continuation(
        run_key="new-source-run",
        project_id="sample-project",
        stage_number=4,
    ) is None


def test_ambiguous_active_legacy_jobs_fail_closed(tmp_path: Path) -> None:
    controller = UiJobController(tmp_path / "jobs")
    for suffix in ("first", "second"):
        controller.accept_external(
            operation="managed-remote-run",
            project_id="sample-project",
            stage_number=4,
            external_job_id=f"managed-job-{suffix}",
            run_id=f"managed-run-{suffix}",
            status="running",
        )

    with pytest.raises(ConfigurationError, match="多个未绑定的活动任务"):
        controller.latest_continuation(
            run_key="source-run-key",
            project_id="sample-project",
            stage_number=4,
        )


def test_local_job_reconciliation_marks_missing_pid_operational_failed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    controller = UiJobController(tmp_path / "jobs")
    now = datetime.now(tz=UTC)
    original = UiJobRecord(
        job_id="job-dead-local-worker",
        operation="run",
        status="running",
        project_id="sample-project",
        run_id="sample-run",
        stage_number=4,
        execution_target="local-current-host",
        process_id=424242,
        created_at=now,
        updated_at=now,
    )
    dump_model(original, controller._path(original.job_id))
    monkeypatch.setattr(controller, "_pid_exists", lambda process_id: False)

    reconciled = controller.load(original.job_id)

    assert reconciled.status == "operational-failed"
    assert reconciled.error == "local-ui-worker-exited-without-terminal-record"
    assert reconciled.stage_number == 4
    assert reconciled.process_id == 424242
    assert (
        len(
            tuple(
                (
                    controller._path(original.job_id).with_name(f"{original.job_id}.json.revisions")
                ).glob("revision-*.json")
            )
        )
        == 1
    )


def test_linux_zombie_pid_is_not_running(monkeypatch) -> None:
    monkeypatch.setattr(jobs.os, "kill", lambda _pid, _signal: None)
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda _path, **_kwargs: "424242 (python worker) Z 1 1 1 0",
    )
    monkeypatch.setattr(jobs.sys, "platform", "linux")

    assert UiJobController._pid_exists(424242) is False


def test_local_job_reconciliation_never_reconciles_external_job(
    tmp_path: Path,
    monkeypatch,
) -> None:
    controller = UiJobController(tmp_path / "jobs")
    now = datetime.now(tz=UTC)
    external = UiJobRecord(
        job_id="job-external-running",
        operation="remote-run",
        status="running",
        external_job_id="managed-job-0001",
        process_id=424242,
        created_at=now,
        updated_at=now,
    )
    dump_model(external, controller._path(external.job_id))
    monkeypatch.setattr(controller, "_pid_exists", lambda process_id: False)

    assert controller.load(external.job_id).status == "running"
