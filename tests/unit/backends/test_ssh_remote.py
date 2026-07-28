from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pytest import MonkeyPatch

from easydesign.backends.executors import SshRemoteConnection, SshRemoteExecutor
from easydesign.core import ProgressSnapshot


def _executor(tmp_path: Path) -> SshRemoteExecutor:
    identity = tmp_path / "id_ed25519"
    known_hosts = tmp_path / "known_hosts"
    identity.write_text("private\n", encoding="utf-8")
    known_hosts.write_text("host key\n", encoding="utf-8")
    return SshRemoteExecutor(
        SshRemoteConnection(
            executor_id="suzhou2-a100x8",
            host="192.0.2.10",
            user="root",
            port=22,
            identity_file=identity,
            known_hosts_file=known_hosts,
            ssh_executable=Path("/usr/bin/ssh"),
            rsync_executable=Path("/usr/bin/rsync"),
            remote_work_root=Path("/data/easydesign"),
            remote_runs_root=Path("/data/easydesign/runs"),
            remote_easydesign_executable=Path("/data/easydesign/bin/easydesign"),
            remote_profile=Path("/data/easydesign/profile.yaml"),
            connect_timeout_seconds=15,
        )
    )


def test_ssh_probe_requires_strict_host_identity_and_reports_resources(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []

    def fake_run(command: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        joined = " ".join(command)
        if " hostname" in joined:
            stdout = "remote-a100\n"
        elif "--version" in joined:
            stdout = "0.1.0.dev11\n"
        elif "nvidia-smi" in joined:
            stdout = "\n".join(str(index) for index in range(8)) + "\n"
        else:
            stdout = "1B-blocks  Available\n7000000000000 6500000000000\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    probe = _executor(tmp_path).probe()

    assert probe.gpu_count == 8
    assert probe.filesystem_available_bytes == 6_500_000_000_000
    assert all("BatchMode=yes" in item for item in commands)
    assert all("StrictHostKeyChecking=yes" in item for item in commands)
    assert all(
        any(argument.startswith("UserKnownHostsFile=") for argument in item)
        for item in commands
    )


def test_ssh_submission_stages_exact_config_and_uses_persistent_systemd_worker(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    source = tmp_path / "source-run"
    source.mkdir()
    (source / "manifest.json").write_text("{}\n", encoding="utf-8")
    config = tmp_path / "custom-name.yaml"
    config.write_text("schema_version: '0.7'\n", encoding="utf-8")
    commands: list[tuple[str, ...]] = []

    def fake_run(command: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Running as unit easydesign-apoe-50k.service.\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    submission = _executor(tmp_path).submit(
        job_id="apoe-50k",
        project_id="apoe",
        run_id="scale-50k",
        source_run=source,
        source_run_manifest_sha256="a" * 64,
        config_path=config,
        config_sha256="b" * 64,
    )

    rsync_commands = [item for item in commands if item[0] == "/usr/bin/rsync"]
    assert len(rsync_commands) == 2
    assert rsync_commands[1][-1].endswith(
        ":/data/easydesign/jobs/apoe-50k/input/easydesign.yaml"
    )
    launch = next(item for item in commands if "systemd-run" in item[-1])
    assert "EASYDESIGN_REMOTE_EXECUTOR_ID=suzhou2-a100x8" in launch[-1]
    assert "--from-run /data/easydesign/jobs/apoe-50k/source-run" in launch[-1]
    assert submission.remote_run_root == "/data/easydesign/runs/apoe/scale-50k"
    assert submission.source_run_manifest_sha256 == "a" * 64


def test_ssh_progress_resume_and_manifest_file_pull_are_explicit(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    snapshot = ProgressSnapshot(
        stage_id="06-scale-generation-and-refolding",
        updated_at=datetime(2026, 7, 27, 4, 0, tzinfo=UTC),
        status="running",
        total_tasks=20,
        pending_tasks=12,
        waiting_tasks=0,
        running_tasks=8,
        succeeded_tasks=0,
        failed_tasks=0,
        planned_candidates=50_000,
        collected_candidates=0,
    )
    commands: list[tuple[str, ...]] = []

    def fake_run(command: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        joined = " ".join(command)
        stdout = (
            snapshot.model_dump_json()
            if "runs watch" in joined
            else "Running as unit easydesign-job-resume-0001.service.\n"
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    (tmp_path / "easydesign-workspace.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "0.1",
                "workspace_id": "ssh-test",
                "runtime_root": "runtime",
                "projects_root": "projects",
                "runs_root": "runs",
                "archives_root": "archives",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))
    executor = _executor(tmp_path)

    observed = executor.progress(Path("/data/easydesign/runs/project/run"))
    resume_output = executor.resume(
        remote_run_root=Path("/data/easydesign/runs/project/run"),
        unit_name="easydesign-job-resume-0001",
    )
    executor.pull_files(
        remote_root=Path("/data/easydesign/runs/project/run"),
        relative_paths=("manifests/LATEST", "manifests/run-manifest-r0001.json"),
        destination=tmp_path / "runs" / "mirror",
    )

    assert observed.planned_candidates == 50_000
    assert "resume" in resume_output
    pull = next(item for item in commands if item[0] == "/usr/bin/rsync")
    assert "--files-from" in pull
    assert pull[-2].endswith(":/data/easydesign/runs/project/run/")
    assert any("runs resume" in item[-1] for item in commands)
