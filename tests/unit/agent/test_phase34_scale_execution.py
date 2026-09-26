"""Scale dispatch uses the current Gate 4 allocation and recovers the same kernel run."""

from types import SimpleNamespace

import pytest
import yaml

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase34_contracts import (
    ExecutionProjection,
    Gate4PromotionAuthority,
    ScaleCampaignSpecification,
)
from easydesign.agent.phase34_scale import current_batch_store, register_scale_campaign
from easydesign.agent.phase34_scale_execution import dispatch_batch
from tests.unit.agent.test_phase34_final_runtime import micro_fixture


def test_scale_exact_batch_dispatch_resume_and_config_tampering(design_bridge, monkeypatch):
    bridge, _, _ = micro_fixture(design_bridge)
    card = bridge.downstream_card()
    bridge.store.respond(
        bridge.thread,
        card.card_id,
        "approve",
        "synthetic-scientist",
        selected_option_id="PROMOTE_TO_SCALE",
    )
    bridge.apply_decision(card)
    authority = bridge.load_contract(
        kind="phase34-scale-authority", contract_type=Gate4PromotionAuthority
    )
    campaign = ScaleCampaignSpecification(
        campaign_id="adapter-validation",
        promotion_authority=authority,
        execution=ExecutionProjection(
            mode="validation-micro",
            requested_production_candidates=20,
            execution_candidates=4,
            uses_real_generation_backend=True,
            uses_real_prediction_backend=True,
            purpose="Synthetic adapter invocation: backend launch is intercepted.",
        ),
        strategy_allocations={s: 2 for s in authority.selected_strategy_ids},
        generation_backend="boltzgen-0.3.2",
        prediction_backend="openfold3-af3-jax",
        allocation_policy="explicit-micro-projection",
    )
    with pytest.raises(AgentBoundaryError, match="backend"):
        register_scale_campaign(
            bridge, campaign.model_copy(update={"prediction_backend": "protenix-v2"})
        )
    journal = register_scale_campaign(bridge, campaign, batch_size=1)
    assert len(journal.manifest.batches) == 4
    assert current_batch_store(bridge).digest == journal.digest
    batch = journal.manifest.batches[0]
    jobs, launched = [], []
    config_path = bridge.project / "metadata" / "scale-test-config.yaml"

    def launch(project, *, phase, config, internal_start, base, run_id, detach):
        assert project == bridge.project and phase == "scale"
        assert internal_start == 3 and detach and base is not None
        assert config.workflow.stop_after_stage == 4 and config.stage05 is None
        actual = {
            f"{v.variant_id}-scaffold-{s}": v.candidates_per_strategy
            for v in config.stage03.variants
            for s in v.scaffold_ids
        }
        assert actual == batch.strategy_allocations
        assert sum(actual.values()) == 1
        config_path.write_text(yaml.safe_dump(config.model_dump(mode="json")))
        job = SimpleNamespace(
            job_id="scale-test-worker",
            operation="run",
            project_root=project,
            config_path=config_path,
            step=3,
            run_id=run_id,
            status="detached",
        )
        jobs.insert(0, job)
        launched.append(job)
        return None, job

    monkeypatch.setattr("easydesign.agent.phase34_scale_execution._launch", launch)
    bridge.controller = SimpleNamespace(list=lambda **_: jobs)
    first = dispatch_batch(bridge, journal, batch)
    assert first["status"] == "queued"
    assert dispatch_batch(bridge, journal, batch) == first
    assert len(launched) == 1
    resumed = SimpleNamespace(
        job_id="scale-test-resume",
        operation="resume",
        project_root=bridge.project,
        run_root=bridge.context.runs_root / bridge.project_id / first["run_id"],
        step=4,
        run_id=first["run_id"],
        status="running",
    )
    jobs.insert(0, resumed)
    assert dispatch_batch(bridge, journal, batch)["job_id"] == "scale-test-resume"
    assert len(launched) == 1
    resumed.run_root = bridge.context.runs_root / "other-project" / first["run_id"]
    with pytest.raises(AgentBoundaryError, match="recovery worker"):
        dispatch_batch(bridge, journal, batch)
    jobs.pop(0)
    config = yaml.safe_load(config_path.read_text())
    config["stage04"]["executor"]["max_task_attempts"] += 1
    config_path.write_text(yaml.safe_dump(config))
    with pytest.raises(AgentBoundaryError, match="configuration differs"):
        dispatch_batch(bridge, journal, batch)
    assert len(launched) == 1
