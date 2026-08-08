from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from easydesign.cli import main
from easydesign.core import (
    ArtifactRef,
    Attempt,
    CodeIdentity,
    CodeIdentitySource,
    ConfigurationError,
    ExecutionStatus,
    StageId,
    StageManifest,
    dump_model,
)
from easydesign.orchestration import (
    DiagnosticCheck,
    DiagnosticReport,
    DiagnosticStatus,
    diagnose_runtime,
    execute_pipeline,
    initialize_project,
    initialize_runtime_profile,
    list_runs,
    validate_run_configuration,
)
from easydesign.orchestration.application import (
    PROTENIX_V2_CHECKPOINT_SHA256,
    _prepared_existing_run,
    _probe_protenix,
    _required_backends,
)
from easydesign.orchestration.config import LoadedSequenceRunConfig, load_run_config
from easydesign.orchestration.profile import ProtenixV2Runtime
from easydesign.orchestration.workspace import (
    RunIndexEntry,
    initialize_run_workspace,
    upsert_run_index_entries,
)


@pytest.fixture(autouse=True)
def _declare_test_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        "\n".join(
            (
                'schema_version: "0.1"',
                "workspace_id: test-workspace",
                "runtime_root: runtime",
                "projects_root: projects",
                "runs_root: runs",
                "archives_root: archives",
                "",
            )
        ),
        encoding="utf-8",
    )
    repository = Path(__file__).resolve().parents[3]
    git_config = tmp_path / "runtime" / "state" / "git" / "test.config"
    git_config.parent.mkdir(parents=True, exist_ok=True)
    git_config.write_text(
        f"[safe]\n\tdirectory = {repository}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(git_config))
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))


def _project_and_profile(tmp_path: Path) -> tuple[Path, Path]:
    fasta = tmp_path / "target.fasta"
    fasta.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    initialized = initialize_project(
        project_root=tmp_path / "demo",
        target=fasta,
    )
    profile = initialize_runtime_profile(
        tmp_path / "runtime" / "profile.yaml",
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

    assert plan.profile_id == "workspace-local"
    assert plan.required_backends == ("protenix-v2",)
    assert plan.runs_root.name == "runs"
    assert not (plan.runs_root / "demo").exists()


def test_stage01_openfold3_is_explicit_and_does_not_change_default(
    tmp_path: Path,
) -> None:
    fasta = tmp_path / "target.fasta"
    fasta.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    initialized = initialize_project(project_root=tmp_path / "demo", target=fasta)
    payload = yaml.safe_load(initialized.config_path.read_text(encoding="utf-8"))
    assert payload["stage01"]["structure_prediction"]["backend"] == "protenix-v2"
    payload["stage01"]["structure_prediction"]["backend"] = "openfold3-af3-jax"
    initialized.config_path.write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )

    plan = validate_run_configuration(initialized.config_path)

    assert plan.required_backends == ("openfold3-af3-jax",)


def test_full_doctor_fails_when_linked_backends_are_not_configured(
    tmp_path: Path,
) -> None:
    profile = initialize_runtime_profile(
        tmp_path / "runtime" / "profile.yaml",
        runs_root=(tmp_path / "runs").resolve(),
    )

    regular = diagnose_runtime(profile_path=profile)
    full = diagnose_runtime(profile_path=profile, full=True)

    assert regular.ok
    assert not full.ok
    unavailable = {
        check.name: check
        for check in full.checks
        if check.name in {"protenix-v2", "pymol-pse", "scannet-epitope", "boltzgen", "tnp"}
    }
    assert set(unavailable) == {
        "protenix-v2",
        "pymol-pse",
        "scannet-epitope",
        "boltzgen",
        "tnp",
    }
    assert all(check.status is DiagnosticStatus.FAILED for check in unavailable.values())
    assert all("未声明" in check.message for check in unavailable.values())


def test_targeted_runtime_probe_checks_only_requested_backends(tmp_path: Path) -> None:
    profile = initialize_runtime_profile(
        tmp_path / "runtime" / "profile.yaml",
        runs_root=(tmp_path / "runs").resolve(),
    )

    report = diagnose_runtime(
        profile_path=profile,
        backend_ids=("boltzgen", "tnp"),
    )

    failed_backends = {
        check.name for check in report.checks if check.status is DiagnosticStatus.FAILED
    }
    assert failed_backends == {"boltzgen", "tnp"}
    assert not report.ok


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


