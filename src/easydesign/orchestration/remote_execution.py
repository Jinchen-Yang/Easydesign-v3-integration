"""Application API for checksum-verified whole-run SSH submission."""

from __future__ import annotations

import re
from pathlib import Path

from platformdirs import user_state_path

import easydesign
from easydesign.backends.executors import (
    SshRemoteConnection,
    SshRemoteExecutor,
    SshRemoteProbe,
    SshRemoteStatus,
    SshRemoteSubmission,
)
from easydesign.core import (
    ConfigurationError,
    ExecutionStatus,
    ManifestStateError,
    RunManifest,
    dump_model,
    load_model,
    sha256_file,
)

from .config import load_run_config
from .profile import LoadedRuntimeProfile, SshRemoteRuntime, load_runtime_profile


def _connection(
    executor_id: str,
    runtime: SshRemoteRuntime,
) -> SshRemoteConnection:
    for local_path, label in (
        (runtime.identity_file, "identity_file"),
        (runtime.known_hosts_file, "known_hosts_file"),
        (runtime.ssh_executable, "ssh_executable"),
        (runtime.rsync_executable, "rsync_executable"),
    ):
        if not local_path.is_file():
            raise ConfigurationError(f"remote executor {label} 不存在: {local_path}")
    return SshRemoteConnection(
        executor_id=executor_id,
        host=runtime.host,
        user=runtime.user,
        port=runtime.port,
        identity_file=runtime.identity_file,
        known_hosts_file=runtime.known_hosts_file,
        ssh_executable=runtime.ssh_executable,
        rsync_executable=runtime.rsync_executable,
        remote_work_root=runtime.remote_work_root,
        remote_runs_root=runtime.remote_runs_root,
        remote_easydesign_executable=runtime.remote_easydesign_executable,
        remote_profile=runtime.remote_profile,
        connect_timeout_seconds=runtime.connect_timeout_seconds,
    )


def _runtime(
    profile: LoadedRuntimeProfile,
    executor_id: str,
) -> SshRemoteRuntime:
    runtime = profile.profile.remote_executors.get(executor_id)
    if runtime is None:
        raise ConfigurationError(f"runtime profile 未声明 remote executor: {executor_id}")
    return runtime


def _executor(
    *,
    profile_path: Path | None,
    executor_id: str,
) -> SshRemoteExecutor:
    profile = load_runtime_profile(profile_path)
    return SshRemoteExecutor(_connection(executor_id, _runtime(profile, executor_id)))


def probe_remote_executor(
    *,
    executor_id: str,
    profile_path: Path | None = None,
) -> SshRemoteProbe:
    probe = _executor(profile_path=profile_path, executor_id=executor_id).probe()
    expected = easydesign.__version__
    if probe.easydesign_version != expected:
        raise ConfigurationError(
            f"remote EasyDesign 版本不一致: expected={expected}, "
            f"observed={probe.easydesign_version}"
        )
    return probe


def _latest_source_run(source_run: Path) -> tuple[RunManifest, Path]:
    root = source_run.expanduser().resolve()
    pointer = root / "manifests" / "LATEST"
    if not pointer.is_file():
        raise ManifestStateError(f"remote submission source 缺少 LATEST: {pointer}")
    manifest_path = root / "manifests" / pointer.read_text(encoding="utf-8").strip()
    manifest = load_model(manifest_path, RunManifest)
    if manifest.status is not ExecutionStatus.SUCCEEDED:
        raise ManifestStateError("remote submission source run 必须是 succeeded")
    for reference in manifest.stage_manifest_refs:
        reference.verify(root)
    return manifest, manifest_path


def remote_job_record_path(executor_id: str, job_id: str) -> Path:
    return (
        user_state_path("easydesign", appauthor=False)
        / "remote-jobs"
        / executor_id
        / f"{job_id}.json"
    )


def submit_remote_pipeline(
    *,
    executor_id: str,
    job_id: str,
    run_id: str,
    config_path: Path,
    source_run: Path,
    profile_path: Path | None = None,
) -> SshRemoteSubmission:
    for value, label in ((job_id, "job_id"), (run_id, "run_id")):
        if re.fullmatch(r"^[a-z0-9][a-z0-9._-]*$", value) is None:
            raise ConfigurationError(f"{label} 不符合稳定 ID 规则: {value}")
    config = load_run_config(config_path).config
    source_manifest, source_manifest_path = _latest_source_run(source_run)
    if source_manifest.project_id != config.project_id:
        raise ManifestStateError("remote config project_id 与 source run 不一致")
    probe_remote_executor(executor_id=executor_id, profile_path=profile_path)
    executor = _executor(profile_path=profile_path, executor_id=executor_id)
    submission = executor.submit(
        job_id=job_id,
        project_id=config.project_id,
        run_id=run_id,
        source_run=source_run.expanduser().resolve(),
        source_run_manifest_sha256=sha256_file(source_manifest_path),
        config_path=config_path.expanduser().resolve(),
        config_sha256=sha256_file(config_path.expanduser().resolve()),
    )
    record_path = remote_job_record_path(executor_id, job_id)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    dump_model(submission, record_path)
    return submission


def read_remote_submission(
    *,
    executor_id: str,
    job_id: str,
) -> SshRemoteSubmission:
    path = remote_job_record_path(executor_id, job_id)
    if not path.is_file():
        raise ConfigurationError(f"remote job record 不存在: {path}")
    return load_model(path, SshRemoteSubmission)


def read_remote_status(
    *,
    executor_id: str,
    job_id: str,
    profile_path: Path | None = None,
) -> SshRemoteStatus:
    submission = read_remote_submission(executor_id=executor_id, job_id=job_id)
    return _executor(
        profile_path=profile_path,
        executor_id=executor_id,
    ).status(submission.unit_name)
