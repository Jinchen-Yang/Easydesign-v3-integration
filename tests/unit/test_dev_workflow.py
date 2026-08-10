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
        "--mode", "dev-local", "--path", "src/easydesign/cli.py"
    )
    assert first["required_reading"] == [
        "docs/agent/DEVELOPMENT_AGENT.md",
        "docs/agent/LOCAL_CLI_AND_VIEWER.md",
    ]
    bundle = first["policy_bundle_id"]
    second = _context(
        "--mode", "dev-local", "--path", "src/easydesign/cli.py",
        "--known-bundle-id", str(bundle),
    )
    assert second["policy_bundle_id"] == bundle
    assert second["policy_unchanged"] is True
    assert second["required_reading"] == []


def test_context_scope_expansion_only_requests_new_guide() -> None:
    local = _context(
        "--mode", "dev-local", "--path", "src/easydesign/cli.py"
    )
    expanded = _context(
        "--mode", "integration", "--path", "src/easydesign/cli.py",
        "--path", "src/easydesign/stages/s02_hotspot_discovery/models.py",
        "--known-bundle-id", str(local["policy_bundle_id"]),
    )
    assert expanded["required_reading"] == [
        "docs/agent/SCIENTIFIC_PIPELINE.md"
    ]


def test_task_paths_select_only_local_guides() -> None:
    assert dev.selected_guides("dev-local", ["src/easydesign/cli.py"]) == (
        "docs/agent/LOCAL_CLI_AND_VIEWER.md",
    )
    assert dev.selected_guides(
        "integration", ["src/easydesign/stages/s02_hotspot_discovery/models.py"]
    ) == ("docs/agent/SCIENTIFIC_PIPELINE.md",)
    assert dev.selected_guides(
        "ops", ["src/easydesign/orchestration/runtime_setup.py"]
    ) == ("docs/agent/RUNTIME_AND_DATA.md",)
    assert dev.selected_guides("dev-local", ["scripts/bootstrap.py"]) == (
        "docs/agent/RUNTIME_AND_DATA.md",
    )
    assert dev.selected_guides("integration", ["src/easydesign/runtime_guard.py"]) == (
        "docs/agent/RUNTIME_AND_DATA.md",
    )
    assert dev.selected_guides(
        "integration",
        [".agents/skills/easydesign-development/SKILL.md"],
    ) == ("docs/agent/LOCAL_CLI_AND_VIEWER.md",)


def test_context_uses_development_guide_instead_of_research_agents() -> None:
    payload = _context("--mode", "inspect")
    assert payload["paths"] == ["docs/agent/DEVELOPMENT_AGENT.md"]
    assert payload["required_reading"] == [
        "docs/agent/DEVELOPMENT_AGENT.md",
        "docs/agent/LOCAL_CLI_AND_VIEWER.md",
    ]
    assert "AGENTS.md" not in payload["required_reading"]


def test_risk_classification_requires_integration_for_science_and_local_worker() -> None:
    assert dev.minimum_mode(["README.md"]) == "dev-local"
    assert dev.minimum_mode(["src/easydesign/cli.py"]) == "dev-local"
    assert dev.minimum_mode(["src/easydesign/orchestration/local_jobs.py"]) == "integration"
    assert dev.minimum_mode(["src/easydesign/runtime_guard.py"]) == "integration"
    assert dev.minimum_mode(["src/easydesign/core/manifests.py"]) == "integration"
    assert dev.minimum_mode(["scripts/bootstrap.py"]) == "integration"
    assert dev.minimum_mode(
        [".agents/skills/easydesign-development/SKILL.md"]
    ) == "integration"
    assert dev.routed_tests(["scripts/bootstrap.py"]) == (
        "tests/unit/test_bootstrap.py",
        "tests/unit/test_uv_onboarding.py",
    )
    assert dev.routed_tests(["src/easydesign/orchestration/local_jobs.py"]) == (
        "tests/unit/test_cli.py",
        "tests/unit/test_local_jobs.py",
        "tests/unit/test_runtime_guard.py",
    )
    assert dev.routed_tests(
        [".agents/skills/easydesign-development/SKILL.md"]
    ) == (
        "tests/unit/test_agent_skill.py",
        "tests/unit/test_dev_workflow.py",
    )


def test_every_development_policy_test_route_exists() -> None:
    policy = json.loads(
        (ROOT / "config/development-policy.json").read_text(encoding="utf-8")
    )
    routed = {
        test
        for route in policy["test_routes"]
        for test in route["tests"]
    }
    missing = sorted(path for path in routed if not (ROOT / path).is_file())
    assert missing == []


def test_core_sync_report_is_read_only() -> None:
    parsed = dev.parser().parse_args(["core-sync-report", "--against", "main"])
    assert parsed.against == "main"
    assert not hasattr(parsed, "write")


def test_core_sync_report_includes_dirty_shared_science_paths(
    monkeypatch: object,
    capsys: object,
) -> None:
    outputs = {
        ("diff", "--name-status", "main...HEAD"): "M\tsrc/easydesign/core/manifests.py\n",
        ("diff", "--name-status", "HEAD"): "M\tsrc/easydesign/backends/demo.py\n",
        ("ls-files", "--others", "--exclude-standard"): (
            "src/easydesign/stages/new_stage_helper.py\n"
        ),
        ("log", "--format=%H%x09%s", "main..HEAD"): "",
        ("rev-parse", "HEAD"): "abc123\n",
    }

    def fake_git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        del check
        prefix = next(key for key in outputs if arguments[: len(key)] == key)
        return subprocess.CompletedProcess(
            ["git", *arguments], 0, stdout=outputs[prefix], stderr=""
        )

    monkeypatch.setattr(dev, "_git", fake_git)  # type: ignore[attr-defined]
    parsed = dev.parser().parse_args(["core-sync-report", "--against", "main"])
    assert parsed.function(parsed) == 0
    payload = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert payload["working_tree_included"] is True
    assert {(row["source"], row["path"]) for row in payload["differences"]} == {
        ("committed", "src/easydesign/core/manifests.py"),
        ("working-tree", "src/easydesign/backends/demo.py"),
        ("working-tree", "src/easydesign/stages/new_stage_helper.py"),
    }


def test_makefile_has_no_ui_or_remote_release_targets() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "build-wheel-staging:" in makefile
    assert "@set -eu;" in makefile
    assert "-m build --wheel --no-isolation" in makefile
    assert "EASYDESIGN_UV" not in makefile
    assert "test-web:" in makefile
    assert "release-build:" not in makefile
    assert "18769" not in makefile
    assert "dist/" not in makefile


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
                    "path": "runtime/tmp", "review_policy": "age",
                    "minimum_age_days": 2, "budget_bytes": 1,
                }
            ],
        }
    }
    report = dev.cleanup_report_payload(
        limit=10, root=tmp_path, policy=policy, now=now
    )
    assert report["automatic_deletion"] is False
    assert report["roots"][0]["over_budget"] is True
    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert after == before


def test_repository_retention_policy_protects_science_and_apoe() -> None:
    policy = json.loads(
        (ROOT / "config/development-policy.json").read_text(encoding="utf-8")
    )["runtime_retention"]
    assert policy["automatic_deletion"] is False
    assert {
        "examples/apoe-ui-demo", "workspace/projects", "workspace/runs"
    } <= set(policy["protected_paths"])
