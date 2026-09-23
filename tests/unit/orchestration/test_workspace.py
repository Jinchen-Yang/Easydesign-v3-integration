from __future__ import annotations

import hashlib
import json
import multiprocessing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from easydesign.backends.structure_prediction import ProtenixV2Adapter
from easydesign.backends.target_sources import PyMOLPseAdapter
from easydesign.core import (
    CodeIdentity,
    CodeIdentitySource,
    ManifestStateError,
    RunManifest,
    RuntimeProfileRef,
    StageId,
    load_model,
)
from easydesign.orchestration import (
    ResolvedRunConfig,
    RunIndex,
    RunIndexEntry,
    initialize_pse_run,
    initialize_sequence_run,
)
from easydesign.orchestration.task_tracking import load_latest_runtime_model
from easydesign.orchestration.workspace import ProjectNavigation, upsert_run_index_entries

ROOT = Path(__file__).resolve().parents[3]
APOE_CONFIG = ROOT / "examples/stage01-apoe/easydesign.yaml"


def adapter() -> ProtenixV2Adapter:
    return ProtenixV2Adapter(
        executable=Path("/envs/protenix-v2/bin/protenix"),
        model_root=Path("/models/protenix"),
    )


def _concurrent_run_index_writer(
    runs_root: Path,
    writer_number: int,
    ready: multiprocessing.synchronize.Event,
    start: multiprocessing.synchronize.Event,
) -> None:
    ready.set()
    if not start.wait(timeout=10):
        raise RuntimeError("concurrent run-index test did not start")
    slug = f"writer-{writer_number}"
    upsert_run_index_entries(
        runs_root,
        (
            RunIndexEntry(
                category="project-run",
                path=f"{slug}/fresh",
                layout_version="1",
                status="pending",
                project_id=slug,
                run_id="fresh",
            ),
        ),
        generated_at=datetime(2026, 9, 23, 8, writer_number, tzinfo=UTC),
    )


def test_run_index_preserves_all_eight_concurrent_writers(tmp_path: Path) -> None:
    ctx = multiprocessing.get_context("spawn")
    runs_root = tmp_path / "runs"
    start = ctx.Event()
    ready = [ctx.Event() for _ in range(8)]
    processes = [
        ctx.Process(
            target=_concurrent_run_index_writer,
            args=(runs_root, writer_number, ready[writer_number], start),
        )
        for writer_number in range(8)
    ]
    for process in processes:
        process.start()
    assert all(event.wait(timeout=20) for event in ready)
    start.set()
    for process in processes:
        process.join(timeout=30)
        assert not process.is_alive()
        assert process.exitcode == 0

    index = load_latest_runtime_model(runs_root / "run-index.json", RunIndex)
    assert {entry.path for entry in index.entries} == {
        f"writer-{writer_number}/fresh" for writer_number in range(8)
    }
    for writer_number in range(8):
        navigation = load_latest_runtime_model(
            runs_root / f"writer-{writer_number}/PROJECT.json",
            ProjectNavigation,
        )
        assert navigation.project_id == f"writer-{writer_number}"


