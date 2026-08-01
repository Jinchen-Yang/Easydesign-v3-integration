"""Dedicated SSH pairing with append-only logical unpairing.

The controller creates or reuses a dedicated key inside the EasyDesign
workspace. A password may be accepted for one bootstrap request only: it is
written directly to an OpenSSH pseudo-terminal and is never persisted, logged,
placed in argv, or exported through the environment.
"""

from __future__ import annotations

import base64
import errno
import hashlib
import os
import select
import shlex
import shutil
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from easydesign.core import BackendContractError, ConfigurationError
from easydesign.core.artifacts import ID_PATTERN
from easydesign.workspace_context import WorkspaceContext

from .profile import SshRemoteRuntime


class SshHostIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    key_type: str = Field(min_length=1)
    fingerprint: str = Field(pattern=r"^SHA256:[A-Za-z0-9+/]+$")
    known_hosts_line: str = Field(min_length=1)
    observed_at: datetime


class RemoteExecutorPairingRevision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    revision: int = Field(ge=1)
    executor_id: str = Field(pattern=ID_PATTERN)
    controller_id: str = Field(pattern=ID_PATTERN)
    state: Literal["awaiting-public-key", "paired", "unpaired"]
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    user: str = Field(min_length=1)
    host_identity: SshHostIdentity
    identity_file: Path
    public_key_file: Path
    known_hosts_file: Path
    public_key_fingerprint: str = Field(min_length=8)
    public_key: str = Field(min_length=32)
    managed_worker_root: str = "/data/easydesign/managed-worker"
    created_at: datetime
    updated_at: datetime
    previous_revision_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )


