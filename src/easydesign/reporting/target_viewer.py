"""从正式 Stage 01 Target Bundle 生成便携、只读的 Mol* 报告。"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Literal, cast

from easydesign.core import (
    ArtifactRef,
    EasyDesignError,
    ErrorInfo,
    ExecutionStatus,
    RunManifest,
    StageId,
    StageManifest,
    dump_model,
    load_model,
    sha256_file,
)
from easydesign.stages.s01_target_preparation import (
    ImportedStructureProvenance,
    ImportedStructureQualityReport,
    PredictionProvenance,
    PseSourceAnnotations,
    ResidueMapping,
    StructureQualityReport,
    TargetBundle,
    TargetStructureOrigin,
)

from .models import (
    REPORT_ID,
    TargetViewerData,
    TargetViewerOutcome,
    TargetViewerReportManifest,
    ViewerAnnotationSummary,
    ViewerColorCount,
    ViewerDownload,
    ViewerMetric,
    ViewerResidue,
)

REPORT_POINTER_PATTERN = re.compile(
    r"^report-(?P<revision>[0-9]{4,})/report-manifest\.json$"
)
RUN_POINTER_PATTERN = re.compile(r"^run-manifest\.v(?P<revision>[0-9]{4,})\.json$")
STATIC_ROOT = files("easydesign.reporting").joinpath("static", "target_viewer")
STATIC_FILES = {
    "index.html": "index.html",
    "assets/molstar.js": "vendor/molstar/molstar.js",
    "assets/molstar.css": "vendor/molstar/molstar.css",
    "assets/MOLSTAR_LICENSE.txt": "vendor/molstar/LICENSE",
    "assets/easydesign-viewer.js": "easydesign-viewer.js",
    "assets/easydesign-viewer.css": "easydesign-viewer.css",
}


class TargetViewerReportError(EasyDesignError):
    """Target Viewer 来源、生成或发布不满足报告契约。"""


@dataclass(frozen=True, slots=True)
class _ViewerSources:
    run_manifest_path: Path
    stage_manifest_path: Path
    bundle_path: Path
    bundle: TargetBundle
    mapping: ResidueMapping
    quality: StructureQualityReport | ImportedStructureQualityReport | None
    provenance: PredictionProvenance | ImportedStructureProvenance | None
    annotations: PseSourceAnnotations | None


def _atomic_pointer(content: str, path: Path) -> None:
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
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _read_pointer(path: Path, pattern: re.Pattern[str], label: str) -> str:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise TargetViewerReportError(f"无法读取 {label} pointer: {path}") from error
    if pattern.fullmatch(value) is None:
        raise TargetViewerReportError(f"{label} pointer 非法: {value!r}")
    return value


def _load_current_run_manifest(run_root: Path) -> tuple[RunManifest, Path]:
    pointer = run_root / "manifests" / "LATEST"
    relative = _read_pointer(pointer, RUN_POINTER_PATTERN, "RunManifest")
    manifest_path = run_root / "manifests" / relative
    manifest = load_model(manifest_path, RunManifest)
    if manifest.status not in {ExecutionStatus.RUNNING, ExecutionStatus.SUCCEEDED}:
        raise TargetViewerReportError(
            f"Target Viewer 只接受 running/succeeded run，实际为 {manifest.status}"
        )
    return manifest, manifest_path


def _load_sources(run_root: Path) -> _ViewerSources:
    run, run_manifest_path = _load_current_run_manifest(run_root)
    stage_refs = [
        reference
        for reference in run.stage_manifest_refs
        if reference.producer_stage == str(StageId.TARGET_PREPARATION)
    ]
    if len(stage_refs) != 1:
        raise TargetViewerReportError(
            f"RunManifest 必须声明恰好一个 Stage 01 manifest，实际为 {len(stage_refs)}"
        )
    stage_manifest_path = stage_refs[0].verify(run_root)
    stage = load_model(stage_manifest_path, StageManifest)
    if stage.stage_id is not StageId.TARGET_PREPARATION:
        raise TargetViewerReportError("RunManifest 的 Stage 01 引用指向错误阶段")
    if stage.status is not ExecutionStatus.SUCCEEDED:
        raise TargetViewerReportError(
            f"Target Viewer 只接受 succeeded Stage 01，实际为 {stage.status}"
        )
    bundle_path = stage.require_output("target-bundle").verify(run_root)
    bundle = load_model(bundle_path, TargetBundle)
    bundle_artifacts: tuple[ArtifactRef, ...] = (
        bundle.target_structure,
        bundle.sequence,
        bundle.residue_mapping,
        bundle.quality_report,
        bundle.provenance,
    )
    if bundle.source_annotations is not None:
        bundle_artifacts += (bundle.source_annotations,)
    declared_outputs = {
        artifact.artifact_id: artifact for artifact in stage.output_artifacts
    }
    for artifact in bundle_artifacts:
        if declared_outputs.get(artifact.artifact_id) != artifact:
            raise TargetViewerReportError(
                "Target Bundle 引用的 artifact 未由 StageManifest 原样声明: "
                f"{artifact.artifact_id}"
            )
    bundle.target_structure.verify(run_root)
    bundle.sequence.verify(run_root)
    mapping_path = bundle.residue_mapping.verify(run_root)
    bundle.quality_report.verify(run_root)
    bundle.provenance.verify(run_root)
    mapping = load_model(mapping_path, ResidueMapping)
    if mapping.target_id != bundle.target_id:
        raise TargetViewerReportError("Target Bundle 与 residue mapping 的 target_id 不一致")
    if mapping.sequence_sha256 != bundle.sequence_sha256:
        raise TargetViewerReportError("Target Bundle 与 residue mapping 的 sequence SHA 不一致")
    if len(mapping.entries) != bundle.sequence_length:
        raise TargetViewerReportError("Target Bundle 与 residue mapping 的残基数量不一致")

    quality: StructureQualityReport | ImportedStructureQualityReport | None
    provenance: PredictionProvenance | ImportedStructureProvenance | None
    if bundle.origin is TargetStructureOrigin.PREDICTED:
        quality = load_model(
            bundle.quality_report.verify(run_root),
            StructureQualityReport,
        )
        provenance = load_model(
            bundle.provenance.verify(run_root),
            PredictionProvenance,
        )
    elif bundle.origin is TargetStructureOrigin.IMPORTED:
        quality = load_model(
            bundle.quality_report.verify(run_root),
            ImportedStructureQualityReport,
        )
        provenance = load_model(
            bundle.provenance.verify(run_root),
            ImportedStructureProvenance,
        )
    else:
        quality = None
        provenance = None

    annotations = (
        None
        if bundle.source_annotations is None
        else load_model(
            bundle.source_annotations.verify(run_root),
            PseSourceAnnotations,
        )
    )
    return _ViewerSources(
        run_manifest_path=run_manifest_path,
        stage_manifest_path=stage_manifest_path,
        bundle_path=bundle_path,
        bundle=bundle,
        mapping=mapping,
        quality=quality,
        provenance=provenance,
        annotations=annotations,
    )


def _metric(key: str, label: str, value: str | int | float | bool) -> ViewerMetric:
    return ViewerMetric(key=key, label=label, value=value)


def _quality_metrics(
    quality: StructureQualityReport | ImportedStructureQualityReport | None,
) -> tuple[ViewerMetric, ...]:
    if isinstance(quality, StructureQualityReport):
        return (
            _metric("plddt", "整体 pLDDT", round(quality.plddt, 3)),
            _metric("ptm", "pTM", round(quality.ptm, 3)),
            _metric("gpde", "gPDE", round(quality.gpde, 3)),
            _metric("ranking-score", "Ranking score", round(quality.ranking_score, 3)),
            _metric("has-clash", "结构冲突", quality.has_clash),
            _metric("recycle-count", "Recycle 次数", quality.recycle_count),
        )
    if isinstance(quality, ImportedStructureQualityReport):
        return (
            _metric("coordinate-states", "坐标 state 数", quality.coordinate_state_count),
            _metric("protein-chains", "蛋白链数", quality.protein_chain_count),
            _metric("residue-count", "结构残基数", quality.residue_count),
            _metric("missing-ca", "缺失 CA 数", quality.missing_ca_count),
            _metric("water-residues", "忽略水分子数", quality.water_residue_count),
        )
    return (_metric("quality-status", "质量报告", "当前来源尚无 Viewer 适配"),)


def _provenance_metrics(
    provenance: PredictionProvenance | ImportedStructureProvenance | None,
) -> tuple[ViewerMetric, ...]:
    if isinstance(provenance, PredictionProvenance):
        values = [
            _metric("backend", "结构后端", provenance.backend_name),
            _metric("backend-version", "后端版本", provenance.backend_version),
            _metric("model", "模型", provenance.model_name),
            _metric("msa-mode", "MSA 模式", str(provenance.msa_mode)),
            _metric("template-mode", "模板模式", str(provenance.template_mode)),
        ]
        if provenance.msa_provider is not None:
            values.append(_metric("msa-provider", "MSA provider", provenance.msa_provider))
        if provenance.msa_depth is not None:
            values.append(_metric("msa-depth", "MSA depth", provenance.msa_depth))
        return tuple(values)
    if isinstance(provenance, ImportedStructureProvenance):
        return (
            _metric("backend", "导入后端", provenance.backend_name),
            _metric("backend-version", "后端版本", provenance.backend_version),
            _metric("source-format", "来源格式", provenance.source_format),
            _metric("selected-object", "PyMOL object", provenance.selected_object),
            _metric("author-chain", "Author chain", provenance.author_chain_id),
            _metric("coordinate-state", "Coordinate state", provenance.coordinate_state),
        )
    return (_metric("provenance-status", "来源详情", "当前来源尚无 Viewer 适配"),)


def _annotations_by_label(
    mapping: ResidueMapping,
    annotations: PseSourceAnnotations | None,
) -> tuple[dict[tuple[str, int], str], ViewerAnnotationSummary]:
    if annotations is None:
        return {}, ViewerAnnotationSummary(status="not_applicable")
    entries = {entry.label_seq_id: entry for entry in mapping.entries}
    colors: dict[tuple[str, int], str] = {}
    for annotation in annotations.residues:
        entry = entries.get(annotation.label_seq_id)
        if entry is None:
            raise TargetViewerReportError(
                f"PSE annotation 引用了 mapping 中不存在的 label_seq_id="
                f"{annotation.label_seq_id}"
            )
        if (
            annotation.author_chain_id != entry.author_chain_id
            or annotation.author_residue_id != entry.author_residue_id
            or annotation.insertion_code != entry.insertion_code
        ):
            raise TargetViewerReportError(
                f"PSE annotation 与 residue mapping 身份不一致: "
                f"label_seq_id={annotation.label_seq_id}"
            )
        colors[(entry.label_chain_id, entry.label_seq_id)] = annotation.ca_color_hex
    if len(colors) != len(mapping.entries):
        raise TargetViewerReportError("PSE annotation 未覆盖全部 mapping 残基")
    summary = ViewerAnnotationSummary(
        status="available",
        annotation_type=annotations.annotation_type,
        interpretation="uninterpreted",
        color_counts=tuple(
            ViewerColorCount(
                color_hex=count.ca_color_hex,
                residue_count=count.residue_count,
            )
            for count in annotations.color_counts
        ),
    )
    return colors, summary


def _viewer_data(sources: _ViewerSources) -> TargetViewerData:
    colors, annotation_summary = _annotations_by_label(
        sources.mapping,
        sources.annotations,
    )
    residues = tuple(
        ViewerResidue(
            sequence_index=entry.sequence_index,
            amino_acid=entry.amino_acid,
            label_asym_id=entry.label_chain_id,
            label_seq_id=entry.label_seq_id,
            auth_asym_id=entry.author_chain_id,
            auth_seq_id=entry.author_residue_id,
            insertion_code=entry.insertion_code,
            pse_color_hex=colors.get((entry.label_chain_id, entry.label_seq_id)),
        )
        for entry in sources.mapping.entries
    )
    bundle = sources.bundle
    return TargetViewerData(
        target_id=bundle.target_id,
        origin=cast(
            Literal["experimental", "imported", "predicted"],
            str(bundle.origin),
        ),
        sequence_length=bundle.sequence_length,
        sequence_sha256=bundle.sequence_sha256,
        structure_sha256=bundle.target_structure.sha256,
        quality_metrics=_quality_metrics(sources.quality),
        provenance_metrics=_provenance_metrics(sources.provenance),
        annotation=annotation_summary,
        residues=residues,
        downloads=(
            ViewerDownload(
                label="下载 target.cif",
                relative_path="data/target.cif",
                sha256=bundle.target_structure.sha256,
            ),
            ViewerDownload(
                label="下载 sequence.fasta",
                relative_path="data/sequence.fasta",
                sha256=bundle.sequence.sha256,
            ),
            ViewerDownload(
                label="下载 residue-mapping.json",
                relative_path="data/residue-mapping.json",
                sha256=bundle.residue_mapping.sha256,
            ),
        ),
    )


def _next_revision(report_base: Path) -> int:
    pointer = report_base / "LATEST"
    if not pointer.exists():
        return 1
    relative = _read_pointer(pointer, REPORT_POINTER_PATTERN, "Target Viewer")
    match = REPORT_POINTER_PATTERN.fullmatch(relative)
    assert match is not None
    current_path = report_base / relative
    current = load_model(current_path, TargetViewerReportManifest)
    revision = int(match.group("revision"))
    if current.revision != revision:
        raise TargetViewerReportError("Target Viewer LATEST revision 与 manifest 不一致")
    return revision + 1


def _exclusive_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as input_handle, destination.open("xb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle)
    except FileExistsError as error:
        raise TargetViewerReportError(f"不可覆盖 Viewer 文件: {destination}") from error


def _copy_resource(relative_source: str, destination: Path) -> None:
    resource = STATIC_ROOT.joinpath(*relative_source.split("/"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        content = resource.read_bytes()
    except (FileNotFoundError, OSError) as error:
        raise TargetViewerReportError(
            f"EasyDesign wheel 缺少 Target Viewer 静态资源: {relative_source}"
        ) from error
    try:
        with destination.open("xb") as handle:
            handle.write(content)
    except FileExistsError as error:
        raise TargetViewerReportError(f"不可覆盖 Viewer 静态资源: {destination}") from error


def _report_artifact(report_root: Path, relative_path: str, artifact_id: str) -> ArtifactRef:
    suffix = Path(relative_path).suffix.lower()
    formats = {
        ".html": "html",
        ".json": "json",
        ".cif": "mmcif",
        ".fasta": "fasta",
        ".js": "javascript",
        ".css": "css",
        ".txt": "text",
    }
    return ArtifactRef.from_file(
        run_root=report_root,
        relative_path=relative_path,
        artifact_id=artifact_id,
        role="target-viewer-report",
        file_format=formats[suffix],
    )


def _output_artifacts(report_root: Path) -> tuple[ArtifactRef, ...]:
    paths = (
        ("index.html", "viewer-html"),
        ("viewer-data.json", "viewer-data"),
        ("data/target.cif", "viewer-target-structure"),
        ("data/sequence.fasta", "viewer-target-sequence"),
        ("data/residue-mapping.json", "viewer-residue-mapping"),
        ("assets/molstar.js", "molstar-js"),
        ("assets/molstar.css", "molstar-css"),
        ("assets/easydesign-viewer.js", "easydesign-viewer-js"),
        ("assets/easydesign-viewer.css", "easydesign-viewer-css"),
        ("assets/MOLSTAR_LICENSE.txt", "molstar-license"),
    )
    return tuple(
        _report_artifact(report_root, relative_path, artifact_id)
        for relative_path, artifact_id in paths
    )


def _publish_report(staging: Path, final_root: Path, report_base: Path) -> None:
    if final_root.exists():
        raise TargetViewerReportError(f"Viewer report revision 已存在: {final_root}")
    staging.rename(final_root)
    _atomic_pointer(
        f"{final_root.name}/report-manifest.json\n",
        report_base / "LATEST",
    )


def _failure_code(error: Exception) -> str:
    if isinstance(error, EasyDesignError):
        return "target-viewer-contract-failed"
    return "target-viewer-generation-failed"


def generate_stage01_target_viewer(
    run_root: Path,
    generated_at: datetime | None = None,
) -> TargetViewerOutcome:
    """验证正式 Stage 01 产物并生成自包含、不可覆盖的 Target Viewer report。"""

    root = run_root.resolve()
    if not (root / "manifests" / "LATEST").is_file():
        raise TargetViewerReportError(f"run 缺少 manifests/LATEST: {root}")
    report_base = root / "results" / "01-target-preparation" / "target-viewer"
    report_base.mkdir(parents=True, exist_ok=True)
    revision = _next_revision(report_base)
    final_root = report_base / f"report-{revision:04d}"
    if final_root.exists():
        raise TargetViewerReportError(f"Viewer report revision 已存在: {final_root}")
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".report-{revision:04d}.creating-",
            dir=report_base,
        )
    )
    started = datetime.now(UTC) if generated_at is None else generated_at
    source_hashes: dict[str, str | None] = {
        "run": None,
        "stage": None,
        "bundle": None,
        "structure": None,
    }
    try:
        sources = _load_sources(root)
        source_hashes = {
            "run": sha256_file(sources.run_manifest_path),
            "stage": sha256_file(sources.stage_manifest_path),
            "bundle": sha256_file(sources.bundle_path),
            "structure": sources.bundle.target_structure.sha256,
        }
        data = _viewer_data(sources)
        _exclusive_copy(
            sources.bundle.target_structure.verify(root),
            staging / "data" / "target.cif",
        )
        _exclusive_copy(
            sources.bundle.sequence.verify(root),
            staging / "data" / "sequence.fasta",
        )
        _exclusive_copy(
            sources.bundle.residue_mapping.verify(root),
            staging / "data" / "residue-mapping.json",
        )
        for destination, source in STATIC_FILES.items():
            _copy_resource(source, staging / destination)
        dump_model(data, staging / "viewer-data.json")
        artifacts = _output_artifacts(staging)
        warnings = (
            (
                "PSE colors are preserved as uninterpreted source annotations.",
            )
            if sources.annotations is not None
            else ()
        )
        manifest = TargetViewerReportManifest(
            revision=revision,
            status=ExecutionStatus.SUCCEEDED,
            created_at=started,
            completed_at=datetime.now(UTC),
            source_run_manifest_sha256=source_hashes["run"],
            source_stage_manifest_sha256=source_hashes["stage"],
            source_target_bundle_sha256=source_hashes["bundle"],
            source_target_structure_sha256=source_hashes["structure"],
            output_artifacts=artifacts,
            warnings=warnings,
        )
        dump_model(manifest, staging / "report-manifest.json")
        _publish_report(staging, final_root, report_base)
        return TargetViewerOutcome(
            status=ExecutionStatus.SUCCEEDED,
            report_root=final_root,
            manifest_path=final_root / "report-manifest.json",
            entrypoint=final_root / "index.html",
        )
    except (EasyDesignError, OSError, ValueError, KeyError, TypeError) as error:
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir()
        error_info = ErrorInfo(
            code=_failure_code(error),
            message=(str(error) or type(error).__name__)[:4096],
            retryable=False,
        )
        manifest = TargetViewerReportManifest(
            revision=revision,
            status=ExecutionStatus.FAILED,
            created_at=started,
            completed_at=datetime.now(UTC),
            source_run_manifest_sha256=source_hashes["run"],
            source_stage_manifest_sha256=source_hashes["stage"],
            source_target_bundle_sha256=source_hashes["bundle"],
            source_target_structure_sha256=source_hashes["structure"],
            error=error_info,
        )
        dump_model(manifest, staging / "report-manifest.json")
        _publish_report(staging, final_root, report_base)
        return TargetViewerOutcome(
            status=ExecutionStatus.FAILED,
            report_root=final_root,
            manifest_path=final_root / "report-manifest.json",
            error=error_info,
        )


def generate_stage01_target_viewer_nonblocking(
    run_root: Path,
    generated_at: datetime | None = None,
) -> TargetViewerOutcome:
    """用于科学流程自动接入；reporting 基础设施异常也不能推翻 Stage 01。"""

    try:
        return generate_stage01_target_viewer(run_root, generated_at=generated_at)
    except Exception as error:
        report_base = (
            run_root.resolve()
            / "results"
            / "01-target-preparation"
            / "target-viewer"
        )
        error_info = ErrorInfo(
            code="target-viewer-unpublished-failure",
            message=(str(error) or type(error).__name__)[:4096],
            retryable=False,
        )
        return TargetViewerOutcome(
            status=ExecutionStatus.FAILED,
            report_root=report_base,
            manifest_path=report_base / "UNPUBLISHED_REPORTING_FAILURE",
            error=error_info,
        )


def verify_target_viewer_report(report_root: Path) -> TargetViewerReportManifest:
    """验证一个成功 report 的 manifest 和全部自包含文件。"""

    root = report_root.resolve()
    manifest = load_model(
        root / "report-manifest.json",
        TargetViewerReportManifest,
    )
    if manifest.status is not ExecutionStatus.SUCCEEDED:
        raise TargetViewerReportError(
            f"不能打开 failed Target Viewer report: {manifest.error}"
        )
    for artifact in manifest.output_artifacts:
        artifact.verify(root)
    return manifest


def resolve_latest_target_viewer_report(run_root: Path) -> Path:
    """通过 reporting 自有 LATEST 指针定位最新 report，不回退旧 revision。"""

    base = (
        run_root.resolve()
        / "results"
        / "01-target-preparation"
        / "target-viewer"
    )
    relative = _read_pointer(base / "LATEST", REPORT_POINTER_PATTERN, REPORT_ID)
    report_root = (base / Path(relative).parent).resolve()
    try:
        report_root.relative_to(base.resolve())
    except ValueError as error:
        raise TargetViewerReportError("Target Viewer pointer 逃出 report 根目录") from error
    verify_target_viewer_report(report_root)
    return report_root
