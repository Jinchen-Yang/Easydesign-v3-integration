from __future__ import annotations

import json
import os
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
    assert dev.selected_guides("integration", ["scripts/local_ui_release.py"]) == (
        "docs/agent/RELEASE_AND_REMOTE.md",
    )
    assert dev.selected_guides("release", ["src/easydesign/ui/app.py"]) == (
        "docs/agent/RELEASE_AND_REMOTE.md",
        "docs/agent/UI_AND_REPORTING.md",
    )


def test_risk_classification_keeps_local_work_local() -> None:
    assert dev.minimum_mode(["README.md"]) == "dev-local"
    assert dev.minimum_mode(["easydesign"]) == "dev-local"
    assert dev.minimum_mode(["src/easydesign/ui/app.py"]) == "dev-local"
    assert dev.minimum_mode(["scripts/local_ui_release.py"]) == "integration"
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


def test_cleanup_report_is_read_only_and_never_grants_deletion(
    tmp_path: Path,
) -> None:
    now = 1_800_000_000.0
    old = tmp_path / "runtime/tmp/old-test"
    young = tmp_path / "runtime/tmp/young-test"
    protected = tmp_path / "workspace/projects"
    old.mkdir(parents=True)
    young.mkdir(parents=True)
    protected.mkdir(parents=True)
    (old / "result.txt").write_text("old", encoding="utf-8")
    (young / "result.txt").write_text("young", encoding="utf-8")
    old_time = now - 3 * 86_400
    os.utime(old / "result.txt", (old_time, old_time))
    os.utime(old, (old_time, old_time))
    os.utime(young / "result.txt", (now, now))
    os.utime(young, (now, now))
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    policy = {
        "runtime_retention": {
            "automatic_deletion": False,
            "protected_paths": ["workspace/projects"],
            "inventory_roots": [
                {
                    "path": "runtime/tmp",
                    "review_policy": "age",
                    "minimum_age_days": 2,
                    "budget_bytes": 1,
                }
            ],
        }
    }

    report = dev.cleanup_report_payload(
        limit=10,
        root=tmp_path,
        policy=policy,
        now=now,
    )

    assert report["automatic_deletion"] is False
    assert report["protected_paths"] == [
        {"path": "workspace/projects", "exists": True}
    ]
    root_report = report["roots"][0]
    assert root_report["over_budget"] is True
    assert {
        item["path"]: item["status"]
        for item in root_report["largest_entries"]
    } == {
        "runtime/tmp/old-test": "retention-review",
        "runtime/tmp/young-test": "retained-young",
    }
    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert after == before


def test_repository_retention_policy_protects_science_and_disables_automation() -> None:
    policy = json.loads(
        (ROOT / "config/development-policy.json").read_text(encoding="utf-8")
    )["runtime_retention"]

    assert policy["automatic_deletion"] is False
    assert {
        "examples/apoe-ui-demo",
        "workspace/projects",
        "workspace/runs",
        "runtime/envs",
        "runtime/models",
    } <= set(policy["protected_paths"])
