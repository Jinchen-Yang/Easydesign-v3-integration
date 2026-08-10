from __future__ import annotations

import json
import os
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest

from scripts import bootstrap


def _probe(name: str, *, available: bool, throughput: float | None) -> bootstrap.ProbeResult:
    return bootstrap.ProbeResult(
        name=name,
        display_name=name.title(),
        index_url=f"https://{name}.example/simple",
        available=available,
        latency_ms=20 if available else None,
        artifact_bytes=1024 if available else 0,
        throughput_mib_s=throughput,
        error=None if available else "offline",
    )


def _patch_runtime_paths(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap, "ROOT", root)
    monkeypatch.setattr(bootstrap, "CONFIG_PATH", root / "config/bootstrap-indexes.json")
    monkeypatch.setattr(bootstrap, "LOCK_PATH", root / "uv.lock")
    monkeypatch.setattr(bootstrap, "PROJECT_PATH", root / "pyproject.toml")
    monkeypatch.setattr(bootstrap, "STATE_ROOT", root / "runtime/state/bootstrap")
    monkeypatch.setattr(bootstrap, "CACHE_ROOT", root / "runtime/cache/uv")
    monkeypatch.setattr(bootstrap, "TMP_ROOT", root / "runtime/tmp")
    monkeypatch.setattr(bootstrap, "QUARANTINE_ROOT", root / "runtime/quarantine")
    monkeypatch.setattr(bootstrap, "TOOLS_ROOT", root / "runtime/tools")
    monkeypatch.setattr(bootstrap, "VENV_ROOT", root / ".venv")
    monkeypatch.setattr(bootstrap, "VENV_PYTHON", root / ".venv/bin/python")
    monkeypatch.setattr(bootstrap, "VENV_ENTRYPOINT", root / ".venv/bin/easydesign")


def test_index_url_rejects_credentials_http_query_and_fragment() -> None:
    for value in (
        "http://mirror.example/simple",
        "https://user:secret@mirror.example/simple",
        "https://mirror.example/simple?token=secret",
        "https://mirror.example/simple#fragment",
    ):
        with pytest.raises(bootstrap.BootstrapError):
            bootstrap._safe_index_url(value)
    assert bootstrap._safe_index_url("https://mirror.example/simple/") == (
        "https://mirror.example/simple"
    )


def test_auto_ranks_only_available_sources_by_measured_throughput() -> None:
    ranked = bootstrap.rank_probes(
        [
            _probe("official", available=True, throughput=1.0),
            _probe("aliyun", available=True, throughput=8.5),
            _probe("tsinghua", available=False, throughput=None),
        ]
    )
    assert [result.name for result in ranked] == ["aliyun", "official"]


def test_dry_run_does_not_create_environment_or_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    (root / "config").mkdir()
    (root / "scripts").mkdir()
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (root / "easydesign-workspace.yaml").write_text("schema: 1\n", encoding="utf-8")
    config = {
        "schema_version": "0.1",
        "probe_package": "numpy",
        "probe_bytes": 1024,
        "sources": [
            {
                "name": "official",
                "display_name": "Official",
                "index_url": "https://pypi.example/simple",
            }
        ],
    }
    (root / "config/bootstrap-indexes.json").write_text(
        json.dumps(config), encoding="utf-8"
    )
    monkeypatch.setattr(bootstrap, "ROOT", root)
    monkeypatch.setattr(bootstrap, "CONFIG_PATH", root / "config/bootstrap-indexes.json")
    monkeypatch.setattr(bootstrap, "LOCK_PATH", root / "uv.lock")
    monkeypatch.setattr(bootstrap, "PROJECT_PATH", root / "pyproject.toml")
    monkeypatch.setattr(bootstrap, "STATE_ROOT", root / "runtime/state/bootstrap")
    monkeypatch.setattr(
        bootstrap,
        "probe_source",
        lambda *args, **kwargs: _probe("official", available=True, throughput=1.0),
    )
    result = bootstrap.bootstrap(
        Namespace(index="auto", index_url=None, timeout=1.0, dry_run=True, json=True)
    )
    assert result["status"] == "dry-run"
    assert result["would_write"] is False
    assert not (root / ".venv").exists()
    assert not (root / "runtime").exists()


def test_receipts_are_append_only_and_pointer_selects_latest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap, "STATE_ROOT", tmp_path / "runtime/state/bootstrap")
    first = bootstrap._write_receipt({"status": "failed", "attempt": 1})
    second = bootstrap._write_receipt({"status": "success", "attempt": 2})
    assert first != second
    assert json.loads(first.read_text(encoding="utf-8"))["status"] == "failed"
    assert json.loads(second.read_text(encoding="utf-8"))["status"] == "success"
    assert (bootstrap.STATE_ROOT / "BOOTSTRAP_CURRENT").read_text(encoding="utf-8") == (
        f"{second.name}\n"
    )


def test_named_source_failure_is_not_ranked_for_fallback() -> None:
    assert bootstrap.rank_probes([_probe("aliyun", available=False, throughput=None)]) == []


def test_git_identity_rejects_parent_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap, "ROOT", tmp_path / "nested-copy")
    monkeypatch.setattr(
        bootstrap.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout=f"{tmp_path}\nabc123\n", stderr=""
        ),
    )
    assert bootstrap._git_head({}) is None