def test_initialize_sequence_run_creates_one_shallow_workspace(tmp_path: Path) -> None:
    prepared = initialize_sequence_run(
        config_path=APOE_CONFIG,
        runs_root=tmp_path / "runs",
        input_writer=adapter(),
        code_commit="d1b46f9",
        easydesign_version="0.1.0.dev0",
        run_id="20260724-001",
        created_at=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
    )
    workspace = prepared.workspace

    assert workspace.run_root == tmp_path / "runs/apoe/20260724-001"
    assert workspace.config_snapshot.is_file()
    assert workspace.input_snapshot.is_file()
    assert workspace.resolved_config.is_file()
    assert workspace.stage_root(StageId.TARGET_PREPARATION).is_dir()
    assert all(
        not workspace.stage_root(stage).exists()
        for stage in StageId
        if stage is not StageId.TARGET_PREPARATION
    )
    assert not (workspace.run_root / "results").exists()
    assert prepared.protenix_input == (
        workspace.run_root
        / "01-target-preparation/attempt-0001/inputs/protenix-input.json"
    )
    assert prepared.protenix_input.is_file()
    assert not (workspace.run_root / "01-target-preparation/attempts").exists()

    protenix = json.loads(prepared.protenix_input.read_text(encoding="utf-8"))
    assert protenix[0]["name"] == "apoe4-fragment-41-183"
    assert len(protenix[0]["sequences"][0]["proteinChain"]["sequence"]) == 143

    manifest = load_model(workspace.run_manifest, RunManifest)
    assert manifest.project_id == "apoe"
    assert manifest.run_id == "20260724-001"
    assert manifest.config_snapshot.verify(workspace.run_root) == workspace.config_snapshot
    resolved = load_model(workspace.resolved_config, ResolvedRunConfig)
    assert resolved.schema_version == "0.9"
    assert resolved.prediction_request is not None
    assert resolved.prediction_request.msa_mode == "remote"
    assert len(resolved.msa_execution_plan) == 1
    assert resolved.msa_execution_plan[0].endpoint == "https://api.colabfold.com"

    index = load_model(tmp_path / "runs/run-index.json", RunIndex)
    assert index.entries[0].path == "apoe/20260724-001"
    navigation = json.loads(
        (tmp_path / "runs/apoe/PROJECT.json").read_text(encoding="utf-8")
    )
    assert navigation["project_id"] == "apoe"
    assert navigation["runs"][0]["run_id"] == "20260724-001"
    assert not (tmp_path / "runs/apoe/PRIMARY").exists()


def test_initialize_sequence_run_refuses_existing_run(tmp_path: Path) -> None:
    kwargs = {
        "config_path": APOE_CONFIG,
        "runs_root": tmp_path / "runs",
        "input_writer": adapter(),
        "code_commit": "d1b46f9",
        "easydesign_version": "0.1.0.dev0",
        "run_id": "20260724-001",
        "created_at": datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
    }
    initialize_sequence_run(**kwargs)

    with pytest.raises(ManifestStateError, match="不能覆盖"):
        initialize_sequence_run(**kwargs)


def test_stage01_snapshots_independent_paired_msa_and_template(
    tmp_path: Path,
) -> None:
    source = tmp_path / "target.fasta"
    source.write_text(">target\nACDEFGHIK\n", encoding="utf-8")
    paired = tmp_path / "paired.a3m"
    paired.write_text(">query\nACDEFGHIK\n", encoding="utf-8")
    templates = tmp_path / "templates.json"
    templates.write_text("[]\n", encoding="utf-8")
    config = tmp_path / "easydesign.yaml"
    config.write_text(
        f"""
schema_version: "0.9"
project_id: explicit-features
workflow: {{stop_after_stage: 1}}
stage01:
  target:
    id: target
    source: {{type: local-file, path: target.fasta, format: fasta}}
    scope: {{type: full-sequence}}
  structure_prediction:
    backend: protenix-v2
    target_msa: {{mode: disabled}}
    target_paired_msa:
      mode: precomputed
      path: paired.a3m
      sha256: {hashlib.sha256(paired.read_bytes()).hexdigest()}
    target_templates:
      mode: precomputed
      data_path: templates.json
      data_sha256: {hashlib.sha256(templates.read_bytes()).hexdigest()}
stage02: null
stage03: null
stage04: null
stage05: null
stage06: null
stage07: null
""".lstrip(),
        encoding="utf-8",
    )

    prepared = initialize_sequence_run(
        config_path=config,
        runs_root=tmp_path / "runs",
        input_writer=adapter(),
        code_commit="d1b46f9",
        easydesign_version="0.1.0.dev0",
        run_id="explicit-features",
    )
    resolved = load_model(prepared.workspace.resolved_config, ResolvedRunConfig)

    assert resolved.precomputed_msa_snapshot is None
    assert resolved.precomputed_paired_msa_snapshot is not None
    assert resolved.precomputed_template_snapshot is not None
    assert (
        resolved.precomputed_paired_msa_snapshot.verify(prepared.workspace.run_root).read_bytes()
        == paired.read_bytes()
    )
    assert (
        resolved.precomputed_template_snapshot.verify(prepared.workspace.run_root).read_bytes()
        == templates.read_bytes()
    )
    assert resolved.prediction_request is not None
    assert resolved.prediction_request.target_paired_msa_path is not None
    assert str(resolved.prediction_request.target_paired_msa_path).startswith(
        str(prepared.workspace.run_root)
    )
    payload = json.loads(prepared.protenix_input.read_text(encoding="utf-8"))
    protein = payload[0]["sequences"][0]["proteinChain"]
    assert Path(protein["pairedMsaPath"]).is_relative_to(prepared.workspace.run_root)
    assert Path(protein["templatesPath"]).is_relative_to(prepared.workspace.run_root)


