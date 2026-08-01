"""Checksum-verified SSH submission, observation, recovery, and result mirroring."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

import easydesign
from easydesign.backends.executors import (
    ManagedJobRevision,
    ManagedWorkerProbe,
    RemoteJobBundle,
    RemoteJobInput,
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
    ProgressSnapshot,
    RunManifest,
    StageManifest,
    dump_model,
    load_model,
    sha256_file,
)
from easydesign.managed_protocol import (
    MINIMUM_MANAGED_AVAILABLE_BYTES,
    REQUIRED_MANAGED_BACKENDS,
    REQUIRED_MANAGED_GPU_COUNT,
    REQUIRED_MANAGED_STAGE_RANGES,
)
from easydesign.safe_writes import read_last_text_line
from easydesign.stages.s03_boltzgen_configuration.models import StrategyBundle
from easydesign.workspace_context import WorkspaceContext

from .config import load_run_config
from .profile import LoadedRuntimeProfile, SshRemoteRuntime, load_runtime_profile
from .ssh_pairing import RemoteExecutorPairingRevision, RemoteExecutorRegistry
from .task_tracking import atomic_dump_runtime_model
from .workspace import RunIndexEntry, upsert_run_index_entries

ModelT = TypeVar("ModelT", bound=BaseModel)

_REVIEW_ARTIFACT_ROLES = frozenset(
    {
        "target",
        "binder",
        "stage05-full-target-prediction",
        "protenix-summary-confidence",
        "protenix-full-confidence",
        "scientific-negative-result",
        "stage07-protenix-structure",
        "tnp-cdr-vernier-liability-evidence",
        "required-developability-evidence",
        "human-review-package",
    }
)
_MAX_REVIEW_ARTIFACT_BYTES = 25 * 1024 * 1024


class ManagedRemoteSubmission(BaseModel):
    """Controller-side immutable identity for one managed queue submission."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.2"
    revision: int = Field(default=1, ge=1)
    executor_id: str
    job_id: str
    controller_id: str
    project_id: str
    run_id: str
    submitted_at: datetime
    stage_range: tuple[int, ...]
    candidate_budget: int = Field(ge=1)
    requested_sync_mode: str = Field(pattern=r"^(metadata|review|complete)$")
    remote_job_root: str
    remote_run_root: str
    bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_run_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    queue_status: str
    source_run_mode: str = Field(
        default="uploaded-closure",
        pattern=r"^(uploaded-closure|managed-run)$",
    )
    managed_source_run: str | None = None


class ManagedRemoteObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    executor_id: str
    job_id: str
    checked_at: datetime
    connection_state: str = "connected"
    queue: ManagedJobRevision | None = None
    progress: ProgressSnapshot | None = None
    progress_error: str | None = None


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
        runtime = RemoteExecutorRegistry().active_runtimes().get(executor_id)
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
    registered = RemoteExecutorRegistry().active_runtimes()
    return tuple(sorted(set(profile.profile.remote_executors) | set(registered)))


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


def probe_managed_executor(
    *,
    executor_id: str,
    profile_path: Path | None = None,
) -> ManagedWorkerProbe:
    """Probe the fixed managed service rather than a generic remote shell."""

    executor = _executor(profile_path=profile_path, executor_id=executor_id)
    payload = executor.managed_worker_json("probe")
    probe = ManagedWorkerProbe.model_validate(payload)
    require_managed_probe_compatible(probe)
    return probe


def require_managed_probe_compatible(probe: ManagedWorkerProbe) -> None:
    """Fail closed unless the Manager can execute both linked stage chains."""

    if probe.easydesign_version != easydesign.__version__:
        raise ConfigurationError(
            "managed worker EasyDesign 版本不一致: "
            f"expected={easydesign.__version__}, observed={probe.easydesign_version}"
        )
    ranges = {tuple(item) for item in probe.supported_stage_ranges}
    missing_ranges = set(REQUIRED_MANAGED_STAGE_RANGES) - ranges
    backend_states: dict[str, bool] = {
        item.backend_id: item.ready for item in probe.backends
    }
    missing_backends = tuple(
        backend_id
        for backend_id in REQUIRED_MANAGED_BACKENDS
        if not backend_states.get(backend_id, False)
    )
    if (
        missing_ranges
        or missing_backends
        or probe.gpu_count != REQUIRED_MANAGED_GPU_COUNT
        or probe.filesystem_available_bytes < MINIMUM_MANAGED_AVAILABLE_BYTES
    ):
        raise ConfigurationError(
            "managed worker 未就绪: "
            f"missing_stage_ranges={sorted(missing_ranges)}, "
            f"unready_backends={list(missing_backends)}, "
            f"gpu_count={probe.gpu_count}, "
            f"filesystem_available_bytes={probe.filesystem_available_bytes}"
        )


