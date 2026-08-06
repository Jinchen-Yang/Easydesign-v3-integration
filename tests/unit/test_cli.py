from __future__ import annotations

import pytest

from easydesign.cli import _normalize_arguments


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (["ui"], ["ui", "serve"]),
        (["ui", "--port", "18770"], ["ui", "serve", "--port", "18770"]),
        (
            ["--debug", "ui", "--development", "--port", "18770"],
            ["--debug", "ui", "serve", "--development", "--port", "18770"],
        ),
        (["ui", "serve", "--port", "18770"], ["ui", "serve", "--port", "18770"]),
        (["ui", "--help"], ["ui", "--help"]),
        (["doctor", "--full"], ["doctor", "--full"]),
    ],
)
def test_ui_shortcut_is_normalized_by_the_packaged_cli(
    arguments: list[str],
    expected: list[str],
) -> None:
    assert _normalize_arguments(arguments) == expected
