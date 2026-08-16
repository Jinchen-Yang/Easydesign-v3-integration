"""Immutable Stage 05/07 dashboards derived only from declared artifacts."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal, cast

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
from easydesign.safe_writes import (
    append_pointer_revision,
    quarantine_if_workspace_path,
    read_last_text_line,
)
from easydesign.stages.s03_boltzgen_configuration import StrategyBundle
from easydesign.stages.s04_pilot_generation import CandidateIndex, CandidateRecord, PilotBundle
from easydesign.stages.s05_pilot_filtering import (
    AdvisoryValidationReport,
    ExpansionValidationReport,
    PilotFilterReport,
    PilotFilterReportV1_6,
    Stage05Bundle,
    Stage05BundleV0_2,
    TargetConditionedStage05Evidence,
)
from easydesign.stages.s07_final_filtering_and_selection import (
    FinalCandidatePackage,
    FinalCandidatePackageV0_2,
    FinalFilterReport,
    Stage07Bundle,
    Stage07BundleV0_2,
    Stage07PredictionComparisonReport,
    Stage07ReviewCohortIndex,
    TargetConditionedStage07Evidence,
)

from .review_models import (
    REVIEW_DASHBOARD_GENERATOR_VERSION,
    THREEDMOL_LICENSE_SHA256,
    THREEDMOL_SHA256,
    ReviewCandidate,
    ReviewDashboardManifest,
    ReviewDashboardOutcome,
    ReviewDashboardPresentationOverride,
    ReviewDashboardReport,
    ReviewMetricValue,
    ReviewStrategy,
    ReviewStructureEvidence,
    ReviewStructureRoute,
)

REPORT_POINTER_PATTERN = re.compile(
    r"^report-(?P<revision>[0-9]{4,})/report-manifest\.json$"
)
RUN_POINTER_PATTERN = re.compile(r"^run-manifest\.v(?P<revision>[0-9]{4,})\.json$")
STATIC_ROOT = files("easydesign.reporting").joinpath("static", "review_dashboard")
STATIC_FILES = {
    "index.html": "index.html",
    "assets/review-dashboard.css": "review-dashboard.css",
    "assets/review-dashboard.js": "review-dashboard.js",
    "assets/3Dmol-min.js": "vendor/3dmol/3Dmol-min.js",
    "assets/3DMOL_LICENSE.txt": "vendor/3dmol/LICENSE",
}


class ReviewDashboardError(EasyDesignError):
    """Dashboard source, integrity, or publishing contract failed."""


@dataclass(frozen=True, slots=True)
class _DashboardSources:
    run: RunManifest
    run_path: Path
    stage: StageManifest
    stage_path: Path
    stage_bundle_ref: ArtifactRef


def _read_pointer(path: Path, pattern: re.Pattern[str], label: str) -> str:
    try:
        value = read_last_text_line(path)
    except OSError as error:
        raise ReviewDashboardError(f"无法读取 {label} pointer: {path}") from error
    if pattern.fullmatch(value) is None:
        raise ReviewDashboardError(f"{label} pointer 非法: {value!r}")
    return value


def _load_sources(
    run_root: Path,
    report_kind: Literal["stage05", "stage07"],
) -> _DashboardSources:
    relative = _read_pointer(
        run_root / "manifests" / "LATEST",
        RUN_POINTER_PATTERN,
        "RunManifest",
    )
    run_path = run_root / "manifests" / relative
    run = load_model(run_path, RunManifest)
    stage_id = (
        StageId.PILOT_FILTERING
        if report_kind == "stage05"
        else StageId.FINAL_FILTERING_AND_SELECTION
    )
    references = tuple(
        item for item in run.stage_manifest_refs if item.producer_stage == str(stage_id)
    )
    if len(references) != 1:
        raise ReviewDashboardError(
            f"RunManifest 必须声明恰好一个 {stage_id} manifest，实际 {len(references)}"
        )
    stage_path = references[0].verify(run_root)
    stage = load_model(stage_path, StageManifest)
    if stage.stage_id is not stage_id or stage.status is not ExecutionStatus.SUCCEEDED:
        raise ReviewDashboardError(f"dashboard 只接受 succeeded {stage_id}")
    bundle_id = "stage05-bundle" if report_kind == "stage05" else "stage07-bundle"
    bundle_ref = stage.require_output(bundle_id)
    bundle_ref.verify(run_root)
    return _DashboardSources(
        run=run,
        run_path=run_path,
        stage=stage,
        stage_path=stage_path,
        stage_bundle_ref=bundle_ref,
    )


def _route_for(
    *,
    run_root: Path,
    reference: ArtifactRef,
    routes: dict[str, ReviewStructureRoute],
) -> str:
    original = run_root / reference.relative_path
    current = original
    while current != run_root:
        if current.is_symlink():
            raise ReviewDashboardError(f"dashboard 禁止 symlink structure: {original}")
        current = current.parent
    reference.verify(run_root)
    if reference.file_format in {"mmcif", "cif"}:
        mime: Literal["chemical/x-mmcif", "chemical/x-pdb"] = "chemical/x-mmcif"
    elif reference.file_format == "pdb":
        mime = "chemical/x-pdb"
    else:
        raise ReviewDashboardError(
            f"dashboard 不支持 structure format={reference.file_format}"
        )
    token = f"structure-{reference.sha256[:24]}"
    route = ReviewStructureRoute(token=token, artifact=reference, mime_type=mime)
    previous = routes.get(token)
    if previous is not None:
        same_content = (
            previous.artifact.sha256 == reference.sha256
            and previous.artifact.size_bytes == reference.size_bytes
            and previous.mime_type == mime
        )
        if not same_content:
            raise ReviewDashboardError("structure route token collision")
        return token
    routes[token] = route
    return token


def _structure_evidence(
    *,
    run_root: Path,
    reference: ArtifactRef,
    routes: dict[str, ReviewStructureRoute],
    label: str,
    mode: Literal["source", "refolded", "de-novo", "target-conditioned"],
    prediction: Any | None = None,
) -> ReviewStructureEvidence:
    return ReviewStructureEvidence(
        label=label,
        route_token=_route_for(run_root=run_root, reference=reference, routes=routes),
        scientific_mode=mode,
        structure_sha256=reference.sha256,
        backend_identity=(None if prediction is None else prediction.backend_identity),
        release_identity=(
            {} if prediction is None else cast(dict[str, str], prediction.release_identity)
        ),
        template_mode=(None if prediction is None else prediction.template_mode),
        seed=(None if prediction is None else prediction.seed),
        sample_index=(None if prediction is None else getattr(prediction, "sample_index", 0)),
        ranking_score=(
            None if prediction is None else getattr(prediction, "ranking_score", None)
        ),
    )


def _metric(
    key: str,
    label: str,
    value: str | int | float | bool | None,
    source_sha256: str,
    unit: str | None = None,
) -> ReviewMetricValue:
    return ReviewMetricValue(
        key=key,
        label=label,
        value=value,
        unit=unit,
        source_artifact_sha256=source_sha256,
    )


def _validate_stage_local_artifacts(
    sources: _DashboardSources,
    references: tuple[ArtifactRef, ...],
) -> None:
    declared = {item.artifact_id: item for item in sources.stage.output_artifacts}
    stage_id = str(sources.stage.stage_id)
    for reference in references:
        if (
            reference.producer_stage == stage_id
            and declared.get(reference.artifact_id) != reference
        ):
            raise ReviewDashboardError(
                "dashboard source 声称由当前 stage 产生，但未被 StageManifest 原样声明: "
                f"{reference.artifact_id}"
            )


def _load_stage05_report(
    root: Path,
    bundle: Stage05Bundle | Stage05BundleV0_2,
) -> tuple[PilotFilterReport | PilotFilterReportV1_6, Any | None]:
    pilot_raw = json.loads(bundle.pilot_filter_report.verify(root).read_text(encoding="utf-8"))
    pilot = (
        PilotFilterReportV1_6.model_validate(pilot_raw)
        if pilot_raw.get("schema_version") == "0.2"
        else PilotFilterReport.model_validate(pilot_raw)
    )
    expansion_ref = (
        bundle.advisory_validation_report
        if isinstance(bundle, Stage05BundleV0_2)
        else bundle.expansion_validation_report
    )
    if expansion_ref is None:
        return pilot, None
    expansion_raw = json.loads(expansion_ref.verify(root).read_text(encoding="utf-8"))
    expansion = (
        AdvisoryValidationReport.model_validate(expansion_raw)
        if expansion_raw.get("schema_version") == "0.2"
        else ExpansionValidationReport.model_validate(expansion_raw)
    )
    return pilot, expansion


def _stage05_report(
    root: Path,
    sources: _DashboardSources,
    generated_at: datetime,
    presentation: ReviewDashboardPresentationOverride,
) -> ReviewDashboardReport:
    raw = json.loads(
        sources.stage_bundle_ref.verify(root).read_text(encoding="utf-8")
    )
    bundle: Stage05Bundle | Stage05BundleV0_2 = (
        Stage05BundleV0_2.model_validate(raw)
        if raw.get("schema_version") == "0.2"
        else Stage05Bundle.model_validate(raw)
    )
    pilot_report, expansion_report = _load_stage05_report(root, bundle)
    pilot_bundle = load_model(bundle.pilot_bundle.verify(root), PilotBundle)
    pilot_index = load_model(pilot_bundle.candidate_index.verify(root), CandidateIndex)
    pilot_candidates = {item.candidate_id: item for item in pilot_index.candidates}
    expansion_candidates: dict[str, CandidateRecord] = {}
    if bundle.expansion_candidate_index is not None:
        index_raw = json.loads(
            bundle.expansion_candidate_index.verify(root).read_text(encoding="utf-8")
        )
        expansion_index = CandidateIndex.model_validate(index_raw)
        expansion_candidates = {
            item.candidate_id: item for item in expansion_index.candidates
        }
    strategy_bundle = load_model(bundle.strategy_bundle.verify(root), StrategyBundle)
    contracts = {item.strategy_id: item for item in strategy_bundle.strategies}
    routes: dict[str, ReviewStructureRoute] = {}
    prediction_by_id = (
        {} if expansion_report is None else {
            item.candidate_id: item for item in expansion_report.predictions
        }
    )
    conditioned_by_id: dict[str, Any] = {}
    if bundle.target_conditioned_evidence is not None:
        conditioned_evidence = load_model(
            bundle.target_conditioned_evidence.verify(root),
            TargetConditionedStage05Evidence,
        )
        conditioned_by_id = {
            item.candidate_id: item for item in conditioned_evidence.predictions
        }

    candidates: list[ReviewCandidate] = []
    for order, record in enumerate(pilot_report.candidate_records, start=1):
        source = pilot_candidates[record.candidate_id]
        pilot_structures = (
            _structure_evidence(
                run_root=root,
                reference=source.original_structure,
                routes=routes,
                label="生成结构",
                mode="source",
            ),
            _structure_evidence(
                run_root=root,
                reference=source.refolded_structure,
                routes=routes,
                label="局部重折叠",
                mode="refolded",
            ),
        )
        candidates.append(
            ReviewCandidate(
                candidate_id=record.candidate_id,
                strategy_id=record.strategy_id,
                cohort="pilot",
                current_display_order=order,
                metrics=(
                    _metric(
                        "score-screen",
                        "Score screen",
                        record.score_screen,
                        bundle.pilot_filter_report.sha256,
                    ),
                    *tuple(
                        _metric(
                            item.metric_id,
                            item.metric_id,
                            item.value,
                            bundle.pilot_filter_report.sha256,
                            item.unit,
                        )
                        for item in record.metrics
                    ),
                ),
                scientific_record=record.model_dump(mode="json"),
                structures=pilot_structures,
                warnings=tuple(
                    item.missing_reason
                    for item in record.metrics
                    if item.missing_reason is not None
                ),
            )
        )
    if expansion_report is not None:
        if isinstance(bundle, Stage05BundleV0_2):
            assert bundle.advisory_validation_report is not None
            expansion_sha = bundle.advisory_validation_report.sha256
        else:
            assert bundle.expansion_validation_report is not None
            expansion_sha = bundle.expansion_validation_report.sha256
        for order, record in enumerate(expansion_report.candidates, start=1):
            source = expansion_candidates[record.candidate_id]
            expansion_structures = [
                _structure_evidence(
                    run_root=root,
                    reference=source.original_structure,
                    routes=routes,
                    label="生成结构",
                    mode="source",
                ),
                _structure_evidence(
                    run_root=root,
                    reference=source.refolded_structure,
                    routes=routes,
                    label="局部重折叠",
                    mode="refolded",
                ),
            ]
            prediction = prediction_by_id.get(record.candidate_id)
            if prediction is not None:
                expansion_structures.append(
                    _structure_evidence(
                        run_root=root,
                        reference=prediction.predicted_structure,
                        routes=routes,
                        label="De-novo full-target",
                        mode="de-novo",
                        prediction=prediction,
                    )
                )
            conditioned_prediction = conditioned_by_id.get(record.candidate_id)
            if conditioned_prediction is not None:
                expansion_structures.append(
                    _structure_evidence(
                        run_root=root,
                        reference=conditioned_prediction.predicted_structure,
                        routes=routes,
                        label="Target-conditioned full-target",
                        mode="target-conditioned",
                        prediction=conditioned_prediction,
                    )
                )
            candidates.append(
                ReviewCandidate(
                    candidate_id=record.candidate_id,
                    strategy_id=record.strategy_id,
                    cohort="expansion",
                    current_display_order=order,
                    metrics=(
                        _metric(
                            "score-expand-structure",
                            "Score expand structure",
                            record.score_expand_structure,
                            expansion_sha,
                        ),
                        _metric(
                            "local-gate-pass",
                            "Local gate",
                            record.local_gate_pass,
                            expansion_sha,
                        ),
                        _metric(
                            "full-target-status",
                            "Full-target 状态",
                            (
                                "未进入"
                                if prediction is None
                                else prediction.structure_gate_pass
                            ),
                            expansion_sha,
                        ),
                    ),
                    scientific_record=record.model_dump(mode="json"),
                    structures=tuple(expansion_structures),
                )
            )
    summary_by_id = {item.strategy_id: item for item in pilot_report.strategy_summaries}
    promotion_rank = {
        item.strategy_id: item.promotion_rank
        for item in getattr(bundle, "promotion_rank", ())
    }
    strategies = tuple(
        ReviewStrategy(
            strategy_id=strategy_id,
            label=(contracts[strategy_id].hypothesis_id or strategy_id),
            promotion_rank=promotion_rank.get(strategy_id),
            score=summary.score_yaml,
            denominator=summary.candidate_count,
            scientific_record={
                "strategy_contract": contracts[strategy_id].model_dump(mode="json"),
                "pilot_summary": summary.model_dump(mode="json"),
            },
        )
        for strategy_id, summary in sorted(summary_by_id.items())
    )
    source_artifacts = tuple(
        item
        for item in (
            sources.stage_bundle_ref,
            bundle.strategy_bundle,
            bundle.pilot_filter_report,
            bundle.expansion_candidate_index,
            (
                bundle.advisory_validation_report
                if isinstance(bundle, Stage05BundleV0_2)
                else bundle.expansion_validation_report
            ),
            bundle.target_conditioned_evidence,
        )
        if item is not None
    )
    _validate_stage_local_artifacts(
        sources,
        source_artifacts,
    )
    return ReviewDashboardReport(
        report_kind="stage05",
        project_id=sources.run.project_id,
        run_id=sources.run.run_id,
        stage_id="05-pilot-filtering",
        generated_at=generated_at,
        title=presentation.title or "Stage 5 候选审查",
        tabs=("实验方案比较", "全局候选审查"),
        source_run_manifest_sha256=sha256_file(sources.run_path),
        source_stage_manifest_sha256=sha256_file(sources.stage_path),
        source_profile_id=pilot_report.profile_id,
        source_profile_sha256=pilot_report.profile_sha256,
        candidates=tuple(candidates),
        strategies=strategies,
        presentation=presentation,
        structure_routes=tuple(sorted(routes.values(), key=lambda item: item.token)),
        source_artifacts=source_artifacts,
        warnings=tuple(
            item.message
            for item in getattr(expansion_report, "warnings", ())
        ),
    )


def _stage07_report(
    root: Path,
    sources: _DashboardSources,
    generated_at: datetime,
    presentation: ReviewDashboardPresentationOverride,
) -> ReviewDashboardReport:
    raw = json.loads(sources.stage_bundle_ref.verify(root).read_text(encoding="utf-8"))
    bundle: Stage07Bundle | Stage07BundleV0_2 = (
        Stage07BundleV0_2.model_validate(raw)
        if raw.get("schema_version") == "0.2"
        else Stage07Bundle.model_validate(raw)
    )
    if bundle.review_cohort_index is None or bundle.prediction_comparison_report is None:
        raise ReviewDashboardError(
            "Stage 07 run 缺少 review cohort/comparison；请先用 report build 重建科学报告"
        )
    cohort = load_model(
        bundle.review_cohort_index.verify(root),
        Stage07ReviewCohortIndex,
    )
    comparison = load_model(
        bundle.prediction_comparison_report.verify(root),
        Stage07PredictionComparisonReport,
    )
    final_report = load_model(bundle.final_filter_report.verify(root), FinalFilterReport)
    package_raw = json.loads(
        bundle.final_candidate_package.verify(root).read_text(encoding="utf-8")
    )
    package: FinalCandidatePackage | FinalCandidatePackageV0_2 = (
        FinalCandidatePackageV0_2.model_validate(package_raw)
        if package_raw.get("schema_version") == "0.2"
        else FinalCandidatePackage.model_validate(package_raw)
    )
    deep_by_id = {item.candidate_id: item for item in final_report.deep_filter}
    consensus_by_id = {item.candidate_id: item for item in final_report.consensus}
    selections_by_id = {item.candidate_id: item for item in final_report.selections}
    package_by_id = {
        item.candidate_id: item for item in (*package.primary, *package.backup)
    }
    comparisons_by_id: dict[str, list[Any]] = {}
    for item in comparison.comparisons:
        comparisons_by_id.setdefault(item.candidate_id, []).append(item)
    routes: dict[str, ReviewStructureRoute] = {}
    candidates: list[ReviewCandidate] = []
    for entry in cohort.entries:
        structures = [
            _structure_evidence(
                run_root=root,
                reference=entry.source_refolded_structure,
                routes=routes,
                label="Stage 6 refolded",
                mode="refolded",
            )
        ]
        seen: set[tuple[str, str]] = set()
        for pair in comparisons_by_id.get(entry.candidate_id, []):
            for mode, prediction in (
                ("de-novo", pair.de_novo),
                ("target-conditioned", pair.target_conditioned),
            ):
                identity = (mode, prediction.predicted_structure.sha256)
                if identity in seen:
                    continue
                seen.add(identity)
                structures.append(
                    _structure_evidence(
                        run_root=root,
                        reference=prediction.predicted_structure,
                        routes=routes,
                        label=(
                            f"{mode} · seed {prediction.seed} · sample "
                            f"{prediction.sample_index}"
                        ),
                        mode=cast(Any, mode),
                        prediction=prediction,
                    )
                )
        deep = deep_by_id[entry.candidate_id]
        consensus = consensus_by_id.get(entry.candidate_id)
        selection = selections_by_id.get(entry.candidate_id)
        package_item = package_by_id.get(entry.candidate_id)
        candidates.append(
            ReviewCandidate(
                candidate_id=entry.candidate_id,
                strategy_id=entry.strategy_id,
                cohort="review",
                current_display_order=entry.review_rank,
                authoritative_rank=entry.review_rank,
                metrics=(
                    _metric(
                        "score-deep",
                        "Score deep",
                        entry.score_deep,
                        bundle.review_cohort_index.sha256,
                    ),
                    _metric(
                        "seed101-selected",
                        "Seed-101 Top 400",
                        deep.selected_for_seed101,
                        bundle.final_filter_report.sha256,
                    ),
                    _metric(
                        "consensus-pass",
                        "Consensus",
                        None if consensus is None else consensus.consensus_pass,
                        bundle.final_filter_report.sha256,
                    ),
                    _metric(
                        "selection-class",
                        "Selection",
                        None if selection is None else selection.selection_class,
                        bundle.final_filter_report.sha256,
                    ),
                    _metric(
                        "tnp-risk",
                        "TNP",
                        None if package_item is None else package_item.tnp.risk.value,
                        bundle.final_candidate_package.sha256,
                    ),
                ),
                scientific_record={
                    "cohort": entry.model_dump(mode="json"),
                    "deep": deep.model_dump(mode="json"),
                    "consensus": (
                        None if consensus is None else consensus.model_dump(mode="json")
                    ),
                    "selection": (
                        None if selection is None else selection.model_dump(mode="json")
                    ),
                    "package": (
                        None if package_item is None else package_item.model_dump(mode="json")
                    ),
                },
                structures=tuple(structures),
                warnings=(
                    ("默认双模式代表 sample 使用不同 seed；这是非 matched-seed 对照",)
                    if any(
                        item.pair_kind == "best-ranked" and not item.matched_seed
                        for item in comparisons_by_id.get(entry.candidate_id, [])
                    )
                    else ()
                ),
            )
        )
    counts = Counter(item.strategy_id for item in cohort.entries)
    strategies = tuple(
        ReviewStrategy(
            strategy_id=strategy_id,
            label=strategy_id,
            denominator=count,
            scientific_record={"review_cohort_count": count},
        )
        for strategy_id, count in sorted(counts.items())
    )
    conditioned_ref = bundle.target_conditioned_evidence
    if conditioned_ref is not None:
        load_model(conditioned_ref.verify(root), TargetConditionedStage07Evidence)
    source_artifacts = tuple(
        item
        for item in (
            sources.stage_bundle_ref,
            bundle.filter_profile,
            bundle.final_filter_report,
            bundle.final_candidate_package,
            bundle.review_cohort_index,
            bundle.prediction_comparison_report,
            conditioned_ref,
        )
        if item is not None
    )
    _validate_stage_local_artifacts(
        sources,
        source_artifacts,
    )
    return ReviewDashboardReport(
        report_kind="stage07",
        project_id=sources.run.project_id,
        run_id=sources.run.run_id,
        stage_id="07-final-filtering-and-selection",
        generated_at=generated_at,
        title=presentation.title or "Stage 7 最终候选审查",
        tabs=("设计路线比较", "全局候选审查", "双模式预测结果"),
        source_run_manifest_sha256=sha256_file(sources.run_path),
        source_stage_manifest_sha256=sha256_file(sources.stage_path),
        source_profile_id=final_report.profile_id,
        source_profile_sha256=final_report.profile_sha256,
        requested_review_cohort_size=cohort.requested_size,
        actual_review_cohort_size=cohort.actual_size,
        candidates=tuple(candidates),
        strategies=strategies,
        comparisons=tuple(
            item.model_dump(mode="json") for item in comparison.comparisons
        ),
        comparison_advisory_verdicts=tuple(
            item.model_dump(mode="json") for item in comparison.advisory_verdicts
        ),
        presentation=presentation,
        structure_routes=tuple(sorted(routes.values(), key=lambda item: item.token)),
        source_artifacts=source_artifacts,
        warnings=(
            (
                f"Review cohort 为 {cohort.actual_size}/{cohort.requested_size}；"
                "失败候选未用于补齐。"
            ),
        ),
    )


def _source_identity(report: ReviewDashboardReport) -> str:
    payload = {
        "generator": REVIEW_DASHBOARD_GENERATOR_VERSION,
        "kind": report.report_kind,
        "run": report.source_run_manifest_sha256,
        "stage": report.source_stage_manifest_sha256,
        "profile": report.source_profile_sha256,
        "sources": [
            (item.artifact_id, item.sha256, item.size_bytes)
            for item in report.source_artifacts
        ],
        "presentation": report.presentation.model_dump(mode="json"),
        "3dmol": THREEDMOL_SHA256,
        "license": THREEDMOL_LICENSE_SHA256,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _report_base(root: Path, report_kind: Literal["stage05", "stage07"]) -> Path:
    stage = (
        "05-pilot-filtering"
        if report_kind == "stage05"
        else "07-final-filtering-and-selection"
    )
    return root / "results" / stage / "review-dashboard"


def _next_revision(base: Path) -> int:
    revisions = [
        int(match.group("revision"))
        for path in base.glob("report-*")
        if (match := re.fullmatch(r"report-(?P<revision>[0-9]{4,})", path.name))
    ]
    return max(revisions, default=0) + 1


def _copy_resource(relative: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    resource = STATIC_ROOT.joinpath(*Path(relative).parts)
    with resource.open("rb") as source, destination.open("xb") as target:
        shutil.copyfileobj(source, target)


def _output_artifacts(root: Path) -> tuple[ArtifactRef, ...]:
    files_and_ids = (
        ("index.html", "review-dashboard-html"),
        ("report.json", "review-dashboard-data"),
        ("assets/review-dashboard.css", "review-dashboard-css"),
        ("assets/review-dashboard.js", "review-dashboard-js"),
        ("assets/3Dmol-min.js", "review-dashboard-3dmol-js"),
        ("assets/3DMOL_LICENSE.txt", "review-dashboard-3dmol-license"),
    )
    formats = {".html": "html", ".json": "json", ".css": "css", ".js": "javascript", ".txt": "text"}
    return tuple(
        ArtifactRef.from_file(
            run_root=root,
            relative_path=relative,
            artifact_id=artifact_id,
            role="review-dashboard-report",
            file_format=formats[Path(relative).suffix],
        )
        for relative, artifact_id in files_and_ids
    )


def _latest_manifest(base: Path) -> tuple[Path, ReviewDashboardManifest] | None:
    pointer = base / "LATEST"
    if not pointer.is_file():
        return None
    relative = _read_pointer(pointer, REPORT_POINTER_PATTERN, "review dashboard")
    path = base / relative
    return path.parent, load_model(path, ReviewDashboardManifest)


def _publish(staging: Path, final_root: Path, base: Path) -> None:
    if final_root.exists():
        raise ReviewDashboardError(f"dashboard revision 已存在: {final_root}")
    staging.rename(final_root)
    append_pointer_revision(base / "LATEST", f"{final_root.name}/report-manifest.json\n")


def generate_review_dashboard(
    run_root: Path,
    *,
    report_kind: Literal["stage05", "stage07"],
    presentation: ReviewDashboardPresentationOverride | None = None,
    generated_at: datetime | None = None,
) -> ReviewDashboardOutcome:
    """Build or idempotently return a checksum-verified immutable dashboard."""

    root = run_root.resolve()
    started = generated_at or datetime.now(UTC)
    override = presentation or ReviewDashboardPresentationOverride()
    base = _report_base(root, report_kind)
    base.mkdir(parents=True, exist_ok=True)
    sources: _DashboardSources | None = None
    source_identity: str | None = None
    try:
        sources = _load_sources(root, report_kind)
        report = (
            _stage05_report(root, sources, started, override)
            if report_kind == "stage05"
            else _stage07_report(root, sources, started, override)
        )
        source_identity = _source_identity(report)
        latest = _latest_manifest(base)
        if latest is not None:
            latest_root, latest_manifest = latest
            if (
                latest_manifest.status is ExecutionStatus.SUCCEEDED
                and latest_manifest.source_identity_sha256 == source_identity
            ):
                verify_review_dashboard(latest_root)
                return ReviewDashboardOutcome(
                    status=ExecutionStatus.SUCCEEDED,
                    report_root=latest_root,
                    manifest_path=latest_root / "report-manifest.json",
                    entrypoint=latest_root / "index.html",
                )
        revision = _next_revision(base)
        final_root = base / f"report-{revision:04d}"
        staging = Path(
            tempfile.mkdtemp(prefix=f".report-{revision:04d}.creating-", dir=base)
        )
        try:
            for destination, source in STATIC_FILES.items():
                _copy_resource(source, staging / destination)
            dump_model(report, staging / "report.json")
            output = _output_artifacts(staging)
            manifest = ReviewDashboardManifest(
                report_id=(
                    "stage05-review-dashboard"
                    if report_kind == "stage05"
                    else "stage07-review-dashboard"
                ),
                revision=revision,
                status=ExecutionStatus.SUCCEEDED,
                created_at=started,
                completed_at=datetime.now(UTC),
                source_run_manifest_sha256=report.source_run_manifest_sha256,
                source_stage_manifest_sha256=report.source_stage_manifest_sha256,
                source_identity_sha256=source_identity,
                output_artifacts=output,
                warnings=report.warnings,
            )
            dump_model(manifest, staging / "report-manifest.json")
            _publish(staging, final_root, base)
        except Exception:
            if staging.exists():
                quarantine_if_workspace_path(
                    staging,
                    operation="review-dashboard",
                    reason="dashboard staging 生成失败",
                )
            raise
        return ReviewDashboardOutcome(
            status=ExecutionStatus.SUCCEEDED,
            report_root=final_root,
            manifest_path=final_root / "report-manifest.json",
            entrypoint=final_root / "index.html",
        )
    except (EasyDesignError, OSError, ValueError, KeyError, TypeError) as error:
        revision = _next_revision(base)
        final_root = base / f"report-{revision:04d}"
        failure = Path(
            tempfile.mkdtemp(prefix=f".report-{revision:04d}.failed-", dir=base)
        )
        error_info = ErrorInfo(
            code="review-dashboard-generation-failed",
            message=(str(error) or type(error).__name__)[:4096],
            retryable=True,
        )
        manifest = ReviewDashboardManifest(
            report_id=(
                "stage05-review-dashboard"
                if report_kind == "stage05"
                else "stage07-review-dashboard"
            ),
            revision=revision,
            status=ExecutionStatus.FAILED,
            created_at=started,
            completed_at=datetime.now(UTC),
            source_run_manifest_sha256=(
                None if sources is None else sha256_file(sources.run_path)
            ),
            source_stage_manifest_sha256=(
                None if sources is None else sha256_file(sources.stage_path)
            ),
            source_identity_sha256=source_identity,
            error=error_info,
        )
        dump_model(manifest, failure / "report-manifest.json")
        _publish(failure, final_root, base)
        return ReviewDashboardOutcome(
            status=ExecutionStatus.FAILED,
            report_root=final_root,
            manifest_path=final_root / "report-manifest.json",
            error=error_info,
        )


def generate_review_dashboard_nonblocking(
    run_root: Path,
    *,
    report_kind: Literal["stage05", "stage07"],
    generated_at: datetime | None = None,
) -> ReviewDashboardOutcome:
    try:
        return generate_review_dashboard(
            run_root,
            report_kind=report_kind,
            generated_at=generated_at,
        )
    except Exception as error:
        info = ErrorInfo(
            code="review-dashboard-unpublished-failure",
            message=(str(error) or type(error).__name__)[:4096],
            retryable=True,
        )
        base = _report_base(run_root.resolve(), report_kind)
        return ReviewDashboardOutcome(
            status=ExecutionStatus.FAILED,
            report_root=base,
            manifest_path=base / "UNPUBLISHED_REPORTING_FAILURE",
            error=info,
        )


def verify_review_dashboard(report_root: Path) -> ReviewDashboardManifest:
    root = report_root.resolve()
    manifest = load_model(root / "report-manifest.json", ReviewDashboardManifest)
    if manifest.status is not ExecutionStatus.SUCCEEDED:
        raise ReviewDashboardError(f"不能打开 failed dashboard: {manifest.error}")
    for artifact in manifest.output_artifacts:
        artifact.verify(root)
    js = root / "assets" / "3Dmol-min.js"
    license_path = root / "assets" / "3DMOL_LICENSE.txt"
    if sha256_file(js) != manifest.threedmol_sha256:
        raise ReviewDashboardError("3Dmol.js SHA 不匹配")
    if sha256_file(license_path) != manifest.threedmol_license_sha256:
        raise ReviewDashboardError("3Dmol license SHA 不匹配")
    load_model(root / "report.json", ReviewDashboardReport)
    return manifest


def resolve_latest_review_dashboard(
    run_root: Path,
    report_kind: Literal["stage05", "stage07"],
) -> Path:
    base = _report_base(run_root.resolve(), report_kind)
    latest = _latest_manifest(base)
    if latest is None:
        raise ReviewDashboardError(f"没有 {report_kind} dashboard")
    root, _ = latest
    verify_review_dashboard(root)
    return root
