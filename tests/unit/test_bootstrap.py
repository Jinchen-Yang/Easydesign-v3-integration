from __future__ import annotations

import json
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
