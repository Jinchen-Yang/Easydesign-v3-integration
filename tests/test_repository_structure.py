from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_repository_local_product_contract() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_repository.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_remote_and_ui_surfaces_are_absent() -> None:
    forbidden = (
        "src/easydesign/ui",
        "web/workbench",
        "src/easydesign/managed_protocol.py",
        "src/easydesign/backends/executors/ssh_remote.py",
        "src/easydesign/orchestration/remote_execution.py",
        "scripts/local_ui_release.py",
    )
    assert all(not (ROOT / item).exists() for item in forbidden)
