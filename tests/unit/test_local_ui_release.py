from __future__ import annotations

import os
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

from easydesign.core import ConfigurationError
from easydesign.workspace_context import WorkspaceContext
from scripts import local_ui_release as local_ui


def _context(tmp_path: Path) -> WorkspaceContext:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        """schema_version: "0.1"
workspace_id: test-local-ui
runtime_root: runtime
projects_root: projects
runs_root: runs
archives_root: archives
upload_warning_bytes: 1073741824
upload_blocking_bytes: 5368709120
""",
        encoding="utf-8",
    )
    return WorkspaceContext.from_root(tmp_path)


def _wheel(tmp_path: Path, version: str) -> Path:
    wheel = tmp_path / f"easydesign-{version}-py3-none-any.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr(
            f"easydesign-{version}.dist-info/METADATA",
            (
                "Metadata-Version: 2.1\n"
                "Name: easydesign\n"
                f"Version: {version}\n"
            ),
        )
    return wheel


def _prepare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    version: str,
) -> tuple[WorkspaceContext, local_ui.LocalUiRelease]:
    context = _context(tmp_path)
    wheel = _wheel(tmp_path, version)
    uv = tmp_path / "uv"
    uv.write_text("fake uv", encoding="utf-8")
    uv.chmod(0o755)

    def fake_run(
        command: list[str] | tuple[str, ...],
        *,
        cwd: Path,
        environment: dict[str, str],
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, environment, capture_output
        if "export" in command:
            return subprocess.CompletedProcess(command, 0, "httpx==0.28.1 --hash=sha256:test\n", "")
        if "venv" in command:
            venv = Path(command[-1])
            (venv / "bin").mkdir(parents=True)
            for name in ("python", "easydesign"):
                executable = venv / "bin" / name
                executable.write_text("#!/bin/sh\n", encoding="utf-8")
                executable.chmod(0o755)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(local_ui, "_run_checked", fake_run)
    monkeypatch.setattr(
        local_ui,
        "_installed_identity",
        lambda root: {
            "version": version,
            "module": str(root / "venv" / "lib" / "easydesign" / "__init__.py"),
        },
    )
    monkeypatch.setattr(local_ui, "_probe_release", lambda *_args, **_kwargs: None)
    release = local_ui.prepare_release(
        wheel=wheel,
        uv=uv,
        context=context,
        enforce_git=False,
    )
    return context, release


def test_prepare_publishes_noneditable_identity_and_exact_wheel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, release = _prepare(tmp_path, monkeypatch, version="1.2.3")
    root = context.runtime_root / "releases" / "local-ui" / release.release_id

    assert release.release_id == f"1.2.3-{release.wheel_sha256}"
    assert (root / "venv" / "bin" / "easydesign").is_file()
    assert (root / "requirements.lock").is_file()
    assert (root / "uv.lock").is_file()
    assert local_ui.load_release(context, release.release_id) == release
    assert not (context.runtime_root / "state" / "local-ui-activations").exists()


def test_failed_prepare_is_quarantined_without_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)
    wheel = _wheel(tmp_path, "2.0.0")
    uv = tmp_path / "uv"
    uv.write_text("fake uv", encoding="utf-8")
    uv.chmod(0o755)

    def fake_run(
        command: list[str] | tuple[str, ...],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        if "export" in command:
            return subprocess.CompletedProcess(command, 0, "locked==1 --hash=sha256:test\n", "")
        if "venv" in command:
            venv = Path(command[-1])
            (venv / "bin").mkdir(parents=True)
            for name in ("python", "easydesign"):
                path = venv / "bin" / name
                path.write_text("#!/bin/sh\n", encoding="utf-8")
                path.chmod(0o755)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(local_ui, "_run_checked", fake_run)
    monkeypatch.setattr(
        local_ui,
        "_installed_identity",
        lambda root: {"version": "2.0.0", "module": str(root / "venv")},
    )
    monkeypatch.setattr(
        local_ui,
        "_probe_release",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ConfigurationError("probe failed")
        ),
    )

    with pytest.raises(ConfigurationError, match="probe failed"):
        local_ui.prepare_release(
            wheel=wheel,
            uv=uv,
            context=context,
            enforce_git=False,
        )

    quarantines = tuple((context.runtime_root / "quarantine").iterdir())
    assert len(quarantines) == 1
    assert any(path.name.startswith("local-ui-release-") for path in quarantines[0].iterdir())
    assert local_ui.latest_activation(context) is None


class _FakeStarted:
    def __init__(self, pid: int, log_path: Path) -> None:
        self.pid = pid
        self.log_path = log_path
        self.terminated = False

    def poll(self) -> int | None:
        return 0 if self.terminated else None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float) -> int:
        del timeout
        self.terminated = True
        return 0


