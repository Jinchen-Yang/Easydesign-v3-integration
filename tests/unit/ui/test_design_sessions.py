from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from easydesign.core import (
    ArtifactRef,
    Attempt,
    CodeIdentity,
    CodeIdentitySource,
    EvidenceStatus,
    ExecutionStatus,
    RunManifest,
    StageId,
    StageManifest,
    dump_model,
    load_model,
)
from easydesign.orchestration import (
    RunIndex,
    RunIndexEntry,
    archive_project,
    initialize_project,
    list_project_catalog,
    materialize_continuation_config,
    replace_run_index_entries,
    restore_project,
    stage_form_definition,
    upsert_run_index_entries,
)
from easydesign.orchestration.config import LoadedPseRunConfig, load_run_config
from easydesign.orchestration.workspace import initialize_run_workspace
from easydesign.ui import create_ui_app
from easydesign.ui.sessions import DesignSessionStore


def test_design_session_tracks_immutable_config_revisions(tmp_path: Path) -> None:
    store = DesignSessionStore(tmp_path / "sessions")
    session = store.create(
        project_id="target-alpha",
        design_mode="stepwise",
        execution_mode="review-gated",
        created_at=datetime(2026, 7, 27, 8, 0, tzinfo=UTC),
    )
    config = tmp_path / "easydesign.yaml"
    config.write_text('schema_version: "0.7"\n', encoding="utf-8")

    revised = store.add_config_revision(
        session.session_id,
        stage_number=1,
        config_path=config,
        updated_at=datetime(2026, 7, 27, 8, 1, tzinfo=UTC),
    )

    assert revised.current_stage == 1
    assert revised.config_revisions[0].relative_path == (
        "config-revisions/stage01-rev0001.yaml"
    )
    assert (
        tmp_path
        / "sessions"
        / session.session_id
        / revised.config_revisions[0].relative_path
    ).read_text(encoding="utf-8") == config.read_text(encoding="utf-8")


def test_stage_forms_expose_all_seven_stages_without_stage01_input() -> None:
    definitions = [stage_form_definition(number) for number in range(1, 8)]

    assert [item["stage_number"] for item in definitions] == list(range(1, 8))
    assert "source_types" in definitions[0]["defaults"]
    assert definitions[1]["defaults"]["available_modes"] == [
        "automatic",
        "user-provided",
    ]
    assert definitions[6]["defaults"]["final_filter_profile"] == (
        "nanobody-final-v1.5"
    )


def test_deterministic_self_test_completes_seven_stages_and_stays_hidden(
    tmp_path: Path,
) -> None:
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "jobs",
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/self-tests",
            json={"mode": "deterministic-seven-stage", "confirmed": True},
        )
        assert response.status_code == 200
        record = response.json()
        assert record["engineering_status"] == "passed"
        assert record["stage_statuses"] == {
            f"stage{number:02d}": "passed" for number in range(1, 8)
        }
        assert client.get("/api/v1/projects").json()["projects"] == []
        catalog = client.get(
            "/api/v1/project-catalog?include_developer_smoke=true"
        ).json()["entries"]
        assert catalog[0]["category"] == "developer-smoke-run"


def test_project_archive_and_restore_move_index_paths_without_changing_run(
    tmp_path: Path,
) -> None:
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "jobs",
    )
    with TestClient(app) as client:
        record = client.post(
            "/api/v1/self-tests",
            json={"mode": "deterministic-seven-stage", "confirmed": True},
        ).json()
    runs_root = tmp_path / "runs"
    index = load_model(runs_root / "run-index.json", RunIndex)
    project_entry = index.entries[0].model_copy(update={"category": "project-run"})
    assert project_entry.run_id is not None
    replace_run_index_entries(
        runs_root,
        (project_entry,),
        generated_at=datetime(2026, 7, 27, 9, 0, tzinfo=UTC),
    )
    before_latest = (
        runs_root
        / record["run_key"]
        / "manifests"
        / "LATEST"
    ).read_text(encoding="utf-8")

    archived = archive_project(runs_root, "developer-self-test")
    assert archived.category == "archived-project-run"
    assert list_project_catalog(runs_root, include_archived=True)[0].category == (
        "archived-project-run"
    )
    restored = restore_project(runs_root, "developer-self-test")
    assert restored.category == "project-run"
    restored_root = runs_root / "developer-self-test" / project_entry.run_id
    assert (restored_root / "manifests" / "LATEST").read_text(
        encoding="utf-8"
    ) == before_latest


