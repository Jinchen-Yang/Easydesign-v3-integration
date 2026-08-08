from __future__ import annotations

import json
from pathlib import Path

import pytest

from easydesign.core import ConfigurationError, sha256_file
from easydesign.orchestration import runtime_link
from easydesign.orchestration.profile import RuntimeProfile, load_runtime_profile


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    local = tmp_path / "local"
    source_repo = tmp_path / "source"
    source = source_repo / "runtime"
    (local / "environments/locks").mkdir(parents=True)
    (local / "easydesign-workspace.yaml").write_text(
        'schema_version: "0.1"\nworkspace_id: local-test\n', encoding="utf-8"
    )
    lock = local / "environments/locks/test-env-linux-64.lock.json"
    lock.write_text("{}\n", encoding="utf-8")
    prefix = source / "envs/test-env"
    prefix.mkdir(parents=True)
    inventory = source / "state/environment-inventories/test-env.json"
    _write_json(inventory, {"packages": []})
    asset = source / "models/checkpoint.bin"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"verified-model")
    environment_revision = source / "state/registries/environments/revision-000001.json"
    _write_json(
        environment_revision,
        {
            "environment_id": "test-env",
            "lock_sha256": sha256_file(lock),
            "relative_prefix": "runtime/envs/test-env",
            "status": "available",
            "package_inventory": "runtime/state/environment-inventories/test-env.json",
            "package_inventory_sha256": sha256_file(inventory),
        },
    )
    asset_revision = source / "state/registries/assets/revision-000001.json"
    _write_json(
        asset_revision,
        {
            "asset_id": "test-asset",
            "relative_path": "runtime/models/checkpoint.bin",
            "status": "available",
            "sha256": sha256_file(asset),
            "size_bytes": asset.stat().st_size,
        },
    )
    _write_json(
        source / "environment-registry.json",
        {"record_directory": "runtime/state/registries/environments"},
    )
    _write_json(
        source / "asset-registry.json",
        {"record_directory": "runtime/state/registries/assets"},
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(local))
    monkeypatch.setattr(runtime_link, "SCIENCE_ENVIRONMENTS", ("test-env",))
    monkeypatch.setattr(runtime_link, "REQUIRED_ASSETS", ("test-asset",))

    def profile(context: object, receipt: runtime_link.RuntimeLinkReceipt) -> RuntimeProfile:
        from easydesign.workspace_context import WorkspaceContext

        assert isinstance(context, WorkspaceContext)
        return RuntimeProfile(
            profile_id="linked-test",
            runs_root=context.runs_root,
            runtime_link_source=receipt.source_runtime,
            runtime_linked_at=receipt.linked_at,
        )

    monkeypatch.setattr(runtime_link, "_profile", profile)
    return local, source


def test_runtime_link_is_local_receipt_plus_read_only_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local, source = _fixture(tmp_path, monkeypatch)
    source_files_before = {
        path.relative_to(source): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in source.rglob("*")
        if path.is_file()
    }

    result = runtime_link.link_runtime(source)
    verified = runtime_link.verify_runtime_link()
    loaded = load_runtime_profile()

    assert result.environment_count == 1
    assert result.asset_count == 1
    assert verified.source_runtime == source.resolve()
    assert loaded.profile.profile_id == "linked-test"
    assert result.receipt.is_relative_to(local / "runtime")
    source_files_after = {
        path.relative_to(source): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in source.rglob("*")
        if path.is_file()
    }
    assert source_files_after == source_files_before


def test_runtime_link_fails_closed_after_registry_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local, source = _fixture(tmp_path, monkeypatch)
    runtime_link.link_runtime(source)
    marker = source / "asset-registry.json"
    marker.write_text('{"record_directory":"changed"}\n', encoding="utf-8")

    with pytest.raises(ConfigurationError, match="identity 已变化"):
        runtime_link.verify_runtime_link()
