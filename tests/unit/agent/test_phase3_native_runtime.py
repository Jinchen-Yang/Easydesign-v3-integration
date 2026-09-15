"""Synthetic populations exercise the real graph; no biological acceptance is claimed."""

import json

import pytest

from easydesign.agent.cli import run_session
from easydesign.agent.phase3_native import project_native_measurement
from easydesign.agent.phase34_opinions import PilotDiagnosisOpinion
from easydesign.core.errors import ArtifactIntegrityError
from tests.agent_support import ScriptedModel, scripted_config
from tests.unit.agent.test_phase3_native_ranking import opinion_for, population
from tests.unit.agent.test_phase34_runtime import runtime_fixture


class NativeRankingModel(ScriptedModel):
    opinion: PilotDiagnosisOpinion

    def bind_tools(self, tools, **kwargs):
        assert self.role == "pilot-diagnosis", "No Judge/AFO/upstream model is required"
        assert tools == [PilotDiagnosisOpinion]
        return self

    def answer(self, messages):
        packet = json.loads(messages[-1].content)
        assert packet["version"] == "ranked-pilot-v1"
        return self.call("PilotDiagnosisOpinion", **self.opinion.model_dump(mode="json"))


@pytest.mark.asyncio
@pytest.mark.parametrize("passes,incomplete", [(0, False), (1, False), (0, True), (1, True)])
async def test_native_graph_gate4_and_restart_without_judge_or_prediction(
    design_bridge, tmp_path, monkeypatch, passes, incomplete
):
    bridge = runtime_fixture(design_bridge)
    authority = bridge.pilot_authority()
    plan = authority.pilot_plan
    fake, fake_arms, candidates, profile = population(
        tmp_path,
        (("arm-a", (passes, 0, 0, 0, 0, 0, 0)),),
        incomplete=incomplete,
        per_strategy=40,
    )
    mapping = dict(zip(fake_arms[0].strategy_ids, plan.arms[0].strategy_ids, strict=True))
    remapped = tuple(
        c.model_copy(
            update={
                "strategy_id": mapping[c.strategy_id],
                "candidate_id": f"{mapping[c.strategy_id]}-candidate-{c.ordinal_within_strategy}",
            }
        )
        for c in candidates
    )
    measured = project_native_measurement(
        candidates=remapped,
        profiles={s: profile for s in plan.execution_allocations},
        planned=plan.execution_allocations,
        execution=fake.execution,
        source_sha256="b" * 64,
    )
    bridge.publish_contract(
        kind="phase34-pilot-measurement",
        contract=measured,
        dependencies={"authority": authority.authority_id, "execution_job_id": "synthetic-worker"},
    )
    actual_run = bridge.run
    monkeypatch.setattr(
        bridge,
        "run",
        lambda run_id=None: (tmp_path, None) if run_id == "synthetic-pilot" else actual_run(run_id),
    )
    opinion = opinion_for(measured, plan.arms)
    models = {
        r: NativeRankingModel(role=r, opinion=opinion)
        for r in (
            "coordinator",
            "target",
            "site",
            "binder",
            "judge",
            "pilot-diagnosis",
            "final-selection",
        )
    }
    result = await run_session(
        bridge, scripted_config(), models, "SYNTHETIC native population, no biological claims"
    )
    assert result["status"] == "awaiting-human-approval"
    card = bridge.downstream_card()
    assert card.gate_type == "pilot-promotion"
    board = card.scientific_summary["ranked_pilot"]
    expected = "OPERATIONAL_INCOMPLETE" if incomplete else "PROMOTION" if passes else "RECOVERY"
    assert board["arm_leaderboard"][0]["mode"] == expected
    assert card.scientific_summary["independent_review"]["availability"] == "not-requested"
    before = [e for e in bridge.store.events(bridge.thread) if e["kind"] == "model-call"]
    assert len(before) == 1 and before[0]["payload"]["role"] == "pilot-diagnosis"
    repeated = await run_session(
        bridge, scripted_config(), models, "SYNTHETIC native population, no biological claims"
    )
    assert repeated["card"]["card_id"] == card.card_id
    assert len([e for e in bridge.store.events(bridge.thread) if e["kind"] == "model-call"]) == 1
    assert bridge.project_latest("phase34-scale-authority") is None
    if passes and not incomplete:
        assert bridge.downstream_packet("judge")["dossier_sha256"] == card.evidence_id
        # Direct API approval must not bypass source integrity after a card was shown.
        (tmp_path / "synthetic-profile.yaml").write_text("tampered source")
        bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-scientist")
        with pytest.raises(ArtifactIntegrityError):
            bridge.apply_decision(card)
        assert bridge.project_latest("phase34-scale-authority") is None
