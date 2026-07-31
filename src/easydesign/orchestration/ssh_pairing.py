"""Dedicated SSH pairing with append-only logical unpairing.

Passwords are never accepted or persisted.  The controller creates a dedicated
key inside the EasyDesign workspace, shows the public key to the operator, and
only marks an executor paired after strict host identity and worker probes pass.
"""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import subprocess
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


def scan_host_identity(
    *,
    host: str,
    port: int,
    ssh_keyscan_executable: Path | None = None,
    timeout_seconds: float = 15.0,
    observed_at: datetime | None = None,
) -> SshHostIdentity:
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
    columns = lines[0].split()
    if len(columns) != 3:
        raise BackendContractError("ssh-keyscan 返回的 host key 格式无效")
    try:
        key_bytes = base64.b64decode(columns[2], validate=True)
    except ValueError as error:
        raise BackendContractError("ssh-keyscan host key 不是有效 Base64") from error
    fingerprint = base64.b64encode(hashlib.sha256(key_bytes).digest()).decode().rstrip("=")
    return SshHostIdentity(
        host=host,
        port=port,
        key_type=columns[1],
        fingerprint=f"SHA256:{fingerprint}",
        known_hosts_line=lines[0],
        observed_at=datetime.now(UTC) if observed_at is None else observed_at,
    )


class RemoteExecutorRegistry:
    def __init__(self, context: WorkspaceContext | None = None) -> None:
        self.context = WorkspaceContext.discover() if context is None else context
        self.root = self.context.remote_executor_registry_root
        self.context.assert_write_path(self.root)

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
        host_identity = scan_host_identity(
            host=host,
            port=port,
            ssh_keyscan_executable=ssh_keyscan_executable,
            observed_at=timestamp,
        )
        if host_identity.fingerprint != confirmed_host_fingerprint:
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
    """Human-executed append command; no password or private key is embedded."""

    import shlex

    quoted = shlex.quote(record.public_key)
    return (
        "install -d -m 700 ~/.ssh && "
        f"printf '%s\\n' {quoted} >> ~/.ssh/authorized_keys && "
        "chmod 600 ~/.ssh/authorized_keys"
    )
