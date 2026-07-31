from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from easydesign.core import ConfigurationError
from easydesign.core.hashing import sha256_bytes
from easydesign.ui.uploads import UploadStore
from easydesign.workspace_context import WorkspaceContext


def _workspace(tmp_path: Path) -> WorkspaceContext:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "0.1",
                "workspace_id": "upload-test",
                "runtime_root": "runtime",
                "projects_root": "projects",
                "runs_root": "runs",
                "archives_root": "archives",
            }
        ),
        encoding="utf-8",
    )
    value = WorkspaceContext.from_root(tmp_path)
    value.ensure_layout()
    return value


def test_upload_receipt_survives_restart_and_reuses_identical_pending_file(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    content = b"portable-upload-fixture"
    digest = sha256_bytes(content)
    store = UploadStore(workspace)
    receipt, target = store.begin(
        filename="target.pse",
        size_bytes=len(content),
        sha256=digest,
    )
    target.write_bytes(content)
    ready = store.ready(receipt.upload_token)

    assert ready.relative_path == f"runtime/tmp/ui-uploads/{receipt.upload_token}/target.pse"
    assert ready.path_ref == f"runtime://tmp/ui-uploads/{receipt.upload_token}/target.pse"

    restarted = UploadStore(workspace)
    reused = restarted.find_reusable(
        filename="target.pse",
        size_bytes=len(content),
        sha256=digest,
    )

    assert reused is not None
    assert reused.upload_token == ready.upload_token
    assert restarted.resolve(ready.upload_token).read_bytes() == content


def test_stale_upload_is_only_suggested_and_never_automatically_removed(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    content = b"keep-until-explicit-approval"
    now = datetime(2026, 7, 30, tzinfo=UTC)
    store = UploadStore(workspace)
    receipt, target = store.begin(
        filename="target.cif",
        size_bytes=len(content),
        sha256=sha256_bytes(content),
        created_at=now - timedelta(days=8),
    )
    target.write_bytes(content)
    store.ready(
        receipt.upload_token,
        updated_at=now - timedelta(days=8),
    )

    suggestions = store.suggested_cleanup(now=now)

    assert [item.upload_token for item in suggestions] == [receipt.upload_token]
    assert target.read_bytes() == content


def test_upload_limits_come_from_workspace_declaration_and_paths_are_rejected(
    tmp_path: Path,
) -> None:
    declaration_path = tmp_path / "easydesign-workspace.yaml"
    content = {
        "schema_version": "0.1",
        "workspace_id": "upload-config-test",
        "runtime_root": "runtime",
        "projects_root": "projects",
        "runs_root": "runs",
        "archives_root": "archives",
    }
    content["upload_warning_bytes"] = 16
    content["upload_blocking_bytes"] = 32
    declaration_path.write_text(yaml.safe_dump(content), encoding="utf-8")
    workspace = WorkspaceContext.from_root(tmp_path)
    workspace.ensure_layout()
    store = UploadStore(workspace)

    assert store.capacity(16)["warning"] is True
    assert store.capacity(32)["blocked"] is True
    with pytest.raises(ConfigurationError, match="basename"):
        store.begin(
            filename="../target.pse",
            size_bytes=1,
            sha256=sha256_bytes(b"x"),
        )
