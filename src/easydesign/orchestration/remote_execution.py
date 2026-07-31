"""Checksum-verified SSH submission, observation, recovery, and result mirroring."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

import easydesign
from easydesign.backends.executors import (
    SshRemoteConnection,
    SshRemoteExecutor,
    SshRemoteJobRecord,
    SshRemoteObservation,
    SshRemoteProbe,
    SshRemoteStatus,
    SshRemoteSubmission,
    SshRemoteSyncReport,
)
from easydesign.core import (
    ArtifactRef,
    ConfigurationError,
    ExecutionStatus,
    ManifestStateError,
    RunManifest,
    StageManifest,
    dump_model,
    load_model,
    sha256_file,
)
from easydesign.safe_writes import read_last_text_line
from easydesign.workspace_context import WorkspaceContext

from .config import load_run_config
from .profile import LoadedRuntimeProfile, SshRemoteRuntime, load_runtime_profile
from .task_tracking import atomic_dump_runtime_model
from .workspace import RunIndexEntry, upsert_run_index_entries

ModelT = TypeVar("ModelT", bound=BaseModel)


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


def resolve_remote_executor(
    *,
    profile_path: Path | None,
    executor_id: str,
) -> SshRemoteExecutor:
    """Resolve only an explicitly registered SSH executor; never scan SSH config."""

    return _executor(profile_path=profile_path, executor_id=executor_id)


def list_remote_executor_ids(
    *,
    profile_path: Path | None = None,
) -> tuple[str, ...]:
    """列出 profile 明确声明的远端；不扫描 SSH config 或局域网。"""

    profile = load_runtime_profile(profile_path)
    return tuple(sorted(profile.profile.remote_executors))


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
    manifest_path = root / "manifests" / read_last_text_line(pointer)
    manifest = load_model(manifest_path, RunManifest)
    if manifest.status is not ExecutionStatus.SUCCEEDED:
        raise ManifestStateError("remote submission source run 必须是 succeeded")
    manifest.config_snapshot.verify(root)
    for reference in manifest.stage_manifest_refs:
        reference.verify(root)
    return manifest, manifest_path


def remote_job_record_path(executor_id: str, job_id: str) -> Path:
    return (
        WorkspaceContext.discover().remote_job_root
        / executor_id
        / f"{job_id}.json"
    )


def _new_job_record(submission: SshRemoteSubmission) -> SshRemoteJobRecord:
    return SshRemoteJobRecord(
        submission=submission,
        active_unit_name=submission.unit_name,
        unit_history=(submission.unit_name,),
        updated_at=submission.submitted_at,
    )


def read_remote_job_record(
    *,
    executor_id: str,
    job_id: str,
) -> SshRemoteJobRecord:
    path = remote_job_record_path(executor_id, job_id)
    if not path.is_file():
        raise ConfigurationError(f"remote job record 不存在: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ConfigurationError(f"remote job record 无效: {path}")
    if "submission" in payload:
        return SshRemoteJobRecord.model_validate(payload)
    # dev11 只保存 submission；读取时迁移为内存中的 0.2 记录，不改写历史文件。
    return _new_job_record(SshRemoteSubmission.model_validate(payload))


def list_remote_job_records(
    *,
    executor_id: str | None = None,
) -> tuple[SshRemoteJobRecord, ...]:
    root = WorkspaceContext.discover().remote_job_root
    if not root.is_dir():
        return ()
    candidates = (
        root.glob("*/*.json")
        if executor_id is None
        else (root / executor_id).glob("*.json")
    )
    records: list[SshRemoteJobRecord] = []
    for path in sorted(candidates):
        records.append(
            read_remote_job_record(
                executor_id=path.parent.name,
                job_id=path.stem,
            )
        )
    return tuple(records)


def submit_remote_pipeline(
    *,
    executor_id: str,
    job_id: str,
    run_id: str,
    config_path: Path,
    source_run: Path | None = None,
    project_root: Path | None = None,
    profile_path: Path | None = None,
) -> SshRemoteSubmission:
    """提交 continuation，或把一个完整项目目录提交为全新远端 run。"""

    for value, label in ((job_id, "job_id"), (run_id, "run_id")):
        if re.fullmatch(r"^[a-z0-9][a-z0-9._-]*$", value) is None:
            raise ConfigurationError(f"{label} 不符合稳定 ID 规则: {value}")
    if (source_run is None) == (project_root is None):
        raise ConfigurationError("remote submit 必须且只能提供 source_run 或 project_root")
    selected_config = config_path.expanduser().resolve()
    config = load_run_config(selected_config).config
    probe_remote_executor(executor_id=executor_id, profile_path=profile_path)
    executor = _executor(profile_path=profile_path, executor_id=executor_id)
    if source_run is not None:
        source_manifest, source_manifest_path = _latest_source_run(source_run)
        if source_manifest.project_id != config.project_id:
            raise ManifestStateError("remote config project_id 与 source run 不一致")
        submission = executor.submit(
            job_id=job_id,
            project_id=config.project_id,
            run_id=run_id,
            source_run=source_run.expanduser().resolve(),
            source_run_manifest_sha256=sha256_file(source_manifest_path),
            config_path=selected_config,
            config_sha256=sha256_file(selected_config),
        )
    else:
        assert project_root is not None
        root = project_root.expanduser().resolve()
        if not root.is_dir():
            raise ConfigurationError(f"remote project root 不存在: {root}")
        try:
            config_relative = selected_config.relative_to(root)
        except ValueError as error:
            raise ConfigurationError("remote config 必须位于 project_root 内") from error
        submission = executor.submit_project(
            job_id=job_id,
            project_id=config.project_id,
            run_id=run_id,
            project_root=root,
            config_relative_path=config_relative,
            config_sha256=sha256_file(selected_config),
        )
    record_path = remote_job_record_path(executor_id, job_id)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    dump_model(_new_job_record(submission), record_path)
    return submission


def read_remote_submission(
    *,
    executor_id: str,
    job_id: str,
) -> SshRemoteSubmission:
    return read_remote_job_record(
        executor_id=executor_id,
        job_id=job_id,
    ).submission


def read_remote_status(
    *,
    executor_id: str,
    job_id: str,
    profile_path: Path | None = None,
) -> SshRemoteStatus:
    record = read_remote_job_record(executor_id=executor_id, job_id=job_id)
    return _executor(
        profile_path=profile_path,
        executor_id=executor_id,
    ).status(record.active_unit_name)


def observe_remote_pipeline(
    *,
    executor_id: str,
    job_id: str,
    profile_path: Path | None = None,
) -> SshRemoteObservation:
    """读取 worker 和结构化 progress；progress 不可用时保留 worker 事实。"""

    record = read_remote_job_record(executor_id=executor_id, job_id=job_id)
    executor = _executor(profile_path=profile_path, executor_id=executor_id)
    worker = executor.status(record.active_unit_name)
    progress = None
    progress_error = None
    try:
        progress = executor.progress(Path(record.submission.remote_run_root))
    except Exception as error:
        progress_error = str(error)[:4096] or error.__class__.__name__
    return SshRemoteObservation(
        executor_id=executor_id,
        job_id=job_id,
        checked_at=datetime.now(UTC),
        remote_run_root=record.submission.remote_run_root,
        worker=worker,
        progress=progress,
        progress_error=progress_error,
    )


def resume_remote_pipeline(
    *,
    executor_id: str,
    job_id: str,
    profile_path: Path | None = None,
) -> SshRemoteJobRecord:
    """在断线、进程失败或主机重启后显式创建新的 systemd resume unit。"""

    record = read_remote_job_record(executor_id=executor_id, job_id=job_id)
    executor = _executor(profile_path=profile_path, executor_id=executor_id)
    current = executor.status(record.active_unit_name)
    if current.active_state == "active":
        raise ConfigurationError("远端 worker 仍在运行，禁止重复 resume")
    probe_remote_executor(executor_id=executor_id, profile_path=profile_path)
    next_count = record.resume_count + 1
    unit_name = f"{record.submission.unit_name}-resume-{next_count:04d}"
    executor.resume(
        remote_run_root=Path(record.submission.remote_run_root),
        unit_name=unit_name,
    )
    updated = record.model_copy(
        update={
            "active_unit_name": unit_name,
            "unit_history": (*record.unit_history, unit_name),
            "resume_count": next_count,
            "updated_at": datetime.now(UTC),
        }
    )
    atomic_dump_runtime_model(
        updated,
        remote_job_record_path(executor_id, job_id),
    )
    return updated


def _safe_relative(value: str) -> str:
    path = Path(value)
    if value in {"", "."} or path.is_absolute() or ".." in path.parts:
        raise ManifestStateError(f"remote artifact 路径不安全: {value}")
    return path.as_posix()


def _stage_artifacts(stage: StageManifest) -> Iterable[ArtifactRef]:
    yield from stage.input_artifacts
    yield from stage.output_artifacts
    for attempt in stage.attempts:
        yield from attempt.log_artifacts


def _remote_model(
    executor: SshRemoteExecutor,
    remote_root: Path,
    relative_path: str,
    model_type: type[ModelT],
) -> ModelT:
    try:
        return model_type.model_validate_json(
            executor.read_text(remote_root / _safe_relative(relative_path))
        )
    except ValueError as error:
        raise ManifestStateError(
            f"远端模型无效: {relative_path}: {error}"
        ) from error


def _remote_manifest_closure(
    executor: SshRemoteExecutor,
    remote_root: Path,
) -> tuple[RunManifest, str, tuple[StageManifest, ...], set[str]]:
    remote_pointer_lines = [
        line.strip()
        for line in executor.read_text(remote_root / "manifests" / "LATEST").splitlines()
        if line.strip()
    ]
    if not remote_pointer_lines:
        raise ManifestStateError("远端 run LATEST 没有有效 revision")
    latest_name = remote_pointer_lines[-1]
    if Path(latest_name).name != latest_name or not latest_name.endswith(".json"):
        raise ManifestStateError("远端 LATEST 指针无效")
    latest_relative = f"manifests/{latest_name}"
    manifest = _remote_model(executor, remote_root, latest_relative, RunManifest)
    paths = {
        "manifests/LATEST",
        latest_relative,
        _safe_relative(manifest.config_snapshot.relative_path),
    }
    stages: list[StageManifest] = []
    for reference in manifest.stage_manifest_refs:
        paths.add(_safe_relative(reference.relative_path))
        stage = _remote_model(
            executor,
            remote_root,
            reference.relative_path,
            StageManifest,
        )
        stages.append(stage)
        paths.update(_safe_relative(item.relative_path) for item in _stage_artifacts(stage))
    for relative in (
        "06-scale-generation-and-refolding/attempt-0001/runtime/progress.json",
        "06-scale-generation-and-refolding/attempt-0001/runtime/scale-state.json",
        "06-scale-generation-and-refolding/attempt-0001/runtime/task-events.jsonl",
    ):
        if executor.is_file(remote_root / relative):
            paths.add(relative)
    return manifest, latest_relative, tuple(stages), paths


def _artifact_refs_in_json(value: Any) -> Iterable[ArtifactRef]:
    if isinstance(value, dict):
        required = {
            "artifact_id",
            "role",
            "relative_path",
            "file_format",
            "sha256",
            "size_bytes",
        }
        if required.issubset(value):
            try:
                yield ArtifactRef.model_validate(value)
            except ValueError:
                pass
        for child in value.values():
            yield from _artifact_refs_in_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _artifact_refs_in_json(child)


def _verify_local_manifest_closure(
    destination: Path,
    manifest: RunManifest,
    stages: tuple[StageManifest, ...],
) -> None:
    manifest.config_snapshot.verify(destination)
    for reference, stage in zip(manifest.stage_manifest_refs, stages, strict=True):
        reference.verify(destination)
        for artifact in _stage_artifacts(stage):
            artifact.verify(destination)


def sync_remote_pipeline(
    *,
    executor_id: str,
    job_id: str,
    destination: Path,
    mode: str = "metadata",
    profile_path: Path | None = None,
) -> SshRemoteSyncReport:
    """增量拉取 manifest 闭包；complete 额外拉取嵌套 candidate ArtifactRef。"""

    if mode not in {"metadata", "complete"}:
        raise ConfigurationError("remote sync mode 只允许 metadata 或 complete")
    record = read_remote_job_record(executor_id=executor_id, job_id=job_id)
    executor = _executor(profile_path=profile_path, executor_id=executor_id)
    remote_root = Path(record.submission.remote_run_root)
    target = destination.expanduser().resolve()
    if target.is_symlink():
        raise ConfigurationError("remote sync destination 禁止 symlink")
    manifest, latest_relative, stages, paths = _remote_manifest_closure(
        executor,
        remote_root,
    )
    executor.pull_files(
        remote_root=remote_root,
        relative_paths=tuple(sorted(paths)),
        destination=target,
    )
    _verify_local_manifest_closure(target, manifest, stages)

    if mode == "complete":
        inspected: set[str] = set()
        while True:
            new_paths: set[str] = set()
            for relative in sorted(paths - inspected):
                inspected.add(relative)
                path = target / relative
                if path.suffix.lower() != ".json" or not path.is_file():
                    continue
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                for reference in _artifact_refs_in_json(payload):
                    safe = _safe_relative(reference.relative_path)
                    if safe not in paths:
                        new_paths.add(safe)
            if not new_paths:
                break
            executor.pull_files(
                remote_root=remote_root,
                relative_paths=tuple(sorted(new_paths)),
                destination=target,
            )
            paths.update(new_paths)
        for relative in sorted(paths):
            path = target / relative
            if path.suffix.lower() != ".json" or not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for reference in _artifact_refs_in_json(payload):
                reference.verify(target)

    manifest_path = target / latest_relative
    files = tuple(path for path in target.rglob("*") if path.is_file())
    report = SshRemoteSyncReport(
        executor_id=executor_id,
        job_id=job_id,
        mode=mode,
        synced_at=datetime.now(UTC),
        destination=target,
        remote_run_root=str(remote_root),
        file_count=len(files),
        size_bytes=sum(path.stat().st_size for path in files),
        run_manifest_sha256=sha256_file(manifest_path),
        completed_artifact_closure=mode == "complete",
    )
    atomic_dump_runtime_model(report, target / ".remote-sync-report.json")

    if target.parent.name == manifest.project_id and target.name == manifest.run_id:
        runs_root = target.parent.parent
        upsert_run_index_entries(
            runs_root,
            (
                RunIndexEntry(
                    category="project-run",
                    path=f"{manifest.project_id}/{manifest.run_id}",
                    layout_version="1",
                    status=str(manifest.status),
                    project_id=manifest.project_id,
                    run_id=manifest.run_id,
                    notes=(
                        f"Read-only remote mirror from {executor_id}/{job_id}; "
                        f"sync mode={mode}.",
                    ),
                ),
            ),
            generated_at=datetime.now(UTC),
        )
    return report