def test_bootstrap_child_environment_is_fully_clone_local(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_runtime_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("HOME", "/outside/home")
    monkeypatch.setenv("PIP_INDEX_URL", "https://outside.example/simple")
    monkeypatch.setenv("VIRTUAL_ENV", "/outside/venv")

    environment = bootstrap._environment()

    assert environment["HOME"] == str(tmp_path / "runtime/home")
    assert environment["UV_PYTHON_INSTALL_DIR"] == str(
        tmp_path / "runtime/tools/uv-python"
    )
    assert environment["XDG_CONFIG_HOME"] == str(tmp_path / "runtime/state/xdg-config")
    assert environment["PIP_CONFIG_FILE"] == os.devnull
    assert environment["UV_NO_CONFIG"] == "1"
    assert environment["UV_NO_SYSTEM_CONFIG"] == "1"
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert "PIP_INDEX_URL" not in environment
    assert "VIRTUAL_ENV" not in environment
    assert Path(environment["GIT_CONFIG_GLOBAL"]).is_relative_to(tmp_path)


def test_global_uv_is_used_without_copying_or_mutating_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_runtime_paths(tmp_path, monkeypatch)
    source = tmp_path / "global-bin/uv"
    source.parent.mkdir()
    source.write_bytes(b"fixed-uv-binary")
    source.chmod(0o755)
    monkeypatch.setattr(bootstrap.shutil, "which", lambda _name: str(source))
    monkeypatch.setattr(
        bootstrap,
        "_capture",
        lambda *args, **kwargs: f"uv {bootstrap.UV_VERSION} (x86_64-unknown-linux-gnu)",
    )

    selected = bootstrap._find_uv({})

    assert selected == source.resolve()
    assert source.read_bytes() == b"fixed-uv-binary"
    assert not (tmp_path / "runtime/tools/uv-0.12.3").exists()


def test_staged_venv_is_managed_and_relocatable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_runtime_paths(tmp_path, monkeypatch)
    (tmp_path / ".python-version").write_text("3.11\n", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        environment: dict[str, str],
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del environment, check
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(bootstrap, "_run", fake_run)
    monkeypatch.setattr(bootstrap, "_capture", lambda *args, **kwargs: "3.11")
    staged = tmp_path / "runtime/tmp/bootstrap-test/.venv"

    bootstrap._create_staged_venv(Path("/workspace/uv"), {}, staged)

    assert "--managed-python" in commands[0]
    assert "--relocatable" in commands[0]
    assert commands[0][-1] == str(staged)


def test_existing_venv_is_never_modified_or_quarantined(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_runtime_paths(tmp_path, monkeypatch)
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    marker = tmp_path / ".venv/keep-me"
    marker.parent.mkdir()
    marker.write_text("user-data", encoding="utf-8")

    with pytest.raises(bootstrap.BootstrapError, match="拒绝覆盖"):
        bootstrap._install_environment(
            Namespace(timeout=1.0),
            config={},
            selected_sources=(),
            requested="auto",
        )

    assert marker.read_text(encoding="utf-8") == "user-data"
    assert not bootstrap.QUARANTINE_ROOT.exists()
    receipts = tuple(bootstrap.STATE_ROOT.glob("bootstrap-*.json"))
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_text(encoding="utf-8"))["status"] == "failed"


def test_receipt_failure_quarantines_environment_created_by_this_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_runtime_paths(tmp_path, monkeypatch)
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    uv = tmp_path / "global-bin/uv"
    uv.parent.mkdir()
    uv.write_bytes(b"fixed-uv-binary")
    uv.chmod(0o755)
    selected = _probe("official", available=True, throughput=1.0)
    bootstrap.TMP_ROOT.mkdir(parents=True)

    monkeypatch.setattr(bootstrap, "_probe_sources", lambda *args, **kwargs: [selected])
    monkeypatch.setattr(bootstrap, "_environment", lambda: {})
    monkeypatch.setattr(bootstrap, "_find_uv", lambda _environment: uv)
    monkeypatch.setattr(bootstrap, "_uv_version", lambda *args, **kwargs: "uv 0.12.3")
    monkeypatch.setattr(bootstrap, "_git_head", lambda _environment: "abc123")

    def create_staged_venv(
        _uv: Path,
        _environment: dict[str, str],
        target: Path,
    ) -> None:
        (target / "bin").mkdir(parents=True)
        (target / "bin/python").write_text("python", encoding="utf-8")
        (target / "bin/easydesign").write_text("easydesign", encoding="utf-8")

    def run(
        command: list[str],
        *,
        environment: dict[str, str],
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del environment, check
        if "--output-file" in command:
            Path(command[-1]).write_text("dependency==1 --hash=sha256:abc\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(bootstrap, "_create_staged_venv", create_staged_venv)
    monkeypatch.setattr(bootstrap, "_run", run)
    monkeypatch.setattr(bootstrap, "_capture", lambda *args, **kwargs: "easydesign 0.1")
    monkeypatch.setattr(
        bootstrap,
        "_write_receipt",
        lambda _payload: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(OSError, match="disk full"):
        bootstrap._install_environment(
            Namespace(timeout=1.0),
            config={},
            selected_sources=(selected,),
            requested="auto",
        )

    assert not bootstrap.VENV_ROOT.exists()
    metadata = tuple(bootstrap.QUARANTINE_ROOT.rglob("quarantine.json"))
    assert len(metadata) == 2
    assert any(
        json.loads(path.read_text(encoding="utf-8"))["operation"] == "bootstrap-venv"
        for path in metadata
    )
