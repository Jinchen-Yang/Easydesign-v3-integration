"""A failed bound Target job is a deterministic, one-way agent boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import SystemMessage

from easydesign.agent.cli import run_session
from easydesign.agent.contracts import (
    TargetInterpretation,
    TargetJobTerminalFailure,
)
from easydesign.agent.control_flow import next_action
from easydesign.agent.harness import RoleBoundary
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.phase2_tools import PHASE2_ALLOWED
from easydesign.agent.phase34_runtime import Phase34Runtime
from easydesign.agent.target_assessment import register_target
from easydesign.agent.tools import build_tools
from easydesign.core import (
    ArtifactRef,
    Attempt,
    ConfigurationError,
    ErrorInfo,
    ExecutionStatus,
    StageManifest,
    sha256_file,
)
from tests.agent_support import ScriptedModel, scripted_config


def _failure_view(
    bridge: Phase2Bridge,
    tmp_path: Any,
    monkeypatch: Any,
    *,
    job_status: str = "operational-failed",
    retryable: bool = False,
    receipt_run_id: str | None = "run-synthetic",
    current_run_id: str = "run-synthetic",
    manifest_status: ExecutionStatus = ExecutionStatus.FAILED,
    workflow_state: Any = None,
    current_exists: bool = True,
    integrity_status: str = "verified",
    include_stage_ref: bool = True,
    include_typed_error: bool = True,
    corrupt_stage_ref: bool = False,
    resolve_error: Exception | None = None,
    expect_failure: bool = True,
) -> dict[str, Any] | None:
    now = datetime.now(UTC)
    stage = StageManifest(
        stage_id="01-target-preparation",
        contract_version="1.0",
        status=ExecutionStatus.FAILED,
        created_at=now,
        completed_at=now,
        attempts=(
            (
                Attempt(
                    attempt_id="attempt-0001",
                    status=ExecutionStatus.FAILED,
                    created_at=now,
                    started_at=now,
                    ended_at=now,
                    backend_name="synthetic-source",
                    executor_name="in-process",
                    error=ErrorInfo(
                        code="stage01-source-failed",
                        message="synthetic deterministic source failure",
                        retryable=retryable,
                    ),
                ),
            )
            if include_typed_error
            else ()
        ),
    )
    root = tmp_path / "failed-run"
    path = root / "01-target-preparation/stage-manifest.v0001.json"
    path.parent.mkdir(parents=True)
    path.write_text(stage.model_dump_json(indent=2), encoding="utf-8")
    ref = ArtifactRef(
        artifact_id="stage-01-manifest",
        role="stage-manifest",
        relative_path=path.relative_to(root).as_posix(),
        file_format="json",
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        producer_stage="01-target-preparation",
        producer_attempt="attempt-0001",
    )
    if corrupt_stage_ref:
        ref = ref.model_copy(update={"sha256": "0" * 64})
    manifest_path = root / "manifests/run-manifest.v0001.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        "easydesign.agent.tools.TargetBridge._target_job_status",
        lambda self: {
            "status": job_status,
            "job_id": "job-synthetic",
            "run_id": receipt_run_id,
            "error": "ValueError: wrapper must not replace the attempt failure",
            "phase": "prepare",
        },
    )
    def resolve(_project: Any, required: bool = False) -> Any:
        if resolve_error is not None:
            raise resolve_error
        if not current_exists:
            return None
        return SimpleNamespace(
            run_id=current_run_id,
            latest_manifest=manifest_path,
            status=manifest_status,
            integrity_status=integrity_status,
            integrity_message=(
                None if integrity_status == "verified" else "synthetic integrity failure"
            ),
        )

    monkeypatch.setattr("easydesign.agent.tools.resolve_project_run", resolve)
    monkeypatch.setattr(
        bridge,
        "run",
        lambda run_id=None: (
            root,
            SimpleNamespace(
                run_id=current_run_id,
                revision=1,
                status=manifest_status,
                workflow_state=workflow_state,
                stage_manifest_refs=(ref,) if include_stage_ref else (),
            ),
        ),
    )
    failure = bridge.target_terminal_failure()
    if expect_failure:
        assert failure is not None
    return failure


@pytest.mark.parametrize("job_status", ["operational-failed", "scientific-failed"])
def test_failed_target_job_preserves_attempt_failure_and_is_terminal(
    bridge: Any, tmp_path: Any, monkeypatch: Any, job_status: str
) -> None:
    phase2 = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    failure = _failure_view(phase2, tmp_path, monkeypatch, job_status=job_status)
    assert failure is not None

    assert failure == {
        "terminal_state": "failed",
        "code": "stage01-source-failed",
        "message": "synthetic deterministic source failure",
        "retryable": False,
        "failure_ref": failure["failure_ref"],
        "attempt_id": "attempt-0001",
        "job_id": "job-synthetic",
        "run_id": "run-synthetic",
        "current_run_id": "run-synthetic",
        "manifest_status": "failed",
        "job_status": job_status,
        "job_error": "ValueError: wrapper must not replace the attempt failure",
    }
    assert failure["failure_ref"].startswith(
        "01-target-preparation/stage-manifest.v0001.json#sha256="
    )
    state = phase2.scientific_state()
    assert state == {
        "scientific_state": "failed",
        "gate_type": "target-structure",
        "next_specialist": "none",
        "failure": failure,
    }
    action = next_action(phase2)
    assert action.tool is None
    result = phase2.terminal_result("model prose must not replace the failure")
    assert result["status"] == "failed"
    assert result["scientific_state"] == "failed"
    assert result["reason"] == "target-preparation-failed"
    assert result["failure"] == failure
    assert result["message"] == "stage01-source-failed: synthetic deterministic source failure"


def test_retryable_failure_stops_models_but_reports_recovery_required(
    bridge: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    phase2 = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    failure = _failure_view(phase2, tmp_path, monkeypatch, retryable=True)
    assert failure is not None

    assert failure["retryable"] is True
    assert failure["terminal_state"] == "recovery-required"
    assert phase2.scientific_state()["scientific_state"] == "recovery-required"
    result = phase2.terminal_result("")
    assert result["status"] == "recovery-required"
    assert result["reason"] == "target-preparation-recovery-required"


@pytest.mark.parametrize(
    ("manifest_status", "workflow_state", "receipt_run_id", "current_run_id"),
    [
        (ExecutionStatus.SUCCEEDED, None, "run-synthetic", "run-synthetic"),
        (ExecutionStatus.RUNNING, object(), "run-synthetic", "run-synthetic"),
        (ExecutionStatus.SUCCEEDED, None, "run-old", "run-current"),
    ],
)
def test_newer_success_or_pending_gate_overrides_stale_failed_receipt(
    bridge: Any,
    tmp_path: Any,
    monkeypatch: Any,
    manifest_status: ExecutionStatus,
    workflow_state: Any,
    receipt_run_id: str,
    current_run_id: str,
) -> None:
    phase2 = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    failure = _failure_view(
        phase2,
        tmp_path,
        monkeypatch,
        manifest_status=manifest_status,
        workflow_state=workflow_state,
        receipt_run_id=receipt_run_id,
        current_run_id=current_run_id,
        expect_failure=False,
    )
    assert failure is None
    assert phase2.target_terminal_failure() is None


def test_receipt_without_exact_run_failure_requires_reconciliation(
    bridge: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    phase2 = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    failure = _failure_view(
        phase2,
        tmp_path,
        monkeypatch,
        receipt_run_id=None,
    )
    assert failure is not None
    assert failure["terminal_state"] == "recovery-required"
    assert failure["code"] == "target-job-reconciliation-required"
    assert failure["retryable"] is None
    assert failure["attempt_id"] is None
    assert failure["failure_ref"].startswith("manifests/run-manifest.v0001.json#sha256=")


@pytest.mark.parametrize(
    ("options", "message_fragment", "authority_fragment"),
    [
        ({"current_exists": False}, "no current project run", None),
        (
            {"integrity_status": "unavailable"},
            "manifest could not be verified",
            "synthetic integrity failure",
        ),
        ({"include_stage_ref": False}, "no checksum-bound Stage 01 manifest", None),
        ({"include_typed_error": False}, "no typed attempt error", None),
        (
            {"corrupt_stage_ref": True},
            "Stage 01 failure authority could not be read and verified",
            "ArtifactIntegrityError",
        ),
        (
            {"resolve_error": ConfigurationError("ambiguous project runs")},
            "run authority could not be resolved",
            "ConfigurationError",
        ),
    ],
)
def test_unavailable_target_failure_authority_requires_typed_reconciliation(
    bridge: Any,
    tmp_path: Any,
    monkeypatch: Any,
    options: dict[str, Any],
    message_fragment: str,
    authority_fragment: str | None,
) -> None:
    phase2 = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    failure = _failure_view(phase2, tmp_path, monkeypatch, **options)
    assert failure is not None
    assert failure["terminal_state"] == "recovery-required"
    assert failure["code"] == "target-job-reconciliation-required"
    assert failure["retryable"] is None
    assert message_fragment in failure["message"]
    if authority_fragment is not None:
        assert authority_fragment in failure["authority_error"]


@pytest.mark.parametrize("active_status", ["queued", "running"])
def test_newer_active_target_binding_overrides_stale_failed_receipt(
    bridge: Any, active_status: str
) -> None:
    old = SimpleNamespace(
        job_id="job-old-failed",
        status="operational-failed",
        project_id=bridge.project_id,
        project_root=bridge.project,
        step=1,
        run_id="run-old",
        run_root=None,
        error="old failure",
    )
    active = SimpleNamespace(
        job_id="job-current-active",
        status=active_status,
        project_id=bridge.project_id,
        project_root=bridge.project,
        step=1,
        run_id="run-current",
        run_root=None,
        process_id=None,
        error=None,
    )
    jobs = {old.job_id: old, active.job_id: active}
    bridge.controller = SimpleNamespace(load=jobs.__getitem__)
    for label, job in (("old", old), ("current", active)):
        command = bridge.store.prepare(
            bridge.thread,
            "prepare",
            {"target-binding-regression": label},
            job_id=job.job_id,
        )
        if label == "old":
            bridge.store.event(
                bridge.thread,
                "command-ref",
                {"command_id": command["id"], "job_id": job.job_id},
            )

    assert bridge.get_job_status()["status"] == active_status
    assert bridge.target_terminal_failure() is None


@pytest.mark.parametrize(
    ("phase", "job_status"),
    [
        ("pilot", "operational-failed"),
        ("pilot", "scientific-failed"),
        ("scale", "operational-failed"),
        ("scale", "scientific-failed"),
    ],
)
def test_phase34_downstream_failure_is_not_a_target_failure(
    design_bridge: Any, monkeypatch: Any, phase: str, job_status: str
) -> None:
    runtime = Phase34Runtime(
        design_bridge.project, design_bridge.thread, design_bridge.store
    )
    original_controller = runtime.controller
    target_job = next(
        job
        for job in original_controller.list(project_id=runtime.project_id)
        if job.step == 1
    )
    command = runtime.store.prepare(
        runtime.thread,
        "prepare",
        {"target-binding-regression": f"{phase}-{job_status}"},
        job_id=target_job.job_id,
    )
    runtime.store.event(
        runtime.thread,
        "command-ref",
        {"command_id": command["id"], "job_id": target_job.job_id},
    )
    downstream = SimpleNamespace(
        job_id=f"job-{phase}", status=job_status, run_id=f"run-{phase}", step=3
    )
    runtime.controller = SimpleNamespace(
        load=lambda job_id: (
            downstream if job_id == downstream.job_id else original_controller.load(job_id)
        ),
        list=original_controller.list,
    )
    if phase == "pilot":
        monkeypatch.setattr(
            runtime, "pilot_authority", lambda: SimpleNamespace(authority_id="authority")
        )
        records = {
            "phase34-pilot-execution": {
                "authority": "authority",
                "job_id": downstream.job_id,
            }
        }
    else:
        records = {
            "phase34-scale-execution": {
                "manifest": "manifest",
                "job_id": downstream.job_id,
            },
            "phase34-scale-batch-manifest": {"contract_sha256": "manifest"},
        }
    monkeypatch.setattr(runtime, "project_latest", lambda kind: records.get(kind))

    assert runtime.get_job_status() == {
        "status": job_status,
        "job_id": downstream.job_id,
        "run_id": downstream.run_id,
        "phase": phase,
    }
    assert runtime.target_terminal_failure() is None
    assert Phase2Bridge.scientific_state(runtime)["scientific_state"] not in {
        "failed",
        "recovery-required",
    }


@pytest.mark.asyncio
async def test_failed_target_job_stops_before_provider_and_cannot_register_assessment(
    bridge: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    phase2 = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    failure = _failure_view(phase2, tmp_path, monkeypatch)
    assert failure is not None
    execution = phase2.store.begin_execution(phase2.thread, "Inspect failed target")
    guard = RoleBoundary(
        phase2,
        "target",
        scripted_config(),
        "Inspect failed target",
        execution_id=execution["execution_id"],
    )
    invoked = 0

    async def handler(_request: Any) -> Any:
        nonlocal invoked
        invoked += 1
        raise AssertionError("terminal Target failure must stop before the provider")

    request = SimpleNamespace(
        tools=build_tools(phase2, "target"),
        messages=[],
        system_message=SystemMessage(content="Inspect"),
        model=SimpleNamespace(profile={}),
    )
    for _ in range(2):
        with pytest.raises(TargetJobTerminalFailure) as raised:
            await guard.awrap_model_call(request, handler)
        assert raised.value.failure == failure
    assert invoked == 0
    assert not any(e["kind"] == "model-call" for e in phase2.store.events(phase2.thread))

    opinion = TargetInterpretation(
        interpretation=["No runtime facts are available."],
        unresolved_identity=["Target preparation failed."],
        limitations=["No structure interpretation is admissible."],
        recommended_option=None,
        recommended_action="Stop and report the persisted failure.",
    )
    with pytest.raises(TargetJobTerminalFailure):
        register_target(phase2, opinion, None)
    assert not any(
        event["kind"] == "target-assessment" for event in phase2.store.events(phase2.thread)
    )


@pytest.mark.asyncio
async def test_base_coordinator_resume_stops_before_provider_call(
    bridge: Any, monkeypatch: Any
) -> None:
    failure = {
        "terminal_state": "failed",
        "code": "stage01-source-failed",
        "message": "synthetic deterministic source failure",
        "retryable": False,
        "failure_ref": "01-target-preparation/stage-manifest.json#sha256=" + "a" * 64,
    }
    monkeypatch.setattr(bridge, "target_terminal_failure", lambda: failure)
    execution = bridge.store.begin_execution(bridge.thread, "Resume failed target")
    guard = RoleBoundary(
        bridge,
        "coordinator",
        scripted_config(),
        "Resume failed target",
        execution_id=execution["execution_id"],
    )
    invoked = 0

    async def handler(_request: Any) -> Any:
        nonlocal invoked
        invoked += 1
        raise AssertionError("base Coordinator must stop before the provider")

    with pytest.raises(TargetJobTerminalFailure):
        await guard.awrap_model_call(SimpleNamespace(), handler)
    assert invoked == 0
    assert not any(e["kind"] == "model-call" for e in bridge.store.events(bridge.thread))


@pytest.mark.asyncio
async def test_phase2_first_dispatch_reports_failure_without_provider_call(
    bridge: Any, monkeypatch: Any
) -> None:
    phase2 = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    failure = {
        "terminal_state": "failed",
        "code": "stage01-source-failed",
        "message": "synthetic deterministic source failure",
        "retryable": False,
        "failure_ref": "01-target-preparation/stage-manifest.json#sha256=" + "a" * 64,
    }
    monkeypatch.setattr(phase2, "target_terminal_failure", lambda: failure)

    result = await run_session(
        phase2,
        scripted_config(),
        {role: ScriptedModel(role=role) for role in PHASE2_ALLOWED},
        "Inspect a deterministically failed target",
    )

    assert result["status"] == "failed"
    assert result["scientific_state"] == "failed"
    assert result["failure"] == failure
    assert not any(e["kind"] == "model-call" for e in phase2.store.events(phase2.thread))
