"""Explicit, verified import of completed native task shards; never a remote executor.

Original run/worker state is retained. An import attests only that an already approved
Pilot's exact population is available from declared immutable scientific artifacts.
This runtime API has no model tool and neither grants approval nor launches compute.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from easydesign.core import (
    ArtifactRef,
    StageId,
    canonical_model_sha256,
    load_model,
    sha256_file,
)
from easydesign.orchestration.stage05 import _latest_manifest, _stage_from_run
from easydesign.orchestration.task_tracking import load_latest_runtime_model
from easydesign.stages.s03_boltzgen_configuration import StrategyBundle
from easydesign.stages.s04_pilot_generation import CandidateRecord, PilotExecutionState, PilotPlan

from .contracts import AgentBoundaryError
from .phase3_native import profiles_from_tasks, project_native_measurement, refold_contact_metrics
from .phase34_contracts import ExecutionProjection, FrozenContract, PilotMeasurement
from .phase34_plan import ApprovedGate3Context, compiled_records
from .session_store import confined, identity


class NativePilotImport(FrozenContract):
    authority_id: str
    execution_job_id: str
    destination_run_id: str
    source_manifest_sha256s: tuple[str, ...]
    measurement_sha256: str
    source_refs: tuple[ArtifactRef, ...]
    imported_by: str
    semantics: str = "Verified native task population; original worker/run status is unchanged."


def _ref(root: Path, path: Path, name: str) -> ArtifactRef:
    path = confined(root, path)
    return ArtifactRef.from_file(
        run_root=root,
        relative_path=path.relative_to(root).as_posix(),
        artifact_id=name,
        role="native-pilot-import-source",
        file_format=path.suffix.lstrip(".") or "text",
    )


def _rebase(ref: ArtifactRef, source: Path, destination: Path) -> ArtifactRef:
    ref.verify(source)
    result = ref.model_copy(
        update={"relative_path": (source.relative_to(destination) / ref.relative_path).as_posix()}
    )
    result.verify(destination)
    return result


def _state_source(root: Path, path: Path, state: PilotExecutionState) -> ArtifactRef:
    # Same immutable revision convention as load_latest_runtime_model; retain the selected bytes.
    choices = [path, *sorted(path.with_name(path.name + ".revisions").glob("revision-*.json"))]
    for p in reversed(choices):
        try:
            if load_model(p, PilotExecutionState) == state:
                return _ref(root, p, "native-execution-state")
        except (ValueError, OSError):
            continue
    raise AgentBoundaryError("Native import cannot locate its verified state revision")


def import_native_pilot_shards(
    bridge: Any, *, source_roots: tuple[Path, ...], imported_by: str
) -> NativePilotImport:
    """Source roots must be explicit copies inside the current execution run's directory."""
    authority = bridge.pilot_authority()
    execution = bridge.project_latest("phase34-pilot-execution")
    if not authority or not execution or execution["authority"] != authority.authority_id:
        raise AgentBoundaryError("Native import requires current Gate 3 execution authority")
    plan = authority.pilot_plan
    if plan is None or plan.validation_only or not imported_by.strip() or not source_roots:
        raise AgentBoundaryError("Native import needs formal authority and an explicit operator")
    context = bridge.load_contract(
        kind="phase34-approved-gate3", contract_type=ApprovedGate3Context
    )
    destination, _ = bridge.run(execution["run_id"])
    proposal = bridge.selected_design()
    expected = {r.strategy_id: r for r in compiled_records(bridge, proposal)}
    sources, candidates, profiles, additions, manifest_shas = [], [], {}, {}, []
    failed_attempts: dict[str, int] = {}
    seen_strategies: set[str] = set()
    for raw_root in source_roots:
        root = confined(destination, raw_root)
        run, manifest_path = _latest_manifest(root)
        if run.project_id != bridge.project_id:
            raise AgentBoundaryError("Imported run belongs to a different project")
        config_ref = run.config_snapshot
        config_ref.verify(root)
        stage1, stage1_ref = _stage_from_run(root, run, StageId.TARGET_PREPARATION)
        stage3, stage3_ref = _stage_from_run(root, run, StageId.BOLTZGEN_CONFIGURATION)
        target_ref = stage1.require_output("target-bundle")
        if target_ref.sha256 != context.target_bundle_sha256:
            raise AgentBoundaryError("Imported Pilot target differs from the approved target")
        bundle_ref = stage3.require_output("strategy-bundle")
        bundle = load_model(bundle_ref.verify(root), StrategyBundle)
        if bundle.hotspots_sha256 != plan.hotspot_sha256:
            raise AgentBoundaryError("Imported Pilot hotspot identity differs from Gate 3")
        stage = root / "04-pilot-generation/attempt-0001"
        kernel_path = stage / "artifacts/pilot-plan.json"
        kernel = load_model(kernel_path, PilotPlan)
        state_path = stage / "runtime/task-state.json"
        state = load_latest_runtime_model(state_path, PilotExecutionState)
        if (
            state.plan_sha256 != sha256_file(kernel_path)
            or kernel.strategy_bundle_sha256 != bundle_ref.sha256
        ):
            raise AgentBoundaryError("Imported native task plan changed its compiled bundle")
        records = {r.strategy_id: r for r in bundle.strategies}
        by_task = {t.task_id: t for t in state.tasks}
        active = {c.strategy_id for c in state.candidates}
        if active & seen_strategies or active - set(plan.execution_allocations):
            raise AgentBoundaryError("Native shards overlap or exceed approved strategy scope")
        seen_strategies.update(active)
        for strategy in active:
            source, reviewed = records[strategy], expected[strategy]
            fields = (
                "region_id",
                "scaffold_id",
                "binding_label_seq_ids",
                "avoid_label_seq_ids",
                "design_specification_sha256",
                "variant_scaffold_sha256",
                "scaffold_template",
            )
            if any(getattr(source, key) != getattr(reviewed, key) for key in fields):
                raise AgentBoundaryError(
                    "Imported native YAML/scaffold differs from approved Design"
                )
        group_counts = Counter(c.strategy_id for c in state.candidates)
        for candidate in state.candidates:
            task = by_task[candidate.task_id]
            if (
                task.status != "succeeded"
                or task.strategy_id != candidate.strategy_id
                or group_counts[candidate.strategy_id]
                != plan.execution_allocations[candidate.strategy_id]
                or task.collected_candidates != group_counts[candidate.strategy_id]
                or candidate.candidate_id not in task.candidate_ids
            ):
                raise AgentBoundaryError(
                    "Imported native task is incomplete or has inconsistent identity"
                )
        group_profiles, config_refs = profiles_from_tasks(root, state.candidates, state.tasks)
        for strategy, profile in group_profiles.items():
            profiles[strategy] = profile.model_copy(
                update={"configuration_ref": _rebase(profile.configuration_ref, root, destination)}
            )
        for c in state.candidates:
            additions[c.candidate_id] = refold_contact_metrics(root, c, records[c.strategy_id])
            converted = {}
            for field in ("original_structure", "refolded_structure", "design_mask_source"):
                ref = getattr(c, field)
                if ref is not None:
                    converted[field] = _rebase(ref, root, destination)
                    sources.append(converted[field])
            candidates.append(
                CandidateRecord.model_validate(c.model_copy(update=converted).model_dump())
            )
        for task in state.tasks:
            if task.strategy_id in active:
                failed_attempts[task.strategy_id] = sum(a.status == "failed" for a in task.attempts)
        manifest_ref = _ref(root, manifest_path, "native-source-manifest")
        manifest_shas.append(manifest_ref.sha256)
        for ref in (
            manifest_ref,
            config_ref,
            stage1_ref,
            stage3_ref,
            target_ref,
            bundle_ref,
            _ref(root, kernel_path, "native-source-plan"),
            _state_source(root, state_path, state),
            *config_refs,
        ):
            sources.append(_rebase(ref, root, destination))
    if dict(Counter(c.strategy_id for c in candidates)) != plan.execution_allocations:
        raise AgentBoundaryError("Imported native population does not complete the approved Pilot")
    refs = tuple({(r.relative_path, r.sha256): r for r in sources}.values())
    source_identity = identity({"sources": [r.model_dump(mode="json") for r in refs]})
    measured = project_native_measurement(
        candidates=tuple(candidates),
        profiles=profiles,
        planned=plan.execution_allocations,
        source_sha256=source_identity,
        source_refs=refs,
        additional_metrics=additions,
        failed_attempts=failed_attempts,
        execution=ExecutionProjection(
            mode=plan.mode,
            requested_production_candidates=sum(plan.production_allocations.values()),
            execution_candidates=sum(plan.execution_allocations.values()),
            uses_real_generation_backend=True,
            uses_real_prediction_backend=False,
            purpose="Explicit verified native task import; original worker states retained.",
        ),
    )
    receipt = NativePilotImport(
        authority_id=authority.authority_id,
        execution_job_id=execution["job_id"],
        destination_run_id=execution["run_id"],
        source_manifest_sha256s=tuple(manifest_shas),
        measurement_sha256=canonical_model_sha256(measured),
        source_refs=refs,
        imported_by=imported_by,
    )
    bridge.publish_contract(
        kind="phase34-pilot-measurement",
        contract=measured,
        dependencies={
            "authority": authority.authority_id,
            "execution_job_id": execution["job_id"],
            "measurement_version": "native-boltz2-pilot-v1",
        },
    )
    bridge.publish_contract(
        kind="phase34-native-pilot-import",
        contract=receipt,
        dependencies={
            "authority": authority.authority_id,
            "measurement": receipt.measurement_sha256,
        },
    )
    return receipt


def current_native_import(bridge: Any, execution: dict[str, Any], authority_id: str) -> bool:
    event = bridge.project_latest("phase34-native-pilot-import")
    measured = bridge.project_latest("phase34-pilot-measurement")
    if event is None or measured is None or event["dependencies"].get("authority") != authority_id:
        return False
    receipt = bridge.load_contract(
        kind="phase34-native-pilot-import", contract_type=NativePilotImport
    )
    if (
        receipt.measurement_sha256 != measured["contract_sha256"]
        or receipt.authority_id != authority_id
        or receipt.execution_job_id != execution["job_id"]
        or receipt.destination_run_id != execution["run_id"]
    ):
        return False
    measurement = bridge.load_contract(
        kind="phase34-pilot-measurement", contract_type=PilotMeasurement
    )
    if measurement.native_evidence is None or any(
        a.planned_candidates != a.generated_candidates for a in measurement.arms
    ):
        raise AgentBoundaryError("Imported native evidence no longer covers the approved scope")
    root, _ = bridge.run(execution["run_id"])
    for ref in receipt.source_refs:
        ref.verify(root)
    return True