def test_stage01_decision_continuation_restores_precomputed_msa_snapshot(
    tmp_path: Path,
) -> None:
    sequence = "ACDEFGHIKLMNPQRSTVWY"
    fasta = tmp_path / "target.fasta"
    fasta.write_text(f">target\n{sequence}\n", encoding="utf-8")
    a3m = tmp_path / "target.a3m"
    a3m.write_text(
        f">query\n{sequence}\n>homolog\n{sequence}\n",
        encoding="utf-8",
    )
    initialized = initialize_project(
        project_root=tmp_path / "demo",
        target=fasta,
        precomputed_msa=a3m,
    )
    prepared = initialize_run_workspace(
        config_path=initialized.config_path,
        runs_root=tmp_path / "runs",
        easydesign_version="0.1.0.dev13",
        code_identity=CodeIdentity(
            version="0.1.0.dev13",
            source=CodeIdentitySource.INSTALLED_PACKAGE,
            dirty=False,
            content_sha256="b" * 64,
        ),
        run_id="precomputed-decision",
    )

    restored = _prepared_existing_run(prepared.workspace.run_root)

    assert isinstance(restored.loaded_config, LoadedSequenceRunConfig)
    assert restored.loaded_config.precomputed_msa_path is not None
    assert restored.loaded_config.precomputed_msa_path.read_bytes() == a3m.read_bytes()


def test_sasa_only_stage02_does_not_require_scannet_backend(tmp_path: Path) -> None:
    pse = tmp_path / "target.pse"
    pse.write_bytes(b"synthetic")
    initialized = initialize_project(
        project_root=tmp_path / "demo",
        target=pse,
        stop_after_stage=2,
        stage02_method="sasa",
    )

    plan = validate_run_configuration(initialized.config_path)

    assert plan.required_backends == ("pymol-pse",)


def test_stage06_continuation_only_requires_boltzgen_backend(tmp_path: Path) -> None:
    pse = tmp_path / "target.pse"
    pse.write_bytes(b"synthetic")
    initialized = initialize_project(
        project_root=tmp_path / "demo",
        target=pse,
        stop_after_stage=2,
        stage02_method="sasa",
    )
    payload = yaml.safe_load(initialized.config_path.read_text(encoding="utf-8"))
    payload["workflow"]["stop_after_stage"] = 6
    payload["stage03"] = {}
    payload["stage04"] = {}
    payload["stage05"] = {}
    payload["stage06"] = {
        "scale_profile": "smoke-1000",
        "preauthorized_candidate_limit": 1000,
        "allocation_policy": "equal-across-promoted-v1",
    }
    initialized.config_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    loaded = load_run_config(initialized.config_path)

    assert _required_backends(loaded, start_stage=6) == ("boltzgen",)


def test_cli_project_init_and_status_resume_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fasta = tmp_path / "target.fasta"
    fasta.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    project = tmp_path / "projects/cli-demo"

    assert main(["project", "init", str(project), "--target", str(fasta)]) == 0
    assert main(["project", "status", str(project), "--json"]) == 0
    output = capsys.readouterr().out
    assert "状态: initialized" in output
    assert '"status": "target-not-started"' in output
    assert '"phase": "prepare"' in output