def probe_pending_managed_executor(
    pairing: RemoteExecutorPairingRevision,
) -> ManagedWorkerProbe:
    """Probe an awaiting pairing before publishing a ``paired`` revision."""

    runtime = RemoteExecutorRegistry.runtime_for_record(pairing)
    executor = SshRemoteExecutor(_connection(pairing.executor_id, runtime))
    payload = executor.managed_worker_json("probe")
    probe = ManagedWorkerProbe.model_validate(payload)
    require_managed_probe_compatible(probe)
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


def _local_manifest_closure(
    source_run: Path,
    manifest: RunManifest,
    manifest_path: Path,
) -> tuple[str, ...]:
    """Return the verified, manifest-derived closure needed by a continuation."""

    root = source_run.expanduser().resolve()
    selected: set[str] = {
        manifest_path.relative_to(root).as_posix(),
        _safe_relative(manifest.config_snapshot.relative_path),
    }
    selected.update(
        _pointer_revision_closure(root, root / "manifests" / "LATEST")
    )
    stages: list[StageManifest] = []
    for reference in manifest.stage_manifest_refs:
        selected.add(_safe_relative(reference.relative_path))
        stage = load_model(reference.verify(root), StageManifest)
        stages.append(stage)
        selected.update(_safe_relative(item.relative_path) for item in _stage_artifacts(stage))
    inspected: set[str] = set()
    while True:
        additions: set[str] = set()
        for relative in sorted(selected - inspected):
            inspected.add(relative)
            path = root / relative
            if not path.is_file():
                raise ManifestStateError(f"managed submission 闭包缺失: {relative}")
            if path.suffix.lower() != ".json":
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for reference in _artifact_refs_in_json(payload):
                safe = _safe_relative(reference.relative_path)
                reference.verify(root)
                if safe not in selected:
                    additions.add(safe)
        if not additions:
            break
        selected.update(additions)
    _verify_local_manifest_closure(root, manifest, tuple(stages))
    return tuple(sorted(selected))


def _pointer_revision_closure(root: Path, pointer: Path) -> tuple[str, ...]:
    """Return the immutable base pointer and every published revision."""

    resolved_root = root.expanduser().resolve()
    candidates = [
        pointer,
        *sorted(pointer.with_name(f"{pointer.name}.revisions").glob("revision-*.txt")),
    ]
    selected: list[str] = []
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
            raise ManifestStateError(f"managed submission pointer 不安全: {candidate}")
        selected.append(_safe_relative(candidate.relative_to(resolved_root).as_posix()))
    return tuple(selected)


def _managed_config_input_closure(
    config_path: Path,
    candidates: Iterable[Path | None],
) -> tuple[tuple[str, Path], ...]:
    """Freeze config-relative local inputs without permitting path escape."""

    base = config_path.expanduser().resolve().parent
    selected: dict[str, Path] = {}
    for candidate in candidates:
        if candidate is None:
            continue
        resolved = candidate.expanduser().resolve(strict=True)
        if not resolved.is_file() or not resolved.is_relative_to(base):
            raise ConfigurationError(
                f"managed config 本地输入必须位于配置目录内: {resolved}"
            )
        relative = _safe_relative(resolved.relative_to(base).as_posix())
        selected[relative] = resolved
    return tuple(sorted(selected.items()))


def _copy_new_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as reader, destination.open("xb") as writer:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            writer.write(chunk)
        writer.flush()
        os.fsync(writer.fileno())


def _managed_stage_range(
    *,
    manifest: RunManifest,
    stop_after_stage: int,
) -> tuple[int, ...]:
    stages = tuple(
        int(reference.producer_stage.split("-", 1)[0])
        for reference in manifest.stage_manifest_refs
        if reference.producer_stage is not None
    )
    latest = max(stages, default=0)
    if latest == 3:
        return (4, 5) if stop_after_stage >= 5 else (4,)
    if latest == 5:
        return (6, 7) if stop_after_stage >= 7 else (6,)
    raise ManifestStateError("managed SSH 只接受 Stage 03→04/05 或 Stage 05→06/07 continuation")


