from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from easydesign.core import ConfigurationError, TargetInputError
from easydesign.local_worker import _failure_status
from easydesign.orchestration.application import RunSummary
from easydesign.orchestration.local_jobs import LocalStepJob, LocalStepJobController
from easydesign.orchestration.local_project import (
    STAGE_FILENAMES,
    initialize_local_project,
    project_config_path,
)
from easydesign.orchestration.local_steps import (
    _guidance,
    _wait_or_detach,
    resume_step,
    stage_template,
    status_step,
    validate_step,
)
from easydesign.workspace_context import WorkspaceContext


def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        'schema_version: "0.1"\nworkspace_id: local-test\n', encoding="utf-8"
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))
    return tmp_path


def test_local_project_is_flat_and_canonical_config_is_append_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workspace(tmp_path, monkeypatch)
    target = root / "target.fasta"
    target.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    project = root / "workspace/projects/example"

    initialized = initialize_local_project(project_root=project, target=target)

    assert initialized.project_root == project
    assert all((project / name).is_file() for name in STAGE_FILENAMES.values())
    assert project_config_path(project).name == "easydesign.rev-000001.yaml"
    assert (project / "CONFIG_CURRENT").read_text(encoding="utf-8").splitlines() == [
        "config-revisions/easydesign.rev-000001.yaml"
    ]
    assert not (project / "easydesign.yaml").exists()
    result = validate_step(1, project)
    assert result.status == "valid"
    assert result.step == 1


def test_manual_stage02_template_is_strict_and_project_local(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workspace(tmp_path, monkeypatch)
    target = root / "target.fasta"
    target.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    project = root / "workspace/projects/manual"
    initialize_local_project(project_root=project, target=target)

    result = stage_template(2, project, manual=True)

    template = result.generated_files[0]
    assert template == project / "02-hotspot-discovery.manual.yaml"
    assert "numbering: label" in template.read_text(encoding="utf-8")
    assert result.status == "template-created"
    with pytest.raises(FileExistsError):
        stage_template(2, project, manual=True)


def test_pse_project_defaults_to_independent_sasa_and_scannet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workspace(tmp_path, monkeypatch)
    pse = root / "target.pse"
    pse.write_bytes(b"synthetic-pse")
    project = root / "workspace/projects/pse-auto"

    initialize_local_project(project_root=project, target=pse)

    payload = yaml.safe_load(
        (project / "02-hotspot-discovery.yaml").read_text(encoding="utf-8")
    )
    assert payload["mode"] == "automatic"
    assert payload["methods"] == ["sasa", "scannet"]
    assert payload["user_regions"] is None


def test_approval_guidance_never_lists_a_config_revision_as_input(tmp_path: Path) -> None:
    project = tmp_path / "project"
    config = project / "config-revisions/easydesign.rev-000003.yaml"
    approval = project / "02-approval.sasa.run-1.yaml"

    actions = _guidance(
        status="awaiting-human-approval",
        step=2,
        project_root=project,
        run_id="run-1",
        generated=(config, approval),
    )

    assert any(str(approval) in action for action in actions)
    assert all(str(config) not in action for action in actions)


def test_external_old_ui_source_run_is_rejected_before_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workspace(tmp_path, monkeypatch)
    old_run = tmp_path.parent / "easydesign-clean/workspace/runs/old"
    old_run.mkdir(parents=True)
    bundle = root / "bundle.json"
    bundle.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="旧 UI run"):
        initialize_local_project(
            project_root=root / "workspace/projects/rejected",
            target_bundle=bundle,
            source_run_root=old_run,
        )


def test_worker_loss_becomes_explicit_operational_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workspace(tmp_path, monkeypatch)
    context = WorkspaceContext.from_root(root)
    context.ensure_layout()
    controller = LocalStepJobController(context)
    now = datetime.now(UTC)
    job = LocalStepJob(
        job_id="job-deadworker0001",
        operation="run",
        status="running",
        project_id="example",
        project_root=context.projects_root / "example",
        step=4,
        config_path=context.projects_root / "example/config.yaml",
        process_id=999_999_999,
        branch="codex/vscode-local",
        log_path=context.runtime_root / "logs/job.log",
        drain_path=context.runtime_root / "state/local-jobs/job.drain",
        created_at=now,
        updated_at=now,
    )
    controller.update(job)

    loaded = controller.load(job.job_id)

    assert loaded.status == "operational-failed"
    assert loaded.error == "local-worker-exited-without-terminal-receipt"


def test_target_input_failure_is_not_mislabeled_as_operational() -> None:
    assert _failure_status(TargetInputError("strict scientific gate")) == "scientific-failed"
    assert _failure_status(OSError("disk unavailable")) == "operational-failed"


def test_worker_launch_is_detached_and_uses_only_local_writable_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workspace(tmp_path, monkeypatch)
    context = WorkspaceContext.from_root(root)
    context.ensure_layout()
    controller = LocalStepJobController(context)
    project = context.projects_root / "detached"
    project.mkdir()
    config = project / "config.yaml"
    config.write_text("schema_version: '0.7'\n", encoding="utf-8")
    captured: dict[str, Any] = {}

    class Process:
        pid = 424242

    def fake_popen(command: list[str], **kwargs: Any) -> Process:
        captured["command"] = command
        captured.update(kwargs)
        return Process()

    monkeypatch.setattr(
        "easydesign.orchestration.local_jobs.subprocess.Popen",
        fake_popen,
    )
    monkeypatch.setattr(
        "easydesign.orchestration.local_jobs._branch",
        lambda _context: "codex/vscode-local",
    )

    job = controller.launch(
        operation="run",
        project_id="detached",
        project_root=project,
        step=4,
        config_path=config,
    )

    assert job.process_id == 424242
    assert captured["start_new_session"] is True
    environment = captured["env"]
    assert environment["HOME"] == str(context.runtime_root / "home")
    assert environment["HF_HOME"] == str(context.runtime_root / "cache/huggingface")
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"


