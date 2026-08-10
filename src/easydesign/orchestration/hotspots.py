"""Stage 02 人工区域审批和不可变 ``hotspots.yaml`` 发布。"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from easydesign.core import (
    ArtifactRef,
    Attempt,
    ExecutionStatus,
    ManifestStateError,
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
from easydesign.stages.s01_target_preparation import TargetBundle
from easydesign.stages.s02_hotspot_discovery import (
    AnnotationReport,
    ApprovalRecord,
    ApprovedHotspotSet,
    AutomaticRegionSource,
    EvidenceLevel,
    HotspotEvidence,
    HotspotReviewRequest,
    HotspotReviewSelection,
    HotspotsFile,
    RecommendedRegionSet,
    RegionMethod,
    RegionSource,
    UserProvidedRegionSet,
)

from .config import UserRegionInitialApprovalConfig
from .workspace import (
    RunIndexEntry,
    load_resolved_run_config,
    upsert_run_index_entries,
)

APPROVAL_ATTEMPT_ID = "attempt-0002"


def _strictly_later(candidate: datetime, previous: datetime) -> datetime:
    return candidate if candidate > previous else previous + timedelta(microseconds=1)


def _atomic_pointer(text: str, path: Path) -> None:
    append_pointer_revision(path, text)


def _exclusive_copy(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as source_handle, destination.open("xb") as target:
            shutil.copyfileobj(source_handle, target)
    except FileExistsError as error:
        raise ManifestStateError(f"审批输入不可覆盖: {destination}") from error
    return destination


def _dump_yaml(model: HotspotReviewRequest | HotspotsFile, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(
                model.model_dump(mode="json", exclude_none=False),
                handle,
                allow_unicode=True,
                sort_keys=False,
            )
    except FileExistsError as error:
        raise ManifestStateError(f"YAML 不可覆盖: {path}") from error
    return path


def _load_review(path: Path) -> HotspotReviewRequest:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ManifestStateError(f"审批 YAML 读取失败: {path}: {error}") from error
    return HotspotReviewRequest.model_validate(raw)


def _load_current(
    run_root: Path,
) -> tuple[RunManifest, Path, StageManifest, Path, StageManifest, TargetBundle]:
    latest = run_root / "manifests" / "LATEST"
    try:
        manifest_name = read_last_text_line(latest)
    except OSError as error:
        raise ManifestStateError(f"无法读取 run manifest LATEST: {latest}") from error
    run_path = run_root / "manifests" / manifest_name
    run = load_model(run_path, RunManifest)
    if run.status is not ExecutionStatus.RUNNING:
        raise ManifestStateError("只有等待审批的 running run 可以执行 hotspot 审批")
    if run.workflow_state is None or run.workflow_state.action != "approve-hotspots":
        raise ManifestStateError("当前 run 不处于 Stage 02 hotspot 审批状态")

    stages: dict[StageId, tuple[StageManifest, Path]] = {}
    for reference in run.stage_manifest_refs:
        path = reference.verify(run_root)
        stage = load_model(path, StageManifest)
        stages[stage.stage_id] = (stage, path)
    try:
        stage01, _stage01_path = stages[StageId.TARGET_PREPARATION]
        stage02, stage02_path = stages[StageId.HOTSPOT_DISCOVERY]
    except KeyError as error:
        raise ManifestStateError("当前 run 缺少 Stage 01 或 Stage 02 manifest") from error
    if (
        stage01.status is not ExecutionStatus.SUCCEEDED
        or stage02.status is not ExecutionStatus.SUCCEEDED
    ):
        raise ManifestStateError("Stage 01/02 必须成功后才能审批")
    bundle = load_model(stage01.require_output("target-bundle").verify(run_root), TargetBundle)
    return run, run_path, stage01, stage02_path, stage02, bundle


def _region_artifact_id(method: RegionMethod) -> str:
    if method is RegionMethod.SASA_SURFACE_DIVERSITY:
        return "sasa-recommended-regions"
    return "scannet-recommended-regions"


def export_hotspot_review(
    run_root: Path,
    *,
    method: RegionMethod | None = None,
    output: Path,
) -> Path:
    """导出可编辑审批模板；不改变 run。"""

    root = run_root.resolve()
    run, _run_path, _stage01, stage02_path, stage02, bundle = _load_current(root)
    user_ref = next(
        (
            reference
            for reference in stage02.output_artifacts
            if reference.artifact_id == "user-provided-regions"
        ),
        None,
    )
    region_source: RegionSource
    if user_ref is not None:
        if method is not None:
            raise ManifestStateError("用户提供区域不接受 SASA/ScanNet method 选择")
        artifact_id = user_ref.artifact_id
        region_ref = user_ref
        user_regions = load_model(
            region_ref.verify(root),
            UserProvidedRegionSet,
        )
        regions: RecommendedRegionSet | UserProvidedRegionSet = user_regions
        region_source = user_regions.region_source
    else:
        if method is None:
            available_methods: list[RegionMethod] = []
            for candidate in RegionMethod:
                if any(
                    reference.artifact_id == _region_artifact_id(candidate)
                    for reference in stage02.output_artifacts
                ):
                    available_methods.append(candidate)
            if len(available_methods) != 1:
                raise ManifestStateError(
                    "automatic Stage 02 存在多个或没有可审批方法；请显式指定 --method"
                )
            method = available_methods[0]
        artifact_id = _region_artifact_id(method)
        region_ref = stage02.require_output(artifact_id)
        regions = load_model(region_ref.verify(root), RecommendedRegionSet)
        if regions.method is not method:
            raise ManifestStateError("推荐区域 artifact 的方法身份不一致")
        if len(regions.regions) < regions.minimum_region_count:
            raise ManifestStateError(
                "自动候选不足最低数量，不能导出可批准模板；需要人工复核算法或输入"
            )
        region_source = AutomaticRegionSource(
            method=method,
            recommendation_artifact_id=artifact_id,
            recommendation_sha256=region_ref.sha256,
        )
    annotation_ref = stage02.require_output("stage02-annotation-report")
    annotation = load_model(annotation_ref.verify(root), AnnotationReport)
    if isinstance(regions, RecommendedRegionSet):
        selections = tuple(
            HotspotReviewSelection(
                id=area_id,
                source_region_id=region.region_id,
            )
            for area_id, region in zip(
                ("A", "B", "C"),
                regions.regions,
                strict=False,
            )
        )
    else:
        selections = tuple(
            HotspotReviewSelection(
                id=region.id,
                source_region_id=region.source_region_id,
            )
            for region in regions.regions
        )
    request = HotspotReviewRequest(
        project_id=run.project_id,
        run_id=run.run_id,
        target_id=bundle.target_id,
        method=method,
        region_source=region_source,
        source_stage_manifest_sha256=sha256_file(stage02_path),
        source_regions_artifact_id=artifact_id,
        source_regions_sha256=region_ref.sha256,
        selection_basis=annotation.evidence_level,
        annotation_status=annotation.status,
        selections=selections,
    )
    return _dump_yaml(request, output.expanduser().resolve())


def _label_ranges(values: tuple[int, ...]) -> str:
    ranges: list[str] = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        ranges.append(str(start) if start == previous else f"{start}..{previous}")
        start = previous = value
    ranges.append(str(start) if start == previous else f"{start}..{previous}")
    return ",".join(ranges)


def _approved_set(
    *,
    selection: HotspotReviewSelection,
    regions: RecommendedRegionSet | UserProvidedRegionSet,
    annotation: AnnotationReport,
) -> ApprovedHotspotSet:
    if isinstance(regions, RecommendedRegionSet):
        region_by_id = {region.region_id: region for region in regions.regions}
        automatic_region = region_by_id[selection.source_region_id]
        members = automatic_region.members
        source_region_id = automatic_region.region_id
        risk_flags: list[str] = []
        evidence = [
            HotspotEvidence(
                type="structural-region",
                source=str(regions.method),
                description=(
                    f"完整自动候选 {automatic_region.region_id}; ranking_score="
                    f"{automatic_region.ranking_score:.6f}."
                ),
            )
        ]
    else:
        user_region_by_id = {
            region.source_region_id: region for region in regions.regions
        }
        user_region = user_region_by_id[selection.source_region_id]
        members = user_region.members
        source_region_id = user_region.source_region_id
        source_type = regions.region_source.type
        risk_flags = ["user_annotation_requires_biological_review"]
        evidence = [
            HotspotEvidence(
                type="user-provided-region",
                source=source_type,
                description=(
                    f"完整用户区域 {user_region.source_region_id}; "
                    "members preserved without expansion, deletion, or reranking."
                ),
            )
        ]
    label_ids = tuple(member.label_seq_id for member in members)
    label_set = set(label_ids)
    for feature in annotation.mapped_features:
        if label_set.intersection(feature.label_seq_ids):
            description = feature.description or "no-description"
            evidence.append(
                HotspotEvidence(
                    type="uniprot-feature",
                    source=annotation.accession or "uniprot",
                    description=f"{feature.feature_type}: {description}",
                )
            )
            risk_flags.append(
                f"uniprot:{feature.feature_type}:{description}"[:1024]
            )
    for motif in annotation.motif_warnings:
        if label_set.intersection(motif.label_seq_ids):
            motif_text = "-".join(str(value) for value in motif.label_seq_ids)
            evidence.append(
                HotspotEvidence(
                    type="sequence-motif",
                    source="target-sequence",
                    description=(
                        f"Potential N-X-S/T motif at label positions {motif_text}; "
                        "sequence warning only."
                    ),
                )
            )
            risk_flags.append(f"potential-glycosylation-motif:{motif_text}")
    auth_residues = tuple(
        f"{member.auth_asym_id}:{member.auth_seq_id}"
        f"{member.insertion_code or ''}"
        for member in members
    )
    return ApprovedHotspotSet(
        id=selection.id,
        slug=f"area-{selection.id.lower()}-{selection.design_goal}",
        source_region_id=source_region_id,
        design_goal=selection.design_goal,
        biological_rationale=selection.biological_rationale,
        structural_rationale=selection.structural_rationale,
        auth_residues=auth_residues,
        label_seq_ids=label_ids,
        label_ranges=_label_ranges(label_ids),
        evidence=tuple(evidence),
        risk_flags=tuple(risk_flags),
    )


def _artifact(
    *,
    run_root: Path,
    path: Path,
    artifact_id: str,
    role: str,
    file_format: str,
    produced: bool,
) -> ArtifactRef:
    return ArtifactRef.from_file(
        run_root=run_root,
        relative_path=path.relative_to(run_root).as_posix(),
        artifact_id=artifact_id,
        role=role,
        file_format=file_format,
        producer_stage=(
            str(StageId.HOTSPOT_DISCOVERY) if produced else None
        ),
        producer_attempt=APPROVAL_ATTEMPT_ID if produced else None,
    )


def approve_hotspots(
    run_root: Path,
    *,
    input_path: Path,
    approved_at: datetime | None = None,
    authority: str = "human",
    policy_id: str | None = None,
    approval_source: str = "explicit-review",
) -> Path:
    """验证完整区域选择并以新 attempt 发布唯一 ``hotspots.yaml``。"""

    if authority not in {"human", "deterministic-policy"}:
        raise ManifestStateError(f"未知 hotspot approval authority: {authority}")
    if authority == "deterministic-policy" and policy_id is None:
        raise ManifestStateError("deterministic-policy approval 必须提供 policy_id")
    if authority == "human" and policy_id is not None:
        raise ManifestStateError("human approval 不得携带 policy_id")
    if authority == "deterministic-policy":
        approval_source = "deterministic-policy"
    if approval_source not in {
        "explicit-review",
        "initial-run-config",
        "deterministic-policy",
    }:
        raise ManifestStateError(f"未知 approval_source: {approval_source}")
    if approval_source == "initial-run-config" and authority != "human":
        raise ManifestStateError("initial-run-config 必须记录 human authority")

    root = run_root.resolve()
    run, run_path, stage01, stage02_path, stage02, bundle = _load_current(root)
    source_input = input_path.expanduser().resolve()
    request = _load_review(source_input)
    if (
        request.project_id != run.project_id
        or request.run_id != run.run_id
        or request.target_id != bundle.target_id
    ):
        raise ManifestStateError("审批文件不属于当前 project/run/target")
    if request.source_stage_manifest_sha256 != sha256_file(stage02_path):
        raise ManifestStateError("Stage 02 manifest 已变化；请重新导出审批模板")
    region_ref = stage02.require_output(request.source_regions_artifact_id)
    if region_ref.sha256 != request.source_regions_sha256:
        raise ManifestStateError("审批文件引用的推荐区域 artifact 已变化")
    if isinstance(request.region_source, AutomaticRegionSource):
        if (
            request.method is None
            or region_ref.artifact_id != _region_artifact_id(request.method)
        ):
            raise ManifestStateError("automatic 审批的 method/artifact 身份不一致")
        automatic_regions = load_model(
            region_ref.verify(root),
            RecommendedRegionSet,
        )
        if (
            automatic_regions.method is not request.method
            or request.region_source.recommendation_artifact_id
            != region_ref.artifact_id
            or request.region_source.recommendation_sha256 != region_ref.sha256
        ):
            raise ManifestStateError("automatic 审批的 region_source 身份不一致")
        regions: RecommendedRegionSet | UserProvidedRegionSet = automatic_regions
        available = {
            region.region_id for region in automatic_regions.regions
        }
    else:
        if region_ref.artifact_id != "user-provided-regions":
            raise ManifestStateError("用户提供区域必须引用标准化 user-provided artifact")
        user_regions = load_model(region_ref.verify(root), UserProvidedRegionSet)
        if user_regions.region_source != request.region_source:
            raise ManifestStateError("用户区域来源身份与标准化 artifact 不一致")
        regions = user_regions
        available = {
            region.source_region_id for region in user_regions.regions
        }
    selected = {selection.source_region_id for selection in request.selections}
    if not selected.issubset(available):
        raise ManifestStateError("审批只能选择当前 artifact 中的完整区域")
    if not request.approved_by:
        raise ManifestStateError("approved_by 不能为空")
    for selection in request.selections:
        if not selection.biological_rationale or not selection.structural_rationale:
            raise ManifestStateError(
                f"区域 {selection.id} 必须填写 biological_rationale 和 "
                "structural_rationale"
            )
    annotation_ref = stage02.require_output("stage02-annotation-report")
    annotation = load_model(annotation_ref.verify(root), AnnotationReport)
    if (
        request.selection_basis != annotation.evidence_level
        or request.annotation_status != annotation.status
    ):
        raise ManifestStateError("审批文件的 annotation/evidence 身份不一致")
    if (
        annotation.evidence_level is EvidenceLevel.STRUCTURAL_ONLY
        and not request.acknowledge_evidence_limitations
    ):
        raise ManifestStateError(
            "structural-only 审批必须设置 acknowledge_evidence_limitations: true"
        )
    if (
        not isinstance(request.region_source, AutomaticRegionSource)
        and not request.acknowledge_user_provided_regions
    ):
        raise ManifestStateError(
            "用户提供区域审批必须设置 "
            "acknowledge_user_provided_regions: true"
        )

    attempt_root = root / str(StageId.HOTSPOT_DISCOVERY) / APPROVAL_ATTEMPT_ID
    if attempt_root.exists():
        raise ManifestStateError(f"审批 attempt 已存在，禁止覆盖: {attempt_root}")
    inputs = attempt_root / "inputs"
    artifacts = attempt_root / "artifacts"
    copied_input = _exclusive_copy(source_input, inputs / "hotspots-review.yaml")
    normalized_request = _dump_yaml(
        request,
        artifacts / "approval-request.yaml",
    )
    timestamp = datetime.now(UTC) if approved_at is None else approved_at
    timestamp = _strictly_later(timestamp, run.updated_at)
    approval_sets = tuple(
        _approved_set(
            selection=selection,
            regions=regions,
            annotation=annotation,
        )
        for selection in request.selections
    )
    hotspots = HotspotsFile(
        project_id=run.project_id,
        run_id=run.run_id,
        target_id=bundle.target_id,
        target_structure_sha256=bundle.target_structure.sha256,
        coordinate_model_ids=(
            bundle.coordinate_ensemble.model_ids
            if bundle.coordinate_ensemble is not None
            else ("1",)
        ),
        method=request.method,
        region_source=request.region_source,
        selection_basis=annotation.evidence_level,
        annotation_status=annotation.status,
        approval_request_sha256=sha256_file(normalized_request),
        approved_by=request.approved_by,
        approval_authority=authority,
        approval_source=approval_source,
        policy_id=policy_id,
        hotspot_sets=approval_sets,
    )
    hotspots_path = _dump_yaml(hotspots, artifacts / "hotspots.yaml")
    record = ApprovalRecord(
        approved_at=timestamp,
        approved_by=request.approved_by,
        method=request.method,
        region_source=request.region_source,
        source_stage_manifest_sha256=request.source_stage_manifest_sha256,
        approval_input_sha256=sha256_file(copied_input),
        selected_region_ids=tuple(
            selection.source_region_id for selection in request.selections
        ),
        acknowledge_user_provided_regions=(
            request.acknowledge_user_provided_regions
        ),
        acknowledge_evidence_limitations=(
            request.acknowledge_evidence_limitations
        ),
        authority=authority,
        approval_source=approval_source,
        policy_id=policy_id,
    )
    record_path = dump_model(record, artifacts / "approval-record.json")
    approval_input_ref = _artifact(
        run_root=root,
        path=copied_input,
        artifact_id="hotspot-approval-input",
        role="human-approval-input",
        file_format="yaml",
        produced=False,
    )
    output_refs = (
        _artifact(
            run_root=root,
            path=normalized_request,
            artifact_id="approval-request",
            role="normalized-human-approval",
            file_format="yaml",
            produced=True,
        ),
        _artifact(
            run_root=root,
            path=record_path,
            artifact_id="approval-record",
            role="human-approval-record",
            file_format="json",
            produced=True,
        ),
        _artifact(
            run_root=root,
            path=hotspots_path,
            artifact_id="hotspots",
            role="stage03-hotspot-input",
            file_format="yaml",
            produced=True,
        ),
    )
    attempt = Attempt(
        attempt_id=APPROVAL_ATTEMPT_ID,
        status=ExecutionStatus.SUCCEEDED,
        created_at=timestamp,
        started_at=timestamp,
        ended_at=timestamp,
        backend_name=(
            "deterministic-hotspot-policy"
            if authority == "deterministic-policy"
            else "human-hotspot-approval"
        ),
        backend_version="0.1",
        executor_name="easydesign-local",
    )
    dump_model(attempt, attempt_root / "attempt-manifest.json")
    approved_stage = StageManifest(
        stage_id=StageId.HOTSPOT_DISCOVERY,
        contract_version="0.3",
        status=ExecutionStatus.SUCCEEDED,
        created_at=stage02.created_at,
        completed_at=timestamp,
        input_artifacts=stage02.input_artifacts + (approval_input_ref,),
        output_artifacts=output_refs,
        attempts=stage02.attempts + (attempt,),
        selected_attempt_id=APPROVAL_ATTEMPT_ID,
        warnings=(
            (
                "Approved regions are complete outputs from one automatic method."
                if isinstance(regions, RecommendedRegionSet)
                else "Approved regions are complete user-provided regions."
            ),
            "No score fusion or region member editing was performed.",
            (
                "User-provided regions require biological review and are not "
                "scientifically validated binding sites."
                if not isinstance(regions, RecommendedRegionSet)
                else "Automatic proposals remain method-specific."
            ),
            (
                "Scientific evidence limitations were explicitly acknowledged."
                if annotation.evidence_level is EvidenceLevel.STRUCTURAL_ONLY
                else "UniProt annotations were retained as evidence/warnings only."
            ),
        ),
    )
    approved_stage.validate_inputs_declared_by((stage01,))
    approved_stage_path = dump_model(
        approved_stage,
        artifacts / "stage-manifest.json",
    )
    stage_ref = _artifact(
        run_root=root,
        path=approved_stage_path,
        artifact_id="stage-02-manifest",
        role="stage-manifest",
        file_format="json",
        produced=True,
    )
    retained = tuple(
        reference
        for reference in run.stage_manifest_refs
        if reference.producer_stage != str(StageId.HOTSPOT_DISCOVERY)
    )
    resolved, _ = load_resolved_run_config(root)
    completed = resolved.stop_after_stage == 2
    next_run = run.next_revision(
        updated_at=timestamp,
        status=(
            ExecutionStatus.SUCCEEDED if completed else ExecutionStatus.RUNNING
        ),
        completed_at=timestamp if completed else None,
        stage_manifest_refs=retained + (stage_ref,),
        clear_workflow_state=True,
    )
    next_path = (
        root
        / "manifests"
        / f"run-manifest.v{next_run.revision:04d}.json"
    )
    dump_model(next_run, next_path)
    _atomic_pointer(f"{next_path.name}\n", root / "manifests" / "LATEST")
    del run_path
    runs_root = root.parent.parent
    upsert_run_index_entries(
        runs_root,
        (
            RunIndexEntry(
                category="project-run",
                path=root.relative_to(runs_root).as_posix(),
                layout_version="1",
                status="succeeded" if completed else "stage02-approved",
                project_id=run.project_id,
                run_id=run.run_id,
                notes=(
                    "Stage 02 regions approved; hotspots.yaml published.",
                ),
            ),
        ),
        generated_at=timestamp,
    )
    return hotspots_path


def approve_hotspots_by_policy(
    run_root: Path,
    *,
    method: RegionMethod,
    region_count: int,
    allow_structural_only: bool,
    policy_id: str = "stage02-single-method-top-regions-v1",
) -> Path:
    """unattended 专用：只批准单一方法已发布的完整 Top 2–3。"""

    if region_count not in {2, 3}:
        raise ManifestStateError("unattended region_count 必须是 2 或 3")
    root = run_root.resolve()
    temporary = root / "02-hotspot-discovery" / ".policy-review.yaml"
    if temporary.exists():
        raise ManifestStateError(f"临时 policy review 已存在: {temporary}")
    export_hotspot_review(root, method=method, output=temporary)
    try:
        raw = yaml.safe_load(temporary.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ManifestStateError("自动导出的 hotspot review 不是 mapping")
        selections = raw.get("selections")
        if not isinstance(selections, list) or len(selections) < region_count:
            raise ManifestStateError(
                "自动推荐区域不足 unattended_approval.region_count"
            )
        raw["approved_by"] = f"policy:{policy_id}"
        raw["acknowledge_evidence_limitations"] = allow_structural_only
        raw["selections"] = selections[:region_count]
        for selection in raw["selections"]:
            if not isinstance(selection, dict):
                raise ManifestStateError("hotspot selection 不是 mapping")
            selection["design_goal"] = "exploratory"
            selection["biological_rationale"] = (
                "Unattended 1.0 deterministic policy selected the complete "
                "method-ranked region; no biological annotation was used to rerank."
            )
            selection["structural_rationale"] = (
                "The region is a complete connected proposal from the configured "
                "single Stage 02 method and preserves its original members."
            )
        approved_input = temporary.with_name(".policy-review-approved.yaml")
        with approved_input.open("x", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(raw, handle, allow_unicode=True, sort_keys=False)
        return approve_hotspots(
            root,
            input_path=approved_input,
            authority="deterministic-policy",
            policy_id=policy_id,
            approval_source="deterministic-policy",
        )
    finally:
        quarantine_if_workspace_path(
            temporary,
            operation="hotspot-policy-review",
            reason="自动审批 staging 已消费",
        )
        quarantine_if_workspace_path(
            locals().get("approved_input"),
            operation="hotspot-policy-review-approved",
            reason="自动审批输入已复制进不可变 attempt",
        )


def approve_hotspots_from_initial_config(
    run_root: Path,
    *,
    approval: UserRegionInitialApprovalConfig,
) -> Path:
    """unattended 用户区域：消费用户在初始 YAML 中签署的人工批准。"""

    root = run_root.resolve()
    temporary = root / "02-hotspot-discovery" / ".initial-config-review.yaml"
    if temporary.exists():
        raise ManifestStateError(f"临时 config review 已存在: {temporary}")
    export_hotspot_review(root, method=None, output=temporary)
    try:
        raw = yaml.safe_load(temporary.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ManifestStateError("自动导出的 hotspot review 不是 mapping")
        exported = raw.get("selections")
        if not isinstance(exported, list):
            raise ManifestStateError("自动导出的 hotspot selections 不是 list")
        by_id = {
            item.id: item
            for item in approval.selections
        }
        exported_ids = {
            item.get("id")
            for item in exported
            if isinstance(item, dict)
        }
        if exported_ids != set(by_id):
            raise ManifestStateError(
                "unattended 初始审批必须为全部标准化用户区域提供理由"
            )
        for selection in exported:
            if not isinstance(selection, dict):
                raise ManifestStateError("hotspot selection 不是 mapping")
            selection_id = selection.get("id")
            if selection_id not in by_id:
                raise ManifestStateError("初始审批包含未知区域 id")
            configured = by_id[selection_id]
            selection["design_goal"] = str(configured.design_goal)
            selection["biological_rationale"] = configured.biological_rationale
            selection["structural_rationale"] = configured.structural_rationale
        raw["approved_by"] = approval.approved_by
        raw["acknowledge_user_provided_regions"] = (
            approval.acknowledge_user_provided_regions
        )
        raw["acknowledge_evidence_limitations"] = (
            approval.acknowledge_evidence_limitations
        )
        approved_input = temporary.with_name(".initial-review-approved.yaml")
        with approved_input.open("x", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(raw, handle, allow_unicode=True, sort_keys=False)
        return approve_hotspots(
            root,
            input_path=approved_input,
            authority="human",
            approval_source="initial-run-config",
        )
    finally:
        quarantine_if_workspace_path(
            temporary,
            operation="hotspot-initial-review",
            reason="初始审批 staging 已消费",
        )
        quarantine_if_workspace_path(
            locals().get("approved_input"),
            operation="hotspot-initial-review-approved",
            reason="初始审批输入已复制进不可变 attempt",
        )
