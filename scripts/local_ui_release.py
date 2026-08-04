"""Prepare and activate immutable localhost UI releases without touching workers."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from email.parser import Parser
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from easydesign.core import ConfigurationError
from easydesign.orchestration.task_tracking import load_latest_runtime_model
from easydesign.ui.models import UiJobRecord
from easydesign.workspace_context import WorkspaceContext

ROOT = Path(__file__).resolve().parents[1]
FORMAL_PORT = 18769
DEFAULT_PROBE_PORT = 18768
ACTIVE_UI_JOB_STATUSES = {
    "queued",
    "waiting-resource",
    "admitting",
    "running",
    "drain-requested",
    "submitted",
}
RELEASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{1,159}$")


class LocalUiRelease(BaseModel):
    """Identity and provenance frozen inside one immutable release directory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    release_id: str
    version: str
    wheel_filename: str
    wheel_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    uv_lock_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    created_at: datetime


class LocalUiActivation(BaseModel):
    """One append-only successful activation or rollback."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    revision: int = Field(ge=1)
    action: Literal["activate", "rollback"]
    release_id: str
    version: str
    wheel_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    previous_revision: int | None = None
    process_id: int = Field(ge=1)
    log_path: str
    activated_at: datetime


class StartedProcess:
    """Small protocol wrapper used by production Popen and deterministic tests."""

    def __init__(self, process: subprocess.Popen[bytes], log_path: Path) -> None:
        self.process = process
        self.log_path = log_path

    @property
    def pid(self) -> int:
        return self.process.pid

    def poll(self) -> int | None:
        return self.process.poll()

    def terminate(self) -> None:
        self.process.terminate()

    def wait(self, timeout: float) -> int:
        return self.process.wait(timeout=timeout)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_exclusive(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, allow_nan=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _wheel_identity(path: Path) -> tuple[str, str]:
    try:
        with ZipFile(path) as archive:
            metadata_files = [
                name
                for name in archive.namelist()
                if name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_files) != 1:
                raise ConfigurationError("wheel 必须且只能包含一份 dist-info/METADATA")
            metadata = Parser().parsestr(
                archive.read(metadata_files[0]).decode("utf-8")
            )
    except (BadZipFile, KeyError, OSError, UnicodeDecodeError) as error:
        raise ConfigurationError(f"wheel metadata 无法验证: {error}") from error
    name = metadata.get("Name", "").strip().lower()
    version = metadata.get("Version", "").strip()
    if name != "easydesign" or not version:
        raise ConfigurationError("wheel identity 必须是带明确版本的 easydesign")
    return name, version


def _resolve_uv(explicit: Path | None = None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    candidates.extend(
        sorted((ROOT / "runtime" / "tools").glob("uv-*/bin/uv"), reverse=True)
    )
    discovered = shutil.which("uv")
    if discovered:
        candidates.append(Path(discovered))
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    raise ConfigurationError("找不到精确 uv；请先完成 workspace uv onboarding")


def _environment(context: WorkspaceContext) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(context.child_environment())
    # Dependency artifacts belong to this source checkout and its frozen lock,
    # not to the destination workspace. Missing archives may be fetched during
    # hashed requirements sync; the EasyDesign wheel itself remains local-only.
    environment["UV_CACHE_DIR"] = str(ROOT / "runtime" / "cache" / "uv")
    environment["UV_SYSTEM_CERTS"] = "1"
    environment["UV_PYTHON_DOWNLOADS"] = "never"
    return environment


def _run_checked(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=cwd,
        env=environment,
        check=True,
        capture_output=capture_output,
        text=True,
        timeout=600,
    )


def _git_output(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return completed.stdout.strip()


def _require_clean_synced_main() -> str:
    if _git_output("branch", "--show-current") != "main":
        raise ConfigurationError("正式 local UI release 只允许从 main 准备")
    if _git_output("status", "--porcelain"):
        raise ConfigurationError("正式 local UI release 要求 clean worktree")
    head = _git_output("rev-parse", "HEAD")
    remote = _git_output("rev-parse", "origin/main")
    if head != remote:
        raise ConfigurationError("正式 local UI release 要求 HEAD == origin/main")
    return head


def _release_root(context: WorkspaceContext) -> Path:
    return context.runtime_root / "releases" / "local-ui"


def _release_path(context: WorkspaceContext, release_id: str) -> Path:
    if RELEASE_ID_PATTERN.fullmatch(release_id) is None or ".." in release_id:
        raise ConfigurationError("local UI release_id 非法")
    path = (_release_root(context) / release_id).resolve()
    if not path.is_relative_to(_release_root(context).resolve()):
        raise ConfigurationError("local UI release_id 逃出 release root")
    return path


def load_release(context: WorkspaceContext, release_id: str) -> LocalUiRelease:
    root = _release_path(context, release_id)
    try:
        record = LocalUiRelease.model_validate_json(
            (root / "release.json").read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise ConfigurationError(f"local UI release record 无法验证: {release_id}") from error
    if record.release_id != release_id:
        raise ConfigurationError("local UI release 目录与 record identity 不一致")
    wheel = root / "wheel" / record.wheel_filename
    if not wheel.is_file() or _sha256(wheel) != record.wheel_sha256:
        raise ConfigurationError("local UI release wheel identity 不一致")
    frozen_lock = root / "uv.lock"
    if not frozen_lock.is_file() or _sha256(frozen_lock) != record.uv_lock_sha256:
        raise ConfigurationError("local UI release 内的 uv.lock identity 不一致")
    command = root / "venv" / "bin" / "easydesign"
    if not command.is_file():
        raise ConfigurationError("local UI release 缺少非 editable console script")
    return record


def _installed_identity(release_root: Path) -> dict[str, str]:
    python = release_root / "venv" / "bin" / "python"
    program = (
        "import easydesign,json,pathlib;"
        "print(json.dumps({'version':easydesign.__version__,"
        "'module':str(pathlib.Path(easydesign.__file__).resolve())}))"
    )
    completed = subprocess.run(
        [str(python), "-I", "-c", program],
        cwd=release_root,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise ConfigurationError("installed identity 不是 object")
    module = Path(str(payload.get("module", ""))).resolve()
    if not module.is_relative_to((release_root / "venv").resolve()):
        raise ConfigurationError("local UI release 意外导入 editable/source checkout")
    return {"version": str(payload.get("version", "")), "module": str(module)}


def _formal_command(
    context: WorkspaceContext,
    release_root: Path,
    *,
    port: int,
) -> list[str]:
    command = [
        str(release_root / "venv" / "bin" / "easydesign"),
        "ui",
        "serve",
        "--host",
        "127.0.0.1",
        "--runs-root",
        str(context.runs_root),
        "--projects-root",
        str(context.projects_root),
        "--port",
        str(port),
    ]
    if context.profile_path.is_file():
        command.extend(["--profile", str(context.profile_path)])
    return command


def _wait_health(
    *,
    port: int,
    expected_version: str | None,
    process: StartedProcess,
    timeout_seconds: float = 25.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error = "health 尚未响应"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ConfigurationError("local UI process 在 health 前退出")
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/v1/health", timeout=1.0
            ) as response:
                raw_payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(raw_payload, dict):
                raise ConfigurationError("local UI health payload 不是 object")
            payload = cast(dict[str, Any], raw_payload)
            if payload.get("status") != "ok":
                raise ConfigurationError("local UI health status 不是 ok")
            if expected_version is not None and payload.get("version") != expected_version:
                raise ConfigurationError("local UI health 版本与 release 不一致")
            if payload.get("deployment_mode") != "formal":
                raise ConfigurationError("正式 local UI 意外运行在 development 模式")
            return payload
        except (OSError, ValueError, urllib.error.URLError) as error:
            last_error = str(error)
            time.sleep(0.25)
    raise ConfigurationError(f"local UI health 超时: {last_error}")


def _terminate_started(process: StartedProcess) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=15.0)
    except subprocess.TimeoutExpired as error:
        raise ConfigurationError("local UI 未响应 SIGTERM；不会升级为强制终止") from error


def _probe_release(
    context: WorkspaceContext,
    release_root: Path,
    *,
    version: str,
    port: int,
) -> None:
    if port == FORMAL_PORT or not 1 <= port <= 65535:
        raise ConfigurationError("release probe 必须使用合法的非 18769 端口")
    log_path = release_root / "probe.log"
    with log_path.open("xb") as log:
        process = subprocess.Popen(
            _formal_command(context, release_root, port=port),
            cwd=context.root,
            env=_environment(context),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    started = StartedProcess(process, log_path)
    try:
        _wait_health(port=port, expected_version=version, process=started)
    finally:
        _terminate_started(started)


def prepare_release(
    *,
    wheel: Path,
    uv: Path | None = None,
    probe_port: int = DEFAULT_PROBE_PORT,
    context: WorkspaceContext | None = None,
    enforce_git: bool = True,
) -> LocalUiRelease:
    """Create one immutable release; failures move staging to quarantine."""

    selected = WorkspaceContext.discover(ROOT) if context is None else context
    selected.ensure_layout()
    source_commit = _require_clean_synced_main() if enforce_git else "0" * 40
    source_wheel = wheel.expanduser().resolve()
    if not source_wheel.is_file():
        raise ConfigurationError(f"正式 wheel 不存在: {source_wheel}")
    _, version = _wheel_identity(source_wheel)
    if enforce_git:
        if not source_wheel.is_relative_to((ROOT / "dist").resolve()):
            raise ConfigurationError("正式 local UI release 只接受 dist/ 下的 wheel")
        with (ROOT / "pyproject.toml").open("rb") as handle:
            project_version = tomllib.load(handle)["project"]["version"]
        if version != project_version:
            raise ConfigurationError("wheel 版本与 pyproject.toml 不一致")
    wheel_sha256 = _sha256(source_wheel)
    release_id = f"{version}-{wheel_sha256}"
    target = _release_path(selected, release_id)
    if target.exists():
        return load_release(selected, release_id)

    uv_path = _resolve_uv(uv)
    if enforce_git:
        validation_environment = _environment(selected)
        validation_environment["EASYDESIGN_UV"] = str(uv_path)
        _run_checked(
            [
                str(ROOT / ".venv" / "bin" / "python"),
                str(ROOT / "scripts" / "check_built_wheel.py"),
                "--wheel",
                str(source_wheel),
            ],
            cwd=ROOT,
            environment=validation_environment,
        )
    operation_id = (
        "local-ui-release-"
        f"{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{uuid4().hex[:10]}"
    )
    staging = selected.runtime_root / "tmp" / operation_id
    selected.assert_write_path(staging)
    staging.mkdir(parents=True, exist_ok=False)
    try:
        wheel_root = staging / "wheel"
        wheel_root.mkdir()
        staged_wheel = wheel_root / source_wheel.name
        shutil.copy2(source_wheel, staged_wheel)
        if _sha256(staged_wheel) != wheel_sha256:
            raise ConfigurationError("staged wheel SHA-256 与输入不一致")
        frozen_lock = staging / "uv.lock"
        shutil.copy2(ROOT / "uv.lock", frozen_lock)

        environment = _environment(selected)
        exported = _run_checked(
            [
                str(uv_path),
                "export",
                "--frozen",
                "--offline",
                "--no-dev",
                "--extra",
                "ui",
                "--no-emit-project",
                "--format",
                "requirements.txt",
            ],
            cwd=ROOT,
            environment=environment,
            capture_output=True,
        )
        requirements = staging / "requirements.lock"
        with requirements.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(exported.stdout)
            if not exported.stdout.endswith("\n"):
                handle.write("\n")
        venv = staging / "venv"
        _run_checked(
            [
                str(uv_path),
                "venv",
                "--relocatable",
                "--python",
                str(ROOT / ".venv" / "bin" / "python"),
                str(venv),
            ],
            cwd=ROOT,
            environment=environment,
        )
        _run_checked(
            [
                str(uv_path),
                "pip",
                "sync",
                "--python",
                str(venv / "bin" / "python"),
                "--require-hashes",
                str(requirements),
            ],
            cwd=ROOT,
            environment=environment,
        )
        _run_checked(
            [
                str(uv_path),
                "pip",
                "install",
                "--python",
                str(venv / "bin" / "python"),
                "--offline",
                "--no-deps",
                "--reinstall",
                str(staged_wheel),
            ],
            cwd=ROOT,
            environment=environment,
        )
        identity = _installed_identity(staging)
        if identity["version"] != version:
            raise ConfigurationError("安装后的 EasyDesign 版本与 wheel metadata 不一致")
        record = LocalUiRelease(
            release_id=release_id,
            version=version,
            wheel_filename=source_wheel.name,
            wheel_sha256=wheel_sha256,
            uv_lock_sha256=_sha256(frozen_lock),
            source_commit=source_commit,
            created_at=datetime.now(tz=UTC),
        )
        _write_json_exclusive(
            staging / "release.json", record.model_dump(mode="json")
        )
        _probe_release(
            selected,
            staging,
            version=version,
            port=probe_port,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        os.rename(staging, target)
        if _installed_identity(target)["version"] != version:
            raise ConfigurationError("relocatable venv 发布后 identity 失效")
        return load_release(selected, release_id)
    except Exception as error:
        failed = target if target.exists() else staging
        if failed.exists():
            selected.quarantine(
                failed,
                operation="local-ui-release",
                reason=str(error)[:1000],
            )
        if isinstance(error, ConfigurationError):
            raise
        raise ConfigurationError(f"local UI release 准备失败: {error}") from error


def _activation_root(context: WorkspaceContext) -> Path:
    return context.runtime_root / "state" / "local-ui-activations"


def latest_activation(context: WorkspaceContext) -> LocalUiActivation | None:
    errors: list[str] = []
    for path in reversed(sorted(_activation_root(context).glob("revision-*.json"))):
        try:
            return LocalUiActivation.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as error:
            errors.append(f"{path.name}: {error}")
    if errors:
        raise ConfigurationError("local UI activation 没有合法 revision: " + "; ".join(errors))
    return None


def _append_activation(
    context: WorkspaceContext,
    *,
    release: LocalUiRelease,
    action: Literal["activate", "rollback"],
    process_id: int,
    log_path: Path,
) -> LocalUiActivation:
    root = _activation_root(context)
    root.mkdir(parents=True, exist_ok=True)
    previous = latest_activation(context)
    revisions = sorted(root.glob("revision-*.json"))
    revision = 1 if not revisions else int(revisions[-1].stem.split("-")[-1]) + 1
    record = LocalUiActivation(
        revision=revision,
        action=action,
        release_id=release.release_id,
        version=release.version,
        wheel_sha256=release.wheel_sha256,
        previous_revision=None if previous is None else previous.revision,
        process_id=process_id,
        log_path=log_path.relative_to(context.root).as_posix(),
        activated_at=datetime.now(tz=UTC),
    )
    _write_json_exclusive(
        root / f"revision-{revision:06d}.json", record.model_dump(mode="json")
    )
    return record


@contextmanager
def _operation_lock(context: WorkspaceContext) -> Iterator[None]:
    root = context.runtime_root / "state" / "local-ui"
    root.mkdir(parents=True, exist_ok=True)
    with (root / "operation.lock").open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _active_ui_jobs(context: WorkspaceContext) -> tuple[str, ...]:
    active: list[str] = []
    for path in sorted(context.ui_job_root.glob("job-*.json")):
        try:
            record = load_latest_runtime_model(path, UiJobRecord)
        except Exception as error:
            raise ConfigurationError(f"UI job record 无法验证: {path.name}") from error
        if record.status in ACTIVE_UI_JOB_STATUSES:
            active.append(record.job_id)
    return tuple(active)


def _listener_pid() -> int | None:
    socket_inodes: set[str] = set()
    observed_proc_net = False
    for table in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        if not table.is_file():
            continue
        observed_proc_net = True
        try:
            lines = table.read_text(encoding="utf-8").splitlines()[1:]
        except OSError as error:
            raise ConfigurationError(f"无法读取 {table}") from error
        for line in lines:
            fields = line.split()
            if len(fields) < 10 or fields[3] != "0A":
                continue
            try:
                port = int(fields[1].rsplit(":", maxsplit=1)[1], 16)
            except (IndexError, ValueError):
                continue
            if port == FORMAL_PORT:
                socket_inodes.add(fields[9])
    if not observed_proc_net:
        raise ConfigurationError("当前平台缺少 /proc/net，无法审计 18769 listener")
    if not socket_inodes:
        return None

    pids: set[int] = set()
    for process_root in Path("/proc").iterdir():
        if not process_root.name.isdigit():
            continue
        file_descriptors = process_root / "fd"
        try:
            descriptors = tuple(file_descriptors.iterdir())
        except OSError:
            continue
        for descriptor in descriptors:
            try:
                target = os.readlink(descriptor)
            except OSError:
                continue
            if target.startswith("socket:[") and target[8:-1] in socket_inodes:
                pids.add(int(process_root.name))
                break
    if not pids:
        raise ConfigurationError("18769 正在监听，但无法解析其 PID identity")
    if len(pids) != 1:
        raise ConfigurationError(f"18769 存在多个 listener PID: {sorted(pids)}")
    return next(iter(pids))


def _validated_listener(
    context: WorkspaceContext,
    current: LocalUiActivation | None,
) -> tuple[int, tuple[str, ...]] | None:
    pid = _listener_pid()
    if pid is None:
        return None
    try:
        arguments = tuple(
            item.decode("utf-8")
            for item in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            if item
        )
        cwd = Path(f"/proc/{pid}/cwd").resolve()
    except (OSError, UnicodeDecodeError) as error:
        raise ConfigurationError("无法验证 18769 listener identity") from error
    joined = " ".join(arguments)
    if cwd != context.root or "easydesign" not in joined or " ui serve " not in f" {joined} ":
        raise ConfigurationError("18769 listener 不是当前 workspace 的 EasyDesign UI")
    if "--port" not in arguments or str(FORMAL_PORT) not in arguments:
        raise ConfigurationError("18769 listener command line 与端口不一致")
    if current is not None:
        expected = _release_path(context, current.release_id).resolve()
        if not any(
            Path(item).resolve(strict=False).is_relative_to(expected)
            for item in arguments[:2]
        ):
            raise ConfigurationError("18769 listener 不是当前 activation 的 immutable release")
    return pid, arguments


def _stop_listener(pid: int) -> None:
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.2)
    raise ConfigurationError("正式 UI 未响应 SIGTERM；不会终止科学 worker 或强制 kill")


def _launch_release(
    context: WorkspaceContext,
    release: LocalUiRelease,
    *,
    label: str,
) -> StartedProcess:
    root = _release_path(context, release.release_id)
    log_root = context.runtime_root / "logs" / "local-ui"
    log_root.mkdir(parents=True, exist_ok=True)
    log_path = log_root / (
        f"{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%SZ')}-{label}-{uuid4().hex[:8]}.log"
    )
    with log_path.open("xb") as log:
        process = subprocess.Popen(
            _formal_command(context, root, port=FORMAL_PORT),
            cwd=context.root,
            env=_environment(context),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return StartedProcess(process, log_path)


def _restore_previous(
    context: WorkspaceContext,
    previous: LocalUiActivation | None,
    legacy_arguments: tuple[str, ...] | None,
) -> None:
    if previous is not None:
        release = load_release(context, previous.release_id)
        restored = _launch_release(context, release, label="restore")
        _wait_health(
            port=FORMAL_PORT,
            expected_version=release.version,
            process=restored,
        )
        return
    if legacy_arguments is None:
        return
    log_root = context.runtime_root / "logs" / "local-ui"
    log_root.mkdir(parents=True, exist_ok=True)
    log_path = log_root / (
        f"{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%SZ')}-legacy-restore-{uuid4().hex[:8]}.log"
    )
    with log_path.open("xb") as log:
        process = subprocess.Popen(
            list(legacy_arguments),
            cwd=context.root,
            env=os.environ.copy(),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    _wait_health(
        port=FORMAL_PORT,
        expected_version=None,
        process=StartedProcess(process, log_path),
    )


def activate_release(
    *,
    release_id: str,
    action: Literal["activate", "rollback"] = "activate",
    confirmed: bool,
    context: WorkspaceContext | None = None,
) -> LocalUiActivation:
    """Switch 18769 transactionally; the previous activation survives failures."""

    if not confirmed:
        raise ConfigurationError("正式 UI activation 必须显式传 --confirmed")
    selected = WorkspaceContext.discover(ROOT) if context is None else context
    release = load_release(selected, release_id)
    with _operation_lock(selected):
        active_jobs = _active_ui_jobs(selected)
        if active_jobs:
            raise ConfigurationError(
                "存在活动 UI operation，拒绝切换 18769: " + ", ".join(active_jobs)
            )
        previous = latest_activation(selected)
        if previous is not None and previous.release_id == release_id:
            raise ConfigurationError("目标 release 已是当前 activation")
        listener = _validated_listener(selected, previous)
        legacy_arguments = None if listener is None else listener[1]
        if listener is not None:
            _stop_listener(listener[0])
        started: StartedProcess | None = None
        try:
            started = _launch_release(selected, release, label=action)
            _wait_health(
                port=FORMAL_PORT,
                expected_version=release.version,
                process=started,
            )
            return _append_activation(
                selected,
                release=release,
                action=action,
                process_id=started.pid,
                log_path=started.log_path,
            )
        except Exception:
            if started is not None:
                _terminate_started(started)
            _restore_previous(selected, previous, legacy_arguments)
            raise


def manager_handoff(
    context: WorkspaceContext,
    release_id: str | None = None,
) -> dict[str, str]:
    if release_id is None:
        current = latest_activation(context)
        if current is None:
            raise ConfigurationError("尚无 local UI activation")
        release_id = current.release_id
    release = load_release(context, release_id)
    wheel = _release_path(context, release.release_id) / "wheel" / release.wheel_filename
    return {
        "release_id": release.release_id,
        "version": release.version,
        "wheel": str(wheel),
        "wheel_sha256": release.wheel_sha256,
    }


def status_payload(context: WorkspaceContext) -> dict[str, Any]:
    current = latest_activation(context)
    listener = _validated_listener(context, current)
    return {
        "activation": None if current is None else current.model_dump(mode="json"),
        "listener_pid": None if listener is None else listener[0],
        "active_ui_jobs": list(_active_ui_jobs(context)),
        "manager_handoff": (
            None if current is None else manager_handoff(context, current.release_id)
        ),
    }


def serve_active(context: WorkspaceContext) -> int:
    current = latest_activation(context)
    if current is None:
        raise ConfigurationError("尚无 local UI activation")
    release = load_release(context, current.release_id)
    command = _formal_command(
        context,
        _release_path(context, release.release_id),
        port=FORMAL_PORT,
    )
    os.chdir(context.root)
    os.execve(command[0], command, _environment(context))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare")
    prepare.add_argument("--wheel", type=Path, required=True)
    prepare.add_argument("--uv", type=Path)
    prepare.add_argument("--probe-port", type=int, default=DEFAULT_PROBE_PORT)
    prepare.add_argument("--confirmed", action="store_true")

    activate = commands.add_parser("activate")
    activate.add_argument("--release-id", required=True)
    activate.add_argument("--confirmed", action="store_true")

    rollback = commands.add_parser("rollback")
    rollback.add_argument("--release-id", required=True)
    rollback.add_argument("--confirmed", action="store_true")

    handoff = commands.add_parser("manager-wheel")
    handoff.add_argument("--release-id")
    commands.add_parser("status")
    commands.add_parser("serve-active")
    return root


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        context = WorkspaceContext.discover(ROOT)
        if arguments.command == "prepare":
            if not arguments.confirmed:
                raise ConfigurationError("正式 release prepare 必须显式传 --confirmed")
            payload: Any = prepare_release(
                wheel=arguments.wheel,
                uv=arguments.uv,
                probe_port=arguments.probe_port,
                context=context,
            ).model_dump(mode="json")
        elif arguments.command in {"activate", "rollback"}:
            payload = activate_release(
                release_id=arguments.release_id,
                action="rollback" if arguments.command == "rollback" else "activate",
                confirmed=arguments.confirmed,
                context=context,
            ).model_dump(mode="json")
        elif arguments.command == "manager-wheel":
            payload = manager_handoff(context, arguments.release_id)
        elif arguments.command == "status":
            payload = status_payload(context)
        else:
            return serve_active(context)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except (ConfigurationError, OSError, subprocess.SubprocessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
