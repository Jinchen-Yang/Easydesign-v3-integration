"""Pilot measurement adapter: existing kernels, exact approved population, no expansion."""

from __future__ import annotations

import fcntl
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from easydesign.backends.executors import NvidiaSmiProbe
from easydesign.core import (
    ArtifactRef,
    ManifestStateError,
    TaskStatus,
    canonical_model_sha256,
    dump_model,
    load_model,
)
from easydesign.filtering import METRIC_DEFINITION_VERSION, evaluate_pilot_candidates_v1_6
from easydesign.filtering.nanobody_v1_6 import (
    PROFILE_SOURCE_SHA256_V1_6,
    PROFILE_SOURCE_SHA256_V1_7,
    PilotProfileId,
)
from easydesign.orchestration.application import _complex_prediction_adapter_builder
from easydesign.orchestration.config import stage05_config_for_backend
from easydesign.orchestration.profile import load_runtime_profile_by_identity
from easydesign.orchestration.stage05 import (
    _batch_structure_metrics,
    _load_upstream,
    _predict_selected_candidates,
)
from easydesign.orchestration.task_tracking import load_latest_runtime_model
from easydesign.orchestration.workspace import load_resolved_run_config
from easydesign.stages.s04_pilot_generation import PilotPlan, TaskTable
from easydesign.stages.s05_pilot_filtering import (
    FullTargetExecutionState,
    FullTargetPredictionRecord,
    PilotFilterReportV1_6,
)

from .contracts import AgentBoundaryError
from .phase3 import project_pilot_measurement
from .phase34_contracts import (
    ExecutionProjection,
    FrozenContract,
    MetricObservation,
    PilotMeasurement,
)
from .phase34_partial_reference import (
    PartialReferencePrediction,
    partial_reference_required,
    recover_partial_reference_predictions,
)
from .session_store import confined

MEASUREMENT_VERSION = "verified-prediction-missingness-v2"


class PilotPredictionEvidence(FrozenContract):
    authority_id: str
    candidate_index_sha256: str
    predictions: tuple[FullTargetPredictionRecord | PartialReferencePrediction, ...]
    evidence_refs: tuple[ArtifactRef, ...]
    operational_failure: str | None = None


_PREDICTION_METRICS = {
    "pairwise_iptm": None,
    "minimum_interface_pae_angstrom": "angstrom",
    "binder_ptm": None,
    "binder_pose_rmsd_angstrom": "angstrom",
    "target_ca_rmsd_angstrom": "angstrom",
    "severe_clash_count": "count",
    "moderate_clash_count": "count",
}


def attach_prediction_metrics(
    measurement: PilotMeasurement,
    predictions: tuple[FullTargetPredictionRecord | PartialReferencePrediction, ...],
) -> PilotMeasurement:
    """Keep prediction metrics distinct from generation/refolding metrics and their units."""
    by_id = {p.candidate_id: p for p in predictions}
    if len(by_id) != len(predictions) or set(by_id) - {
        c.lineage.candidate_id for c in measurement.candidates
    }:
        raise AgentBoundaryError("Prediction evidence contains foreign/duplicate candidates")
    candidates = []
    for candidate in measurement.candidates:
        prediction = by_id.get(candidate.lineage.candidate_id)
        if prediction and prediction.strategy_id != candidate.lineage.strategy_id:
            raise AgentBoundaryError("Prediction changed candidate strategy lineage")
        metrics = tuple(
            MetricObservation(
                metric_id="independent-prediction-" + name,
                value=getattr(prediction, name) if prediction else None,
                unit=unit,
                available=prediction is not None and getattr(prediction, name) is not None,
                missing_reason=(
                    getattr(prediction, "unavailable_metric_reasons", {}).get(name)
                    if prediction is not None
                    else "Independent prediction not available"
                ),
                source=prediction.backend_identity if prediction else "independent-prediction",
                definition_version=(
                    prediction.confidence_metric_definition_version
                    if name in {"pairwise_iptm", "minimum_interface_pae_angstrom", "binder_ptm"}
                    else METRIC_DEFINITION_VERSION
                )
                if prediction
                else "model-neutral-complex-v1",
            )
            for name, unit in _PREDICTION_METRICS.items()
        )
        candidates.append(candidate.model_copy(update={"metrics": (*candidate.metrics, *metrics)}))
    arms = []
    for arm in measurement.arms:
        group = [c for c in candidates if c.lineage.strategy_id == arm.strategy_id]
        missing = Counter(m.metric_id for c in group for m in c.metrics if not m.available)
        arms.append(
            arm.model_copy(
                update={
                    "predicted_candidates": sum(c.lineage.candidate_id in by_id for c in group),
                    "missing_by_metric": dict(missing),
                }
            )
        )
    return PilotMeasurement.model_validate(
        measurement.model_copy(
            update={"candidates": tuple(candidates), "arms": tuple(arms)}
        ).model_dump()
    )


