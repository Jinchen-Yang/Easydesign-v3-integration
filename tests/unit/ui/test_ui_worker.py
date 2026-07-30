from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from easydesign.core import dump_model, load_model
from easydesign.ui import worker
from easydesign.ui.jobs import UiJobController
from easydesign.ui.models import UiJobRecord
from easydesign.ui.security import UiRunRegistry
from easydesign.ui.sessions import DesignSessionStore


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
    run_root.mkdir(parents=True)
    config = tmp_path / "stage02.yaml"
    config.write_text("schema_version: '0.7'\n", encoding="utf-8")
    now = datetime.now(tz=UTC)
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