def test_activation_and_rollback_append_revisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, first = _prepare(tmp_path, monkeypatch, version="1.0.0")
    _, second = _prepare(tmp_path, monkeypatch, version="1.1.0")
    launched: list[_FakeStarted] = []

    def fake_launch(
        selected: WorkspaceContext,
        release: local_ui.LocalUiRelease,
        *,
        label: str,
    ) -> _FakeStarted:
        log = selected.runtime_root / "logs" / "local-ui" / f"{label}-{len(launched)}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(release.release_id, encoding="utf-8")
        process = _FakeStarted(1000 + len(launched), log)
        launched.append(process)
        return process

    monkeypatch.setattr(local_ui, "_active_ui_jobs", lambda _context: ())
    monkeypatch.setattr(local_ui, "_validated_listener", lambda *_args: None)
    monkeypatch.setattr(local_ui, "_launch_release", fake_launch)
    monkeypatch.setattr(local_ui, "_wait_health", lambda **_kwargs: {"status": "ok"})

    revision_one = local_ui.activate_release(
        release_id=first.release_id,
        confirmed=True,
        context=context,
    )
    revision_two = local_ui.activate_release(
        release_id=second.release_id,
        confirmed=True,
        context=context,
    )
    revision_three = local_ui.activate_release(
        release_id=first.release_id,
        action="rollback",
        confirmed=True,
        context=context,
    )

    assert [revision_one.revision, revision_two.revision, revision_three.revision] == [1, 2, 3]
    assert revision_three.action == "rollback"
    assert revision_three.previous_revision == 2
    assert local_ui.latest_activation(context) == revision_three
    assert len(tuple((context.runtime_root / "state" / "local-ui-activations").glob("*.json"))) == 3
    handoff = local_ui.manager_handoff(context)
    assert handoff["release_id"] == first.release_id
    assert handoff["wheel_sha256"] == first.wheel_sha256


def test_failed_switch_keeps_current_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, first = _prepare(tmp_path, monkeypatch, version="3.0.0")
    _, second = _prepare(tmp_path, monkeypatch, version="3.1.0")
    log = context.runtime_root / "logs" / "local-ui" / "switch.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("test", encoding="utf-8")
    first_activation = local_ui._append_activation(
        context,
        release=first,
        action="activate",
        process_id=100,
        log_path=log,
    )
    started = _FakeStarted(101, log)
    restored: list[str | None] = []
    monkeypatch.setattr(local_ui, "_active_ui_jobs", lambda _context: ())
    monkeypatch.setattr(local_ui, "_validated_listener", lambda *_args: None)
    monkeypatch.setattr(local_ui, "_launch_release", lambda *_args, **_kwargs: started)
    monkeypatch.setattr(
        local_ui,
        "_wait_health",
        lambda **_kwargs: (_ for _ in ()).throw(ConfigurationError("bad health")),
    )
    monkeypatch.setattr(
        local_ui,
        "_restore_previous",
        lambda _context, previous, _legacy: restored.append(
            None if previous is None else previous.release_id
        ),
    )

    with pytest.raises(ConfigurationError, match="bad health"):
        local_ui.activate_release(
            release_id=second.release_id,
            confirmed=True,
            context=context,
        )

    assert started.terminated is True
    assert restored == [first.release_id]
    assert local_ui.latest_activation(context) == first_activation


def test_active_ui_operation_blocks_switch_before_process_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, release = _prepare(tmp_path, monkeypatch, version="4.0.0")
    monkeypatch.setattr(local_ui, "_active_ui_jobs", lambda _context: ("job-running",))
    monkeypatch.setattr(
        local_ui,
        "_validated_listener",
        lambda *_args: (_ for _ in ()).throw(AssertionError("must not inspect listener")),
    )

    with pytest.raises(ConfigurationError, match="job-running"):
        local_ui.activate_release(
            release_id=release.release_id,
            confirmed=True,
            context=context,
        )


def test_cli_requires_explicit_confirmation() -> None:
    arguments = local_ui.parser().parse_args(
        ["activate", "--release-id", "1.0.0-" + "a" * 64]
    )

    assert arguments.confirmed is False
    assert local_ui.FORMAL_PORT == 18769


def test_real_immutable_venv_prepare_when_explicitly_enabled(tmp_path: Path) -> None:
    wheel_value = os.environ.get("EASYDESIGN_TEST_LOCAL_UI_WHEEL")
    uv_value = os.environ.get("EASYDESIGN_TEST_LOCAL_UI_UV")
    if not wheel_value or not uv_value:
        pytest.skip("真实 local UI release 集成测试未显式启用")
    context = _context(tmp_path)

    release = local_ui.prepare_release(
        wheel=Path(wheel_value),
        uv=Path(uv_value),
        probe_port=local_ui.DEFAULT_PROBE_PORT,
        context=context,
        enforce_git=False,
    )

    root = context.runtime_root / "releases" / "local-ui" / release.release_id
    identity = local_ui._installed_identity(root)
    assert identity["version"] == release.version
    assert Path(identity["module"]).is_relative_to(root / "venv")
    assert local_ui.latest_activation(context) is None