def _save_exact(root: Path, path: Path, model: Any, name: str) -> ArtifactRef:
    if path.exists():
        if load_model(path, type(model)) != model:
            raise AgentBoundaryError("Published Pilot evidence changed on recovery")
    else:
        dump_model(model, path)
    return ArtifactRef.from_file(
        run_root=root,
        relative_path=path.relative_to(root).as_posix(),
        artifact_id=name,
        role="phase34-pilot-evidence",
        file_format="json",
    )


def incomplete_prediction_evidence(
    *,
    root: Path,
    runtime: Path,
    artifacts: Path,
    authority_id: str,
    index: Any,
    index_sha256: str,
    error: ManifestStateError,
) -> PilotPredictionEvidence:
    """Retain verified terminal worker outcomes, never downgrade a fact/checksum error."""
    if str(error) != "Stage 05 Protenix full-target tasks 未全部完成，可使用 runs resume":
        raise error
    state = load_latest_runtime_model(runtime / "full-target-state.json", FullTargetExecutionState)
    if state.progress.status != "incomplete" or not any(
        t.status == TaskStatus.FAILED for t in state.tasks
    ):
        raise error
    if any(t.status not in {TaskStatus.SUCCEEDED, TaskStatus.FAILED} for t in state.tasks):
        raise error
    by_id = {c.candidate_id: c.strategy_id for c in index.candidates}
    if set(state.selected_candidate_ids) != set(by_id):
        raise AgentBoundaryError("Incomplete prediction state has a foreign population")
    for prediction in state.predictions:
        if by_id[prediction.candidate_id] != prediction.strategy_id:
            raise AgentBoundaryError("Incomplete prediction changed strategy lineage")
    refs = tuple(
        ref
        for p in state.predictions
        for ref in (p.predicted_structure, p.summary_confidence, p.full_confidence)
    )
    for ref in refs:
        ref.verify(root)
    state_ref = _save_exact(
        root,
        artifacts / f"prediction-terminal-state-{canonical_model_sha256(state)}.json",
        state,
        "v3-prediction-terminal-state",
    )
    return PilotPredictionEvidence(
        authority_id=authority_id,
        candidate_index_sha256=index_sha256,
        predictions=state.predictions,
        evidence_refs=(*refs, state_ref),
        operational_failure="Independent prediction exhausted its bounded attempt budget; "
        "failed candidates retain missing metrics, without a biological failure conclusion.",
    )


def evaluate_pilot(bridge: Any) -> dict[str, Any]:
    """Idempotent backend operation; never calls a model or invokes legacy expansion."""
    authority = bridge.pilot_authority()
    execution = bridge.project_latest("phase34-pilot-execution")
    if authority is None or execution is None or execution["authority"] != authority.authority_id:
        raise AgentBoundaryError("Pilot measurements require the current execution authority")
    plan = authority.pilot_plan
    assert plan is not None
    existing = bridge.project_latest("phase34-pilot-measurement")
    if (
        existing
        and existing["dependencies"].get("authority") == authority.authority_id
        and existing["dependencies"].get("measurement_version") == MEASUREMENT_VERSION
        and (
            existing["dependencies"].get("execution_job_id", execution["job_id"])
            == execution["job_id"]
        )
    ):
        bridge.load_contract(kind="phase34-pilot-measurement", contract_type=PilotMeasurement)
        return {"status": "pilot-measured", "measurement_sha256": existing["contract_sha256"]}
    result = measure_execution(
        bridge,
        authority_id=authority.authority_id,
        plan=plan,
        execution=execution,
        allocations=plan.execution_allocations,
        projection=ExecutionProjection(
            mode=plan.mode,
            requested_production_candidates=sum(plan.production_allocations.values()),
            execution_candidates=sum(plan.execution_allocations.values()),
            uses_real_generation_backend=True,
            uses_real_prediction_backend=True,
            purpose="Exact approved Pilot scope; all-candidate prediction, no expansion.",
        ),
    )
    if result["status"] != "measured":
        return result
    measured = result["measurement"]
    bridge.store.event(bridge.thread, "phase34-pilot-measurement-sources", result["sources"])
    bridge.publish_contract(
        kind="phase34-pilot-measurement",
        contract=measured,
        dependencies={
            "authority": authority.authority_id,
            "execution_job_id": execution["job_id"],
            "prediction": result["sources"]["predictions"]["sha256"],
            "measurement_version": MEASUREMENT_VERSION,
        },
    )
    return {"status": "pilot-measured", "measurement_sha256": canonical_model_sha256(measured)}