def _managed_candidate_budget(
    *,
    source_run: Path,
    manifest: RunManifest,
    stage_range: tuple[int, ...],
    config: Any,
) -> int:
    if stage_range[0] == 6:
        assert config.stage06 is not None
        return 1_000 if config.stage06.scale_profile == "smoke-1000" else 50_000
    stage03_ref = next(
        (
            reference
            for reference in manifest.stage_manifest_refs
            if reference.producer_stage == "03-boltzgen-configuration"
        ),
        None,
    )
    if stage03_ref is None:
        raise ManifestStateError("managed Stage 04 提交缺少 Stage 03 manifest")
    stage03 = load_model(stage03_ref.verify(source_run), StageManifest)
    strategy_ref = stage03.require_output("strategy-bundle")
    bundle = load_model(strategy_ref.verify(source_run), StrategyBundle)
    stage03_config = config.stage03
    if stage03_config is None:
        raise ManifestStateError("managed Stage 04 提交缺少 Stage 03 config")
    return len(bundle.strategies) * int(stage03_config.candidates_per_strategy)


def _managed_record_root(executor_id: str, job_id: str) -> Path:
    context = WorkspaceContext.discover()
    return context.runtime_root / "state" / "managed-remote-jobs" / executor_id / job_id


def list_managed_remote_submissions(
    *,
    executor_id: str | None = None,
) -> tuple[ManagedRemoteSubmission, ...]:
    context = WorkspaceContext.discover()
    base = context.runtime_root / "state" / "managed-remote-jobs"
    candidates = (
        base.glob("*/*/revisions/revision-*.json")
        if executor_id is None
        else (base / executor_id).glob("*/revisions/revision-*.json")
    )
    latest: dict[tuple[str, str], Path] = {}
    for path in sorted(candidates):
        latest[(path.parents[2].name, path.parents[1].name)] = path
    return tuple(
        ManagedRemoteSubmission.model_validate_json(path.read_text(encoding="utf-8"))
        for path in latest.values()
    )


def read_managed_remote_submission(*, executor_id: str, job_id: str) -> ManagedRemoteSubmission:
    record = next(
        (
            item
            for item in list_managed_remote_submissions(executor_id=executor_id)
            if item.job_id == job_id
        ),
        None,
    )
    if record is None:
        raise ConfigurationError(f"managed remote job 不存在: {executor_id}/{job_id}")
    return record


def _matching_managed_source(
    *,
    executor: SshRemoteExecutor,
    executor_id: str,
    manifest: RunManifest,
    manifest_path: Path,
) -> tuple[ManagedRemoteSubmission, str] | None:
    """Find the same reviewed run in managed storage by immutable identity."""

    expected_remote = executor.connection.remote_runs_root / manifest.project_id / manifest.run_id
    candidates = sorted(
        (
            item
            for item in list_managed_remote_submissions(executor_id=executor_id)
            if item.project_id == manifest.project_id
            and item.run_id == manifest.run_id
            and Path(item.remote_run_root) == expected_remote
        ),
        key=lambda item: (item.submitted_at, item.job_id),
        reverse=True,
    )
    if not candidates:
        return None
    manifest_name = manifest_path.name
    identity = executor.file_identity(expected_remote / "manifests" / manifest_name)
    local_sha256 = sha256_file(manifest_path)
    if identity.sha256 != local_sha256:
        raise ManifestStateError("本地 review 镜像与 Suzhou2 managed source manifest 不一致")
    try:
        relative = expected_remote.relative_to(executor.connection.remote_work_root)
    except ValueError as error:
        raise ManifestStateError("Suzhou2 managed runs_root 不在 worker 根目录内") from error
    expected_relative = Path("runs") / manifest.project_id / manifest.run_id
    if relative != expected_relative:
        raise ManifestStateError("Suzhou2 managed source 必须位于 runs/<project>/<run>")
    return candidates[0], relative.as_posix()


