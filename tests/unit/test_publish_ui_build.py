from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_publisher() -> ModuleType:
    path = ROOT / "scripts/publish_ui_build.py"
    spec = importlib.util.spec_from_file_location("publish_ui_build_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_publish_replaces_static_tree_without_carrying_old_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publisher = _load_publisher()
    target = tmp_path / "package" / "static"
    staging_root = tmp_path / "runtime" / "tmp"
    staging = staging_root / "ui-build"
    quarantine_root = tmp_path / "runtime" / "quarantine"
    target.mkdir(parents=True)
    staging.mkdir(parents=True)
    (target / "index.html").write_text("old", encoding="utf-8")
    (target / "assets").mkdir()
    (target / "assets" / "index-old.js").write_text("old", encoding="utf-8")
    (staging / "index.html").write_text("new", encoding="utf-8")
    (staging / "assets").mkdir()
    (staging / "assets" / "index-new.js").write_text("new", encoding="utf-8")

    monkeypatch.setattr(publisher, "ROOT", tmp_path)
    monkeypatch.setattr(publisher, "TARGET", target)
    monkeypatch.setattr(publisher, "STAGING_ROOT", staging_root)
    monkeypatch.setattr(publisher, "QUARANTINE_ROOT", quarantine_root)
    monkeypatch.setattr(sys, "argv", ["publish_ui_build.py", str(staging)])

    assert publisher.main() == 0
    assert (target / "assets" / "index-new.js").read_text(encoding="utf-8") == "new"
    assert not (target / "assets" / "index-old.js").exists()
    revisions = list(quarantine_root.iterdir())
    assert len(revisions) == 1
    assert (revisions[0] / "previous-static/assets/index-old.js").is_file()
