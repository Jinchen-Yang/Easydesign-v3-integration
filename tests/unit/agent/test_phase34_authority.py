from typing import Any

import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase34_authority import (
    accept_pilot_plan,
    pilot_review_card,
    plan_for_design,
    verify_pilot_authority,
)
from easydesign.agent.phase34_bridge import Phase34Bridge
from easydesign.agent.phase34_plan import BoundPilotPlan
from tests.unit.agent.test_design_runtime import binder_intent, design_card, propose_design


def prepared(bridge: Any) -> tuple[Any, Any, Any]:
    downstream = Phase34Bridge(bridge.project, bridge.thread, bridge.store)
    propose_design(downstream, binder_intent(avoid_label_seq_ids=[5]))
    plan = plan_for_design(
        downstream, downstream.current_design(), prediction_backend="openfold3-af3-jax"
    )
    card = pilot_review_card(downstream, design_card(downstream), plan)
    return downstream, plan, card


def test_gate3_real_product_authority_preserves_arm_hypothesis_and_constraints(design_bridge):
    bridge, plan, card = prepared(design_bridge)
    assert len(plan.production_allocations) == 7
    assert sum(plan.production_allocations.values()) == 280
    assert plan.arms[0].hypothesis == binder_intent().arms[0].hypothesis
    assert plan.arms[0].failure_interpretation == binder_intent().arms[0].failure_interpretation
    assert plan.arms[0].changed_factors == tuple(binder_intent().arms[0].changed_factors)
    assert all(s["avoid_label_seq_ids"] == [5] for s in plan.arms[0].compiled_settings)
    with pytest.raises(AgentBoundaryError, match="explicit Scientist"):
        accept_pilot_plan(bridge, card)
    bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-scientist")
    authority = accept_pilot_plan(bridge, card)
    assert verify_pilot_authority(bridge, authority) == plan
    assert accept_pilot_plan(bridge, card) == authority
    assert (
        len(
            [
                e
                for e in bridge.store.events(bridge.thread)
                if e["kind"] == "phase34-pilot-authority"
            ]
        )
        == 1
    )
    restarted = Phase34Bridge(bridge.project, "pilot-restart", bridge.store)
    assert verify_pilot_authority(restarted, authority) == plan
    assert not any(j.step > 2 for j in bridge.controller.list(project_id=bridge.project_id))


def test_pilot_authority_cannot_expand_allocation_or_change_backend(design_bridge):
    bridge, plan, card = prepared(design_bridge)
    bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-scientist")
    authority = accept_pilot_plan(bridge, card)
    forged = authority.model_copy(
        update={"pilot_plan": plan.model_copy(update={"prediction_backend": "protenix-v2"})}
    )
    with pytest.raises(AgentBoundaryError, match="changed"):
        verify_pilot_authority(bridge, forged)
    with pytest.raises(AgentBoundaryError, match="project"):
        verify_pilot_authority(
            bridge,
            authority.model_copy(
                update={"pilot_plan": plan.model_copy(update={"project_id": "another-project"})}
            ),
        )


def test_explicit_bounded_scientific_pilot_keeps_default_design_and_exact_approval(design_bridge):
    bridge, default_plan, original_card = prepared(design_bridge)
    selected = {s: 10 for s in default_plan.production_allocations}
    plan = plan_for_design(
        bridge,
        bridge.current_design(),
        prediction_backend="openfold3-af3-jax",
        pilot_allocations=selected,
    )
    assert sum(default_plan.execution_allocations.values()) == 280
    assert sum(plan.execution_allocations.values()) == 70
    assert plan.production_allocations == plan.execution_allocations == selected
    assert all(s["candidates_per_strategy"] == 40 for a in plan.arms for s in a.compiled_settings)
    assert not plan.validation_only and plan.mode == "formal-pilot"
    card = pilot_review_card(bridge, original_card, plan)
    with pytest.raises(AgentBoundaryError, match="explicit Scientist"):
        accept_pilot_plan(bridge, card)
    bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-scientist")
    authority = accept_pilot_plan(bridge, card)
    assert verify_pilot_authority(bridge, authority) == plan
    for invalid in ({**selected, next(iter(selected)): 41}, {"foreign-scaffold": 10}):
        with pytest.raises(AgentBoundaryError, match="Design budgets"):
            plan_for_design(
                bridge,
                bridge.current_design(),
                prediction_backend="openfold3-af3-jax",
                pilot_allocations=invalid,
            )


def test_pilot_plan_stale_design_rejected_before_freeze(design_bridge):
    bridge, plan, card = prepared(design_bridge)
    bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-scientist")
    propose_design(bridge, binder_intent(name="changed", avoid_label_seq_ids=[6]))
    with pytest.raises(AgentBoundaryError, match="stale"):
        accept_pilot_plan(bridge, card)
    assert bridge.approved_design() is None


def test_micro_plan_keeps_production_intent_and_cannot_be_scientific_approval(design_bridge):
    bridge, plan, card = prepared(design_bridge)
    strategy = next(iter(plan.production_allocations))
    micro = plan_for_design(
        bridge,
        bridge.current_design(),
        prediction_backend="openfold3-af3-jax",
        mode="validation-micro",
        execution_allocations={strategy: 2},
    )
    assert sum(micro.production_allocations.values()) == 280
    assert sum(micro.execution_allocations.values()) == 2
    with pytest.raises(AgentBoundaryError, match="Micro validation"):
        pilot_review_card(bridge, card, micro)
    raw = micro.model_dump(mode="json")
    raw["execution_allocations"] = {strategy: 7}
    with pytest.raises(ValueError, match="six candidates"):
        BoundPilotPlan.model_validate(raw)


def test_reject_cannot_produce_pilot_authority(design_bridge):
    bridge, _, card = prepared(design_bridge)
    bridge.store.respond(bridge.thread, card.card_id, "reject", "synthetic-scientist")
    with pytest.raises(AgentBoundaryError, match="does not authorize"):
        accept_pilot_plan(bridge, card)
