from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts import dev

ROOT = Path(__file__).resolve().parents[2]


def _context(*arguments: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "scripts/dev.py", "context", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return json.loads(completed.stdout)


def test_context_receipt_avoids_reloading_unchanged_policy() -> None:
    first = _context(
        "--mode",
        "dev-local",
        "--path",
        "src/easydesign/ui/app.py",
    )

    assert first["required_reading"] == [
        "AGENTS.md",
        "docs/agent/UI_AND_REPORTING.md",
    ]
    bundle = first["policy_bundle_id"]
    second = _context(
        "--mode",
        "dev-local",
        "--path",
        "src/easydesign/ui/app.py",
        "--known-bundle-id",
        str(bundle),
    )

    assert second["policy_bundle_id"] == bundle
    assert second["policy_unchanged"] is True
    assert second["required_reading"] == []


def test_context_scope_expansion_only_requests_the_new_guide() -> None:
    ui = _context(
        "--mode",
        "dev-local",
        "--path",
        "src/easydesign/ui/app.py",
    )
    expanded = _context(
        "--mode",
        "dev-local",
        "--path",
        "src/easydesign/ui/app.py",
        "--path",
        "src/easydesign/orchestration/workspace.py",
        "--known-bundle-id",
        str(ui["policy_bundle_id"]),
    )

    assert expanded["required_reading"] == [
        "docs/agent/RUNTIME_AND_DATA.md"
    ]
    assert expanded["selected_guides"] == [
        "docs/agent/RUNTIME_AND_DATA.md",
        "docs/agent/UI_AND_REPORTING.md",
    ]


def test_task_paths_select_only_relevant_guides() -> None:
    assert dev.selected_guides(
        "dev-local", ["src/easydesign/ui/app.py"]
    ) == ("docs/agent/UI_AND_REPORTING.md",)
    assert dev.selected_guides("dev-local", ["easydesign"]) == ()
    assert dev.selected_guides("release", ["src/easydesign/ui/app.py"]) == (
        "docs/agent/RELEASE_AND_REMOTE.md",
        "docs/agent/UI_AND_REPORTING.md",
    )


def test_risk_classification_keeps_local_work_local() -> None:
    assert dev.minimum_mode(["README.md"]) == "dev-local"
    assert dev.minimum_mode(["easydesign"]) == "dev-local"
    assert dev.minimum_mode(["src/easydesign/ui/app.py"]) == "dev-local"
    assert dev.minimum_mode(["src/easydesign/managed_protocol.py"]) == "integration"
    assert dev.minimum_mode(["src/easydesign/core/manifests.py"]) == "integration"


def test_development_ui_defaults_to_isolated_port() -> None:
    arguments = dev.parser().parse_args(["ui"])

    assert arguments.port == 18770
    assert dev.main(["ui", "--port", "18769"]) == 2


def test_legacy_build_targets_have_an_explicit_release_gate() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "build-ui-staging:" in makefile
    assert "build-wheel-staging:" in makefile
    assert "release-build:" in makefile
    assert 'test "$(RELEASE)" = "1"' in makefile
    assert "dist/easydesign-0.1.0.dev" not in makefile
