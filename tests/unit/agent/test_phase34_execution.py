from types import SimpleNamespace

import pytest
import yaml

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase34_authority import accept_pilot_plan
from easydesign.agent.phase34_execution import execute_pilot
from tests.unit.agent.test_phase34_authority import prepared


def test_pilot_dispatch_and_recovery_bind_one_run_and_exact_configuration(
    design_bridge, monkeypatch
):
    bridge, plan, card = prepared(design_bridge)
    bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-scientist")
    authority = accept_pilot_plan(bridge, card)
    jobs = list(bridge.controller.list(project_id=bridge.project_id))
    launched = []
    config_path = bridge.project / "metadata" / "synthetic-pilot-config.yaml"

    def dispatch(project, *, phase, config, internal_start, base, run_id, detach):
        assert project == bridge.project and phase == "pilot"
        assert config.workflow.stop_after_stage == 4
        assert internal_start == 3 and detach
        assert config.stage05 is None  # The generation worker cannot enter legacy expansion.
        assert sum(
            v.candidates_per_strategy * len(v.scaffold_ids) for v in config.stage03.variants
        ) == sum(plan.execution_allocations.values())
        config_path.write_text(yaml.safe_dump(config.model_dump(mode="json")))
        job = SimpleNamespace(
            job_id="synthetic-worker",
            run_id=run_id,
            project_root=project,
            config_path=config_path,
            step=3,
            status="running",
        )
        launched.append(job)
        jobs.append(job)
        return None, job

    monkeypatch.setattr("easydesign.agent.phase34_execution._launch", dispatch)
    bridge.controller = SimpleNamespace(list=lambda **_: jobs)
    first = execute_pilot(bridge, authority)
    second = execute_pilot(bridge, authority)
    assert first == second
    assert len(launched) == 1
    resumed = SimpleNamespace(
        job_id="synthetic-resume",
        operation="resume",
        run_id=first["run_id"],
        project_root=bridge.project,
        run_root=bridge.context.runs_root / bridge.project_id / first["run_id"],
        step=4,
        config_path=None,
        status="running",
    )
    jobs.insert(0, resumed)
    assert execute_pilot(bridge, authority)["job_id"] == "synthetic-resume"
    assert len(launched) == 1
    config = yaml.safe_load(config_path.read_text())
    config["stage04"]["executor"]["max_task_attempts"] = 4
    config_path.write_text(yaml.safe_dump(config))
    with pytest.raises(AgentBoundaryError, match="different approved configuration"):
        execute_pilot(bridge, authority)
    assert len(launched) == 1