class SshPublicKeyInstallResult(BaseModel):
    """Result of the bounded one-time password bootstrap."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    status: Literal["installed", "already-present"]
    public_key_fingerprint: str = Field(min_length=8)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_new(path: Path, payload: str, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode or 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        if not payload.endswith("\n"):
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


_HOST_KEY_PREFERENCE = {
    "ssh-ed25519": 0,
    "ecdsa-sha2-nistp256": 1,
    "ssh-rsa": 2,
}


def scan_host_identities(
    *,
    host: str,
    port: int,
    ssh_keyscan_executable: Path | None = None,
    timeout_seconds: float = 15.0,
    observed_at: datetime | None = None,
) -> tuple[SshHostIdentity, ...]:
    executable = (
        Path(shutil.which("ssh-keyscan") or "")
        if ssh_keyscan_executable is None
        else ssh_keyscan_executable
    )
    if not executable.is_file():
        raise ConfigurationError("ssh-keyscan 不可用")
    try:
        result = subprocess.run(
            (str(executable), "-p", str(port), "-T", str(int(timeout_seconds)), host),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds + 2,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BackendContractError(f"SSH host identity 探针失败: {error}") from error
    lines = tuple(
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if result.returncode != 0 or not lines:
        detail = (result.stderr.strip() or result.stdout.strip())[:2048]
        raise BackendContractError(f"SSH host identity 探针失败: {detail}")
    timestamp = datetime.now(UTC) if observed_at is None else observed_at
    identities: dict[tuple[str, str], SshHostIdentity] = {}
    for line in lines:
        columns = line.split()
        if len(columns) != 3:
            raise BackendContractError("ssh-keyscan 返回的 host key 格式无效")
        try:
            key_bytes = base64.b64decode(columns[2], validate=True)
        except ValueError as error:
            raise BackendContractError("ssh-keyscan host key 不是有效 Base64") from error
        fingerprint = (
            "SHA256:"
            + base64.b64encode(hashlib.sha256(key_bytes).digest()).decode().rstrip("=")
        )
        identity = SshHostIdentity(
            host=host,
            port=port,
            key_type=columns[1],
            fingerprint=fingerprint,
            known_hosts_line=line,
            observed_at=timestamp,
        )
        identities[(identity.key_type, identity.fingerprint)] = identity
    if not identities:
        raise BackendContractError("ssh-keyscan 未返回可用的 host key")
    return tuple(
        sorted(
            identities.values(),
            key=lambda item: (
                _HOST_KEY_PREFERENCE.get(item.key_type, 100),
                item.key_type,
                item.fingerprint,
                item.known_hosts_line,
            ),
        )
    )


def scan_host_identity(
    *,
    host: str,
    port: int,
    ssh_keyscan_executable: Path | None = None,
    timeout_seconds: float = 15.0,
    observed_at: datetime | None = None,
) -> SshHostIdentity:
    """Return the deterministic preferred identity for display compatibility."""

    return scan_host_identities(
        host=host,
        port=port,
        ssh_keyscan_executable=ssh_keyscan_executable,
        timeout_seconds=timeout_seconds,
        observed_at=observed_at,
    )[0]


class RemoteExecutorRegistry:
    def __init__(self, context: WorkspaceContext | None = None) -> None:
        self.context = WorkspaceContext.discover() if context is None else context
        self.root = self.context.remote_executor_registry_root
        self.context.assert_write_path(self.root)

    def key_pair_available(self, executor_id: str) -> bool:
        """Return true only when the complete workspace key pair already exists."""

        secret_root = self.context.runtime_root / "secrets" / "ssh" / executor_id
        identity = secret_root / "id_ed25519"
        public = secret_root / "id_ed25519.pub"
        if identity.exists() != public.exists():
            raise ConfigurationError("专用 SSH key pair 不完整，拒绝覆盖或重建")
        return identity.is_file() and public.is_file()

    def _revision_paths(self, executor_id: str) -> tuple[Path, ...]:
        return tuple(sorted((self.root / executor_id / "revisions").glob("*.json")))

    def latest(self, executor_id: str) -> RemoteExecutorPairingRevision | None:
        paths = self._revision_paths(executor_id)
        if not paths:
            return None
        return RemoteExecutorPairingRevision.model_validate_json(
            paths[-1].read_text(encoding="utf-8")
        )

    def list_latest(self) -> tuple[RemoteExecutorPairingRevision, ...]:
        if not self.root.is_dir():
            return ()
        return tuple(
            item
            for executor in sorted(path for path in self.root.iterdir() if path.is_dir())
            if (item := self.latest(executor.name)) is not None
        )

    def _append(
        self,
        model: RemoteExecutorPairingRevision,
    ) -> RemoteExecutorPairingRevision:
        path = (
            self.root
            / model.executor_id
            / "revisions"
            / f"revision-{model.revision:06d}.json"
        )
        _write_new(path, model.model_dump_json(indent=2))
        return model

    def begin_pairing(
        self,
        *,
        executor_id: str,
        controller_id: str,
        host: str,
        port: int,
        user: str,
        confirmed_host_fingerprint: str,
        ssh_keyscan_executable: Path | None = None,
        ssh_keygen_executable: Path | None = None,
        now: datetime | None = None,
    ) -> RemoteExecutorPairingRevision:
        timestamp = datetime.now(UTC) if now is None else now
        host_identities = scan_host_identities(
            host=host,
            port=port,
            ssh_keyscan_executable=ssh_keyscan_executable,
            observed_at=timestamp,
        )
        host_identity = next(
            (
                identity
                for identity in host_identities
                if identity.fingerprint == confirmed_host_fingerprint
            ),
            None,
        )
        if host_identity is None:
            raise BackendContractError(
                "SSH host fingerprint 与用户确认值不一致；拒绝继续配对"
            )
        secret_root = self.context.runtime_root / "secrets" / "ssh" / executor_id
        self.context.assert_write_path(secret_root)
        identity = secret_root / "id_ed25519"
        public = secret_root / "id_ed25519.pub"
        if identity.exists() != public.exists():
            raise ConfigurationError("专用 SSH key pair 不完整，拒绝覆盖或重建")
        if not identity.exists():
            executable = (
                Path(shutil.which("ssh-keygen") or "")
                if ssh_keygen_executable is None
                else ssh_keygen_executable
            )
            if not executable.is_file():
                raise ConfigurationError("ssh-keygen 不可用")
            secret_root.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                (
                    str(executable),
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-C",
                    f"easydesign:{controller_id}:{executor_id}",
                    "-f",
                    str(identity),
                ),
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise BackendContractError(
                    "专用 SSH key 生成失败: "
                    + (result.stderr.strip() or result.stdout.strip())[:2048]
                )
        if os.name == "posix" and identity.stat().st_mode & 0o077:
            identity.chmod(0o600)
        known_hosts_root = self.context.runtime_root / "state" / "ssh-known-hosts" / executor_id
        known_hosts_root.mkdir(parents=True, exist_ok=True)
        known_hosts = known_hosts_root / f"host-{timestamp.strftime('%Y%m%dT%H%M%SZ')}.txt"
        _write_new(known_hosts, host_identity.known_hosts_line, mode=0o600)
        public_key = public.read_text(encoding="utf-8").strip()
        key_columns = public_key.split()
        if len(key_columns) < 2:
            raise ConfigurationError("专用 SSH 公钥格式无效")
        key_bytes = base64.b64decode(key_columns[1])
        key_fingerprint = (
            "SHA256:"
            + base64.b64encode(hashlib.sha256(key_bytes).digest()).decode().rstrip("=")
        )
        previous = self.latest(executor_id)
        previous_paths = self._revision_paths(executor_id)
        revision = RemoteExecutorPairingRevision(
            revision=1 if previous is None else previous.revision + 1,
            executor_id=executor_id,
            controller_id=controller_id,
            state="awaiting-public-key",
            host=host,
            port=port,
            user=user,
            host_identity=host_identity,
            identity_file=identity,
            public_key_file=public,
            known_hosts_file=known_hosts,
            public_key_fingerprint=key_fingerprint,
            public_key=public_key,
            created_at=timestamp if previous is None else previous.created_at,
            updated_at=timestamp,
            previous_revision_sha256=(
                None if not previous_paths else _sha256(previous_paths[-1])
            ),
        )
        return self._append(revision)

    def mark_paired(
        self,
        executor_id: str,
        *,
        now: datetime | None = None,
    ) -> RemoteExecutorPairingRevision:
        previous = self.latest(executor_id)
        if previous is None or previous.state != "awaiting-public-key":
            raise ConfigurationError("executor 不处于等待安装公钥状态")
        timestamp = datetime.now(UTC) if now is None else now
        paths = self._revision_paths(executor_id)
        return self._append(
            previous.model_copy(
                update={
                    "revision": previous.revision + 1,
                    "state": "paired",
                    "updated_at": timestamp,
                    "previous_revision_sha256": _sha256(paths[-1]),
                }
            )
        )

    def unpair(
        self,
        executor_id: str,
        *,
        now: datetime | None = None,
    ) -> RemoteExecutorPairingRevision:
        previous = self.latest(executor_id)
        if previous is None:
            raise ConfigurationError("executor 尚未登记")
        timestamp = datetime.now(UTC) if now is None else now
        paths = self._revision_paths(executor_id)
        return self._append(
            previous.model_copy(
                update={
                    "revision": previous.revision + 1,
                    "state": "unpaired",
                    "updated_at": timestamp,
                    "previous_revision_sha256": _sha256(paths[-1]),
                }
            )
        )

    @staticmethod
    def runtime_for_record(
        record: RemoteExecutorPairingRevision,
    ) -> SshRemoteRuntime:
        """Build an SSH runtime without changing the durable pairing state."""

        managed_root = Path(record.managed_worker_root)
        return SshRemoteRuntime(
            host=record.host,
            user=record.user,
            port=record.port,
            identity_file=record.identity_file,
            known_hosts_file=record.known_hosts_file,
            ssh_executable=Path(shutil.which("ssh") or "/usr/bin/ssh"),
            rsync_executable=Path(shutil.which("rsync") or "/usr/bin/rsync"),
            remote_work_root=managed_root,
            remote_runs_root=managed_root / "runs",
            remote_easydesign_executable=managed_root / "service" / "easydesign",
            remote_profile=managed_root / "config" / "profile.yaml",
        )

    def active_runtimes(self) -> dict[str, SshRemoteRuntime]:
        result: dict[str, SshRemoteRuntime] = {}
        for record in self.list_latest():
            if record.state != "paired":
                continue
            result[record.executor_id] = self.runtime_for_record(record)
        return result


def public_key_install_command(record: RemoteExecutorPairingRevision) -> str:
    """Idempotent remote command; no password or private key is embedded."""

    quoted = shlex.quote(record.public_key)
    return (
        "umask 077 && install -d -m 700 ~/.ssh && touch ~/.ssh/authorized_keys && "
        "chmod 600 ~/.ssh/authorized_keys && "
        f"if grep -qxF {quoted} ~/.ssh/authorized_keys; then "
        "printf \"%s\\n\" EASYDESIGN_PUBLIC_KEY_ALREADY_PRESENT; "
        "else "
        f"printf '\\n%s\\n' {quoted} >> ~/.ssh/authorized_keys && "
        "printf \"%s\\n\" EASYDESIGN_PUBLIC_KEY_INSTALLED; fi"
    )


def _redact_password(value: str, password: str) -> str:
    """Keep a misbehaving SSH client or test double from echoing a secret."""

    return value.replace(password, "[REDACTED]") if password else value


def install_public_key_with_password(
    record: RemoteExecutorPairingRevision,
    password: str,
    *,
    ssh_executable: Path | None = None,
    timeout_seconds: float = 45.0,
) -> SshPublicKeyInstallResult:
    """Install the workspace key through one password-authenticated SSH call."""

    if record.state != "awaiting-public-key":
        raise ConfigurationError("executor 不处于等待安装公钥状态")
    if os.name != "posix":
        raise ConfigurationError(
            "当前控制端不支持网页内一次性密码安装；请使用页面提供的手动公钥命令"
        )
    if not password or len(password) > 1024 or any(
        char in password for char in "\r\n\0"
    ):
        raise ConfigurationError("一次性 SSH 密码格式无效")
    if (
        record.host.startswith("-")
        or any(char in record.host for char in "\r\n\0")
        or record.user.startswith("-")
        or "@" in record.user
        or any(char in record.user for char in "\r\n\0")
    ):
        raise ConfigurationError("SSH host 或用户名格式无效")
    executable = (
        Path(shutil.which("ssh") or "")
        if ssh_executable is None
        else ssh_executable
    )
    if not executable.is_file():
        raise ConfigurationError("ssh 不可用")
    if not record.known_hosts_file.is_file():
        raise ConfigurationError("已确认的 SSH host key 记录不存在")

    import pty

    arguments = (
        str(executable),
        "-F",
        "/dev/null",
        "-p",
        str(record.port),
        "-o",
        "BatchMode=no",
        "-o",
        "PubkeyAuthentication=no",
        "-o",
        "PreferredAuthentications=password,keyboard-interactive",
        "-o",
        "PasswordAuthentication=yes",
        "-o",
        "KbdInteractiveAuthentication=yes",
        "-o",
        "NumberOfPasswordPrompts=1",
        "-o",
        f"UserKnownHostsFile={record.known_hosts_file}",
        "-o",
        "GlobalKnownHostsFile=/dev/null",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"ConnectTimeout={max(1, int(timeout_seconds))}",
        f"{record.user}@{record.host}",
        public_key_install_command(record),
    )
    child_pid, master_fd = pty.fork()
    if child_pid == 0:  # pragma: no cover - subprocess integration boundary
        environment = os.environ.copy()
        environment.update({"LC_ALL": "C", "LANG": "C"})
        os.execve(str(executable), arguments, environment)

    output = bytearray()
    password_sent = False
    deadline = time.monotonic() + timeout_seconds
    wait_status: int | None = None
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master_fd], [], [], 0.2)
            if ready:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                    chunk = b""
                if chunk:
                    output.extend(chunk)
                    if len(output) > 65536:
                        del output[:-65536]
                    if not password_sent and b"password:" in bytes(output).lower():
                        os.write(master_fd, password.encode("utf-8") + b"\n")
                        password_sent = True
                else:
                    _, wait_status = os.waitpid(child_pid, 0)
                    break
            finished, child_status = os.waitpid(child_pid, os.WNOHANG)
            if finished == child_pid:
                wait_status = child_status
                break
        if wait_status is None:
            finished, child_status = os.waitpid(child_pid, os.WNOHANG)
            if finished == child_pid:
                wait_status = child_status
        if wait_status is None:
            os.kill(child_pid, signal.SIGTERM)
            _, wait_status = os.waitpid(child_pid, 0)
            detail = _redact_password(
                output.decode("utf-8", errors="replace"), password
            )[-2048:]
            timeout_detail = detail or "远端未响应"
            raise BackendContractError(
                f"一次性 SSH 公钥安装超时: {timeout_detail}"
            )
    finally:
        os.close(master_fd)

    rendered = _redact_password(output.decode("utf-8", errors="replace"), password)
    exit_code = os.waitstatus_to_exitcode(wait_status)
    if exit_code != 0:
        detail = rendered[-2048:].strip()
        failure_detail = detail or "认证失败"
        raise BackendContractError(
            f"一次性 SSH 公钥安装失败（exit={exit_code}）: {failure_detail}"
        )
    if "EASYDESIGN_PUBLIC_KEY_INSTALLED" in rendered:
        installation_status: Literal["installed", "already-present"] = "installed"
    elif "EASYDESIGN_PUBLIC_KEY_ALREADY_PRESENT" in rendered:
        installation_status = "already-present"
    else:
        raise BackendContractError("远端未返回 EasyDesign 公钥安装确认")
    return SshPublicKeyInstallResult(
        status=installation_status,
        public_key_fingerprint=record.public_key_fingerprint,
    )