def test_project_archive_preserves_legacy_layout_without_manifest(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "runs"
    legacy_root = runs_root / "legacy-target" / "legacy-run"
    evidence = legacy_root / "01-target-preparation" / "attempts" / "README.txt"
    evidence.parent.mkdir(parents=True)
    evidence.write_text("historical evidence\n", encoding="utf-8")
    replace_run_index_entries(
        runs_root,
        (
            RunIndexEntry(
                category="project-run",
                path="legacy-target/legacy-run",
                layout_version="legacy-0",
                status="stage01-succeeded",
                project_id="legacy-target",
                run_id="legacy-run",
            ),
        ),
        generated_at=datetime(2026, 7, 27, 9, 0, tzinfo=UTC),
    )

    archived = archive_project(runs_root, "legacy-target")

    archived_evidence = (
        runs_root
        / "_archive"
        / "legacy-target"
        / "legacy-run"
        / evidence.relative_to(legacy_root)
    )
    assert archived.category == "archived-project-run"
    assert archived_evidence.read_text(encoding="utf-8") == "historical evidence\n"
    assert not legacy_root.exists()

    restored = restore_project(runs_root, "legacy-target")

    assert restored.category == "project-run"
    assert evidence.read_text(encoding="utf-8") == "historical evidence\n"


def test_stage02_continuation_rebases_frozen_local_input(
    tmp_path: Path,
) -> None:
    pse = tmp_path / "source" / "target.pse"
    pse.parent.mkdir()
    pse.write_bytes(b"trusted-pse-fixture")
    initialized = initialize_project(
        project_root=tmp_path / "source-project",
        target=pse,
        stop_after_stage=1,
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
        run_id="stage01-source",
    )
    output = tmp_path / "continuation-project" / "stage02.yaml"

    materialize_continuation_config(
        source_run_root=prepared.workspace.run_root,
        destination=output,
        stage_number=2,
        continue_after_stage=1,
        execution_mode="review-gated",
        options={
            "mode": "user-provided",
            "regions": [{"id": "A", "label_seq_ids": [1, 2]}],
        },
    )

    loaded = load_run_config(output)
    assert isinstance(loaded, LoadedPseRunConfig)
    assert loaded.source_path.read_bytes() == pse.read_bytes()
    assert loaded.source_path.is_relative_to(output.parent)


def _region_editor_run(runs_root: Path) -> Path:
    root = runs_root / "colored-target" / "run-001"
    root.mkdir(parents=True)
    config_path = root / "config-snapshot" / "easydesign.yaml"
    config_path.parent.mkdir()
    config_path.write_text('schema_version: "0.7"\n', encoding="utf-8")
    config = ArtifactRef.from_file(
        run_root=root,
        relative_path="config-snapshot/easydesign.yaml",
        artifact_id="run-config",
        role="user-config-snapshot",
        file_format="yaml",
    )

    def output(
        stage: StageId,
        artifact_id: str,
        filename: str,
        content: str,
        file_format: str,
    ) -> ArtifactRef:
        relative = f"{stage}/attempt-0001/artifacts/{filename}"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ArtifactRef.from_file(
            run_root=root,
            relative_path=relative,
            artifact_id=artifact_id,
            role=artifact_id,
            file_format=file_format,
            producer_stage=str(stage),
            producer_attempt="attempt-0001",
        )

    target = output(
        StageId.TARGET_PREPARATION,
        "target-structure",
        "target.cif",
        "data_target\n#\n",
        "cif",
    )
    mapping = output(
        StageId.TARGET_PREPARATION,
        "residue-mapping",
        "residue-mapping.json",
        (
            '{"entries":['
            '{"label_seq_id":1,"sequence_index":1,"amino_acid":"A",'
            '"source_author_chain_id":"X","source_author_residue_id":"10"},'
            '{"label_seq_id":2,"sequence_index":2,"amino_acid":"C",'
            '"source_author_chain_id":"X","source_author_residue_id":"11"}]}'
        ),
        "json",
    )
    bundle = output(
        StageId.TARGET_PREPARATION,
        "target-bundle",
        "target-bundle.json",
        '{"target_id":"colored-target"}',
        "json",
    )
    annotations = output(
        StageId.TARGET_PREPARATION,
        "source-annotations",
        "source-annotations.json",
        (
            '{"interpretation":"uninterpreted annotation","residues":['
            '{"label_seq_id":1,"ca_color_hex":"#FF0000"},'
            '{"label_seq_id":2,"ca_color_hex":"#00FF00"}]}'
        ),
        "json",
    )
    attempt = Attempt(
        attempt_id="attempt-0001",
        status=ExecutionStatus.SUCCEEDED,
        created_at=datetime(2026, 7, 27, 10, 0, tzinfo=UTC),
        started_at=datetime(2026, 7, 27, 10, 0, tzinfo=UTC),
        ended_at=datetime(2026, 7, 27, 10, 0, tzinfo=UTC),
        backend_name="fixture",
        backend_version="1",
        executor_name="fixture",
    )
    stage01 = StageManifest(
        stage_id=StageId.TARGET_PREPARATION,
        contract_version="0.4",
        status=ExecutionStatus.SUCCEEDED,
        created_at=datetime(2026, 7, 27, 10, 0, tzinfo=UTC),
        completed_at=datetime(2026, 7, 27, 10, 0, tzinfo=UTC),
        output_artifacts=(target, mapping, bundle, annotations),
        attempts=(attempt,),
        selected_attempt_id="attempt-0001",
    )
    stage01_path = root / "01-target-preparation/stage-manifest.json"
    dump_model(stage01, stage01_path)
    stage01_ref = ArtifactRef.from_file(
        run_root=root,
        relative_path=stage01_path.relative_to(root).as_posix(),
        artifact_id="stage-01-manifest",
        role="stage-manifest",
        file_format="json",
        producer_stage=str(StageId.TARGET_PREPARATION),
        producer_attempt="attempt-0001",
    )
    hotspots = output(
        StageId.HOTSPOT_DISCOVERY,
        "hotspots",
        "hotspots.yaml",
        (
            "region_source:\n  type: manual-residue-list\n"
            "hotspot_sets:\n  - id: B\n    label_seq_ids: [2]\n"
        ),
        "yaml",
    )
    stage02 = StageManifest(
        stage_id=StageId.HOTSPOT_DISCOVERY,
        contract_version="0.3",
        status=ExecutionStatus.SUCCEEDED,
        created_at=datetime(2026, 7, 27, 10, 1, tzinfo=UTC),
        completed_at=datetime(2026, 7, 27, 10, 1, tzinfo=UTC),
        output_artifacts=(hotspots,),
        attempts=(attempt,),
        selected_attempt_id="attempt-0001",
    )
    stage02_path = root / "02-hotspot-discovery/stage-manifest.json"
    dump_model(stage02, stage02_path)
    stage02_ref = ArtifactRef.from_file(
        run_root=root,
        relative_path=stage02_path.relative_to(root).as_posix(),
        artifact_id="stage-02-manifest",
        role="stage-manifest",
        file_format="json",
        producer_stage=str(StageId.HOTSPOT_DISCOVERY),
        producer_attempt="attempt-0001",
    )
    run = RunManifest(
        schema_version="1.0",
        revision=1,
        project_id="colored-target",
        run_id="run-001",
        easydesign_version="0.1.0.dev13",
        code_commit="abcdef1",
        status=ExecutionStatus.SUCCEEDED,
        evidence_status=EvidenceStatus.IMPLEMENTED,
        created_at=datetime(2026, 7, 27, 10, 0, tzinfo=UTC),
        updated_at=datetime(2026, 7, 27, 10, 2, tzinfo=UTC),
        completed_at=datetime(2026, 7, 27, 10, 2, tzinfo=UTC),
        config_snapshot=config,
        stage_manifest_refs=(stage01_ref, stage02_ref),
    )
    manifest = root / "manifests/run-manifest.v0001.json"
    dump_model(run, manifest)
    (root / "manifests/LATEST").write_text(f"{manifest.name}\n", encoding="utf-8")
    upsert_run_index_entries(
        runs_root,
        (
            RunIndexEntry(
                category="project-run",
                path="colored-target/run-001",
                layout_version="1",
                status="succeeded",
                project_id="colored-target",
                run_id="run-001",
            ),
        ),
        generated_at=datetime(2026, 7, 27, 10, 3, tzinfo=UTC),
    )
    return root


def test_region_editor_keeps_source_color_and_current_region_as_separate_layers(
    tmp_path: Path,
) -> None:
    run_root = _region_editor_run(tmp_path / "runs")
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "jobs",
    )
    run_key = app.state.easydesign.registry.register(run_root)
    with TestClient(app) as client:
        response = client.get(f"/api/v1/runs/{run_key}/regions/editor")
    assert response.status_code == 200
    projection = response.json()
    assert projection["residues"][0]["source_color"] == "#FF0000"
    assert projection["residues"][0]["current_region"] is None
    assert projection["residues"][1]["source_color"] is None
    assert projection["residues"][1]["current_region"] == "B"
