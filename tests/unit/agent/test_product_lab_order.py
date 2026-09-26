"""Gate 5-bound mock ordering is durable, idempotent and never a real order."""

from __future__ import annotations

from uuid import uuid4

import pytest

from easydesign.agent.cli import run_session
from easydesign.product.contracts import ProductError
from easydesign.product.lab_order import (
    LabOrderCommand,
    LabOrderDraft,
    LabOrderRequirements,
)
from tests.agent_support import scripted_config
from tests.unit.agent.test_phase34_final_runtime import (
    FinalModel,
    micro_fixture,
    scale_fixture,
)
from tests.unit.agent.test_product_api import ROLES, service_for


async def validation_handoff(design_bridge):
    bridge, pilot, context = micro_fixture(design_bridge)
    models = {role: FinalModel(role=role) for role in ROLES}
    goal = "SYNTHETIC validation-only mock order boundary"
    await run_session(bridge, scripted_config(), models, goal)
    card4 = bridge.downstream_card()
    bridge.store.respond(
        bridge.thread,
        card4.card_id,
        "approve",
        "synthetic-scientist",
        selected_option_id="PROMOTE_TO_SCALE",
    )
    bridge.apply_decision(card4)
    scale_fixture(bridge, pilot, context)
    gate5 = await run_session(bridge, scripted_config(), models, goal)
    assert gate5["card"]["gate_type"] == "wet-lab-handoff"
    card5 = bridge.downstream_card()
    finished = await run_session(
        bridge,
        scripted_config(),
        models,
        goal,
        decision="approve",
        card_id=card5.card_id,
        user="synthetic-scientist",
        selected_option_id="wet-lab-panel",
    )
    assert finished["status"] == "finished"
    return bridge


def command(action: str, revision: str, **values):
    return LabOrderCommand(
        request_id=str(uuid4()), revision=revision, action=action, **values
    )


@pytest.mark.asyncio
async def test_gate5_mock_order_is_server_owned_idempotent_and_non_authorizing(
    design_bridge, tmp_path
):
    bridge = await validation_handoff(design_bridge)
    service = service_for(bridge, tmp_path)
    view = service.lab_order("target-test")
    assert view["handoff_status"] == "validation-only-not-authorized-for-experiment"
    assert view["ordering_status"] == "not-ordered"
    assert not view["capabilities"]["real_order"]
    assert len(view["candidates"]) == 4
    assert all(item["sequence_ready"] for item in view["candidates"])
    selected = tuple(item["id"] for item in view["candidates"][:2])
    draft = LabOrderDraft(
        candidate_ids=selected,
        requirements=LabOrderRequirements(
            format="VHH",
            amount="1 mg per sample",
            host="E. coli",
            buffer="PBS",
            profile="simulation-lab",
            notes="Simulation-only packaging review.",
        ),
        reviewed=True,
    )
    saved = service.apply_lab_order(
        "target-test", command("save", view["revision"], draft=draft)
    )["order"]
    assert saved["draft"]["candidate_ids"] == list(selected)
    quoted = service.apply_lab_order(
        "target-test", command("quote", saved["revision"])
    )["order"]
    assert quoted["quote"]["external_request_sent"] is False
    assert quoted["quote"]["non_binding"] is True
    submit = command(
        "submit",
        quoted["revision"],
        acknowledgement="SIMULATED_ORDER_ONLY",
    )
    response = service.apply_lab_order("target-test", submit)
    receipt = response["order"]["receipt"]
    assert receipt["status"] == "simulated-accepted"
    assert receipt["financial_commitment"] is False
    assert receipt["external_request_sent"] is False
    assert receipt["experiment_authorized"] is False
    assert receipt["ordering_status"] == "simulation-only-not-ordered"
    assert set(receipt["candidate_sequence_sha256"]) == set(selected)
    assert service.apply_lab_order("target-test", submit) == response
    assert (
        service.root / "lab-order-receipts" / (receipt["receipt_id"] + ".json")
    ).is_file()
    snapshot = service.snapshot("target-test")
    assert snapshot["capabilities"]["lab_order"] is True
    assert snapshot["lab_order"]["receipt"]["receipt_id"] == receipt["receipt_id"]
    with pytest.raises(ProductError, match="already final"):
        service.apply_lab_order(
            "target-test", command("quote", response["order"]["revision"])
        )


@pytest.mark.asyncio
async def test_mock_order_rejects_stale_state_and_candidate_outside_gate5(
    design_bridge, tmp_path
):
    bridge = await validation_handoff(design_bridge)
    service = service_for(bridge, tmp_path)
    view = service.lab_order("target-test")
    requirements = LabOrderRequirements(
        format="VHH", amount="1 mg", profile="simulation-lab"
    )
    invalid = LabOrderDraft(
        candidate_ids=("candidate-outside-gate5",),
        requirements=requirements,
        reviewed=True,
    )
    with pytest.raises(ProductError) as outside:
        service.apply_lab_order(
            "target-test", command("save", view["revision"], draft=invalid)
        )
    assert outside.value.code == "candidate_outside_gate5"
    valid = LabOrderDraft(
        candidate_ids=(view["candidates"][0]["id"],),
        requirements=requirements,
        reviewed=True,
    )
    saved = service.apply_lab_order(
        "target-test", command("save", view["revision"], draft=valid)
    )["order"]
    with pytest.raises(ProductError) as stale:
        service.apply_lab_order(
            "target-test", command("quote", view["revision"])
        )
    assert stale.value.code == "stale_state"
    assert service.apply_lab_order(
        "target-test", command("quote", saved["revision"])
    )["order"]["quote"]

