from __future__ import annotations

import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_repository import require_completion_timestamp

ROOT = Path(__file__).resolve().parents[1]


def test_repository_foundation_contract() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_repository.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_repository_launcher_preserves_proxy_and_translates_ui_shortcut(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    namespace = runpy.run_path(
        str(ROOT / "easydesign"),
        run_name="easydesign_launcher_test",
    )
    translate = namespace["_translate_arguments"]
    child_environment = namespace["_child_environment"]
    monkeypatch.setenv("HTTPS_PROXY", "http://user-owned-proxy.invalid:7898")

    assert translate(["ui"]) == ["ui", "serve"]
    assert translate(["ui", "--port", "8765"]) == [
        "ui",
        "serve",
        "--port",
        "8765",
    ]
    assert translate(["ui", "serve", "--port", "8765"]) == [
        "ui",
        "serve",
        "--port",
        "8765",
    ]
    assert child_environment()["HTTPS_PROXY"] == os.environ["HTTPS_PROXY"]


def test_repository_launcher_plan_does_not_bootstrap_core(
    tmp_path: Path,
) -> None:
    launcher = tmp_path / "easydesign"
    shutil.copy2(ROOT / "easydesign", launcher)
    locks = tmp_path / "environments" / "locks"
    locks.mkdir(parents=True)
    for source in (ROOT / "environments" / "locks").glob(
        "*-linux-64.lock.json"
    ):
        shutil.copy2(source, locks / source.name)

    completed = subprocess.run(
        [
            sys.executable,
            str(launcher),
            "setup",
            "--component",
            "core-ui",
            "--plan",
            "--pip-index-url",
            "https://pypi.tuna.tsinghua.edu.cn/simple",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "easydesign-core" in completed.stdout
    assert "reporting-web" in completed.stdout
    assert "protenix-v2" not in completed.stdout
    assert not (tmp_path / "runtime").exists()


def test_repository_launcher_rejects_unsafe_pip_index() -> None:
    namespace = runpy.run_path(
        str(ROOT / "easydesign"),
        run_name="easydesign_launcher_pip_index_test",
    )
    validate = namespace["_validated_pip_index_url"]

    assert (
        validate("https://pypi.tuna.tsinghua.edu.cn/simple")
        == "https://pypi.tuna.tsinghua.edu.cn/simple"
    )
    with pytest.raises(SystemExit, match="完整 HTTPS URL"):
        validate("http://example.invalid/simple")


@pytest.mark.parametrize(
    ("record", "expected_error"),
    [
        ("- 状态：`implemented`\n", "必须且只能包含一个完成时间"),
        (
            "- 完成时间：2026-07-25 14:30:00\n",
            "必须是带 UTC offset 的 RFC 3339 秒级时间",
        ),
        (
            "- 完成时间：2026-13-40T14:30:00+08:00\n",
            "必须是带 UTC offset 的 RFC 3339 秒级时间",
        ),
        (
            "- 完成时间：2026-07-25T14:30:00+08:00\n"
            "- 完成时间：2026-07-25T14:31:00+08:00\n",
            "必须且只能包含一个完成时间",
        ),
    ],
)
def test_history_completion_timestamp_rejects_invalid_records(
    record: str,
    expected_error: str,
) -> None:
    errors: list[str] = []
    require_completion_timestamp(record, "测试记录", errors)
    assert any(expected_error in error for error in errors)


def test_history_completion_timestamp_accepts_rfc3339_offset() -> None:
    errors: list[str] = []
    require_completion_timestamp(
        "- 完成时间：2026-07-25T14:30:00+08:00\n",
        "测试记录",
        errors,
    )
    assert errors == []
