from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase34_failures import project_generation_failure
from easydesign.orchestration.local_jobs import LocalStepJob


def test_worker_boot_failure_is_missing_evidence_not_scientific_failure(tmp_path):
    now = datetime.now(UTC)
    project = tmp_path / "project"
    job = LocalStepJob(
        job_id="failed-worker",
        operation="run",
        status="failed",
        project_id="project",
        project_root=project,
        step=3,
        run_id="pilot-id",
        branch="codex/test",
        log_path=tmp_path / "worker.log",
        drain_path=tmp_path / "worker.drain",
        created_at=now,
        updated_at=now,
    )
    published = {}
    bridge = SimpleNamespace(
        project=project,
        project_id="project",
        pilot_authority=lambda: SimpleNamespace(
            authority_id="authority",
            pilot_plan=SimpleNamespace(
                mode="validation-micro",
                production_allocations={"arm-a": 280},
                execution_allocations={"arm-a": 2},
            ),
        ),
        project_latest=lambda _: {
            "authority": "authority",
            "job_id": "failed-worker",
            "run_id": "pilot-id",
        },
        controller=SimpleNamespace(load=lambda _: job, path=lambda _: tmp_path / "worker.json"),
        context=SimpleNamespace(runs_root=tmp_path / "runs"),
        thread="validation",
        store=SimpleNamespace(event=lambda *args: None),
        publish_contract=lambda **values: published.update(values),
    )
    assert project_generation_failure(bridge)["status"] == "pilot-operational-evidence-ready"
    measured = published["contract"]
    assert measured.source_filter_report_sha256 is None
    assert measured.source_candidate_index_kind == "generation-failure-receipt"
    assert measured.candidates == measured.unmeasured_candidates == ()
    assert measured.arms[0].operational_failure_count == 2
    assert measured.arms[0].predicted_candidates == measured.arms[0].generated_candidates == 0
    assert not measured.execution.uses_real_generation_backend
    bridge.controller.load = lambda _: job.model_copy(
        update={"project_root": tmp_path / "another-project"}
    )
    with pytest.raises(AgentBoundaryError, match="outside the authorized"):
        project_generation_failure(bridge)