def test_stage03_requires_explicit_config_before_profile_or_workspace(
    tmp_path: Path,
) -> None:
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

    with pytest.raises(ConfigurationError, match="stage03"):
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
        "easydesign.orchestration.application.execute_pse_source",
        lambda *_args, **_kwargs: SimpleNamespace(
            prepared=prepared,
            run_manifest=run_root / "manifests/run-manifest.v0002.json",
            target_viewer=SimpleNamespace(status="succeeded"),
        ),
    )

    def fake_stage02(**kwargs: object) -> object:
        captured["scannet_adapter"] = kwargs["adapter"]
        stage_manifest = run_root / ("02-hotspot-discovery/attempt-0001/stage-manifest.json")
        completed_at = datetime(2026, 7, 28, tzinfo=UTC)
        report = stage_manifest.parent / "artifacts/stage02-report.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("{}\n", encoding="utf-8")
        report_ref = ArtifactRef.from_file(
            run_root=run_root,
            relative_path=report.relative_to(run_root).as_posix(),
            artifact_id="stage02-report",
            role="stage-report",
            file_format="json",
            producer_stage=str(StageId.HOTSPOT_DISCOVERY),
            producer_attempt="attempt-0001",
        )
        attempt = Attempt(
            attempt_id="attempt-0001",
            status=ExecutionStatus.SUCCEEDED,
            created_at=completed_at,
            started_at=completed_at,
            ended_at=completed_at,
            backend_name="test",
            backend_version="1",
            executor_name="test",
        )
        dump_model(
            StageManifest(
                stage_id=StageId.HOTSPOT_DISCOVERY,
                contract_version="0.3",
                status=ExecutionStatus.SUCCEEDED,
                created_at=completed_at,
                completed_at=completed_at,
                output_artifacts=(report_ref,),
                attempts=(attempt,),
                selected_attempt_id=attempt.attempt_id,
            ),
            stage_manifest,
        )
        return SimpleNamespace(
            run_manifest=run_root / "manifests/run-manifest.v0003.json",
            stage_manifest=stage_manifest,
        )

    monkeypatch.setattr(
        "easydesign.orchestration.application.execute_stage02",
        fake_stage02,
    )

    outcome = execute_pipeline(
        initialized.config_path,
        profile_path=profile,
        run_id="run-001",
    )

    assert outcome.status == "awaiting-human-approval"
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


def test_local_structural_only_input_succeeds_with_warning(
    tmp_path: Path,
) -> None:
    pdb = tmp_path / "target.pdb"
    pdb.write_text(
        """ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00 20.00           N
ATOM      2  CA  ALA A   1       1.000   0.000   0.000  1.00 20.00           C
ATOM      3  N   CYS A   2       2.000   0.000   0.000  1.00 20.00           N
ATOM      4  CA  CYS A   2       3.000   0.000   0.000  1.00 20.00           C
END
""",
        encoding="utf-8",
    )
    initialized = initialize_project(
        project_root=tmp_path / "local-structure",
        target=pdb,
    )
    profile = initialize_runtime_profile(
        tmp_path / "runtime" / "profile.yaml",
        runs_root=(tmp_path / "runs").resolve(),
    )

    completed = execute_pipeline(
        initialized.config_path,
        profile_path=profile,
        run_id="local-structure-decision",
    )

    assert completed.status == "succeeded"
    assert completed.run_root is not None
    assert (
        completed.run_root / "01-target-preparation/attempt-0001/artifacts/target-bundle.json"
    ).is_file()
    assert completed.run_manifest is not None
    assert completed.run_manifest.name == "run-manifest.v0002.json"


def test_protenix_doctor_accepts_precomputed_msa_without_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fasta = tmp_path / "target.fasta"
    sequence = "ACDEFGHIKLMNPQRSTVWY"
    fasta.write_text(f">target\n{sequence}\n", encoding="utf-8")
    a3m = tmp_path / "target.a3m"
    a3m.write_text(
        f">query\n{sequence}\n>homolog\n{sequence}\n",
        encoding="utf-8",
    )
    initialized = initialize_project(
        project_root=tmp_path / "precomputed",
        target=fasta,
        precomputed_msa=a3m,
    )
    loaded = load_run_config(initialized.config_path)
    assert isinstance(loaded, LoadedSequenceRunConfig)
    executable = tmp_path / "protenix"
    executable.write_text("", encoding="utf-8")
    model_root = tmp_path / "models"
    checkpoint = model_root / "checkpoint/protenix-v2.pt"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"checkpoint")
    runtime = ProtenixV2Runtime(
        executable=executable,
        model_root=model_root,
        model_checkpoint=checkpoint,
    )
    monkeypatch.setattr(
        "easydesign.orchestration.application.sha256_file",
        lambda _: PROTENIX_V2_CHECKPOINT_SHA256,
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["protenix", "--version"],
            0,
            "protenix, version 2.0.0\n",
            "",
        ),
    )

    assert _probe_protenix(runtime, loaded) == PROTENIX_V2_CHECKPOINT_SHA256
