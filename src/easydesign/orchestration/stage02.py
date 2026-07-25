"""Stage 02 独立 SASA/ScanNet 执行、对比产物和 manifest 发布。"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from easydesign.backends.annotations import (
    FetchedUniProtRecord,
    UniProtAnnotationAdapter,
)
from easydesign.backends.hotspot import (
    ScanNetBackendError,
    ScanNetEpitopeAdapter,
)
from easydesign.core import (
    ArtifactRef,
    Attempt,
    ErrorInfo,
    ExecutionStatus,
    ManifestStateError,
    RunManifest,
    StageId,
    StageManifest,
    WorkflowState,
    WorkflowStateType,
    dump_model,
    load_model,
    sha256_file,
)
from easydesign.stages.s01_target_preparation import ResidueMapping, TargetBundle
from easydesign.stages.s02_hotspot_discovery import (
    AnnotationStatus,
    ProviderExecutionStatus,
    RecommendedRegionSet,
    RegionMethod,
    RegionParameters,
    RegionReviewStatus,
    SasaParameters,
    Stage02Report,
    build_annotation_report,
    compare_independent_methods,
    load_structure_context,
    run_sasa_surface_diversity,
    run_scannet_region_proposals,
)

from .config import (
    RegionProposalMode,
    Stage02Method,
    UniProtAnnotationMode,
)
from .workspace import (
    ResolvedRunConfig,
    RunIndexEntry,
    upsert_run_index_entries,
)

ATTEMPT_ID = "attempt-0001"


@dataclass(frozen=True, slots=True)
class CompletedStage02Run:
    run_root: Path
    attempt_manifest: Path
    stage_manifest: Path
    run_manifest: Path
    comparison: Path | None
    report: Path


class _FrozenUniProtFetcher:
    """只消费 Stage 01 已冻结响应；不会发出网络请求。"""

    def __init__(self, record: FetchedUniProtRecord) -> None:
        self.record = record

    def fetch(self, accession: str) -> FetchedUniProtRecord:
        if accession != self.record.accession:
            raise ManifestStateError(
                "Stage 01 UniProt snapshot accession 与 Stage 02 请求不一致"
            )
        return self.record


def _frozen_uniprot_fetcher(
    run_root: Path,
    bundle: TargetBundle,
    accession: str,
) -> _FrozenUniProtFetcher | None:
    if bundle.retrieval_manifest is None:
        return None
    manifest_path = bundle.retrieval_manifest.verify(run_root)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ManifestStateError("Stage 01 retrieval-manifest 无法读取") from error
    requests = payload.get("requests")
    if not isinstance(requests, list):
        raise ManifestStateError("Stage 01 retrieval-manifest requests 不是 list")
    suffix = f"/uniprotkb/{accession}.json"
    for request in requests:
        if not isinstance(request, dict):
            continue
        url = request.get("url")
        relative = request.get("run_artifact_path")
        if not isinstance(url, str) or not url.split("?", maxsplit=1)[0].endswith(suffix):
            continue
        if not isinstance(relative, str):
            continue
        path = (run_root / relative).resolve()
        if not path.is_relative_to(run_root) or not path.is_file():
            raise ManifestStateError("Stage 01 UniProt snapshot 路径无效")
        expected_sha = request.get("response_sha256")
        actual_sha = sha256_file(path)
        if expected_sha != actual_sha:
            raise ManifestStateError("Stage 01 UniProt snapshot SHA-256 不一致")
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ManifestStateError("Stage 01 UniProt snapshot 顶层不是 object")
        return _FrozenUniProtFetcher(
            FetchedUniProtRecord(
                accession=accession,
                source_url=url,
                source_sha256=actual_sha,
                payload=raw,
            )
        )
    return None


def _strictly_later(candidate: datetime, previous: datetime) -> datetime:
    return candidate if candidate > previous else previous + timedelta(microseconds=1)


def _exclusive_text(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def _exclusive_copy(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as input_handle, destination.open("xb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle)
    except FileExistsError as error:
        raise ManifestStateError(f"Stage 02 artifact 不可覆盖: {destination}") from error
    return destination


def _atomic_pointer(text: str, path: Path) -> None:
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
        producer_stage=str(StageId.HOTSPOT_DISCOVERY),
        producer_attempt=ATTEMPT_ID,
    )


def _load_current_manifest(run_root: Path) -> tuple[RunManifest, Path]:
    latest = run_root / "manifests" / "LATEST"
    try:
        name = latest.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ManifestStateError(f"无法读取 run manifest LATEST: {latest}") from error
    path = run_root / "manifests" / name
    current = load_model(path, RunManifest)
    if current.status is not ExecutionStatus.RUNNING:
        raise ManifestStateError(
            f"Stage 02 只能继续 running run，实际为 {current.status}; "
            "请用 stop_after_stage: 2 新建完整 run"
        )
    return current, path


def _load_stage01(
    run_root: Path,
    current: RunManifest,
) -> tuple[StageManifest, ArtifactRef, Path]:
    stage_ref = next(
        (
            reference
            for reference in current.stage_manifest_refs
            if reference.producer_stage == str(StageId.TARGET_PREPARATION)
        ),
        None,
    )
    if stage_ref is None:
        raise ManifestStateError("RunManifest 没有声明 Stage 01 manifest")
    stage_path = stage_ref.verify(run_root)
    stage = load_model(stage_path, StageManifest)
    if stage.status is not ExecutionStatus.SUCCEEDED:
        raise ManifestStateError("Stage 01 尚未成功，不能执行 Stage 02")
    bundle_ref = stage.require_output("target-bundle")
    bundle_path = bundle_ref.verify(run_root)
    return stage, bundle_ref, bundle_path


def _pml_selector(region: object) -> str:
    from easydesign.stages.s02_hotspot_discovery import CandidateSurfaceRegion

    assert isinstance(region, CandidateSurfaceRegion)
    terms = []
    for member in region.members:
        insertion = member.insertion_code or ""
        terms.append(
            f"(chain {member.auth_asym_id} and resi {member.auth_seq_id}{insertion})"
        )
    return " or ".join(terms)


def _review_script(
    *,
    target_relative_path: str,
    regions: tuple[object, ...],
    colors: tuple[str, ...],
    object_name: str,
) -> str:
    lines = [
        f"load {target_relative_path}, {object_name}",
        f"hide everything, {object_name}",
        f"show cartoon, {object_name}",
        f"color gray70, {object_name}",
    ]
    for index, (region, color) in enumerate(zip(regions, colors, strict=True), start=1):
        selector = _pml_selector(region)
        selection = f"{object_name}_region_{index}"
        lines.extend(
            [
                f"select {selection}, {object_name} and ({selector})",
                f"color {color}, {selection}",
                f"show sticks, {selection}",
            ]
        )
    lines.extend(["orient", "zoom visible", ""])
    return "\n".join(lines)


def _publish_run_revision(
    *,
    run_root: Path,
    current: RunManifest,
    current_path: Path,
    stage_manifest_path: Path,
    ended_at: datetime,
    succeeded: bool,
) -> Path:
    revision = current.revision + 1
    stage_ref = _artifact(
        run_root=run_root,
        path=stage_manifest_path,
        artifact_id="stage-02-manifest",
        role="stage-manifest",
        file_format="json",
    )
    retained = tuple(
        reference
        for reference in current.stage_manifest_refs
        if reference.producer_stage != str(StageId.HOTSPOT_DISCOVERY)
    )
    updated = _strictly_later(ended_at, current.updated_at)
    workflow_state = (
        WorkflowState(
            state=WorkflowStateType.AWAITING_HUMAN_APPROVAL,
            stage_id=StageId.HOTSPOT_DISCOVERY,
            action="approve-hotspots",
            message=(
                "Stage 02 自动选区已完成；必须导出并人工批准完整区域后，"
                "才能发布 hotspots.yaml。"
            ),
        )
        if succeeded
        else None
    )
    next_manifest = current.next_revision(
        updated_at=updated,
        status=ExecutionStatus.RUNNING,
        completed_at=None,
        stage_manifest_refs=retained + (stage_ref,),
        workflow_state=workflow_state,
    )
    path = run_root / "manifests" / f"run-manifest.v{revision:04d}.json"
    dump_model(next_manifest, path)
    _atomic_pointer(f"{path.name}\n", run_root / "manifests" / "LATEST")
    del current_path
    return path


def execute_stage02_comparison(
    *,
    run_root: Path,
    adapter: ScanNetEpitopeAdapter | None = None,
    annotation_adapter: UniProtAnnotationAdapter | None = None,
    started_at: datetime | None = None,
) -> CompletedStage02Run:
    """运行 YAML 选择的独立方法；任一已选择方法失败时不发布结果。"""

    root = run_root.resolve()
    current, current_path = _load_current_manifest(root)
    stage01, bundle_ref, bundle_path = _load_stage01(root, current)
    resolved = load_model(root / "config-snapshot" / "resolved-config.json", ResolvedRunConfig)
    stage02_config = resolved.user_config.stage02
    if stage02_config is None:
        raise ManifestStateError("resolved config 缺少 Stage 02 配置")
    if stage02_config.mode is not RegionProposalMode.AUTOMATIC:
        raise ManifestStateError(
            f"Stage 02 mode={stage02_config.mode} 尚未实现；禁止回退到 automatic"
        )
    automatic = stage02_config.automatic
    assert automatic is not None
    attempt_root = root / str(StageId.HOTSPOT_DISCOVERY) / ATTEMPT_ID
    if attempt_root.exists():
        raise ManifestStateError(f"Stage 02 attempt 已存在，禁止覆盖: {attempt_root}")
    artifacts = attempt_root / "artifacts"
    work = attempt_root / "work"
    logs = attempt_root / "logs"
    sasa_dir = artifacts / "sasa"
    scannet_dir = artifacts / "scannet-epitope"
    annotation_dir = artifacts / "annotations"
    selected_directories = [work, logs, annotation_dir]
    if Stage02Method.SASA in stage02_config.methods:
        selected_directories.append(sasa_dir)
    if Stage02Method.SCANNET in stage02_config.methods:
        selected_directories.append(scannet_dir)
    for directory in selected_directories:
        directory.mkdir(parents=True, exist_ok=False)

    start = datetime.now(UTC) if started_at is None else started_at
    stdout = ""
    stderr = ""
    backend_version: str | None = None
    failure: Exception | None = None
    error_code = "stage02-comparison-failed"
    output_paths: list[tuple[Path, str, str, str]] = []
    comparison_path: Path | None = None
    report_path = artifacts / "stage02-report.json"
    try:
        bundle, context = load_structure_context(
            run_root=root,
            target_bundle_path=bundle_path,
        )
        mapping = load_model(bundle.residue_mapping.verify(root), ResidueMapping)
        sequence_text = bundle.sequence.verify(root).read_text(encoding="utf-8")
        target_sequence = "".join(
            line.strip()
            for line in sequence_text.splitlines()
            if line.strip() and not line.startswith(">")
        )
        if len(target_sequence) != bundle.sequence_length:
            raise ManifestStateError(
                "Target Bundle sequence artifact 长度与 bundle 不一致"
            )
        annotation_mode = stage02_config.annotations.uniprot
        accession = resolved.user_config.stage01.target.identity.uniprot_accession
        if accession is None and bundle.identity_report is not None:
            identity_payload = json.loads(
                bundle.identity_report.verify(root).read_text(encoding="utf-8")
            )
            if isinstance(identity_payload, dict):
                resolved_accession = identity_payload.get("accession")
                if isinstance(resolved_accession, str):
                    accession = resolved_accession
        if annotation_mode is UniProtAnnotationMode.REQUIRED and accession is None:
            raise ManifestStateError(
                "stage02.annotations.uniprot=required 时必须在 "
                "stage01.target.identity 提供 uniprot_accession"
            )
        requested_accession = (
            accession
            if annotation_mode is not UniProtAnnotationMode.OFF
            else None
        )
        selected_annotation_adapter: Any = annotation_adapter
        if requested_accession is not None and selected_annotation_adapter is None:
            frozen = _frozen_uniprot_fetcher(root, bundle, requested_accession)
            selected_annotation_adapter = (
                frozen if frozen is not None else UniProtAnnotationAdapter()
            )
        annotation_report = build_annotation_report(
            target_sequence=target_sequence,
            residue_mapping=mapping,
            accession=requested_accession,
            fetcher=selected_annotation_adapter,
        )
        if (
            annotation_mode is UniProtAnnotationMode.REQUIRED
            and annotation_report.status is not AnnotationStatus.SUCCEEDED
        ):
            raise ManifestStateError(
                "required UniProt annotation 未成功: "
                f"status={annotation_report.status}, error={annotation_report.error}"
            )
        annotation_path = dump_model(
            annotation_report,
            annotation_dir / "annotation-report.json",
        )
        output_paths.append(
            (
                annotation_path,
                "stage02-annotation-report",
                "scientific-annotation",
                "json",
            )
        )
        region_parameters = RegionParameters(
            requested_region_count=automatic.requested_region_count,
            minimum_region_count=automatic.minimum_region_count,
            target_member_count=automatic.patch.target_member_count,
            minimum_member_count=automatic.patch.minimum_member_count,
            heavy_atom_neighbor_angstrom=automatic.patch.heavy_atom_neighbor_angstrom,
            anchor_neighbor_angstrom=automatic.patch.anchor_neighbor_angstrom,
            compactness_radius_angstrom=automatic.patch.compactness_radius_angstrom,
        )
        sasa_parameters = SasaParameters(
            rsasa_threshold=automatic.sasa.rsasa_threshold,
            relaxed_threshold=automatic.sasa.relaxed_threshold,
            probe_radius_angstrom=automatic.sasa.probe_radius_angstrom,
            sphere_points=automatic.sasa.sphere_points,
            ensemble_consensus_fraction=(
                automatic.sasa.ensemble_consensus_fraction
            ),
        )
        providers: list[ProviderExecutionStatus] = []
        sasa_recommended: RecommendedRegionSet | None = None
        scannet_recommended: RecommendedRegionSet | None = None
        if Stage02Method.SASA in stage02_config.methods:
            sasa_evidence, sasa_pool, sasa_recommended = (
                run_sasa_surface_diversity(
                    context=context,
                    region_parameters=region_parameters,
                    sasa_parameters=sasa_parameters,
                    avoid_label_seq_ids=frozenset(
                        automatic.avoid_label_seq_ids
                    ),
                )
            )
            sasa_evidence = sasa_evidence.model_copy(
                update={"annotation_status": annotation_report.status}
            )
            sasa_evidence_path = dump_model(
                sasa_evidence,
                sasa_dir / "residue-evidence.json",
            )
            sasa_pool_path = dump_model(
                sasa_pool,
                sasa_dir / "candidate-regions.json",
            )
            sasa_recommended_path = dump_model(
                sasa_recommended,
                sasa_dir / "recommended-regions.json",
            )
            sasa_pml = _exclusive_text(
                _review_script(
                    target_relative_path=(
                        "../../../../" + bundle.target_structure.relative_path
                    ),
                    regions=tuple(sasa_recommended.regions),
                    colors=("red", "orange", "yellow")[
                        : len(sasa_recommended.regions)
                    ],
                    object_name="target_sasa",
                ),
                sasa_dir / "review-regions.pml",
            )
            output_paths.extend(
                (
                    (
                        sasa_evidence_path,
                        "sasa-residue-evidence",
                        "residue-evidence",
                        "json",
                    ),
                    (
                        sasa_pool_path,
                        "sasa-candidate-regions",
                        "candidate-region-pool",
                        "json",
                    ),
                    (
                        sasa_recommended_path,
                        "sasa-recommended-regions",
                        "recommended-region-set",
                        "json",
                    ),
                    (
                        sasa_pml,
                        "sasa-review-script",
                        "visual-review-script",
                        "pml",
                    ),
                )
            )
            providers.append(
                ProviderExecutionStatus(
                    method=sasa_recommended.method,
                    status="succeeded",
                    message=(
                        "SASA/geometry independent candidate pool generated "
                        f"from {len(context.model_ids)} coordinate model(s)."
                    ),
                )
            )

        if Stage02Method.SCANNET in stage02_config.methods:
            if len(context.model_ids) != 1:
                raise ManifestStateError(
                    "unsupported_ensemble: ScanNet v0.1 只接受单模型；"
                    "请将 stage02.methods 改为 [sasa]"
                )
            if adapter is None:
                raise ManifestStateError(
                    "配置选择了 ScanNet，但没有提供 ScanNet adapter"
                )
            product = adapter.predict(context=context, work_dir=work / "scannet")
            stdout = product.stdout
            stderr = product.stderr
            backend_version = product.commit
            runtime_probe_path = dump_model(
                product.probe,
                scannet_dir / "runtime-probe.json",
            )
            raw_csv = _exclusive_copy(
                product.raw_csv,
                scannet_dir / "raw-predictions.csv",
            )
            scannet_evidence, scannet_pool, scannet_recommended = (
                run_scannet_region_proposals(
                    context=context,
                    probabilities=product.probabilities,
                    method_version=f"{product.commit}:{adapter.model_name}",
                    region_parameters=region_parameters,
                )
            )
            scannet_evidence = scannet_evidence.model_copy(
                update={"annotation_status": annotation_report.status}
            )
            scannet_evidence_path = dump_model(
                scannet_evidence,
                scannet_dir / "residue-evidence.json",
            )
            scannet_pool_path = dump_model(
                scannet_pool,
                scannet_dir / "candidate-regions.json",
            )
            scannet_recommended_path = dump_model(
                scannet_recommended,
                scannet_dir / "recommended-regions.json",
            )
            scannet_pml = _exclusive_text(
                _review_script(
                    target_relative_path=(
                        "../../../../" + bundle.target_structure.relative_path
                    ),
                    regions=tuple(scannet_recommended.regions),
                    colors=("cyan", "blue", "magenta")[
                        : len(scannet_recommended.regions)
                    ],
                    object_name="target_scannet",
                ),
                scannet_dir / "review-regions.pml",
            )
            output_paths.extend(
                (
                    (
                        runtime_probe_path,
                        "scannet-runtime-probe",
                        "backend-runtime-probe",
                        "json",
                    ),
                    (
                        raw_csv,
                        "scannet-raw-predictions",
                        "backend-raw-output",
                        "csv",
                    ),
                    (
                        scannet_evidence_path,
                        "scannet-residue-evidence",
                        "residue-evidence",
                        "json",
                    ),
                    (
                        scannet_pool_path,
                        "scannet-candidate-regions",
                        "candidate-region-pool",
                        "json",
                    ),
                    (
                        scannet_recommended_path,
                        "scannet-recommended-regions",
                        "recommended-region-set",
                        "json",
                    ),
                    (
                        scannet_pml,
                        "scannet-review-script",
                        "visual-review-script",
                        "pml",
                    ),
                )
            )
            providers.append(
                ProviderExecutionStatus(
                    method=scannet_recommended.method,
                    status="succeeded",
                    message=(
                        "ScanNet epitope no-MSA ran on explicitly requested "
                        f"{product.probe.execution_device.upper()}; independent "
                        "candidate pool generated."
                    ),
                )
            )

        comparison_status = "not-applicable"
        if sasa_recommended is not None and scannet_recommended is not None:
            comparison = compare_independent_methods(
                context=context,
                sasa=sasa_recommended,
                scannet=scannet_recommended,
            )
            comparison_path = dump_model(
                comparison,
                artifacts / "method-comparison.json",
            )
            comparison_pml = _exclusive_text(
                _review_script(
                    target_relative_path=(
                        "../../../" + bundle.target_structure.relative_path
                    ),
                    regions=tuple(sasa_recommended.regions)
                    + tuple(scannet_recommended.regions),
                    colors=(
                        "red",
                        "orange",
                        "yellow",
                        "cyan",
                        "blue",
                        "magenta",
                    )[
                        : len(sasa_recommended.regions)
                        + len(scannet_recommended.regions)
                    ],
                    object_name="target_comparison",
                ),
                artifacts / "review-comparison.pml",
            )
            output_paths.extend(
                (
                    (
                        comparison_path,
                        "method-comparison",
                        "method-comparison",
                        "json",
                    ),
                    (
                        comparison_pml,
                        "comparison-review-script",
                        "visual-review-script",
                        "pml",
                    ),
                )
            )
            comparison_status = "generated"

        annotation_warning = (
            "Scientific annotation was not requested; selection basis is structural-only."
            if annotation_report.status is AnnotationStatus.NOT_REQUESTED
            else (
                f"Scientific annotation status={annotation_report.status}; "
                "raw SASA/ScanNet rankings were not changed."
            )
        )
        report = Stage02Report(
            target_id=bundle.target_id,
            annotation_status=annotation_report.status,
            evidence_level=annotation_report.evidence_level,
            identity_resolution=annotation_report.identity_resolution,
            comparison_status=comparison_status,
            pse_source_annotations_consumed=False,
            fused_ranking_generated=False,
            stage03_handoff=RegionReviewStatus.AWAITING_REGION_SELECTION,
            providers=tuple(providers),
            warnings=(
                annotation_warning,
                "No fused score or default winning method was generated.",
                "Human region selection is required before Stage 03.",
            ),
        )
        dump_model(report, report_path)
        output_paths.append(
            (report_path, "stage02-report", "stage-report", "json")
        )
    except ScanNetBackendError as error:
        failure = error
        error_code = error.error_code
        stdout = error.stdout
        stderr = error.stderr
    except Exception as error:
        failure = error

    ended = _strictly_later(datetime.now(UTC), start)
    stdout_path = _exclusive_text(stdout, logs / "stdout.log")
    stderr_path = _exclusive_text(stderr, logs / "stderr.log")
    log_refs = (
        _artifact(
            run_root=root,
            path=stdout_path,
            artifact_id="stage02-stdout",
            role="backend-log",
            file_format="text",
        ),
        _artifact(
            run_root=root,
            path=stderr_path,
            artifact_id="stage02-stderr",
            role="backend-log",
            file_format="text",
        ),
    )
    if failure is None:
        methods = set(stage02_config.methods)
        if methods == {Stage02Method.SASA, Stage02Method.SCANNET}:
            backend_name = "independent-sasa-scannet"
        elif methods == {Stage02Method.SASA}:
            backend_name = "sasa-surface-diversity"
        else:
            backend_name = "scannet-epitope-no-msa"
        executor_name = (
            f"local-{adapter.config.execution_device}-subprocess"
            if adapter is not None
            else "local-python"
        )
        attempt = Attempt(
            attempt_id=ATTEMPT_ID,
            status=ExecutionStatus.SUCCEEDED,
            created_at=start,
            started_at=start,
            ended_at=ended,
            backend_name=backend_name,
            backend_version=backend_version,
            executor_name=executor_name,
            log_artifacts=log_refs,
        )
    else:
        if not report_path.exists():
            provider_failures = tuple(
                ProviderExecutionStatus(
                    method=(
                        RegionMethod.SASA_SURFACE_DIVERSITY
                        if method is Stage02Method.SASA
                        else RegionMethod.SCANNET_EPITOPE_NO_MSA
                    ),
                    status="failed",
                    message=str(failure)[:4096] or type(failure).__name__,
                )
                for method in stage02_config.methods
            )
            report = Stage02Report(
                target_id=resolved.user_config.stage01.target.target_id,
                annotation_status=AnnotationStatus.FAILED,
                providers=provider_failures,
                warnings=(
                    "At least one requested Stage 02 method did not complete.",
                    "Stage 03 remains blocked.",
                ),
            )
            dump_model(report, report_path)
        methods = set(stage02_config.methods)
        backend_name = (
            "independent-sasa-scannet"
            if methods == {Stage02Method.SASA, Stage02Method.SCANNET}
            else (
                "sasa-surface-diversity"
                if methods == {Stage02Method.SASA}
                else "scannet-epitope-no-msa"
            )
        )
        executor_name = (
            f"local-{adapter.config.execution_device}-subprocess"
            if adapter is not None
            else "local-python"
        )
        attempt = Attempt(
            attempt_id=ATTEMPT_ID,
            status=ExecutionStatus.FAILED,
            created_at=start,
            started_at=start,
            ended_at=ended,
            backend_name=backend_name,
            backend_version=backend_version,
            executor_name=executor_name,
            log_artifacts=log_refs,
            error=ErrorInfo(
                code=error_code,
                message=str(failure)[:4096] or type(failure).__name__,
                retryable=isinstance(failure, ScanNetBackendError),
            ),
        )
    attempt_manifest = dump_model(attempt, attempt_root / "attempt-manifest.json")

    bundle = load_model(bundle_path, TargetBundle)
    input_artifacts = (
        bundle_ref,
        bundle.target_structure,
        bundle.residue_mapping,
    )
    output_artifacts = (
        tuple(
            _artifact(
                run_root=root,
                path=path,
                artifact_id=artifact_id,
                role=role,
                file_format=file_format,
            )
            for path, artifact_id, role, file_format in output_paths
        )
        if failure is None
        else ()
    )
    stage = StageManifest(
        stage_id=StageId.HOTSPOT_DISCOVERY,
        contract_version="0.2",
        status=(
            ExecutionStatus.SUCCEEDED
            if failure is None
            else ExecutionStatus.FAILED
        ),
        created_at=start,
        completed_at=ended,
        input_artifacts=input_artifacts,
        output_artifacts=output_artifacts,
        attempts=(attempt,),
        selected_attempt_id=ATTEMPT_ID if failure is None else None,
        warnings=(
            "PSE source colors were not consumed.",
            (
                "Scientific annotations are evidence-only and never alter raw "
                "SASA or ScanNet rankings."
            ),
            "No fused method ranking was generated.",
            "Human approval is required before hotspots.yaml is published.",
        ),
    )
    stage.validate_inputs_declared_by((stage01,))
    stage_manifest_path = dump_model(stage, artifacts / "stage-manifest.json")
    run_manifest_path = _publish_run_revision(
        run_root=root,
        current=current,
        current_path=current_path,
        stage_manifest_path=stage_manifest_path,
        ended_at=ended,
        succeeded=failure is None,
    )
    runs_root = root.parent.parent
    upsert_run_index_entries(
        runs_root,
        (
            RunIndexEntry(
                category="project-run",
                path=root.relative_to(runs_root).as_posix(),
                layout_version="1",
                status=(
                    "awaiting-region-selection"
                    if failure is None
                    else "stage02-blocked"
                ),
                project_id=current.project_id,
                run_id=current.run_id,
                notes=(
                    (
                        "Stage 02 independent SASA/ScanNet comparison completed; "
                        "human selection required."
                    )
                    if failure is None
                    else (
                        "Stage 02 comparison failed; retained evidence is not "
                        "published for Stage 03."
                    ),
                ),
            ),
        ),
        generated_at=ended,
    )
    if failure is not None:
        raise failure
    return CompletedStage02Run(
        run_root=root,
        attempt_manifest=attempt_manifest,
        stage_manifest=stage_manifest_path,
        run_manifest=run_manifest_path,
        comparison=comparison_path,
        report=report_path,
    )
