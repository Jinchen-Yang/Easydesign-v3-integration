"""Bounded Pilot dispatch through the existing local worker and command journal."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from easydesign.core import ArtifactRef, canonical_model_sha256, sha256_file
from easydesign.orchestration.config import (
    EasyDesignRunConfig,
    LoadedRunConfig,
    load_run_config,
)
from easydesign.orchestration.local_jobs import ACTIVE_JOB_STATUSES
from easydesign.orchestration.local_project import project_config_path
from easydesign.orchestration.research import _latest_foundation, _launch, _pilot_config, _runs
from easydesign.orchestration.workspace import load_resolved_run_config

from .contracts import AgentBoundaryError, ReconciliationRequired
from .phase34_authority import plan_for_design, verify_pilot_authority
from .phase34_contracts import ScientistPilotAuthority, ValidationExecutionAuthority
from .phase34_plan import BoundPilotPlan, ValidatedDesignContext
from .session_store import confined, identity
from .tools import scientific_environment


def validate_downstream_project(bridge: Any) -> LoadedRunConfig | None:
    """Accept only a journaled downstream config while preserving original Target binding."""
    loaded = load_run_config(
        confined(bridge.project, project_config_path(bridge.project)),
        source_base_dir=bridge.project,
    )
    if loaded.config.workflow.stop_after_stage in {1, 2}:
        return None
    digest = canonical_model_sha256(loaded.config)
    row = bridge.store.db.execute(
        "SELECT payload FROM commands WHERE operation IN ('phase34-pilot','phase34-scale') "
        "AND json_extract(payload,'$.config_sha256')=? ORDER BY rowid DESC LIMIT 1",
        (digest,),
    ).fetchone()
    if (
        row is None
        or canonical_model_sha256(
            EasyDesignRunConfig.model_validate(json.loads(row["payload"])["config"])
        )
        != digest
    ):
        raise AgentBoundaryError(
            "Downstream configuration lacks its exact runtime execution intent"
        )
    targets = [
        resolved.user_config
        for run in _runs(bridge.project)
        if (resolved := load_resolved_run_config(run.path)[0]).stop_after_stage == 1
    ]
    if not targets:
        raise AgentBoundaryError("Downstream execution has no preserved Target configuration")
    target = targets[-1]
    original = loaded.config.model_copy(
        update={
            "workflow": target.workflow,
            **{f"stage{n:02d}": getattr(target, f"stage{n:02d}") for n in range(2, 8)},
        }
    )
    if canonical_model_sha256(original) != canonical_model_sha256(target):
        raise AgentBoundaryError("Downstream execution changed the original Target configuration")
    if loaded.source_path is not None:
        confined(bridge.project, loaded.source_path)
    return replace(loaded, config=target)


def execution_config(
    bridge: Any, plan: BoundPilotPlan, proposal: dict[str, Any]
) -> EasyDesignRunConfig:
    return allocated_execution_config(bridge, plan, proposal, plan.execution_allocations)


def allocated_execution_config(
    bridge: Any, plan: BoundPilotPlan, proposal: dict[str, Any], selected: dict[str, int]
) -> EasyDesignRunConfig:
    """Compile exact counts while preserving the original scientific Design settings."""
    foundation = _latest_foundation(bridge.project)
    if foundation is None:
        raise AgentBoundaryError("Pilot requires an approved foundation")
    strategy_path = ArtifactRef.model_validate(proposal["strategy_ref"]).verify(bridge.project)
    config = _pilot_config(bridge.project, foundation, strategy_path, plan.prediction_backend)
    # Stage 05's legacy service includes automatic diagnostic expansion. The v3
    # measurement adapter reuses its kernels on exactly the authorized candidates.
    config = config.model_copy(
        update={
            "workflow": config.workflow.model_copy(update={"stop_after_stage": 4}),
            "stage05": None,
        }
    )
    # Pilot/Scale projection changes counts/scaffold membership, never scientific YAML.
    assert config.stage03 is not None and config.stage04 is not None
    variants = []
    for variant in config.stage03.variants or ():
        scaffolds = [
            s for s in variant.scaffold_ids if f"{variant.variant_id}-scaffold-{s}" in selected
        ]
        if not scaffolds:
            continue
        counts = {selected[f"{variant.variant_id}-scaffold-{s}"] for s in scaffolds}
        if len(counts) != 1:
            raise AgentBoundaryError("A micro arm requires a consistent per-scaffold count")
        variants.append(
            variant.model_copy(
                update={"scaffold_ids": tuple(scaffolds), "candidates_per_strategy": counts.pop()}
            )
        )
    native = tuple(
        v.model_copy(update={"candidates_per_strategy": selected[v.variant_id]})
        for v in config.stage03.native_variants or ()
        if v.variant_id in selected
    )
    projected_ids = {f"{v.variant_id}-scaffold-{s}" for v in variants for s in v.scaffold_ids}
    projected_ids.update(v.variant_id for v in native)
    if projected_ids != set(selected):
        raise AgentBoundaryError("Micro projection changed the compiled strategy identity")
    stage03 = config.stage03.model_copy(
        update={
            "variants": tuple(variants),
            "native_variants": native,
            "candidates_per_strategy": max(selected.values()),
        }
    )
    stage04 = config.stage04.model_copy(
        update={
            "required_complete_candidates_per_strategy": max(selected.values()),
            "executor": plan.executor,
        }
    )
    return EasyDesignRunConfig.model_validate(
        config.model_copy(update={"stage03": stage03, "stage04": stage04}).model_dump()
    )


def execute_pilot(
    bridge: Any,
    authority: ScientistPilotAuthority | ValidationExecutionAuthority,
) -> dict[str, Any]:
    """One authority maps to one run; a process restart reattaches its exact worker."""
    if isinstance(authority, ScientistPilotAuthority):
        plan = verify_pilot_authority(bridge, authority)
        approved = bridge.approved_design()
        assert approved is not None
        proposal = approved["proposal"]
    else:
        micro_plan = authority.pilot_plan
        proposal = bridge.current_design()
        if micro_plan is None or not micro_plan.validation_only or proposal is None:
            raise AgentBoundaryError("Micro execution needs a current bound validation plan")
        plan = micro_plan
        published = bridge.load_contract(
            kind="phase34-pilot-authority", contract_type=ValidationExecutionAuthority
        )
        if (
            published != authority
            or plan_for_design(
                bridge,
                proposal,
                prediction_backend=plan.prediction_backend,
                mode="validation-micro",
                execution_allocations=plan.execution_allocations,
                executor=plan.executor,
            )
            != plan
        ):
            raise AgentBoundaryError("Micro execution differs from the explicitly registered plan")
    config = execution_config(bridge, plan, proposal)
    config_sha = canonical_model_sha256(config)
    run_id = "pilot-v3-" + authority.authority_id[:24]
    binding = {"authority": authority.authority_id, "plan": canonical_model_sha256(plan)}
    with bridge.store.writer():
        command = bridge.store.prepare(
            bridge.thread,
            "phase34-pilot",
            binding,
            run_id=run_id,
            config_sha256=config_sha,
            config=config.model_dump(mode="json"),
        )
        if command["payload"]["config_sha256"] != config_sha:
            raise AgentBoundaryError("Authorized Pilot execution configuration changed")
        matches = [
            j for j in bridge.controller.list(project_id=bridge.project_id) if j.run_id == run_id
        ]
        originals = [j for j in matches if getattr(j, "operation", "run") == "run"]
        if len(originals) > 1:
            raise ReconciliationRequired(
                "Pilot has multiple execution receipts; reconcile original jobs"
            )
        job = matches[0] if matches else None
        if job is not None:
            if not originals:
                raise ReconciliationRequired("Pilot recovery has no original worker receipt")
            original = originals[0]
            if (
                original.project_root != bridge.project
                or original.config_path is None
                or original.step != 3
            ):
                raise AgentBoundaryError("Pilot worker does not belong to this project and stage")
            loaded = load_run_config(
                confined(bridge.project, original.config_path), source_base_dir=bridge.project
            )
            if canonical_model_sha256(loaded.config) != config_sha:
                raise AgentBoundaryError("Pilot worker used a different approved configuration")
            if any(
                getattr(j, "operation", "run") != "run"
                and (
                    j.operation != "resume"
                    or j.project_root != bridge.project
                    or j.run_root != bridge.context.runs_root / bridge.project_id / run_id
                    or j.step != 4
                )
                for j in matches
            ):
                raise AgentBoundaryError("Pilot recovery worker differs from the authorized run")
        elif command["state"] != "prepared":
            # A crash before any worker receipt is safe to retry only when no run was published.
            if (bridge.context.runs_root / bridge.project_id / run_id).exists():
                raise ReconciliationRequired("Pilot run exists without its worker receipt")
        if job is None:
            if any(
                j.status in ACTIVE_JOB_STATUSES
                for j in bridge.controller.list(project_id=bridge.project_id)
            ):
                raise AgentBoundaryError("An existing scientific job still owns this project")
            bridge.store.update(command["id"], "dispatching")
            bridge.failpoint("before_pilot_dispatch")
            with scientific_environment():
                _, job = _launch(
                    bridge.project,
                    phase="pilot",
                    config=config,
                    internal_start=3,
                    base=_latest_foundation(bridge.project),
                    run_id=run_id,
                    detach=True,
                )
            bridge.failpoint("after_pilot_dispatch")
        bridge.store.update(command["id"], "submitted", job_id=job.job_id, run_id=run_id)
        payload = {
            **binding,
            "job_id": job.job_id,
            "run_id": run_id,
            "config_sha256": config_sha,
            "validation_only": plan.validation_only,
        }
        previous = bridge.project_latest("phase34-pilot-execution")
        if previous is None or any(previous.get(k) != v for k, v in payload.items()):
            bridge.store.event(bridge.thread, "phase34-pilot-execution", payload)
        return {"status": job.status, **payload}


def register_micro_plan(
    bridge: Any, plan: BoundPilotPlan, *, reason: str
) -> ValidationExecutionAuthority:
    """Trusted CLI/validation harness only. This function is never an LLM tool."""
    if plan.mode != "validation-micro" or plan.project_id != bridge.project_id:
        raise AgentBoundaryError("Only a bounded current-project micro plan may be registered")
    proposal = bridge.current_design()
    if (
        proposal is None
        or plan_for_design(
            bridge,
            proposal,
            prediction_backend=plan.prediction_backend,
            mode="validation-micro",
            execution_allocations=plan.execution_allocations,
            executor=plan.executor,
        )
        != plan
    ):
        raise AgentBoundaryError("Micro plan does not match the current reviewed Design")
    authority = ValidationExecutionAuthority(
        authority_id=identity({"plan": plan.model_dump(mode="json"), "reason": reason}),
        fixture_id=plan.design_proposal_id,
        reason=reason,
        pilot_plan=plan,
    )
    bridge.publish_contract(
        kind="phase34-pilot-authority",
        contract=authority,
        dependencies={"plan": canonical_model_sha256(plan)},
    )
    context = ValidatedDesignContext(
        project_id=bridge.project_id,
        target_identity=plan.target_binding,
        target_bundle_sha256=sha256_file(bridge.target_state()["bundle_path"]),
        site_intent_sha256=identity(bridge.approved_site()["proposal"]["intent"]),
        strategy_sha256=plan.strategy_sha256,
        compiled_manifest_sha256=plan.compiled_manifest_sha256,
        execution_plan_sha256=canonical_model_sha256(plan),
        planned_candidates=sum(plan.production_allocations.values()),
        plan=plan,
        evidence_refs=tuple(bridge.design_snapshot(proposal)["evidence_refs"]),
    )
    bridge.publish_contract(
        kind="phase34-approved-gate3",
        contract=context,
        dependencies={"validation_authority": authority.authority_id},
    )
    return authority
