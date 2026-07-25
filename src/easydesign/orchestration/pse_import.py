"""Stage 01 PSE import 执行、Target Bundle 与 manifest 发布。"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from easydesign.backends.target_sources import (
    PseBackendExecutionError,
    PyMOLPseAdapter,
)
from easydesign.backends.target_sources.remote import (
    ScientificHttpClient,
    uniprot_accession,
)
from easydesign.core import (
    ArtifactRef,
    Attempt,
    ErrorInfo,
    ExecutionStatus,
    RunManifest,
    StageId,
    StageManifest,
    dump_model,
    load_model,
)
from easydesign.reporting import (
    TargetViewerOutcome,
    generate_stage01_target_viewer_nonblocking,
)
from easydesign.stages.s01_target_preparation import (
    BuiltTargetBundle,
    build_imported_pse_target_bundle,
)

from .workspace import (
    PreparedPseRun,
    ResolvedRunConfig,
    RunIndexEntry,
    upsert_run_index_entries,
)

ATTEMPT_ID = "attempt-0001"


@dataclass(frozen=True, slots=True)
class CompletedPseRun:
    prepared: PreparedPseRun
    built_bundle: BuiltTargetBundle
    attempt_manifest: Path
    stage_manifest: Path
    run_manifest: Path
    target_viewer: TargetViewerOutcome


def _exclusive_text(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def _atomic_pointer(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _artifact(
    *,
    run_root: Path,
    path: Path,
    artifact_id: str,
    role: str,
    file_format: str,
) -> ArtifactRef:
    return ArtifactRef.from_file(
        run_root=run_root,
        relative_path=path.relative_to(run_root).as_posix(),
        artifact_id=artifact_id,
        role=role,
        file_format=file_format,
        producer_stage=str(StageId.TARGET_PREPARATION),
        producer_attempt=ATTEMPT_ID,
    )


def _strictly_later(candidate: datetime, previous: datetime) -> datetime:
    return candidate if candidate > previous else previous + timedelta(microseconds=1)


def _publish_run_revision(
    *,
    prepared: PreparedPseRun,
    stage_manifest_path: Path,
    ended_at: datetime,
    succeeded: bool,
) -> Path:
    workspace = prepared.workspace
    current = load_model(workspace.run_manifest, RunManifest)
    stage_ref = _artifact(
        run_root=workspace.run_root,
        path=stage_manifest_path,
        artifact_id="stage-01-manifest",
        role="stage-manifest",
        file_format="json",
    )
    updated = _strictly_later(ended_at, current.updated_at)
    stop_after_stage = prepared.loaded_config.config.workflow.stop_after_stage
    if not succeeded:
        status = ExecutionStatus.FAILED
        completed_at: datetime | None = updated
    elif stop_after_stage == 1:
        status = ExecutionStatus.SUCCEEDED
        completed_at = updated
    else:
        status = ExecutionStatus.RUNNING
        completed_at = None
    next_manifest = current.next_revision(
        updated_at=updated,
        status=status,
        completed_at=completed_at,
        stage_manifest_refs=(stage_ref,),
    )
    path = workspace.run_root / "manifests" / "run-manifest.v0002.json"
    dump_model(next_manifest, path)
    _atomic_pointer(f"{path.name}\n", workspace.latest_manifest_pointer)
    upsert_run_index_entries(
        workspace.runs_root,
        (
            RunIndexEntry(
                category="project-run",
                path=workspace.run_root.relative_to(workspace.runs_root).as_posix(),
                layout_version="1",
                status=str(status),
                project_id=workspace.project_id,
                run_id=workspace.run_id,
                notes=((
                    "Stage 01 PSE import published without prediction or MSA."
                    if succeeded
                    else "Stage 01 PSE import failed; attempt evidence retained."
                ),),
            ),
        ),
        generated_at=updated,
    )
    return path


def execute_pse_import(
    *,
    prepared: PreparedPseRun,
    adapter: PyMOLPseAdapter,
    started_at: datetime | None = None,
) -> CompletedPseRun:
    """执行 PyMOL worker，并发布成功或失败的完整不可变 manifest 链。"""

    workspace = prepared.workspace
    attempt_root = workspace.attempt_root(StageId.TARGET_PREPARATION, ATTEMPT_ID)
    work_dir = attempt_root / "work"
    logs_dir = attempt_root / "logs"
    start = datetime.now(UTC) if started_at is None else started_at
    built: BuiltTargetBundle | None = None
    stdout = ""
    stderr = ""
    failure: Exception | None = None
    error_code = "pse-import-failed"
    backend_version: str | None = None
    try:
        product = adapter.extract(
            request_path=prepared.pse_request,
            run_root=workspace.run_root,
            output_dir=work_dir,
        )
        stdout = product.stdout
        stderr = product.stderr
        backend_version = product.response.pymol_version
        reference_sequence: str | None = None
        reference_start: int | None = None
        identity_report: dict[str, Any] | None = None
        retrieval_records: tuple[dict[str, Any], ...] = ()
        accession = prepared.loaded_config.config.target.identity.uniprot_accession
        if accession is not None:
            retrieval_dir = work_dir / "retrieval"
            retrieval_dir.mkdir(parents=True, exist_ok=False)
            with ScientificHttpClient(
                evidence_dir=retrieval_dir,
                cache_mode=str(
                    prepared.loaded_config.config.workflow.cache_mode
                ),
            ) as client:
                payload = uniprot_accession(client, accession).json()
                if not isinstance(payload, dict):
                    raise ValueError("UniProt accession 响应必须是 mapping")
                try:
                    canonical = str(payload["sequence"]["value"]).upper()
                    resolved_accession = str(payload["primaryAccession"])
                    taxonomy_id = int(payload["organism"]["taxonId"])
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError("UniProt 响应缺少身份或 canonical sequence") from error
                observed = product.response.sequence
                positions = [
                    index + 1
                    for index in range(len(canonical))
                    if canonical.startswith(observed, index)
                ]
                if len(positions) != 1:
                    raise ValueError(
                        "PSE observed sequence 必须与 UniProt canonical sequence "
                        f"形成唯一精确子序列映射: matches={len(positions)}"
                    )
                reference_sequence = canonical
                reference_start = positions[0]
                identity_report = {
                    "schema_version": "0.1",
                    "status": "resolved",
                    "identity_status": "resolved",
                    "identity_resolution": "explicit-accession-exact-subsequence",
                    "accession": resolved_accession,
                    "taxonomy_id": taxonomy_id,
                    "input_sequence_reference_start": reference_start,
                    "input_sequence_reference_end": (
                        reference_start + len(observed) - 1
                    ),
                }
                retrieval_records = tuple(
                    record.model_dump(mode="json") for record in client.records
                )
        built = build_imported_pse_target_bundle(
            run_root=workspace.run_root,
            attempt_id=ATTEMPT_ID,
            target_id=prepared.loaded_config.config.target.target_id,
            source_label=workspace.input_snapshot.name,
            product=product,
            reference_sequence=reference_sequence,
            reference_start=reference_start,
            identity_report=identity_report,
            retrieval_records=retrieval_records,
        )
    except PseBackendExecutionError as error:
        failure = error
        error_code = error.error_code
        stdout = error.stdout
        stderr = error.stderr
    except Exception as error:
        failure = error

    ended = _strictly_later(datetime.now(UTC), start)
    stdout_path = _exclusive_text(stdout, logs_dir / "stdout.log")
    stderr_path = _exclusive_text(stderr, logs_dir / "stderr.log")
    log_refs = (
        _artifact(
            run_root=workspace.run_root,
            path=stdout_path,
            artifact_id="pymol-stdout",
            role="backend-log",
            file_format="text",
        ),
        _artifact(
            run_root=workspace.run_root,
            path=stderr_path,
            artifact_id="pymol-stderr",
            role="backend-log",
            file_format="text",
        ),
    )
    if failure is None:
        assert built is not None
        attempt = Attempt(
            attempt_id=ATTEMPT_ID,
            status=ExecutionStatus.SUCCEEDED,
            created_at=start,
            started_at=start,
            ended_at=ended,
            backend_name=adapter.backend_name,
            backend_version=backend_version,
            executor_name="local-subprocess",
            log_artifacts=log_refs,
        )
    else:
        attempt = Attempt(
            attempt_id=ATTEMPT_ID,
            status=ExecutionStatus.FAILED,
            created_at=start,
            started_at=start,
            ended_at=ended,
            backend_name=adapter.backend_name,
            backend_version=backend_version,
            executor_name="local-subprocess",
            log_artifacts=log_refs,
            error=ErrorInfo(
                code=error_code,
                message=str(failure)[:4096] or type(failure).__name__,
                retryable=isinstance(failure, PseBackendExecutionError),
            ),
        )
    attempt_manifest = attempt_root / "attempt-manifest.json"
    dump_model(attempt, attempt_manifest)

    resolved = load_model(workspace.resolved_config, ResolvedRunConfig)
    input_artifacts = (resolved.input_snapshot,)
    if built is None:
        output_artifacts: tuple[ArtifactRef, ...] = ()
        selected_attempt_id = None
        stage_status = ExecutionStatus.FAILED
    else:
        bundle = built.bundle
        assert bundle.source_annotations is not None
        output_artifacts = (
            bundle.target_structure,
            bundle.sequence,
            bundle.residue_mapping,
            bundle.quality_report,
            bundle.provenance,
            bundle.source_annotations,
            built.bundle_artifact,
        ) + tuple(
            artifact
            for artifact in (
                bundle.reference_sequence,
                bundle.residue_mapping_tsv,
                bundle.identity_report,
                bundle.scope_report,
                bundle.structure_candidates,
                bundle.structure_candidates_tsv,
                bundle.retrieval_manifest,
                bundle.target_pdb,
            )
            if artifact is not None
        )
        selected_attempt_id = ATTEMPT_ID
        stage_status = ExecutionStatus.SUCCEEDED
    stage = StageManifest(
        stage_id=StageId.TARGET_PREPARATION,
        contract_version="0.4",
        status=stage_status,
        created_at=start,
        completed_at=ended,
        input_artifacts=input_artifacts,
        output_artifacts=output_artifacts,
        attempts=(attempt,),
        selected_attempt_id=selected_attempt_id,
        warnings=(
            ("PyMOL colors are preserved as uninterpreted source annotations.",)
            if built is not None
            else ()
        ),
    )
    stage_manifest = (
        workspace.stage_root(StageId.TARGET_PREPARATION)
        / "stage-manifest.v0001.json"
    )
    dump_model(stage, stage_manifest)
    run_manifest = _publish_run_revision(
        prepared=prepared,
        stage_manifest_path=stage_manifest,
        ended_at=ended,
        succeeded=built is not None,
    )
    if failure is not None:
        raise failure
    assert built is not None
    target_viewer = generate_stage01_target_viewer_nonblocking(
        prepared.workspace.run_root
    )
    return CompletedPseRun(
        prepared=prepared,
        built_bundle=built,
        attempt_manifest=attempt_manifest,
        stage_manifest=stage_manifest,
        run_manifest=run_manifest,
        target_viewer=target_viewer,
    )
