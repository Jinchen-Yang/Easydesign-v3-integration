"""Scale batch dispatch and metric projection through the existing scientific kernels."""

from __future__ import annotations

from typing import Any

from easydesign.core import ArtifactRef, canonical_model_sha256, load_model
from easydesign.orchestration.config import load_run_config
from easydesign.orchestration.local_jobs import ACTIVE_JOB_STATUSES
from easydesign.orchestration.research import _latest_foundation, _launch
from easydesign.stages.s05_pilot_filtering import PilotFilterReportV1_6

from .contracts import AgentBoundaryError, ReconciliationRequired
from .phase34_batches import ScaleBatchPlan, ScaleBatchReceipt, ScaleBatchStore
from .phase34_contracts import (
    DiversityContext,
    ExecutionProjection,
    ScaleCandidateLineageV3,
    ScaleCandidateObservation,
    ScaleCandidateValidity,
)
from .phase34_execution import allocated_execution_config
from .phase34_measurement import PilotPredictionEvidence, measure_execution
from .session_store import confined, identity
from .tools import scientific_environment


def dispatch_batch(bridge: Any, journal: ScaleBatchStore, batch: ScaleBatchPlan) -> dict[str, Any]:
    pilot_authority = bridge.pilot_authority()
    if pilot_authority is None or pilot_authority.pilot_plan is None:
        raise AgentBoundaryError("Scale lost its current Design/Pilot authority")
    config = allocated_execution_config(
        bridge, pilot_authority.pilot_plan, bridge.selected_design(), batch.strategy_allocations
    )
    config_sha = canonical_model_sha256(config)
    run_id = "scale-v3-" + identity({"manifest": journal.digest, "batch": batch.batch_id})[:24]
    binding = {"manifest": journal.digest, "batch": batch.batch_id}
    with bridge.store.writer():
        command = bridge.store.prepare(
            bridge.thread,
            "phase34-scale",
            binding,
            run_id=run_id,
            config_sha256=config_sha,
            config=config.model_dump(mode="json"),
        )
        if command["payload"]["config_sha256"] != config_sha:
            raise AgentBoundaryError("Scale execution configuration changed after authorization")
        jobs = [
            j for j in bridge.controller.list(project_id=bridge.project_id) if j.run_id == run_id
        ]
        originals = [j for j in jobs if j.operation == "run"]
        if len(originals) > 1:
            raise ReconciliationRequired("Scale batch has multiple original run receipts")
        if originals:
            original = originals[0]
            if (
                original.project_root != bridge.project
                or original.config_path is None
                or original.step != 3
            ):
                raise AgentBoundaryError("Scale worker project or stage does not match")
            loaded = load_run_config(
                confined(bridge.project, original.config_path), source_base_dir=bridge.project
            )
            if canonical_model_sha256(loaded.config) != config_sha:
                raise AgentBoundaryError(
                    "Scale worker configuration differs from its approved batch"
                )
            root = bridge.context.runs_root / bridge.project_id / run_id
            if any(
                j.operation != "run"
                and (
                    j.operation != "resume"
                    or j.run_root != root
                    or j.project_root != bridge.project
                    or j.step != 4
                )
                for j in jobs
            ):
                raise AgentBoundaryError("Scale recovery worker does not belong to the bound run")
            job = jobs[0]  # controller lists newest first, including authorized recovery receipts
        else:
            if jobs or (bridge.context.runs_root / bridge.project_id / run_id).exists():
                raise ReconciliationRequired("Scale run exists without its original worker receipt")
            if any(
                j.status in ACTIVE_JOB_STATUSES
                for j in bridge.controller.list(project_id=bridge.project_id)
            ):
                return {"status": "waiting-for-project-worker", **binding}
            bridge.store.update(command["id"], "dispatching")
            with scientific_environment():
                _, job = _launch(
                    bridge.project,
                    phase="scale",
                    config=config,
                    internal_start=3,
                    base=_latest_foundation(bridge.project),
                    run_id=run_id,
                    detach=True,
                )
        bridge.store.update(command["id"], "submitted", job_id=job.job_id, run_id=run_id)
        return {
            "status": job.status,
            "job_id": job.job_id,
            "run_id": run_id,
            "config_sha256": config_sha,
            **binding,
        }


