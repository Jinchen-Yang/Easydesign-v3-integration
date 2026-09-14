"""Operational-negative Pilot evidence; preserve partial products without fabricated metrics."""

from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from easydesign.core import TaskRecord, TaskStatus, canonical_model_sha256, load_model, sha256_file
from easydesign.filtering.nanobody_v1_5 import _required_sequence
from easydesign.orchestration.task_tracking import load_latest_runtime_model
from easydesign.orchestration.workspace import load_resolved_run_config
from easydesign.stages.s04_pilot_generation import CandidateRecord, PilotExecutionState, PilotPlan

from .contracts import AgentBoundaryError
from .phase34_contracts import ExecutionProjection, PilotArmDenominator, PilotMeasurement


def project_generation_failure(bridge: Any) -> dict[str, Any]:
    authority = bridge.pilot_authority()
    execution = bridge.project_latest("phase34-pilot-execution")
    if authority is None or execution is None or execution["authority"] != authority.authority_id:
        raise AgentBoundaryError("Operational evidence has no current execution authority")
    job = bridge.controller.load(execution["job_id"])
    if (
        job.project_root != bridge.project
        or job.run_id != execution["run_id"]
        or job.step not in {3, 4}
    ):
        raise AgentBoundaryError("Failure receipt is outside the authorized Pilot run")
    if job.status in {"queued", "running", "drain-requested", "succeeded"}:
        raise AgentBoundaryError("Only terminal incomplete generation can be projected as failure")
    plan = authority.pilot_plan
    assert plan is not None
    candidates: tuple[CandidateRecord, ...] = ()
    tasks: tuple[TaskRecord, ...] = ()
    source_sha = canonical_model_sha256(job)
    source_kind: Literal["generation-failure-receipt", "partial-generation-state"] = (
        "generation-failure-receipt"
    )
    refs = [str(bridge.controller.path(job.job_id))]
    run_path = bridge.context.runs_root / bridge.project_id / execution["run_id"]
    if run_path.exists():
        root, _ = bridge.run(execution["run_id"])
        resolved, _ = load_resolved_run_config(root)
        if canonical_model_sha256(resolved.user_config) != execution["config_sha256"]:
            raise AgentBoundaryError("Failed Pilot configuration differs from its authorized plan")
        stage = root / "04-pilot-generation/attempt-0001"
        state_path = stage / "runtime/task-state.json"
        if state_path.exists():
            state = load_latest_runtime_model(state_path, PilotExecutionState)
            kernel_path = stage / "artifacts/pilot-plan.json"
            kernel_plan = load_model(kernel_path, PilotPlan)
            if (
                state.plan_sha256 != sha256_file(kernel_path)
                or {s.strategy_id: s.required_complete_candidates for s in kernel_plan.strategies}
                != plan.execution_allocations
            ):
                raise AgentBoundaryError("Partial Pilot changed its authorized strategy population")
            candidates, tasks = state.candidates, state.tasks
            source_sha, source_kind = canonical_model_sha256(state), "partial-generation-state"
            refs.append(str(state_path))
            for c in candidates:
                for ref in (c.original_structure, c.refolded_structure, c.design_mask_source):
                    if ref:
                        ref.verify(root)
    counts = Counter(c.strategy_id for c in candidates)
    if set(counts) - set(plan.execution_allocations):
        raise AgentBoundaryError("Partial Pilot includes an unauthorized strategy")
    failures = {
        t.strategy_id: sum(a.status == TaskStatus.FAILED for a in t.attempts) for t in tasks
    }
    arms = tuple(
        PilotArmDenominator(
            strategy_id=s,
            planned_candidates=n,
            generated_candidates=counts[s],
            valid_execution_products=counts[s],
            predicted_candidates=0,
            metric_evaluable_candidates=0,
            unique_sequences=len({_required_sequence(c) for c in candidates if c.strategy_id == s}),
            legacy_policy_pass_count=0,
            operational_failure_count=n - counts[s],
            failed_generation_attempts=failures.get(s, 0),
            missing_by_metric={"structure-and-prediction-metrics": counts[s]},
        )
        for s, n in sorted(plan.execution_allocations.items())
    )
    measurement = PilotMeasurement(
        execution=ExecutionProjection(
            mode=plan.mode,
            requested_production_candidates=sum(plan.production_allocations.values()),
            execution_candidates=sum(plan.execution_allocations.values()),
            uses_real_generation_backend=any(t.attempts for t in tasks),
            uses_real_prediction_backend=False,
            purpose="Incomplete generation; retained products lack scientific measurements.",
        ),
        source_candidate_index_sha256=source_sha,
        source_candidate_index_kind=source_kind,
        source_filter_report_sha256=None,
        candidates=(),
        unmeasured_candidates=candidates,
        arms=arms,
    )
    bridge.store.event(
        bridge.thread,
        "phase34-pilot-operational-sources",
        {
            "authority": authority.authority_id,
            "job_id": job.job_id,
            "source_refs": refs,
            "source_sha256": source_sha,
            "source_kind": source_kind,
        },
    )
    bridge.publish_contract(
        kind="phase34-pilot-measurement",
        contract=measurement,
        dependencies={"authority": authority.authority_id, "execution_job_id": job.job_id},
    )
    return {
        "status": "pilot-operational-evidence-ready",
        "measurement_sha256": canonical_model_sha256(measurement),
    }