def submit_managed_pipeline(
    *,
    executor_id: str,
    controller_id: str,
    job_id: str,
    run_id: str,
    config_path: Path,
    source_run: Path,
    profile_path: Path | None = None,
    maximum_gpus: int | None = None,
    sync_mode: str = "review",
) -> ManagedRemoteSubmission:
    """Stage and enqueue one manifest-closed continuation on a paired worker."""

    for value, label in (
        (executor_id, "executor_id"),
        (controller_id, "controller_id"),
        (job_id, "job_id"),
        (run_id, "run_id"),
    ):
        if re.fullmatch(r"^[a-z0-9][a-z0-9._-]*$", value) is None:
            raise ConfigurationError(f"{label} 不符合稳定 ID 规则: {value}")
    pairing = RemoteExecutorRegistry().latest(executor_id)
    if pairing is None or pairing.state != "paired":
        raise ConfigurationError(f"managed executor 尚未完成配对: {executor_id}")
    if pairing.controller_id != controller_id:
        raise ConfigurationError("controller_id 与 SSH 配对记录不一致")
    selected_source = source_run.expanduser().resolve()
    manifest, manifest_path = _latest_source_run(selected_source)
    selected_config = config_path.expanduser().resolve()
    loaded_config = load_run_config(selected_config)
    loaded = loaded_config.config
    if manifest.project_id != loaded.project_id:
        raise ManifestStateError("managed config project_id 与 source run 不一致")
    stage_range = _managed_stage_range(
        manifest=manifest,
        stop_after_stage=loaded.workflow.stop_after_stage,
    )
    budget = _managed_candidate_budget(
        source_run=selected_source,
        manifest=manifest,
        stage_range=stage_range,
        config=loaded,
    )
    config_inputs = _managed_config_input_closure(
        selected_config,
        (
            getattr(loaded_config, "source_path", None),
            getattr(loaded_config, "precomputed_msa_path", None),
        ),
    )
    local_record_root = _managed_record_root(executor_id, job_id)
    if local_record_root.exists():
        raise ConfigurationError(f"managed job 本地记录已存在: {job_id}")
    probe_managed_executor(executor_id=executor_id, profile_path=profile_path)
    executor = _executor(profile_path=profile_path, executor_id=executor_id)
    matching_source = _matching_managed_source(
        executor=executor,
        executor_id=executor_id,
        manifest=manifest,
        manifest_path=manifest_path,
    )
    managed_source_run = None if matching_source is None else matching_source[1]
    closure = (
        _local_manifest_closure(selected_source, manifest, manifest_path)
        if managed_source_run is None
        else ()
    )
    job_root = executor.connection.remote_work_root / "jobs" / job_id
    executor._run_remote(("test", "!", "-e", str(job_root)))
    if closure:
        executor._run_remote(("mkdir", "-p", str(job_root / "input" / "source-run")))
        executor.push_files(
            local_root=selected_source,
            relative_paths=closure,
            remote_root=job_root / "input" / "source-run",
        )

    staging = local_record_root / "submission-input"
    staging.mkdir(parents=True, exist_ok=False)
    frozen_config = staging / "easydesign.yaml"
    with frozen_config.open("xb") as handle:
        handle.write(selected_config.read_bytes())
        handle.flush()
        os.fsync(handle.fileno())
    inputs = [
        RemoteJobInput(
            relative_path="easydesign.yaml",
            size_bytes=frozen_config.stat().st_size,
            sha256=sha256_file(frozen_config),
            role="resolved-run-config",
        )
    ]
    for relative, source_path in config_inputs:
        frozen_input = staging / relative
        _copy_new_file(source_path, frozen_input)
        inputs.append(
            RemoteJobInput(
                relative_path=relative,
                size_bytes=frozen_input.stat().st_size,
                sha256=sha256_file(frozen_input),
                role="resolved-config-input",
            )
        )
    for relative in closure:
        path = selected_source / relative
        inputs.append(
            RemoteJobInput(
                relative_path=f"source-run/{relative}",
                size_bytes=path.stat().st_size,
                sha256=sha256_file(path),
                role="manifest-closure",
            )
        )
    bundle = RemoteJobBundle(
        job_id=job_id,
        controller_id=controller_id,
        controller_key_fingerprint=pairing.public_key_fingerprint,
        project_id=loaded.project_id,
        run_id=run_id,
        submitted_at=datetime.now(UTC),
        stage_range=stage_range,  # type: ignore[arg-type]
        candidate_budget=budget,
        easydesign_version=easydesign.__version__,
        config_sha256=sha256_file(frozen_config),
        upstream_manifest_sha256=sha256_file(manifest_path),
        inputs=tuple(inputs),
        source_run_mode=("uploaded-closure" if managed_source_run is None else "managed-run"),
        managed_source_run=managed_source_run,
        maximum_gpus=maximum_gpus,
        requested_sync_mode=sync_mode,  # type: ignore[arg-type]
    )
    bundle_path = staging / "remote-job-bundle.json"
    with bundle_path.open("x", encoding="utf-8") as handle:
        handle.write(bundle.model_dump_json(indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    if config_inputs:
        executor.push_files(
            local_root=staging,
            relative_paths=tuple(relative for relative, _ in config_inputs),
            remote_root=job_root / "input",
        )
    executor.push_file(source=frozen_config, remote_path=job_root / "input/easydesign.yaml")
    executor.push_file(
        source=bundle_path,
        remote_path=job_root / "input/remote-job-bundle.json",
    )
    queued = ManagedJobRevision.model_validate(
        executor.managed_worker_json(
            "enqueue",
            str(job_root / "input/remote-job-bundle.json"),
        )
    )
    submission = ManagedRemoteSubmission(
        executor_id=executor_id,
        job_id=job_id,
        controller_id=controller_id,
        project_id=loaded.project_id,
        run_id=run_id,
        submitted_at=bundle.submitted_at,
        stage_range=stage_range,
        candidate_budget=budget,
        requested_sync_mode=sync_mode,
        remote_job_root=str(job_root),
        remote_run_root=str(executor.connection.remote_runs_root / loaded.project_id / run_id),
        bundle_sha256=bundle.identity_sha256,
        source_run_manifest_sha256=sha256_file(manifest_path),
        config_sha256=sha256_file(frozen_config),
        queue_status=queued.status,
        source_run_mode=bundle.source_run_mode,
        managed_source_run=managed_source_run,
    )
    revision_path = local_record_root / "revisions/revision-000001.json"
    revision_path.parent.mkdir(parents=True, exist_ok=True)
    with revision_path.open("x", encoding="utf-8") as handle:
        handle.write(submission.model_dump_json(indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return submission


def observe_managed_pipeline(
    *,
    executor_id: str,
    job_id: str,
    profile_path: Path | None = None,
) -> ManagedRemoteObservation:
    executor = _executor(profile_path=profile_path, executor_id=executor_id)
    try:
        payload = executor.managed_worker_json("status", job_id)
        queue = ManagedJobRevision.model_validate(payload["queue"])
        raw_progress = payload.get("progress")
        progress = (
            None
            if raw_progress is None
            else ProgressSnapshot.model_validate(raw_progress)
        )
        raw_progress_error = payload.get("progress_error")
        if raw_progress_error is not None and not isinstance(raw_progress_error, str):
            raise ConfigurationError("managed worker progress_error 必须是 string 或 null")
        progress_error = raw_progress_error
        return ManagedRemoteObservation(
            executor_id=executor_id,
            job_id=job_id,
            checked_at=datetime.now(UTC),
            queue=queue,
            progress=progress,
            progress_error=progress_error,
        )
    except Exception as error:
        return ManagedRemoteObservation(
            executor_id=executor_id,
            job_id=job_id,
            checked_at=datetime.now(UTC),
            connection_state="temporarily-disconnected",
            progress_error=str(error)[:4096] or type(error).__name__,
        )


def remote_job_record_path(executor_id: str, job_id: str) -> Path:
    return WorkspaceContext.discover().remote_job_root / executor_id / f"{job_id}.json"


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
        root.glob("*/*.json") if executor_id is None else (root / executor_id).glob("*.json")
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
        raise ManifestStateError(f"远端模型无效: {relative_path}: {error}") from error


def _remote_manifest_closure(
    executor: SshRemoteExecutor,
    remote_root: Path,
) -> tuple[RunManifest, str, tuple[StageManifest, ...], set[str]]:
    latest_name, pointer_evidence = executor.read_versioned_pointer(
        remote_root / "manifests" / "LATEST"
    )
    if Path(latest_name).name != latest_name or not latest_name.endswith(".json"):
        raise ManifestStateError("远端 LATEST 指针无效")
    latest_relative = f"manifests/{latest_name}"
    manifest = _remote_model(executor, remote_root, latest_relative, RunManifest)
    paths = {
        *(
            _safe_relative(path.relative_to(remote_root).as_posix())
            for path in pointer_evidence
        ),
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
    """增量拉取 manifest 闭包。

    ``review`` 只跟随明确白名单中的小型审阅产物；``complete`` 才跟随
    全部嵌套 ArtifactRef。两者都不通过扫描远程目录猜测结果。
    """

    if mode not in {"metadata", "review", "complete"}:
        raise ConfigurationError("remote sync mode 只允许 metadata、review 或 complete")
    try:
        record = read_remote_job_record(executor_id=executor_id, job_id=job_id)
        remote_root = Path(record.submission.remote_run_root)
    except ConfigurationError:
        managed = read_managed_remote_submission(executor_id=executor_id, job_id=job_id)
        remote_root = Path(managed.remote_run_root)
    executor = _executor(profile_path=profile_path, executor_id=executor_id)
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

    if mode in {"review", "complete"}:
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
                    if mode == "review" and (
                        reference.role not in _REVIEW_ARTIFACT_ROLES
                        or reference.size_bytes > _MAX_REVIEW_ARTIFACT_BYTES
                    ):
                        continue
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
                if mode == "review" and reference.relative_path not in paths:
                    continue
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
                        f"Read-only remote mirror from {executor_id}/{job_id}; sync mode={mode}.",
                    ),
                ),
            ),
            generated_at=datetime.now(UTC),
        )
    return report