def test_ctrl_c_detaches_observer_without_stopping_worker(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    job = LocalStepJob(
        job_id="job-ctrlcdetach001",
        operation="run",
        status="running",
        project_id="ctrl-c",
        project_root=tmp_path / "project",
        step=4,
        config_path=tmp_path / "config.yaml",
        process_id=777,
        branch="codex/vscode-local",
        log_path=tmp_path / "job.log",
        drain_path=tmp_path / "job.drain",
        created_at=now,
        updated_at=now,
    )

    class Controller:
        def wait(self, _job_id: str) -> LocalStepJob:
            raise KeyboardInterrupt

        def load(self, _job_id: str) -> LocalStepJob:
            return job

    observed = _wait_or_detach(Controller(), job, detach=False)  # type: ignore[arg-type]

    assert observed.status == "detached"
    assert observed.process_id == 777
    assert job.status == "running"


def test_drain_only_writes_a_safe_checkpoint_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workspace(tmp_path, monkeypatch)
    context = WorkspaceContext.from_root(root)
    context.ensure_layout()
    controller = LocalStepJobController(context)
    now = datetime.now(UTC)
    job = LocalStepJob(
        job_id="job-drainrequest01",
        operation="run",
        status="running",
        project_id="drain",
        project_root=context.projects_root / "drain",
        step=6,
        process_id=None,
        branch="codex/vscode-local",
        log_path=context.runtime_root / "logs/drain.log",
        drain_path=context.runtime_root / "state/local-jobs/job-drainrequest01.drain",
        created_at=now,
        updated_at=now,
    )
    controller.update(job)

    drained = controller.request_drain(job.job_id)

    assert drained.status == "drain-requested"
    assert drained.drain_path.is_file()


def test_resume_infers_only_the_manifest_declared_long_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workspace(tmp_path, monkeypatch)
    target = root / "target.fasta"
    target.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    project = root / "workspace/projects/resume"
    initialize_local_project(project_root=project, target=target)
    run_root = root / "workspace/runs/resume/run-1"
    summary = RunSummary(
        project_id="resume",
        run_id="run-1",
        path=run_root,
        status="running",
        latest_manifest=run_root / "manifests/run-manifest.v0004.json",
        manifest_revision=4,
        completed_stages=(
            "01-target-preparation",
            "02-hotspot-discovery",
            "03-boltzgen-configuration",
        ),
    )
    launched: dict[str, Any] = {}
    now = datetime.now(UTC)

    class Controller:
        def latest(self, _project_id: str) -> None:
            return None

        def launch(self, **values: Any) -> LocalStepJob:
            launched.update(values)
            return LocalStepJob(
                job_id="job-resume0000001",
                status="running",
                branch="codex/vscode-local",
                log_path=root / "runtime/logs/resume.log",
                drain_path=root / "runtime/state/local-jobs/resume.drain",
                created_at=now,
                updated_at=now,
                **values,
            )

    monkeypatch.setattr(
        "easydesign.orchestration.local_steps.resolve_project_run",
        lambda *_args, **_kwargs: summary,
    )
    monkeypatch.setattr(
        "easydesign.orchestration.local_steps.completed_steps",
        lambda _path: (1, 2, 3),
    )
    monkeypatch.setattr(
        "easydesign.orchestration.local_steps.LocalStepJobController",
        Controller,
    )

    result = resume_step(project, detach=True)

    assert result.status == "detached"
    assert result.step == 4
    assert launched["step"] == 4


def test_status_prefers_a_newer_manifest_over_a_terminal_worker_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workspace(tmp_path, monkeypatch)
    target = root / "target.fasta"
    target.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    project = root / "workspace/projects/status"
    initialize_local_project(project_root=project, target=target, project_id="status")
    run_root = root / "workspace/runs/status/run-1"
    old_manifest = run_root / "manifests/run-manifest.v0004.json"
    new_manifest = run_root / "manifests/run-manifest.v0005.json"
    now = datetime.now(UTC)
    job = LocalStepJob(
        job_id="job-status00000001",
        operation="run",
        status="awaiting-human-approval",
        project_id="status",
        project_root=project,
        step=2,
        run_id="run-1",
        run_root=run_root,
        run_manifest=old_manifest,
        branch="codex/vscode-local",
        log_path=root / "runtime/logs/status.log",
        drain_path=root / "runtime/state/local-jobs/status.drain",
        created_at=now,
        updated_at=now,
    )
    summary = RunSummary(
        project_id="status",
        run_id="run-1",
        path=run_root,
        status="succeeded",
        latest_manifest=new_manifest,
        manifest_revision=5,
        completed_stages=("01-target-preparation", "02-hotspot-discovery"),
    )

    class Controller:
        def latest(self, _project_id: str) -> LocalStepJob:
            return job

    monkeypatch.setattr(
        "easydesign.orchestration.local_steps.LocalStepJobController",
        Controller,
    )
    monkeypatch.setattr(
        "easydesign.orchestration.local_steps.resolve_project_run",
        lambda *_args, **_kwargs: summary,
    )
    monkeypatch.setattr(
        "easydesign.orchestration.local_steps.completed_steps",
        lambda _path: (1, 2),
    )

    result = status_step(project, run_id="run-1")

    assert result.status == "succeeded"
    assert result.manifest == new_manifest
