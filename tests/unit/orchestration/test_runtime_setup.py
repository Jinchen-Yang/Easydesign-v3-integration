from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
import yaml

from easydesign.core import ConfigurationError
from easydesign.orchestration import runtime_setup
from easydesign.orchestration.runtime_setup import (
    AssetDefinition,
    EnvironmentRecord,
    ensure_asset,
    latest_environment_records,
    retire_environment,
    setup_plan,
    setup_workspace,
    validate_pip_index_url,
)
from easydesign.orchestration.source_policy import (
    SourceCandidate,
    SourceSelection,
    VerifiedDownload,
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


def test_retire_environment_appends_record_without_changing_prefix(
    tmp_path: Path,
) -> None:
    context = _workspace(tmp_path)
    context.ensure_layout()
    prefix = Path("runtime/envs/pymol-pse-test")
    available = EnvironmentRecord(
        environment_id="pymol-pse",
        lock_sha256="a" * 64,
        relative_prefix=prefix,
        status="available",
        probe_command=("python", "-V"),
        recorded_at=runtime_setup.datetime.now(tz=runtime_setup.UTC),
    )
    first = runtime_setup._append_record(context.environment_registry_root, available)

    retired = retire_environment(
        context,
        "pymol-pse",
        reason="superseded by a newer lock",
    )

    revisions = sorted(context.environment_registry_root.glob("revision-*.json"))
    assert first == revisions[0]
    assert len(revisions) == 2
    assert EnvironmentRecord.model_validate_json(first.read_text()).status == "available"
    assert retired.status == "retired"
    assert retired.relative_prefix == prefix
    assert retired.message == "superseded by a newer lock"
    assert latest_environment_records(context)["pymol-pse"] == retired


def test_retire_environment_is_idempotent(tmp_path: Path) -> None:
    context = _workspace(tmp_path)
    context.ensure_layout()
    runtime_setup._append_record(
        context.environment_registry_root,
        EnvironmentRecord(
            environment_id="pymol-pse",
            lock_sha256="b" * 64,
            relative_prefix=Path("runtime/envs/pymol-pse-test"),
            status="retired",
            probe_command=("python", "-V"),
            recorded_at=runtime_setup.datetime.now(tz=runtime_setup.UTC),
            message="already retired",
        ),
    )

    retired = retire_environment(
        context,
        "pymol-pse",
        reason="duplicate request",
    )

    assert retired.message == "already retired"
    assert len(tuple(context.environment_registry_root.glob("revision-*.json"))) == 1


def test_setup_plan_keeps_every_target_inside_workspace() -> None:
    repository = Path(__file__).resolve().parents[3]
    context = WorkspaceContext.from_root(repository)

    plan = setup_plan(context, component="boltzgen")

    assert len(plan["environments"]) == 1
    assert len(plan["assets"]) == 7
    assert plan["disk"]["incremental_peak_bytes"] >= 0
    for environment in plan["environments"]:
        assert Path(environment["target"]).parts[:2] == ("runtime", "envs")
        assert environment["lock_kind"] == "resolved-package-set"
        assert environment["conda_explicit_sha256"]
    for asset in plan["assets"]:
        assert Path(asset["target"]).parts[:2] == ("runtime", "models")


def test_all_conda_explicit_locks_pin_every_package_sha256() -> None:
    repository = Path(__file__).resolve().parents[3]

    for path in sorted((repository / "environments" / "locks").glob("*.conda-lock.txt")):
        entries = runtime_setup._conda_lock_entries(path)
        assert entries
        assert all(len(package_sha256) == 64 for _url, package_sha256 in entries)


def test_conda_explicit_view_preserves_original_archive_basename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    context.ensure_layout()
    package_sha256 = "a" * 64
    filename = "fixture-package-1.0-0.conda"
    lock = tmp_path / "fixture.conda-lock.txt"
    lock.write_text(
        "@EXPLICIT\n"
        f"https://conda.anaconda.org/fixture/linux-64/{filename}#{package_sha256}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runtime_setup,
        "load_runtime_sources",
        lambda _context: SimpleNamespace(conda_rewrites=()),
    )

    def fake_download(
        _context: WorkspaceContext,
        **kwargs: object,
    ) -> VerifiedDownload:
        destination = kwargs["destination"]
        assert isinstance(destination, Path)
        destination.write_bytes(b"verified package bytes")
        selection = SourceSelection(
            source_id="fixture-source",
            url="https://example.test/fixture-package.conda",
        )
        callback = kwargs["source_callback"]
        assert callable(callback)
        callback(selection)
        return VerifiedDownload(
            path=destination,
            source=selection,
            sha256=package_sha256,
            size_bytes=destination.stat().st_size,
        )

    monkeypatch.setattr(runtime_setup, "download_verified_file", fake_download)

    explicit, source_ids = runtime_setup._materialize_conda_explicit(
        context,
        environment_id="fixture",
        conda_lock=lock,
        source_policy="auto",
        progress_callback=None,
    )

    package_line = next(
        line
        for line in explicit.read_text(encoding="utf-8").splitlines()
        if line.startswith("file:")
    )
    local_package = Path(urlparse(package_line.rsplit("#", maxsplit=1)[0]).path)
    cached_package = (
        context.runtime_root
        / "cache"
        / "conda-artifacts"
        / f"{package_sha256}-{filename}"
    )
    assert local_package.name == filename
    assert explicit.parent.name.endswith(".explicit-view")
    assert local_package.stat().st_ino == cached_package.stat().st_ino
    assert source_ids == ("fixture-source",)


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

    plan = setup_plan(context, component="boltzgen")

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

    plan = setup_plan(context, component=component)

    assert plan["mode"] == "component"
    assert plan["component"] == component
    assert [item["environment_id"] for item in plan["environments"]] == [
        environment_id
    ]
    assert tuple(item["asset_id"] for item in plan["assets"]) == asset_ids


def test_all_component_plan_contains_every_backend_once_in_install_order() -> None:
    repository = Path(__file__).resolve().parents[3]
    context = WorkspaceContext.from_root(repository)

    plan = setup_plan(context, component="all")

    assert plan["mode"] == "component"
    assert plan["component"] == "all"
    assert tuple(
        item["environment_id"] for item in plan["environments"]
    ) == runtime_setup.SETUP_COMPONENT_SEQUENCE
    expected_assets = tuple(
        asset_id
        for component in runtime_setup.SETUP_COMPONENT_SEQUENCE
        for asset_id in runtime_setup.SETUP_COMPONENT_ASSETS[component]
    )
    observed_assets = tuple(item["asset_id"] for item in plan["assets"])
    assert observed_assets == expected_assets
    assert len(observed_assets) == len(set(observed_assets))


def test_setup_plan_rejects_unknown_component() -> None:
    repository = Path(__file__).resolve().parents[3]
    context = WorkspaceContext.from_root(repository)

    with pytest.raises(ConfigurationError, match="未知安装组件"):
        setup_plan(context, component="unknown-component")


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
    monkeypatch.setattr(
        runtime_setup,
        "load_runtime_sources",
        lambda _context: SimpleNamespace(asset_rewrites=()),
    )
    monkeypatch.setattr(
        runtime_setup,
        "rank_source_candidates",
        lambda candidates, _policy: tuple(candidates),
    )

    with pytest.raises(ConfigurationError, match="fetch 失败"):
        runtime_setup._checkout_git(
            context,
            definition,
            context.runtime_root / "models" / definition.destination,
            source_policy="official",
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
        lambda _context, *, component: {
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
            component="pymol-pse",
            accepted_license_ids=set(),
        )

    assert not context.profile_path.exists()


def test_setup_workspace_emits_environment_and_byte_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    asset = AssetDefinition(
        asset_id="fixture-model",
        kind="file",
        source="https://example.test/model.bin",
        destination=Path("fixture/model.bin"),
        sha256="a" * 64,
        expected_size_bytes=100,
        estimated_install_bytes=100,
        license="test-only",
        license_confirmation_required=False,
    )
    monkeypatch.setattr(
        runtime_setup,
        "_setup_selection",
        lambda _context, *, component: (
            "component",
            ("fixture-env",),
            (asset,),
        ),
    )
    monkeypatch.setattr(
        runtime_setup,
        "setup_plan",
        lambda _context, *, component: {
            "disk": {
                "sufficient": True,
                "incremental_peak_bytes": 100,
                "reserve_bytes": 50,
                "free_bytes": 1000,
            }
        },
    )
    monkeypatch.setattr(runtime_setup, "initialize_workspace_metadata", lambda _context: None)
    monkeypatch.setattr(
        runtime_setup,
        "pip_index_candidates",
        lambda *_args, **_kwargs: (
            SourceCandidate(
                source_id="fixture-pip",
                region="official",
                url="https://example.test/simple",
            ),
        ),
    )

    def fake_environment(
        _context: WorkspaceContext,
        environment_id: str,
        **kwargs: object,
    ) -> EnvironmentRecord:
        callback = kwargs["progress_callback"]
        assert callable(callback)
        callback("正在创建锁定 Conda 环境", 0.1)
        download_callback = kwargs["download_progress_callback"]
        assert callable(download_callback)
        download_callback(
            "正在获取锁定 Conda 包 1/2 [fixture-conda]: fixture.conda",
            0.25,
            25,
            100,
            "fixture.conda",
        )
        callback("环境安装与探针完成", 1.0)
        return EnvironmentRecord(
            environment_id=environment_id,
            lock_sha256="b" * 64,
            relative_prefix=Path("runtime/envs/fixture-env"),
            status="available",
            probe_command=("python", "-V"),
            recorded_at=runtime_setup.datetime.now(tz=runtime_setup.UTC),
        )

    def fake_asset(
        _context: WorkspaceContext,
        definition: AssetDefinition,
        **kwargs: object,
    ) -> runtime_setup.AssetRecord:
        callback = kwargs["progress_callback"]
        assert callable(callback)
        callback(50, 100)
        callback(100, 100)
        return runtime_setup.AssetRecord(
            asset_id=definition.asset_id,
            relative_path=Path("runtime/models/fixture/model.bin"),
            status="available",
            sha256="a" * 64,
            size_bytes=100,
            license="test-only",
            recorded_at=runtime_setup.datetime.now(tz=runtime_setup.UTC),
        )

    monkeypatch.setattr(runtime_setup, "ensure_environment", fake_environment)
    monkeypatch.setattr(runtime_setup, "ensure_asset", fake_asset)
    events: list[runtime_setup.SetupProgressUpdate] = []

    summary = setup_workspace(
        context,
        component="fixture",
        accepted_license_ids=set(),
        progress_callback=events.append,
    )

    assert summary.ok is True
    assert events[0].phase == "planning"
    assert any(event.phase == "environment" for event in events)
    conda_byte_event = next(event for event in events if event.bytes_completed == 25)
    assert conda_byte_event.current_item == "fixture.conda"
    assert "fixture-conda" in conda_byte_event.message
    byte_event = next(event for event in events if event.bytes_completed == 50)
    assert byte_event.current_item == "fixture-model"
    assert byte_event.current_step_fraction == 0.5
    assert events[-1].phase == "complete"
    assert events[-1].completed_steps == events[-1].total_steps == 2


def test_setup_workspace_stops_after_first_failed_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    asset = AssetDefinition(
        asset_id="unreached-model",
        kind="file",
        source="https://example.test/model.bin",
        destination=Path("fixture/model.bin"),
        sha256="a" * 64,
        expected_size_bytes=100,
        estimated_install_bytes=100,
        license="test-only",
        license_confirmation_required=False,
    )
    monkeypatch.setattr(
        runtime_setup,
        "_setup_selection",
        lambda _context, *, component: (
            "component",
            ("first-env", "unreached-env"),
            (asset,),
        ),
    )
    monkeypatch.setattr(
        runtime_setup,
        "setup_plan",
        lambda _context, *, component: {
            "disk": {
                "sufficient": True,
                "incremental_peak_bytes": 100,
                "reserve_bytes": 50,
                "free_bytes": 1000,
            }
        },
    )
    monkeypatch.setattr(runtime_setup, "initialize_workspace_metadata", lambda _context: None)
    monkeypatch.setattr(
        runtime_setup,
        "pip_index_candidates",
        lambda *_args, **_kwargs: (
            SourceCandidate(
                source_id="fixture-pip",
                region="official",
                url="https://example.test/simple",
            ),
        ),
    )
    attempted: list[str] = []

    def failed_environment(
        _context: WorkspaceContext,
        environment_id: str,
        **_kwargs: object,
    ) -> EnvironmentRecord:
        attempted.append(environment_id)
        return EnvironmentRecord(
            environment_id=environment_id,
            lock_sha256="b" * 64,
            relative_prefix=Path("runtime/envs/first-env"),
            status="failed",
            probe_command=("python", "-V"),
            recorded_at=runtime_setup.datetime.now(tz=runtime_setup.UTC),
        )

    monkeypatch.setattr(runtime_setup, "ensure_environment", failed_environment)
    monkeypatch.setattr(
        runtime_setup,
        "ensure_asset",
        lambda *_args, **_kwargs: pytest.fail("asset install must not start"),
    )
    events: list[runtime_setup.SetupProgressUpdate] = []

    summary = setup_workspace(
        context,
        component="all",
        accepted_license_ids=set(),
        progress_callback=events.append,
    )

    assert attempted == ["first-env"]
    assert len(summary.environments) == 1
    assert summary.assets == ()
    assert summary.ok is False
    assert events[-1].phase == "failed"
    assert events[-1].current_item == "first-env"
    assert events[-1].completed_steps == 1
    assert events[-1].total_steps == 3


def test_inventory_normalizes_only_workspace_editable_commit() -> None:
    old = {
        "pip_freeze": [
            "-e git+https://example.test/EasyDesign.git@old#egg=easydesign",
            "pydantic==2.13.4",
        ]
    }
    new = {
        "pip_freeze": [
            "-e git+https://example.test/EasyDesign.git@new#egg=easydesign",
            "pydantic==2.13.4",
        ]
    }
    drifted = {
        "pip_freeze": [
            "-e git+https://example.test/EasyDesign.git@new#egg=easydesign",
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


def test_pip_lock_falls_back_without_changing_requirements(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    python = tmp_path / "runtime/envs/fixture/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("fixture", encoding="utf-8")
    requirements = tmp_path / "fixture-requirements.txt"
    requirements.write_text("example==1.0\n", encoding="utf-8")
    candidates = (
        SourceCandidate(
            source_id="first",
            region="china",
            url="https://first.example.test/simple",
        ),
        SourceCandidate(
            source_id="fallback",
            region="official",
            url="https://fallback.example.test/simple",
        ),
    )
    indexes: list[str] = []
    monkeypatch.setenv("PYTHONPATH", "/outside/pythonpath")
    monkeypatch.setenv("PYTHONHOME", "/outside/pythonhome")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        assert "/outside" not in environment["PYTHONPATH"]
        assert "PYTHONHOME" not in environment
        indexes.append(str(environment["PIP_INDEX_URL"]))
        return subprocess.CompletedProcess(
            command,
            0 if len(indexes) == 2 else 1,
            "",
            "",
        )

    monkeypatch.setattr(
        runtime_setup,
        "_pip_reliability_arguments",
        lambda _context, _python: [],
    )
    monkeypatch.setattr(runtime_setup.subprocess, "run", fake_run)

    completed, selected = runtime_setup._install_pip_requirements(
        context,
        python=python,
        requirements=requirements,
        candidates=candidates,
    )

    assert completed.returncode == 0
    assert indexes == [candidate.url for candidate in candidates]
    assert selected.source_id == "fallback"