def measure_execution(
    bridge: Any,
    *,
    authority_id: str,
    plan: Any,
    execution: dict[str, Any],
    allocations: dict[str, int],
    projection: ExecutionProjection,
) -> dict[str, Any]:
    """Shared measured-population adapter for authorized Pilot and Scale batches."""
    root, _ = bridge.run(execution["run_id"])
    work_root = confined(root, root / "phase34" / authority_id / "measurement")
    work_root.mkdir(parents=True, exist_ok=True)
    with (work_root / "execution.lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status": "running", "phase": "pilot-measurement"}
        upstream = _load_upstream(root)
        index = upstream.candidate_index
        counts = dict(Counter(c.strategy_id for c in index.candidates))
        if counts != allocations:
            raise AgentBoundaryError("Generated Pilot population differs from its exact allocation")
        resolved, _ = load_resolved_run_config(root)
        if canonical_model_sha256(resolved.user_config) != execution["config_sha256"]:
            raise AgentBoundaryError("Pilot run configuration changed")
        if resolved.runtime_profile is None:
            raise AgentBoundaryError("Pilot lacks its frozen backend release profile")
        profile = load_runtime_profile_by_identity(resolved.runtime_profile).profile
        config = stage05_config_for_backend(plan.prediction_backend)
        generation_config = resolved.user_config.stage04
        assert config is not None and generation_config is not None
        if config.full_target_prediction.backend != plan.prediction_backend:
            raise AgentBoundaryError("Prediction backend differs from approved Pilot plan")
        now = datetime.now(UTC)
        artifacts = work_root / "artifacts"
        runtime = work_root / "runtime"
        artifacts.mkdir(exist_ok=True)
        runtime.mkdir(exist_ok=True)
        report_path = artifacts / "pilot-filter-report.json"
        if report_path.exists():
            report = load_model(report_path, PilotFilterReportV1_6)
            if report.candidate_index_sha256 != upstream.candidate_index_ref.sha256:
                raise AgentBoundaryError("Pilot metric report refers to another population")
        else:
            metrics = _batch_structure_metrics(
                root=root,
                upstream=upstream,
                candidates=index.candidates,
                runtime_root=runtime,
                phase="v3-pilot-structure-metrics",
                created_at=now,
            )
            report = evaluate_pilot_candidates_v1_6(
                candidates=index.candidates,
                structural_metrics=metrics,
                candidate_index_sha256=upstream.candidate_index_ref.sha256,
                maximum_tier_a_strategies=config.maximum_tier_a_strategies,
                generated_at=now,
                profile_id=cast(PilotProfileId, config.filter_profile),
                profile_sha256=PROFILE_SOURCE_SHA256_V1_7
                if config.filter_profile.endswith("v1.7")
                else PROFILE_SOURCE_SHA256_V1_6,
            )
        report_ref = _save_exact(root, report_path, report, "v3-pilot-filter-report")
        partial_reference = partial_reference_required(root, upstream)
        prediction_path = artifacts / "predictions-v2.json"
        legacy_prediction_path = artifacts / "predictions.json"
        saved_path = prediction_path if prediction_path.exists() else legacy_prediction_path
        if saved_path.exists():
            evidence = load_model(saved_path, PilotPredictionEvidence)
            if (
                evidence.authority_id != authority_id
                or evidence.candidate_index_sha256 != upstream.candidate_index_ref.sha256
            ):
                raise AgentBoundaryError("Prediction evidence is not bound to this Pilot")
            for ref in evidence.evidence_refs:
                ref.verify(root)
        else:
            kernel_plan = load_model(upstream.pilot_bundle.pilot_plan.verify(root), PilotPlan)
            executor = generation_config.executor
            NvidiaSmiProbe().wait_until_idle(
                kernel_plan.devices,
                max_memory_used_mib=executor.max_memory_used_mib,
                max_utilization_percent=executor.max_utilization_percent,
                timeout_seconds=executor.resource_wait_timeout_seconds,
                poll_seconds=executor.resource_poll_seconds,
            )
            try:
                predictions, prediction_refs, msa_refs = _predict_selected_candidates(
                    root=root,
                    artifacts=artifacts,
                    runtime=runtime,
                    work=work_root / "work",
                    upstream=upstream,
                    candidates=index.candidates,
                    selected_ids={c.candidate_id for c in index.candidates},
                    providers=config.full_target_prediction.target_msa.resolved_providers(),
                    prediction_config=config.full_target_prediction,
                    adapter_builder=_complex_prediction_adapter_builder(
                        profile, config.full_target_prediction
                    ),
                    devices=kernel_plan.devices,
                    # Missing experimental coordinates cannot improve on retry.
                    maximum_attempts=1 if partial_reference else executor.max_task_attempts,
                    created_at=now,
                )
                evidence = PilotPredictionEvidence(
                    authority_id=authority_id,
                    candidate_index_sha256=upstream.candidate_index_ref.sha256,
                    predictions=predictions,
                    evidence_refs=(*prediction_refs, *msa_refs),
                )
            except ManifestStateError as error:
                evidence = incomplete_prediction_evidence(
                    root=root,
                    runtime=runtime,
                    artifacts=artifacts,
                    authority_id=authority_id,
                    index=index,
                    index_sha256=upstream.candidate_index_ref.sha256,
                    error=error,
                )
        if partial_reference and not prediction_path.exists():
            recovered, recovered_refs = recover_partial_reference_predictions(
                root=root,
                work=work_root / "work",
                runtime=runtime,
                artifacts=artifacts,
                upstream=upstream,
                prediction_config=config.full_target_prediction,
                adapter_builder=_complex_prediction_adapter_builder(
                    profile, config.full_target_prediction
                ),
                devices=load_model(
                    upstream.pilot_bundle.pilot_plan.verify(root), PilotPlan
                ).devices,
            )
            by_id = {p.candidate_id: p for p in evidence.predictions}
            for prediction in recovered:
                if (
                    prediction.candidate_id in by_id
                    and by_id[prediction.candidate_id] != prediction
                ):
                    raise AgentBoundaryError(
                        "Verified prediction changed during partial-reference recovery"
                    )
                by_id[prediction.candidate_id] = prediction
            evidence = evidence.model_copy(
                update={
                    "predictions": tuple(by_id[i] for i in sorted(by_id)),
                    "evidence_refs": (*evidence.evidence_refs, *recovered_refs),
                    "operational_failure": None
                    if len(by_id) == len(index.candidates)
                    else evidence.operational_failure,
                }
            )
        prediction_ref = _save_exact(root, prediction_path, evidence, "v3-pilot-predictions")
        measured = project_pilot_measurement(
            candidate_index=index,
            candidate_index_sha256=upstream.candidate_index_ref.sha256,
            filter_report=report,
            filter_report_sha256=report_ref.sha256,
            execution=projection,
            planned_by_strategy=allocations,
            predicted_candidate_ids=frozenset(p.candidate_id for p in evidence.predictions),
        )
        measured = attach_prediction_metrics(measured, evidence.predictions)
        generation_tasks = load_model(upstream.pilot_bundle.task_table.verify(root), TaskTable)
        prediction_state = load_latest_runtime_model(
            runtime / "full-target-state.json", FullTargetExecutionState
        )
        failed_generation: Counter[str] = Counter()
        for task in generation_tasks.tasks:
            failed_generation[task.strategy_id] += sum(
                a.status == TaskStatus.FAILED for a in task.attempts
            )
        candidate_strategy = {c.candidate_id: c.strategy_id for c in index.candidates}
        failed_prediction: Counter[str] = Counter()
        metric_collection_failures = {
            p.candidate_id: p.metric_collection_failed_attempts
            for p in evidence.predictions
            if isinstance(p, PartialReferencePrediction)
        }
        for task in prediction_state.tasks:
            if task.strategy_id not in candidate_strategy:
                raise AgentBoundaryError("Prediction execution log cites a foreign candidate")
            failed = sum(a.status == TaskStatus.FAILED for a in task.attempts)
            unavailable_collection = metric_collection_failures.get(task.strategy_id, 0)
            if unavailable_collection > failed:
                raise AgentBoundaryError("Prediction recovery lost its source attempt history")
            failed_prediction[candidate_strategy[task.strategy_id]] += (
                failed - unavailable_collection
            )
        measured = PilotMeasurement.model_validate(
            measured.model_copy(
                update={
                    "arms": tuple(
                        a.model_copy(
                            update={
                                "failed_generation_attempts": failed_generation[a.strategy_id],
                                "failed_prediction_attempts": failed_prediction[a.strategy_id],
                                "operational_failure_count": a.operational_failure_count
                                + a.valid_execution_products
                                - a.predicted_candidates,
                            }
                        )
                        for a in measured.arms
                    )
                }
            ).model_dump()
        )
        return {
            "status": "measured",
            "measurement": measured,
            "sources": {
                "authority": authority_id,
                "run_id": execution["run_id"],
                "candidate_index": upstream.candidate_index_ref.model_dump(mode="json"),
                "filter_report": report_ref.model_dump(mode="json"),
                "predictions": prediction_ref.model_dump(mode="json"),
            },
        }
