from __future__ import annotations

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
