from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from easydesign.core import ConfigurationError
from easydesign.orchestration import runtime_setup
from easydesign.orchestration.runtime_setup import (
    AssetDefinition,
    ensure_asset,
    setup_plan,
    setup_workspace,
    validate_pip_index_url,
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
    assert plan["disk"]["incremental_peak_bytes"] >= 0
    for environment in plan["environments"]:
        assert Path(environment["target"]).parts[:2] == ("runtime", "envs")
        assert environment["lock_kind"] == "resolved-package-set"
        assert environment["conda_explicit_sha256"]
    for asset in plan["assets"]:
        assert Path(asset["target"]).parts[:2] == ("runtime", "models")


def test_setup_plan_uses_fixed_ten_gib_free_space_reserve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Path(__file__).resolve().parents[3]
    context = WorkspaceContext.from_root(repository)
    disk_usage = SimpleNamespace(
        total=300 * runtime_setup.GIB,
        used=250 * runtime_setup.GIB,
        free=50 * runtime_setup.GIB,
    )
    monkeypatch.setattr(runtime_setup.shutil, "disk_usage", lambda _path: disk_usage)

    plan = setup_plan(context, minimal=False, component="boltzgen")

    assert plan["disk"]["reserve_bytes"] == 10 * runtime_setup.GIB
    assert plan["disk"]["sufficient"] is (
        disk_usage.free
        >= plan["disk"]["incremental_peak_bytes"] + 10 * runtime_setup.GIB
    )


def test_boltzgen_cuequivariance_family_is_version_aligned() -> None:
    repository = Path(__file__).resolve().parents[3]
    lock = (
        repository / "environments" / "locks" / "boltzgen-linux-64.pip-lock.txt"
    ).read_text(encoding="utf-8")

    assert {
        line
        for line in lock.splitlines()
        if line.startswith("cuequivariance")
    } == {
        "cuequivariance-ops-cu12==0.10.0",
        "cuequivariance-ops-torch-cu12==0.10.0",
        "cuequivariance-torch==0.10.0",
        "cuequivariance==0.10.0",
    }


@pytest.mark.parametrize(
    ("component", "environment_id", "asset_ids"),
    (
        ("pymol-pse", "pymol-pse", ()),
        (
            "protenix-v2",
            "protenix-v2",
            (
                "protenix-v2-checkpoint",
                "protenix-ccd-components",
                "protenix-ccd-rdkit-cache",
                "protenix-pdb-clusters",
                "protenix-obsolete-releases",
            ),
        ),
        (
            "scannet-epitope",
            "scannet-epitope",
            ("scannet-code-and-epitope-models",),
        ),
        (
            "boltzgen",
            "boltzgen",
            (
                "boltzgen-inference-molecule-dataset",
                "boltzgen-design-diverse-checkpoint",
                "boltzgen-design-adherence-checkpoint",
                "boltzgen-inverse-fold-checkpoint",
                "boltzgen-folding-checkpoint",
                "boltzgen-affinity-checkpoint",
                "boltzgen-source-a3149cf",
            ),
        ),
        ("tnp", "tnp", ("tnp-source-29dcac72",)),
    ),
)
def test_component_plan_contains_only_requested_backend(
    component: str,
    environment_id: str,
    asset_ids: tuple[str, ...],
) -> None:
    repository = Path(__file__).resolve().parents[3]
    context = WorkspaceContext.from_root(repository)

    plan = setup_plan(context, minimal=False, component=component)

    assert plan["mode"] == "component"
    assert plan["component"] == component
    assert [item["environment_id"] for item in plan["environments"]] == [
        environment_id
    ]
    assert tuple(item["asset_id"] for item in plan["assets"]) == asset_ids


def test_setup_plan_rejects_conflicting_component_scope() -> None:
    repository = Path(__file__).resolve().parents[3]
    context = WorkspaceContext.from_root(repository)

    with pytest.raises(ConfigurationError, match="不能同时使用"):
        setup_plan(context, minimal=True, component="pymol-pse")


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


def test_git_asset_fetches_only_pinned_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    revision = "a" * 40
    definition = AssetDefinition(
        asset_id="fixture-source",
        kind="git",
        source="https://example.test/fixture.git",
        destination=Path("fixture/source"),
        revision=revision,
        estimated_install_bytes=100,
        license="test-only",
        license_confirmation_required=False,
    )
    commands: list[tuple[str, ...]] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        rendered = tuple(str(item) for item in command)
        commands.append(rendered)
        if rendered[:3] == ("git", "init", "--quiet"):
            Path(rendered[-1]).mkdir(parents=True)
            return SimpleNamespace(returncode=0)
        if "fetch" in rendered:
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runtime_setup.subprocess, "run", fake_run)

    with pytest.raises(ConfigurationError, match="fetch 失败"):
        runtime_setup._checkout_git(
            context,
            definition,
            context.runtime_root / "models" / definition.destination,
        )

    fetch = next(command for command in commands if "fetch" in command)
    assert fetch[-5:] == ("--depth", "1", "--no-tags", "origin", revision)


def test_disk_preflight_refuses_before_initializing_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    monkeypatch.setattr(
        runtime_setup,
        "setup_plan",
        lambda _context, *, minimal, component=None: {
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


def test_inventory_normalizes_only_workspace_editable_commit() -> None:
    old = {
        "pip_freeze": [
            "-e git+ssh://git@example.test/EasyDesign.git@old#egg=easydesign",
            "pydantic==2.13.4",
        ]
    }
    new = {
        "pip_freeze": [
            "-e git+ssh://git@example.test/EasyDesign.git@new#egg=easydesign",
            "pydantic==2.13.4",
        ]
    }
    drifted = {
        "pip_freeze": [
            "-e git+ssh://git@example.test/EasyDesign.git@new#egg=easydesign",
            "pydantic==2.14.0",
        ]
    }

    normalize = runtime_setup._normalized_environment_inventory
    assert normalize(old) == normalize(new)
    assert normalize(old) != normalize(drifted)


def test_pip_index_must_be_explicit_safe_https_url() -> None:
    assert (
        validate_pip_index_url("https://pypi.tuna.tsinghua.edu.cn/simple/")
        == "https://pypi.tuna.tsinghua.edu.cn/simple"
    )
    with pytest.raises(ConfigurationError, match="无凭据"):
        validate_pip_index_url("https://user:secret@example.test/simple")
    with pytest.raises(ConfigurationError, match="HTTPS"):
        validate_pip_index_url("http://example.test/simple")
