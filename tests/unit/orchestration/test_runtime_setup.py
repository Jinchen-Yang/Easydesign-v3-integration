from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
import yaml

from easydesign.core import ConfigurationError
from easydesign.orchestration import runtime_setup
from easydesign.orchestration.git_sources import GitSourceResult
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


def test_all_five_environments_have_component_specific_reliability_probes() -> None:
    assert set(runtime_setup._ENVIRONMENT_RELIABILITY_PROBES) == set(
        runtime_setup.SETUP_COMPONENT_SEQUENCE
    )
    assert "cmd.fragment" in runtime_setup._ENVIRONMENT_RELIABILITY_PROBES["pymol-pse"]
    assert "cuequivariance_ops_torch" in runtime_setup._ENVIRONMENT_RELIABILITY_PROBES[
        "boltzgen"
    ]
    assert "cuequivariance_ops_torch" in runtime_setup._ENVIRONMENT_RELIABILITY_PROBES[
        "protenix-v2"
    ]
    assert "is_built_with_cuda" in runtime_setup._ENVIRONMENT_RELIABILITY_PROBES[
        "scannet-epitope"
    ]
    assert "mkdssp" in runtime_setup._ENVIRONMENT_RELIABILITY_PROBES["tnp"]


def test_environment_probe_activates_target_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    prefix = context.runtime_root / "envs" / "fixture-lock"
    bin_directory = prefix / "bin"
    bin_directory.mkdir(parents=True)
    (bin_directory / "python").symlink_to(sys.executable)
    for executable in ("mkdssp", "ANARCI"):
        path = bin_directory / executable
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
    lock = runtime_setup.EnvironmentLock(
        environment_id="fixture",
        platform="linux-64",
        conda_explicit=Path("fixture.conda-lock.txt"),
        conda_explicit_sha256="a" * 64,
        python="3.11",
        probe=(
            "python",
            "-c",
            "import os,shutil; "
            f"assert os.environ['CONDA_PREFIX'] == {str(prefix)!r}; "
            f"assert os.environ['PATH'].split(os.pathsep)[0] == {str(bin_directory)!r}; "
            "assert shutil.which('mkdssp'); assert shutil.which('ANARCI')",
        ),
        estimated_install_bytes=1,
    )
    monkeypatch.setattr(
        runtime_setup,
        "_environment_inventory",
        lambda *_args, **_kwargs: (Path("runtime/state/inventory.json"), "b" * 64),
    )

    record = runtime_setup._probe_environment(
        context,
        lock,
        prefix,
        "c" * 64,
    )

    assert record.status == "available"
    assert record.probe_returncode == 0


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