def measure_batch(
    bridge: Any, journal: ScaleBatchStore, batch: ScaleBatchPlan, execution: dict[str, Any]
) -> dict[str, Any]:
    if journal.manifest.campaign.evidence_policy == "boltzgen-native-v1":
        from .phase4_native import measure_native_batch

        return measure_native_batch(bridge, journal, batch, execution)
    campaign = journal.manifest.campaign
    authority = bridge.pilot_authority()
    assert authority is not None and authority.pilot_plan is not None
    count = sum(batch.strategy_allocations.values())
    result = measure_execution(
        bridge,
        authority_id="scale-" + identity({"manifest": journal.digest, "batch": batch.batch_id}),
        plan=authority.pilot_plan,
        execution=execution,
        allocations=batch.strategy_allocations,
        projection=ExecutionProjection(
            mode=campaign.execution.mode,
            requested_production_candidates=count,
            execution_candidates=count,
            uses_real_generation_backend=True,
            uses_real_prediction_backend=True,
            purpose="One exact Gate 4 authorized Scale batch; no automatic expansion.",
        ),
    )
    if result["status"] != "measured":
        return result
    root, _ = bridge.run(execution["run_id"])
    sources = result["sources"]
    predictions = load_model(
        ArtifactRef.model_validate(sources["predictions"]).verify(root), PilotPredictionEvidence
    )
    report = load_model(
        ArtifactRef.model_validate(sources["filter_report"]).verify(root), PilotFilterReportV1_6
    )
    by_id = {p.candidate_id: p for p in predictions.predictions}
    observations, sequences = [], {}
    for c in result["measurement"].candidates:
        line = c.lineage
        cid = (
            "candidate-"
            + identity({"run": execution["run_id"], "candidate": line.candidate_id})[:32]
        )
        prediction = by_id.get(line.candidate_id)
        pid = (
            "prediction-" + identity({"candidate": cid, "seed": prediction.seed})[:24]
            if prediction
            else None
        )
        refs = [line.original_structure, line.refolded_structure]
        if line.design_mask_source:
            refs.append(line.design_mask_source)
        if prediction:
            refs.extend(
                [
                    prediction.predicted_structure,
                    prediction.summary_confidence,
                    prediction.full_confidence,
                ]
            )
        for ref in refs:
            ref.verify(root)
        observations.append(
            ScaleCandidateObservation(
                lineage=ScaleCandidateLineageV3(
                    campaign_id=campaign.campaign_id,
                    source_run_id=execution["run_id"],
                    batch_id=batch.batch_id,
                    shard_id=batch.batch_id,
                    candidate_id=cid,
                    strategy_id=line.strategy_id,
                    strategy_ordinal=line.ordinal_within_strategy,
                    generation_task_id=line.task_id,
                    generation_attempt=line.task_attempt_number,
                    backend_candidate_id=line.backend_candidate_id,
                    prediction_id=pid,
                    prediction_seed=prediction.seed if prediction else None,
                    prediction_ids=(pid,) if pid else (),
                    prediction_seeds=(prediction.seed,) if prediction else (),
                    sequence_sha256=line.sequence_sha256,
                    artifact_refs=tuple(refs),
                ),
                validity=ScaleCandidateValidity.VALID_EVALUATED
                if prediction
                else ScaleCandidateValidity.UNEVALUABLE,
                metrics=c.metrics,
                legacy_policy_annotations=c.legacy_policy_annotations,
                legacy_policy_pass=c.legacy_policy_pass,
                development_score=c.development_score if prediction else None,
                failure_reason=None if prediction else "Independent prediction unavailable",
                diversity=DiversityContext(
                    sequence_cluster_id="seq-" + line.sequence_sha256[:32],
                    method="exact-sequence-sha256; advisory identity clusters; pose unverified",
                ),
                evaluation_level="deep" if prediction else "unavailable",
            )
        )
        sequences[cid] = next(
            r.sequence for r in report.candidate_records if r.candidate_id == line.candidate_id
        )
    receipt = ScaleBatchReceipt(
        manifest_sha256=journal.digest,
        batch_id=batch.batch_id,
        state="completed",
        source_run_id=execution["run_id"],
        candidates=tuple(observations),
        source_refs=tuple(
            f"{execution['run_id']}:{sources[k]['relative_path']}"
            for k in ("candidate_index", "filter_report", "predictions")
        ),
    )
    # The sequence map is a verified projection; persist it before declaring the batch complete.
    bridge.store.event(
        bridge.thread,
        "phase34-scale-batch-sequences",
        {
            "manifest": journal.digest,
            "batch": batch.batch_id,
            "sequences": sequences,
            "receipt_sha256": canonical_model_sha256(receipt),
        },
    )
    journal.append(receipt)
    return {"status": "scale-batch-measured", "batch_id": batch.batch_id}
