from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from easydesign.core import ConfigurationError
from easydesign.orchestration import miniforge
from easydesign.orchestration.source_policy import SourceSelection
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


def test_install_miniforge_is_explicit_verified_and_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    monkeypatch.setenv("PYTHONPATH", "/outside/pythonpath")
    monkeypatch.setenv("PYTHONHOME", "/outside/pythonhome")
    monkeypatch.setenv("VIRTUAL_ENV", "/outside/venv")

    def fake_download(
        selected: WorkspaceContext,
        *,
        show_progress: bool,
        source_policy: str,
    ) -> tuple[Path, SourceSelection]:
        assert show_progress is False
        assert source_policy == "auto"
        selected.ensure_layout()
        installer = selected.runtime_root / "tmp/miniforge-fixture.sh"
        installer.write_text("fixture", encoding="utf-8")
        return installer, SourceSelection(
            source_id="fixture-source",
            url="https://example.test/miniforge.sh",
        )

    def fake_run(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        assert "PYTHONPATH" not in environment
        assert "PYTHONHOME" not in environment
        assert "VIRTUAL_ENV" not in environment
        if command[0] == "/bin/bash":
            prefix = Path(command[-1])
            conda = prefix / "bin/conda"
            conda.parent.mkdir(parents=True)
            conda.write_text("fixture", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 0, "conda 26.3.1\n", "")

    monkeypatch.setattr(miniforge, "_download_installer", fake_download)
    monkeypatch.setattr(miniforge.subprocess, "run", fake_run)

    installed = miniforge.install_miniforge(context, show_progress=False)
    repeated = miniforge.install_miniforge(context, show_progress=False)

    assert installed.status == "installed"
    assert repeated.status == "already-installed"
    assert installed.receipt.installer_sha256 == miniforge.MINIFORGE_INSTALLER_SHA256
    assert installed.receipt.conda_version == "conda 26.3.1"
    assert (context.root / installed.receipt_path).is_file()
    assert (context.root / miniforge.MINIFORGE_PREFIX).is_symlink()
    assert (context.root / miniforge.MINIFORGE_PREFIX).resolve() == (
        context.root / miniforge.MINIFORGE_RELEASE_PREFIX
    )
    assert miniforge.local_miniforge_conda(context).is_file()


def test_install_miniforge_refuses_unrecorded_existing_prefix(tmp_path: Path) -> None:
    context = _workspace(tmp_path)
    prefix = context.root / miniforge.MINIFORGE_PREFIX
    prefix.mkdir(parents=True)
    marker = prefix / "keep-me"
    marker.write_text("user-data", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="目录与 receipt 不完整"):
        miniforge.install_miniforge(context, show_progress=False)

    assert marker.read_text(encoding="utf-8") == "user-data"


def test_miniforge_download_failure_never_starts_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)

    monkeypatch.setattr(
        miniforge,
        "_download_installer",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ConfigurationError("Miniforge installer SHA-256 不匹配")
        ),
    )

    with pytest.raises(ConfigurationError, match="SHA-256 不匹配"):
        miniforge.install_miniforge(context, show_progress=False)

    assert not (context.root / miniforge.MINIFORGE_PREFIX).exists()
    assert not tuple(context.runtime_root.glob("quarantine/*/quarantine.yaml"))


def test_failed_miniforge_install_never_publishes_final_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    monkeypatch.setenv("PYTHONPATH", "/outside/pythonpath")

    def fake_download(
        selected: WorkspaceContext,
        *,
        show_progress: bool,
        source_policy: str,
    ) -> tuple[Path, SourceSelection]:
        del show_progress
        assert source_policy == "auto"
        selected.ensure_layout()
        installer = selected.runtime_root / "tmp/miniforge-fixture.sh"
        installer.write_text("fixture", encoding="utf-8")
        return installer, SourceSelection(
            source_id="fixture-source",
            url="https://example.test/miniforge.sh",
        )

    def fake_run(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        assert "PYTHONPATH" not in environment
        release_prefix = Path(command[-1])
        release_prefix.mkdir(parents=True)
        (release_prefix / "partial").write_text("partial", encoding="utf-8")
        return subprocess.CompletedProcess(command, 9, "", "failed")

    monkeypatch.setattr(miniforge, "_download_installer", fake_download)
    monkeypatch.setattr(miniforge.subprocess, "run", fake_run)

    with pytest.raises(ConfigurationError, match="返回 9"):
        miniforge.install_miniforge(context, show_progress=False)

    assert not (context.root / miniforge.MINIFORGE_PREFIX).exists()
    assert not (context.root / miniforge.MINIFORGE_PREFIX).is_symlink()
    assert not (context.root / miniforge.MINIFORGE_RELEASE_PREFIX).exists()
    metadata = tuple(context.runtime_root.glob("quarantine/*/quarantine.yaml"))
    assert len(metadata) == 1


def test_runtime_setup_prefers_verified_local_miniforge_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    conda = miniforge.local_miniforge_conda(context)
    conda.parent.mkdir(parents=True)
    conda.write_text("fixture", encoding="utf-8")

    from easydesign.orchestration import runtime_setup

    monkeypatch.setattr(runtime_setup, "miniforge_status", lambda _context: object())

    assert runtime_setup._conda_executable(context) == conda.resolve()


def test_runtime_setup_rejects_unrecorded_local_miniforge(tmp_path: Path) -> None:
    context = _workspace(tmp_path)
    conda = miniforge.local_miniforge_conda(context)
    conda.parent.mkdir(parents=True)
    conda.write_text("fixture", encoding="utf-8")

    from easydesign.orchestration.runtime_setup import _conda_executable

    with pytest.raises(ConfigurationError, match="目录与 receipt 不完整"):
        _conda_executable(context)
