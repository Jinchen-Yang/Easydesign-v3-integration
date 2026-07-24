from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from easydesign.cli import main
from easydesign.core import CodeIdentity, CodeIdentitySource, ConfigurationError
from easydesign.orchestration import (
    DiagnosticCheck,
    DiagnosticReport,
    DiagnosticStatus,
    execute_pipeline,
    initialize_project,
    initialize_runtime_profile,
    list_runs,
    validate_run_configuration,
)
from easydesign.orchestration.workspace import RunIndexEntry, upsert_run_index_entries


def _project_and_profile(tmp_path: Path) -> tuple[Path, Path]:
    fasta = tmp_path / "target.fasta"
    fasta.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    initialized = initialize_project(
        project_root=tmp_path / "demo",
        target=fasta,
    )
    profile = initialize_runtime_profile(
        tmp_path / "profile.yaml",
        runs_root=(tmp_path / "runs").resolve(),
    )
    return initialized.config_path, profile


def test_config_validation_does_not_require_backend_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-config"))
    fasta = tmp_path / "target.fasta"
    fasta.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    initialized = initialize_project(project_root=tmp_path / "demo", target=fasta)

    plan = validate_run_configuration(initialized.config_path)

    assert plan.profile_id == "unconfigured"
    assert plan.required_backends == ("protenix-v2",)
    assert not plan.runs_root.exists()


def test_dry_run_preflight_does_not_create_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, profile = _project_and_profile(tmp_path)
    passed = DiagnosticReport(
        ok=True,
        profile_id="local",
        profile_sha256="a" * 64,
        checks=(
            DiagnosticCheck(
                name="fake",
                status=DiagnosticStatus.PASSED,
                message="unit test",
            ),
        ),
    )
    monkeypatch.setattr(
        "easydesign.orchestration.application.diagnose_runtime",
        lambda **_: passed,
    )

    outcome = execute_pipeline(config, profile_path=profile, dry_run=True)

    assert outcome.status == "dry-run"
    assert not (tmp_path / "runs").exists()


def test_cli_init_and_config_validate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fasta = tmp_path / "target.fasta"
    fasta.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    project = tmp_path / "cli-demo"

    assert main(["init", str(project), "--target", str(fasta)]) == 0
    assert main(["config", "validate", str(project / "easydesign.yaml")]) == 0
    output = capsys.readouterr().out
    assert "项目已创建" in output
    assert "配置校验通过" in output


def test_unimplemented_stage_fails_before_profile_or_workspace(tmp_path: Path) -> None:
    pse = tmp_path / "target.pse"
    pse.write_bytes(b"synthetic")
    initialized = initialize_project(
        project_root=tmp_path / "demo",
        target=pse,
        stop_after_stage=2,
    )
    text = initialized.config_path.read_text(encoding="utf-8")
    initialized.config_path.write_text(
        text.replace("stop_after_stage: 2", "stop_after_stage: 3"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="Stage 03"):
        validate_run_configuration(initialized.config_path)


def test_pse_stage02_pipeline_dispatches_through_shared_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pse = tmp_path / "target.pse"
    pse.write_bytes(b"synthetic")
    initialized = initialize_project(
        project_root=tmp_path / "demo",
        target=pse,
        stop_after_stage=2,
    )
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        f"""
schema_version: "0.1"
profile_id: test
runs_root: {(tmp_path / "runs").resolve()}
backends:
  pymol_pse:
    python: /fake/pymol/python
  scannet_epitope:
    python: /fake/scannet/python
    repository_root: /fake/scannet/repository
    execution_device: cpu
""".lstrip(),
        encoding="utf-8",
    )
    passed = DiagnosticReport(
        ok=True,
        profile_id="test",
        profile_sha256="a" * 64,
        checks=(),
    )
    monkeypatch.setattr(
        "easydesign.orchestration.application.diagnose_runtime",
        lambda **_: passed,
    )
    monkeypatch.setattr(
        "easydesign.orchestration.application.resolve_code_identity",
        lambda **_: CodeIdentity(
            version="0.1.0.dev1",
            source=CodeIdentitySource.INSTALLED_PACKAGE,
            dirty=False,
            content_sha256="b" * 64,
        ),
    )
    fake_pymol = object()
    fake_scannet = object()
    monkeypatch.setattr(
        "easydesign.orchestration.application._pymol_adapter",
        lambda _: fake_pymol,
    )
    monkeypatch.setattr(
        "easydesign.orchestration.application._scannet_adapter",
        lambda _: fake_scannet,
    )
    run_root = tmp_path / "runs/demo/run-001"
    prepared = SimpleNamespace(workspace=SimpleNamespace(run_root=run_root))
    captured: dict[str, object] = {}

    def fake_initialize(**kwargs: object) -> object:
        captured["request_writer"] = kwargs["request_writer"]
        return prepared

    monkeypatch.setattr(
        "easydesign.orchestration.application.initialize_pse_run",
        fake_initialize,
    )
    monkeypatch.setattr(
        "easydesign.orchestration.application.execute_pse_import",
        lambda **_: SimpleNamespace(
            prepared=prepared,
            run_manifest=run_root / "manifests/run-manifest.v0002.json",
            target_viewer=SimpleNamespace(status="succeeded"),
        ),
    )

    def fake_stage02(**kwargs: object) -> object:
        captured["scannet_adapter"] = kwargs["adapter"]
        return SimpleNamespace(
            run_manifest=run_root / "manifests/run-manifest.v0003.json"
        )

    monkeypatch.setattr(
        "easydesign.orchestration.application.execute_stage02_comparison",
        fake_stage02,
    )

    outcome = execute_pipeline(
        initialized.config_path,
        profile_path=profile,
        run_id="run-001",
    )

    assert outcome.status == "succeeded"
    assert outcome.run_manifest == run_root / "manifests/run-manifest.v0003.json"
    assert captured == {
        "request_writer": fake_pymol,
        "scannet_adapter": fake_scannet,
    }


def test_runs_list_marks_legacy_entry_unavailable_without_scanning(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    legacy = runs / "apoe/legacy-run"
    legacy.mkdir(parents=True)
    upsert_run_index_entries(
        runs,
        (
            RunIndexEntry(
                category="project-run",
                path="apoe/legacy-run",
                layout_version="legacy-0",
                status="succeeded",
                project_id="apoe",
                run_id="legacy-run",
            ),
        ),
        generated_at=datetime(2026, 7, 25, tzinfo=UTC),
    )

    summaries = list_runs(runs)

    assert len(summaries) == 1
    assert summaries[0].integrity_status == "unavailable"
    assert summaries[0].manifest_revision == 0
    assert summaries[0].integrity_message is not None
