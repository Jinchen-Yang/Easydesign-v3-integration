from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from easydesign.core import ConfigurationError
from easydesign.orchestration import runtime_setup
from easydesign.orchestration.runtime_setup import (
    AssetDefinition,
    ensure_asset,
    setup_plan,
    setup_workspace,
)
from easydesign.workspace_context import WorkspaceContext


def _workspace(tmp_path: Path) -> WorkspaceContext:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "0.1",
                "workspace_id": "test-workspace",
                "runtime_root": "runtime",
                "projects_root": "projects",
                "runs_root": "runs",
                "archives_root": "archives",
            }
        ),
        encoding="utf-8",
    )
    return WorkspaceContext.from_root(tmp_path)


def test_setup_plan_keeps_every_target_inside_workspace() -> None:
    repository = Path(__file__).resolve().parents[3]
    context = WorkspaceContext.from_root(repository)

    plan = setup_plan(context, minimal=False)

    assert len(plan["environments"]) == 7
    assert len(plan["assets"]) == 15
    assert plan["disk"]["incremental_peak_bytes"] > 0
    for environment in plan["environments"]:
        assert Path(environment["target"]).parts[:2] == ("runtime", "envs")
        assert environment["lock_kind"] == "resolved-package-set"
        assert environment["conda_explicit_sha256"]
    for asset in plan["assets"]:
        assert Path(asset["target"]).parts[:2] == ("runtime", "models")


def test_asset_license_gate_writes_record_without_network(tmp_path: Path) -> None:
    context = _workspace(tmp_path)
    definition = AssetDefinition(
        asset_id="fixture-model",
        kind="file",
        source="https://invalid.example.test/model.bin",
        destination=Path("fixture/model.bin"),
        sha256="0" * 64,
        expected_size_bytes=10,
        estimated_install_bytes=10,
        license="test-only",
        license_confirmation_required=True,
    )

    record = ensure_asset(context, definition, accepted_license_ids=set())

    assert record.status == "awaiting-approval"
    assert not (context.runtime_root / "models" / definition.destination).exists()
    assert tuple(context.asset_registry_root.glob("revision-*.json"))


def test_disk_preflight_refuses_before_initializing_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    monkeypatch.setattr(
        runtime_setup,
        "setup_plan",
        lambda _context, *, minimal: {
            "disk": {
                "sufficient": False,
                "incremental_peak_bytes": 100,
                "reserve_bytes": 50,
                "free_bytes": 10,
            }
        },
    )

    with pytest.raises(ConfigurationError, match="磁盘空间不足"):
        setup_workspace(
            context,
            minimal=True,
            accepted_license_ids=set(),
        )

    assert not context.profile_path.exists()
