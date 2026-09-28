from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from easydesign.core import ConfigurationError
from easydesign.orchestration.application import RunSummary
from easydesign.orchestration.local_project import (
    LocalProjectRunBinding,
    resolve_project_run,
)


def _summary(runs_root: Path, project_id: str, run_id: str) -> RunSummary:
    run_root = runs_root / project_id / run_id
    return RunSummary(
        project_id=project_id,
        run_id=run_id,
        path=run_root,
        status="succeeded",
        latest_manifest=run_root / "manifests/run-manifest.v0001.json",
        manifest_revision=1,
        completed_stages=("01-target-preparation",),
    )


def _patch_project(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    project_id: str = "project-a",
) -> tuple[Path, Path, Path]:
    project = tmp_path / "workspace/projects" / project_id
    runtime_root = tmp_path / "workspace/runtime"
    runs_root = tmp_path / "workspace/runs"
    project.mkdir(parents=True)
    runtime_root.mkdir(parents=True)
    runs_root.mkdir(parents=True)
    context = SimpleNamespace(runtime_root=runtime_root, runs_root=runs_root)
    monkeypatch.setattr(
        "easydesign.orchestration.local_project.WorkspaceContext.discover",
        lambda: context,
    )
    monkeypatch.setattr(
        "easydesign.orchestration.local_project.resolve_project_path",
        lambda value, *, must_exist: project,
    )
    monkeypatch.setattr(
        "easydesign.orchestration.local_project.project_config_path",
        lambda root: root / "config.yaml",
    )
    monkeypatch.setattr(
        "easydesign.orchestration.local_project.load_run_config",
        lambda path, *, source_base_dir: SimpleNamespace(
            config=SimpleNamespace(project_id=project_id)
        ),
    )
    return project, runtime_root, runs_root


def test_resolve_project_run_uses_bound_run_without_listing_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, runtime_root, runs_root = _patch_project(monkeypatch, tmp_path)
    run_id = "run-current"
    expected = _summary(runs_root, "project-a", run_id)
    binding_path = runtime_root / "state/local-projects/project-a.json"
    binding_path.parent.mkdir(parents=True)
    binding_path.touch()
    binding = LocalProjectRunBinding(
        project_id="project-a",
        project_root=project,
        run_id=run_id,
        run_root=expected.path,
        updated_at=datetime.now(UTC),
    )
    monkeypatch.setattr(
        "easydesign.orchestration.local_project.load_latest_runtime_model",
        lambda path, model: binding,
    )
    calls: list[tuple[Path, str]] = []

    def direct_show(root: Path, selector: str) -> RunSummary:
        calls.append((root, selector))
        return expected

    monkeypatch.setattr("easydesign.orchestration.local_project.show_run", direct_show)
    monkeypatch.setattr(
        "easydesign.orchestration.local_project.list_runs",
        lambda root: pytest.fail("bound resolution must not list historical runs"),
    )

    assert resolve_project_run(project) == expected
    assert calls == [(runs_root, "project-a/run-current")]


def test_resolve_project_run_rejects_binding_for_another_project_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, runtime_root, runs_root = _patch_project(monkeypatch, tmp_path)
    binding_path = runtime_root / "state/local-projects/project-a.json"
    binding_path.parent.mkdir(parents=True)
    binding_path.touch()
    binding = LocalProjectRunBinding(
        project_id="project-other",
        project_root=project,
        run_id="run-current",
        run_root=runs_root / "project-a/run-current",
        updated_at=datetime.now(UTC),
    )
    monkeypatch.setattr(
        "easydesign.orchestration.local_project.load_latest_runtime_model",
        lambda path, model: binding,
    )
    monkeypatch.setattr(
        "easydesign.orchestration.local_project.show_run",
        lambda root, selector: pytest.fail("invalid binding must not be followed"),
    )

    with pytest.raises(ConfigurationError, match="binding"):
        resolve_project_run(project)


def test_explicit_run_resolves_directly_without_listing_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _runtime_root, runs_root = _patch_project(monkeypatch, tmp_path)
    expected = _summary(runs_root, "project-a", "run-selected")
    selectors: list[str] = []

    def direct_show(root: Path, selector: str) -> RunSummary:
        selectors.append(selector)
        return expected

    monkeypatch.setattr(
        "easydesign.orchestration.local_project.show_run", direct_show
    )
    monkeypatch.setattr(
        "easydesign.orchestration.local_project.list_runs",
        lambda root: pytest.fail("explicit resolution must not list historical runs"),
    )

    assert resolve_project_run(project, run_id="run-selected") == expected
    assert selectors == ["project-a/run-selected"]


def test_missing_explicit_run_preserves_project_api_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from easydesign.core import ManifestStateError

    project, _runtime_root, _runs_root = _patch_project(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "easydesign.orchestration.local_project.show_run",
        lambda root, selector: (_ for _ in ()).throw(
            ManifestStateError(f"run-index 没有匹配 run: {selector}")
        ),
    )

    with pytest.raises(ConfigurationError, match="项目没有匹配 run"):
        resolve_project_run(project, run_id="missing")
    assert resolve_project_run(project, run_id="missing", required=False) is None
