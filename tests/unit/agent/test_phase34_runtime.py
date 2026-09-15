"""Product authority/control flow with synthetic measurements; no scientific acceptance."""

import json
from types import SimpleNamespace

import pytest

from easydesign.agent.cli import run_session
from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.control_flow import next_action
from easydesign.agent.phase34_contracts import (
    ExecutionProjection,
    PilotArmDenominator,
    PilotMeasurement,
)
from easydesign.agent.phase34_execution import execution_config
from easydesign.agent.phase34_runtime import Phase34Runtime
from easydesign.core import canonical_model_sha256
from tests.agent_support import ScriptedModel, scripted_config
from tests.unit.agent.test_phase34_authority import prepared


def runtime_fixture(design_bridge):
    original, plan, card = prepared(design_bridge)
    bridge = Phase34Runtime(original.project, original.thread, original.store)
    bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-scientist")
    bridge.apply_decision(card)
    authority = bridge.pilot_authority()
    assert authority
    config = execution_config(bridge, plan, bridge.selected_design())
    assert config.workflow.stop_after_stage == 4
    assert config.stage05 is None  # Prediction follows the bound v3 plan, not legacy expansion.
    assert plan.prediction_backend == "openfold3-af3-jax"
    assert next_action(bridge).stage == "pilot-dispatch"
    measured = PilotMeasurement(
        execution=ExecutionProjection(
            mode="formal-pilot",
            requested_production_candidates=sum(plan.production_allocations.values()),
            execution_candidates=sum(plan.execution_allocations.values()),
            uses_real_generation_backend=False,
            uses_real_prediction_backend=False,
            purpose="Synthetic operational-negative control-flow regression",
        ),
        source_candidate_index_sha256="a" * 64,
        source_filter_report_sha256="b" * 64,
        candidates=(),
        arms=tuple(
            PilotArmDenominator(
                strategy_id=s,
                planned_candidates=n,
                generated_candidates=0,
                valid_execution_products=0,
                predicted_candidates=0,
                metric_evaluable_candidates=0,
                unique_sequences=0,
                legacy_policy_pass_count=0,
                operational_failure_count=n,
                missing_by_metric={},
            )
            for s, n in plan.execution_allocations.items()
        ),
    )
    bridge.store.event(
        bridge.thread,
        "phase34-pilot-execution",
        {
            "authority": authority.authority_id,
            "plan": canonical_model_sha256(plan),
            "run_id": "synthetic-pilot",
            "job_id": "synthetic-worker",
            "config_sha256": canonical_model_sha256(config),
        },
    )
    bridge.publish_contract(
        kind="phase34-pilot-measurement",
        contract=measured,
        dependencies={"authority": authority.authority_id},
    )
    bridge.controller = SimpleNamespace(
        load=lambda _: SimpleNamespace(status="succeeded"), list=bridge.controller.list
    )
    return bridge


class DownstreamModel(ScriptedModel):
    def bind_tools(self, tools, **kwargs):
        names = {getattr(t, "__name__", getattr(t, "name", "")) for t in tools}
        assert names == {
            "PilotDiagnosisOpinion" if self.role == "pilot-diagnosis" else "DownstreamJudgeOpinion"
        }
        return self

    def answer(self, messages):
        packet = json.loads(messages[-1].content)
        if self.role == "pilot-diagnosis":
            return self.call(
                "PilotDiagnosisOpinion",
                key_observations=["No valid outputs were produced."],
                arm_findings=[
                    {
                        "arm_id": arm,
                        "hypothesis_support": "UNRESOLVED",
                        "observations": ["Execution did not produce usable evidence."],
                        "interpretation": "The design hypothesis was not tested.",
                        "alternative_explanation": "Operational failure.",
                    }
                    for arm in packet["facts"]
                ],
                arm_comparisons=["Arms cannot be distinguished without outputs."],
                operational_confounders=["All generation slots failed."],
                uncertainty=["No biological conclusion follows."],
                next_discriminating_experiment=[
                    "Repair the backend and approve a new bounded plan."
                ],
                recommended_action="RUN_ANOTHER_PILOT",
                rationale="Acquire usable evidence.",
            )
        if self.role == "judge":
            return self.call(
                "DownstreamJudgeOpinion",
                review="NO_MATERIAL_ISSUE",
                brief_rationale="The diagnosis correctly separates execution from "
                "scientific failure.",
                uncertainties=["No functional evidence exists."],
                fact_refs=list(packet["facts"])[:1],
            )
        pytest.fail("Upstream and coordinator models must not be called for downstream diagnosis")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route, expected",
    [
        ("STOP", "scientist-stopped"),
        ("RUN_ANOTHER_PILOT", "pilot-plan-review"),
        ("REVISE_DESIGN", "design-not-proposed"),
        ("REVISE_SITE", "site-not-proposed"),
    ],
)
async def test_actual_graph_diagnosis_judge_and_gate4_routes(design_bridge, route, expected):
    bridge = runtime_fixture(design_bridge)
    models = {
        r: DownstreamModel(role=r)
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
        bridge, scripted_config(), models, "SYNTHETIC downstream control flow"
    )
    assert result["status"] == "awaiting-human-approval", result
    assert result["card"]["gate_type"] == "pilot-promotion"
    card = bridge.downstream_card()
    assert card.scientific_summary["diagnosis"]["design_arms"]
    assert bridge.pilot_authority() is not None
    bridge.store.respond(
        bridge.thread, card.card_id, "approve", "synthetic-scientist", selected_option_id=route
    )
    applied = bridge.apply_decision(card)
    assert applied["status"] == route
    assert next_action(bridge).stage == expected
    # Duplicate human response reconciliation cannot repeat a transition.
    assert bridge.apply_decision(card) == applied
    transitions = [
        e for e in bridge.store.events(bridge.thread) if e["kind"] == "phase34-gate4-transition"
    ]
    assert len(transitions) == 1
    if route == "RUN_ANOTHER_PILOT":
        assert bridge.pilot_authority() is None
        new_card = bridge.frozen_pilot_card()
        assert new_card.card_id != card.card_id
        assert new_card.scientific_summary["pilot_plan"]["parent_gate4_card_id"] == card.card_id
        with pytest.raises(AgentBoundaryError, match="explicit Scientist"):
            from easydesign.agent.phase34_authority import accept_pilot_plan

            accept_pilot_plan(bridge, new_card)


def test_another_pilot_cannot_invent_parent_gate4(design_bridge):
    from easydesign.agent.phase34_authority import plan_for_design

    bridge, _, _ = prepared(design_bridge)
    with pytest.raises(AgentBoundaryError, match="Scientist Gate 4"):
        plan_for_design(
            bridge,
            bridge.current_design(),
            prediction_backend="openfold3-af3-jax",
            parent_gate4_card_id="f" * 64,
        )


def test_new_pending_design_is_reviewed_before_old_frozen_pilot_plan(design_bridge):
    from tests.unit.agent.test_design_runtime import binder_intent, propose_design

    bridge = runtime_fixture(design_bridge)
    approved_id = bridge.approved_design()["proposal_id"]
    propose_design(bridge, binder_intent(name="new-control", avoid_label_seq_ids=[6]))
    assert bridge.current_design()["proposal_id"] != approved_id
    assert bridge.approved_design()["proposal_id"] == approved_id
    assert bridge.next_downstream_action() is None
    assert next_action(bridge).stage != "pilot-plan-review"
