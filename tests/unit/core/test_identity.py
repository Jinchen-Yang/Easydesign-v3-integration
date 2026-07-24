from __future__ import annotations

from pathlib import Path

from easydesign.core import package_tree_sha256


def test_package_tree_sha256_is_deterministic_and_ignores_bytecode(tmp_path: Path) -> None:
    package = tmp_path / "easydesign"
    package.mkdir()
    (package / "a.py").write_text("value = 1\n", encoding="utf-8")
    cache = package / "__pycache__"
    cache.mkdir()
    (cache / "a.pyc").write_bytes(b"ignored")

    first = package_tree_sha256(package)
    (cache / "a.pyc").write_bytes(b"changed")
    second = package_tree_sha256(package)

    assert first == second
    (package / "a.py").write_text("value = 2\n", encoding="utf-8")
    assert package_tree_sha256(package) != first
