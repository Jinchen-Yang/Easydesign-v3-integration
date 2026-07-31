from __future__ import annotations

import base64
import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from easydesign.core import BackendContractError
from easydesign.orchestration.ssh_pairing import (
    RemoteExecutorRegistry,
    public_key_install_command,
    scan_host_identity,
)
from easydesign.workspace_context import WorkspaceContext


def _context(tmp_path: Path) -> WorkspaceContext:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        'schema_version: "0.1"\nworkspace_id: pairing-test\n',
        encoding="utf-8",
    )
    return WorkspaceContext.discover(tmp_path)


def _executable(path: Path, body: str) -> Path:
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _host_key_line() -> tuple[str, str]:
    key = base64.b64encode(b"host-public-key").decode()
    fingerprint = base64.b64encode(
        hashlib.sha256(b"host-public-key").digest()
    ).decode().rstrip("=")
    return f"[suzhou2]:22 ssh-ed25519 {key}", f"SHA256:{fingerprint}"


def test_host_fingerprint_requires_explicit_matching_confirmation(
    tmp_path: Path,
) -> None:
    line, fingerprint = _host_key_line()
    keyscan = _executable(tmp_path / "ssh-keyscan", f"printf '%s\\n' '{line}'\n")
    observed = scan_host_identity(
        host="suzhou2",
        port=22,
        ssh_keyscan_executable=keyscan,
    )
    assert observed.fingerprint == fingerprint


def test_pairing_keeps_key_on_logical_unpair(tmp_path: Path) -> None:
    line, fingerprint = _host_key_line()
    keyscan = _executable(tmp_path / "ssh-keyscan", f"printf '%s\\n' '{line}'\n")
    public_key = base64.b64encode(b"controller-key").decode()
    keygen = _executable(
        tmp_path / "ssh-keygen",
        f"""
while [ "$1" != "-f" ]; do shift; done
shift
printf '%s\\n' 'PRIVATE' > "$1"
printf '%s\\n' 'ssh-ed25519 {public_key} easydesign-test' > "$1.pub"
""",
    )
    registry = RemoteExecutorRegistry(_context(tmp_path))
    waiting = registry.begin_pairing(
        executor_id="suzhou2",
        controller_id="controller-a",
        host="suzhou2",
        port=22,
        user="root",
        confirmed_host_fingerprint=fingerprint,
        ssh_keyscan_executable=keyscan,
        ssh_keygen_executable=keygen,
        now=datetime(2026, 8, 1, tzinfo=UTC),
    )
    assert waiting.state == "awaiting-public-key"
    assert waiting.identity_file.stat().st_mode & 0o077 == 0
    assert "authorized_keys" in public_key_install_command(waiting)
    paired = registry.mark_paired("suzhou2")
    assert paired.state == "paired"
    assert registry.active_runtimes()["suzhou2"].remote_runs_root == Path(
        "/data/easydesign/managed-worker/runs"
    )
    unpaired = registry.unpair("suzhou2")
    assert unpaired.state == "unpaired"
    assert waiting.identity_file.is_file()
    assert waiting.public_key_file.is_file()
    assert registry.active_runtimes() == {}


def test_pairing_rejects_changed_host_fingerprint(tmp_path: Path) -> None:
    line, _fingerprint = _host_key_line()
    keyscan = _executable(tmp_path / "ssh-keyscan", f"printf '%s\\n' '{line}'\n")
    with pytest.raises(BackendContractError, match="不一致"):
        RemoteExecutorRegistry(_context(tmp_path)).begin_pairing(
            executor_id="suzhou2",
            controller_id="controller-a",
            host="suzhou2",
            port=22,
            user="root",
            confirmed_host_fingerprint="SHA256:wrongfingerprint",
            ssh_keyscan_executable=keyscan,
            ssh_keygen_executable=tmp_path / "unused",
        )


def test_private_key_is_not_in_install_command(tmp_path: Path) -> None:
    assert os.name in {"posix", "nt"}