def test_git_asset_materializer_receives_only_pinned_revision(
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
    observed: dict[str, object] = {}

    def fake_materialize(
        _context: WorkspaceContext,
        **kwargs: object,
    ) -> GitSourceResult:
        observed.update(kwargs)
        destination = kwargs["destination"]
        assert isinstance(destination, Path)
        destination.mkdir(parents=True)
        return GitSourceResult(
            path=destination,
            revision=revision,
            content_sha256="b" * 64,
            size_bytes=100,
            source=runtime_setup.SourceSelection(
                source_id="fixture-archive",
                url="https://example.test/fixture.tar.gz",
            ),
        )

    monkeypatch.setattr(runtime_setup, "materialize_git_source", fake_materialize)

    result = runtime_setup._checkout_git(
        context,
        definition,
        context.runtime_root / "models" / definition.destination,
        source_policy="official",
    )

    assert observed["source"] == definition.source
    assert observed["revision"] == revision
    assert result[:3] == (revision, "b" * 64, 100)


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
        status_callback = kwargs["status_callback"]
        assert callable(status_callback)
        status_callback("正在下载并校验资产 [fixture-segmented-http1]")
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
    assert "fixture-segmented-http1" in byte_event.message
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


def test_pip_lock_caches_each_verified_wheel_and_installs_offline(
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
    offline_locks: list[str] = []
    monkeypatch.setenv("PYTHONPATH", "/outside/pythonpath")
    monkeypatch.setenv("PYTHONHOME", "/outside/pythonhome")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        assert "/outside" not in environment["PYTHONPATH"]
        assert "PYTHONHOME" not in environment
        assert "--no-index" in command
        assert "--require-hashes" in command
        lock = Path(command[command.index("--requirement") + 1])
        offline_locks.append(lock.read_text(encoding="utf-8"))
        return subprocess.CompletedProcess(
            command,
            0,
            "",
            "",
        )

    monkeypatch.setattr(
        runtime_setup,
        "_pip_reliability_arguments",
        lambda _context, _python: [],
    )

    def fake_wheel(
        _context: WorkspaceContext,
        *,
        command: list[str],
        candidate: SourceCandidate,
    ) -> subprocess.CompletedProcess[bytes]:
        indexes.append(candidate.url)
        if len(indexes) == 2:
            wheel_dir = Path(command[command.index("--wheel-dir") + 1])
            (wheel_dir / "example-1.0-py3-none-any.whl").write_bytes(
                b"locked wheel bytes"
            )
        return subprocess.CompletedProcess(
            command,
            0 if len(indexes) == 2 else 1,
        )

    monkeypatch.setattr(runtime_setup, "_run_pip_wheel_command", fake_wheel)
    monkeypatch.setattr(runtime_setup.subprocess, "run", fake_run)

    completed, selected = runtime_setup._install_pip_requirements(
        context,
        python=python,
        requirements=requirements,
        candidates=candidates,
        environment_id="fixture",
        environment_lock_sha256="a" * 64,
    )

    assert completed.returncode == 0
    assert indexes == [candidate.url for candidate in candidates]
    assert selected.source_id == "per-wheel-cache:fallback"
    assert selected.url == candidates[1].url
    assert "--hash=sha256:" in offline_locks[0]
    artifact = next(
        (context.runtime_root / "cache" / "pip-artifacts").glob("*/*.whl")
    )
    assert artifact.read_bytes() == b"locked wheel bytes"
    receipt = next(
        (context.runtime_root / "state" / "pip-artifacts").rglob("*.json")
    )
    assert runtime_setup.PipArtifactReceipt.model_validate_json(
        receipt.read_text(encoding="utf-8")
    ).sha256 == runtime_setup.sha256_file(artifact)

    indexes.clear()
    completed_again, _selected_again = runtime_setup._install_pip_requirements(
        context,
        python=python,
        requirements=requirements,
        candidates=candidates,
        environment_id="fixture",
        environment_lock_sha256="a" * 64,
    )

    assert completed_again.returncode == 0
    assert indexes == []
    assert len(offline_locks) == 2

    artifact.write_bytes(b"corrupt wheel cache")
    rebuilt, _selected_rebuilt = runtime_setup._install_pip_requirements(
        context,
        python=python,
        requirements=requirements,
        candidates=candidates,
        environment_id="fixture",
        environment_lock_sha256="a" * 64,
    )

    assert rebuilt.returncode == 0
    assert indexes == [candidate.url for candidate in candidates]
    assert artifact.read_bytes() == b"locked wheel bytes"
    quarantined_wheels = tuple(
        (context.runtime_root / "quarantine").glob("*/*example*.whl")
    )
    assert len(quarantined_wheels) == 1


def test_pip_wheel_timeout_terminates_exact_process_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    monkeypatch.setenv("PYTHONPATH", "/outside/pythonpath")
    captured: dict[str, object] = {}
    waits = 0

    class FakeProcess:
        pid = 4242

        def wait(self, timeout: float | None = None) -> int:
            nonlocal waits
            waits += 1
            if waits == 1:
                raise subprocess.TimeoutExpired("pip wheel", timeout)
            return -15

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        captured["command"] = command
        captured.update(kwargs)
        return FakeProcess()

    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(runtime_setup.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        runtime_setup.os,
        "killpg",
        lambda pid, selected_signal: signals.append((pid, selected_signal)),
    )

    completed = runtime_setup._run_pip_wheel_command(
        context,
        command=["python", "-m", "pip", "wheel", "fixture==1.0"],
        candidate=SourceCandidate(
            source_id="fixture",
            region="official",
            url="https://example.test/simple",
        ),
    )

    assert completed.returncode == 124
    assert signals == [(4242, runtime_setup.signal.SIGTERM)]
    assert captured["start_new_session"] is True
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert "/outside" not in environment["PYTHONPATH"]
    assert environment["PIP_INDEX_URL"] == "https://example.test/simple"


def test_locked_vcs_requirement_is_materialized_once_and_installed_locally(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    context.ensure_layout()
    revision = "a" * 40
    source = "https://github.com/example/fixture.git"
    requirements = tmp_path / "fixture-lock.txt"
    requirements.write_text(
        f"fixture==1.0\nfixture-vcs @ git+{source}@{revision}\n",
        encoding="utf-8",
    )
    definition = AssetDefinition(
        asset_id="fixture-vcs-source",
        kind="git",
        source=source,
        destination=Path("fixture/source"),
        revision=revision,
        estimated_install_bytes=100,
        license="test-only",
        license_confirmation_required=False,
    )
    monkeypatch.setattr(
        runtime_setup,
        "_load_assets",
        lambda _context: runtime_setup.AssetCatalog(assets=(definition,)),
    )
    materialized: list[str] = []

    def fake_ensure_asset(
        _context: WorkspaceContext,
        asset: AssetDefinition,
        **kwargs: object,
    ) -> runtime_setup.AssetRecord:
        materialized.append(asset.asset_id)
        status_callback = kwargs["status_callback"]
        assert callable(status_callback)
        status_callback("正在获取锁定源码归档 [fixture-archive]")
        destination = context.runtime_root / "models" / asset.destination
        destination.mkdir(parents=True)
        return runtime_setup.AssetRecord(
            asset_id=asset.asset_id,
            relative_path=destination.relative_to(context.root),
            status="available",
            revision=revision,
            sha256="b" * 64,
            size_bytes=100,
            source_policy="auto",
            transport_source_id="fixture-archive",
            license=asset.license,
            recorded_at=runtime_setup.datetime.now(tz=runtime_setup.UTC),
        )

    monkeypatch.setattr(runtime_setup, "ensure_asset", fake_ensure_asset)
    progress: list[str] = []

    resolved = runtime_setup._materialize_locked_vcs_requirements(
        context,
        requirements=requirements,
        source_policy="auto",
        progress_callback=lambda message, _fraction: progress.append(message),
        download_progress_callback=None,
    )

    assert materialized == ["fixture-vcs-source"]
    assert requirements.read_text(encoding="utf-8").endswith(
        f"git+{source}@{revision}\n"
    )
    resolved_lines = resolved.read_text(encoding="utf-8").splitlines()
    assert resolved_lines[0] == "fixture==1.0"
    assert resolved_lines[1].startswith("fixture-vcs @ file://")
    assert "fixture-archive" in progress[-1]
    build_source = Path(urlparse(resolved_lines[1].split(" @ ", maxsplit=1)[1]).path)
    assert build_source.parent == resolved.parent
    assert build_source != context.runtime_root / "models" / definition.destination
    runtime_setup._cleanup_resolved_pip_requirements(
        context,
        original=requirements,
        resolved=resolved,
    )
    assert not resolved.parent.exists()


def test_mutated_git_source_is_quarantined_and_rebuilt_from_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    context.ensure_layout()
    revision = "a" * 40
    definition = AssetDefinition(
        asset_id="fixture-source",
        kind="git",
        source="https://github.com/example/fixture.git",
        destination=Path("fixture/source"),
        revision=revision,
        estimated_install_bytes=100,
        license="test-only",
        license_confirmation_required=False,
    )
    destination = context.runtime_root / "models" / definition.destination
    destination.mkdir(parents=True)
    (destination / "mutated-build-output").write_text("drift", encoding="utf-8")
    monkeypatch.setattr(
        runtime_setup,
        "verify_existing_git_source",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ConfigurationError("Git 源码 receipt 与现有内容不一致")
        ),
    )

    def fake_checkout(
        _context: WorkspaceContext,
        _definition: AssetDefinition,
        selected_destination: Path,
        **_kwargs: object,
    ) -> tuple[str, str, int, SourceSelection]:
        assert not selected_destination.exists()
        selected_destination.mkdir(parents=True)
        (selected_destination / "locked-source").write_text("clean", encoding="utf-8")
        return (
            revision,
            "b" * 64,
            5,
            SourceSelection(
                source_id="workspace-archive-cache",
                url="https://example.test/source.tar.gz",
            ),
        )

    monkeypatch.setattr(runtime_setup, "_checkout_git", fake_checkout)

    record = ensure_asset(
        context,
        definition,
        accepted_license_ids=set(),
    )

    assert record.status == "available"
    assert (destination / "locked-source").read_text(encoding="utf-8") == "clean"
    quarantined = tuple(
        (context.runtime_root / "quarantine").glob("*/source/mutated-build-output")
    )
    assert len(quarantined) == 1