def test_initialize_workspace_uses_manifest_12_for_packaged_execution(
    tmp_path: Path,
) -> None:
    identity = CodeIdentity(
        version="0.1.0.dev1",
        source=CodeIdentitySource.INSTALLED_PACKAGE,
        dirty=False,
        content_sha256="a" * 64,
    )
    profile = RuntimeProfileRef(profile_id="test-local", sha256="b" * 64)
    prepared = initialize_sequence_run(
        config_path=APOE_CONFIG,
        runs_root=tmp_path / "runs",
        input_writer=adapter(),
        easydesign_version="0.1.0.dev1",
        code_identity=identity,
        runtime_profile=profile,
        run_id="run-packaged",
        created_at=datetime(2026, 7, 25, 8, 0, tzinfo=UTC),
    )

    manifest = load_model(prepared.workspace.run_manifest, RunManifest)
    resolved = load_model(prepared.workspace.resolved_config, ResolvedRunConfig)
    assert manifest.schema_version == "1.2"
    assert manifest.code_identity == identity
    assert manifest.runtime_profile == profile
    assert resolved.schema_version == "0.9"
    assert resolved.runtime_profile == profile


def test_initialize_pse_run_creates_request_without_prediction(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    pse = input_dir / "target.pse"
    pse.write_bytes(b"synthetic-pse")
    config = input_dir / "easydesign.yaml"
    config.write_text(
        """
schema_version: "0.1"
project_id: demo
target:
  id: demo-pse
  source: target.pse
  format: auto
workflow:
  stop_after_stage: 1
""".lstrip(),
        encoding="utf-8",
    )
    pymol = PyMOLPseAdapter(
        python_executable=Path("/envs/pymol-pse/bin/python")
    )

    prepared = initialize_pse_run(
        config_path=config,
        runs_root=tmp_path / "runs",
        request_writer=pymol,
        code_commit="428e98f",
        easydesign_version="0.1.0.dev0",
        run_id="20260724-002-stage01-pse",
        created_at=datetime(2026, 7, 24, 9, 0, tzinfo=UTC),
    )

    request = json.loads(prepared.pse_request.read_text(encoding="utf-8"))
    assert request["source_relative_path"] == "input-snapshot/target.pse"
    assert request["target_id"] == "demo-pse"
    assert prepared.pse_request.name == "pse-request.json"
    assert not list(prepared.workspace.run_root.rglob("protenix-input.json"))
    resolved = load_model(prepared.workspace.resolved_config, ResolvedRunConfig)
    assert resolved.detected_input_format == "pse"
    assert resolved.target is None
    assert resolved.prediction_request is None
    assert prepared.workspace.latest_manifest_pointer.read_text() == (
        "run-manifest.v0001.json\n"
    )
