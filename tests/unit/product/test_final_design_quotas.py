"""Narrow quota tests: personal cumulative final-design allowance.

Covers the ledger (atomicity, idempotency, scope-qualified keys, actor
preservation), the classification gate (Pilot excluded, every dispatch path),
fact-based settlement planning (live/resumable holds, pool truth, campaign
binding), stage-budget capture transport, and admin/visibility rules.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from easydesign.execution_scope import ExecutionScope
from easydesign.product.accounts import AccountStore, ResourceLimits
from easydesign.product.contracts import ActionRequest, ProductError
from easydesign.product.domain import NativeGateway
from easydesign.product.resource_control import (
    FINAL_DESIGN_RULE,
    ResourceLedger,
    contract_digest,
)
from easydesign.product.resource_supervisor import plan_final_design_action
from easydesign.product.scoped_worker import stage_budgets_from_config
from easydesign.product.service import ProductService
from easydesign.product.tenancy import (
    FinalDesignIntent,
    MultiUserRuntime,
    ScopedProductService,
    final_design_intent,
)
from easydesign.workspace_context import WorkspaceContext

PASSWORD = "Fixture-password-2026!"
KEY = "a" * 64
KEY2 = "b" * 64


@pytest.fixture
def quota_fixture(tmp_path: Path):
    store = AccountStore(tmp_path / "accounts.sqlite")
    admin = store.bootstrap_admin("admin", PASSWORD, "管理员")
    alice = store.register("alice", PASSWORD, "Alice")
    bob = store.register("bob", PASSWORD, "Bob")
    store.update_user(admin, alice.id, status="active")
    store.update_user(admin, bob.id, status="active")
    team = store.create_team(alice, "Team")
    invite = store.invite(alice, team["id"], "bob", role="admin")
    store.respond_invitation(bob, invite["id"], accept=True)
    return store, ResourceLedger(store), admin, alice, bob, team["id"]


def ensure(
    ledger: ResourceLedger,
    user,
    scope_id: str,
    *,
    project: str = "workbench-fixture-1",
    key: str = KEY,
    amount: int = 20,
    subject_id: str | None = None,
    request_id: str = "approve-request-00001",
):
    return ledger.ensure_final_designs(
        user,
        scope_id,
        project,
        request_id,
        key,
        amount,
        subject_id=subject_id or user.id,
    )


# ---------------------------------------------------------------- ledger core


def test_concurrent_approvals_cannot_overspend(quota_fixture):
    _store, ledger, _admin, alice, _bob, _team = quota_fixture

    def approve(index: int) -> str:
        try:
            ensure(ledger, alice, alice.id, key=KEY if index == 0 else KEY2, amount=20)
            return "reserved"
        except ProductError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(approve, range(2)))
    assert sorted(results) == ["final_designs_exhausted", "reserved"]
    balance = ledger.final_designs_balance(alice.id)
    assert balance == {
        "allowance": 30,
        "reserved": 20,
        "delivered": 0,
        "remaining": 10,
    }


def test_personal_allowance_spans_personal_and_team_scopes(quota_fixture):
    _store, ledger, _admin, alice, _bob, team = quota_fixture
    ensure(ledger, alice, alice.id, project="workbench-personal", amount=20)
    with pytest.raises(ProductError) as denied:
        ensure(ledger, alice, team, project="workbench-team", key=KEY2, amount=15)
    assert denied.value.code == "final_designs_exhausted"
    # Settlement charges delivered candidates only; the rest returns to the pool.
    row, _ = ensure(ledger, alice, alice.id, project="workbench-personal-2", key=KEY2, amount=5)
    ledger.settle_final_designs(row["id"], campaign_sha256=KEY, delivered=3)
    # Held 20 + delivered 3 leaves 7: a 7-design team promotion fits, 8 does not.
    ensure(ledger, alice, team, project="workbench-team", key=KEY2, amount=7)
    with pytest.raises(ProductError) as denied:
        ensure(ledger, alice, team, project="workbench-team-2", key="c" * 64, amount=8)
    assert denied.value.code == "final_designs_exhausted"
    balance = ledger.final_designs_balance(alice.id)
    assert (balance["reserved"], balance["delivered"], balance["remaining"]) == (27, 3, 0)


def test_reservation_keys_are_scope_qualified(quota_fixture):
    _store, ledger, _admin, alice, _bob, team = quota_fixture
    first, created = ensure(ledger, alice, alice.id, amount=5)
    second, second_created = ensure(ledger, alice, team, amount=5)
    assert created and second_created and first["id"] != second["id"]
    assert second["scope_id"] == team
    third, third_created = ensure(
        ledger, alice, alice.id, key=KEY2, project="workbench-fixture-2", amount=5
    )
    assert third_created and third["id"] not in {first["id"], second["id"]}


def test_idempotency_preserves_original_billing_person(quota_fixture):
    _store, ledger, _admin, alice, bob, team = quota_fixture
    row, created = ensure(ledger, alice, team, amount=20)
    assert created and row["subject_id"] == alice.id
    # A team admin recovering the same approval cannot shift the charge.
    again, created = ensure(ledger, bob, team, amount=20, subject_id=bob.id)
    assert not created and again["id"] == row["id"] and again["subject_id"] == alice.id
    settled = ledger.settle_final_designs(row["id"], campaign_sha256=KEY, delivered=18)
    assert settled["state"] == "settled" and settled["delivered"] == 18
    # Double refresh must not recharge or re-reserve a settled charge.
    refresh, created = ensure(ledger, alice, team, amount=20)
    assert not created and refresh["state"] == "settled"
    assert ledger.final_designs_balance(alice.id)["delivered"] == 18


def test_reactivation_only_for_never_applied_approvals(quota_fixture):
    _store, ledger, _admin, alice, _bob, _team = quota_fixture
    row, _ = ensure(ledger, alice, alice.id, amount=20)
    ledger.release_final_designs(row["id"], "superseded_authority")
    terminal, created = ensure(ledger, alice, alice.id, amount=20)
    assert not created and terminal["state"] == "released"
    assert ledger.final_designs_balance(alice.id)["reserved"] == 0
    pending, _ = ensure(ledger, alice, alice.id, key=KEY2, project="workbench-fixture-9", amount=5)
    ledger.release_final_designs(pending["id"], "approval_not_applied")
    revived, created = ensure(
        ledger, alice, alice.id, key=KEY2, project="workbench-fixture-9", amount=5
    )
    assert created and revived["state"] == "reserved"
    assert ledger.final_designs_balance(alice.id)["reserved"] == 5


def test_ledger_transitions_are_audited_and_terminal(quota_fixture):
    store, ledger, admin, alice, _bob, _team = quota_fixture
    row, _ = ensure(ledger, alice, alice.id, amount=20)
    ledger.release_final_designs(row["id"], "superseded_authority")
    with pytest.raises(ProductError) as denied:
        ledger.release_final_designs(row["id"], "superseded_authority")
    assert denied.value.code == "final_designs_not_held"
    pending, _ = ensure(ledger, alice, alice.id, key=KEY2, project="workbench-fixture-3", amount=5)
    settled = ledger.settle_final_designs(pending["id"], campaign_sha256=KEY, delivered=7)
    assert ledger.settle_final_designs(pending["id"], campaign_sha256=KEY, delivered=7) == settled
    with pytest.raises(ProductError) as mismatch:
        ledger.settle_final_designs(pending["id"], campaign_sha256=KEY2, delivered=7)
    assert mismatch.value.code == "final_designs_already_settled"
    actions = [event["action"] for event in store.audit(admin)]
    assert "final_designs.reserve" in actions
    assert "final_designs.settle" in actions
    assert "final_designs.release" in actions


def test_legacy_limits_rows_and_field_ranges(quota_fixture):
    store, ledger, admin, alice, _bob, team = quota_fixture
    legacy = {
        "max_active_jobs": 1,
        "max_active_chats": 2,
        "max_gpu_devices": 1,
        "max_upload_bytes": 32 * 1024**2,
        "max_stored_upload_bytes": 10 * 1024**3,
        "max_candidates_per_job": 50_000,
    }
    with store.db(write=True) as db:
        db.execute(
            "UPDATE resource_limits SET limits_json=? WHERE subject_id=?",
            (json.dumps(legacy), alice.id),
        )
    limits = store.limits(alice, alice.id)
    assert limits.final_designs_allowance == 30
    assert limits.pilot_stage_budget == 30 and limits.scale_stage_budget == 30
    with pytest.raises(ValueError):
        ResourceLimits(final_designs_allowance=1_000_001)
    with pytest.raises(ValueError):
        ResourceLimits(pilot_stage_budget=0)
    # A null personal allowance means unrestricted, not zero.
    store.set_limits(admin, alice.id, ResourceLimits(final_designs_allowance=None))
    assert store.limits(alice, alice.id).final_designs_allowance is None
    ensure(ledger, alice, team, amount=5_000)
    assert ledger.final_designs_balance(alice.id)["remaining"] is None


def test_invalid_final_design_requests_are_rejected(quota_fixture):
    _store, ledger, _admin, alice, _bob, _team = quota_fixture
    with pytest.raises(ProductError) as denied:
        ledger.ensure_final_designs(
            alice,
            alice.id,
            "workbench-fixture-1",
            "r" * 16,
            "not-a-key",
            20,
            subject_id=alice.id,
        )
    assert denied.value.code == "invalid_authority"
    with pytest.raises(ProductError) as denied:
        ledger.ensure_final_designs(
            alice, alice.id, "workbench-fixture-1", "r" * 16, KEY, 0, subject_id=alice.id
        )
    assert denied.value.code == "invalid_final_designs_request"
    with pytest.raises(ProductError) as denied:
        ledger.ensure_final_designs(
            alice,
            alice.id,
            "workbench-fixture-1",
            "r" * 16,
            KEY,
            20,
            subject_id="user-invalid",
        )
    assert denied.value.code == "invalid_final_designs_request"


# --------------------------------------------------- stage budgets & capture


def test_stage_budget_capture_is_exactly_once(quota_fixture):
    store, ledger, admin, alice, _bob, team = quota_fixture
    store.set_limits(admin, team, ResourceLimits(pilot_stage_budget=4, scale_stage_budget=6))
    assert ledger.stage_budgets_for(alice, team) == {"pilot": 4, "scale": 6}
    assert ledger.stage_budgets_for(alice, alice.id) == {"pilot": 30, "scale": 30}
    admission, _ = ledger.reserve(
        alice,
        team,
        "create-request-00001",
        {"operation": "create"},
        stage_budgets={"pilot": 4, "scale": 6},
    )
    assert ledger.command_budgets(team, "create-request-00001") == {"pilot": 4, "scale": 6}
    # Admin changes never rewrite a captured command; new commands capture fresh.
    store.set_limits(admin, team, ResourceLimits(pilot_stage_budget=9, scale_stage_budget=9))
    assert ledger.command_budgets(team, "create-request-00001") == {"pilot": 4, "scale": 6}
    ledger.transition(admission.id, "released")
    ledger.reserve(
        alice,
        team,
        "create-request-00002",
        {"operation": "create"},
        stage_budgets=ledger.stage_budgets_for(alice, team),
    )
    assert ledger.command_budgets(team, "create-request-00002") == {"pilot": 9, "scale": 9}


class FakeEventStore:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._events = events

    def events(self, thread: str) -> list[dict[str, Any]]:
        return self._events


def test_frozen_phase34_scope_always_wins_over_settings():
    prior = [
        {
            "kind": "phase34-scope",
            "payload": {
                "through": "handoff",
                "pilot_candidate_budget": 30,
                "scale_candidate_budget": 30,
            },
        }
    ]
    frozen = FakeEventStore(prior)
    assert ProductService._resolved_stage_budgets(
        frozen, "t", "easy", {"pilot": 5, "scale": 7}
    ) == (None, None)
    fresh = FakeEventStore([])
    assert ProductService._resolved_stage_budgets(fresh, "t", "easy", {"pilot": 5, "scale": 7}) == (
        5,
        7,
    )
    assert ProductService._resolved_stage_budgets(fresh, "t", "easy", {}) == (30, 30)
    assert ProductService._resolved_stage_budgets(fresh, "t", "professional", {"pilot": 5}) == (
        None,
        None,
    )


def test_stage_budgets_from_config_transport():
    assert stage_budgets_from_config({"stage_budgets": {"pilot": 5, "scale": None, "junk": 3}}) == {
        "pilot": 5,
        "scale": None,
    }
    assert stage_budgets_from_config({}) is None
    assert stage_budgets_from_config({"stage_budgets": "corrupt"}) is None
    assert stage_budgets_from_config({"stage_budgets": {"pilot": "30"}}) == {"pilot": None}


# ------------------------------------------------------- approval gate logic


class FakeCard:
    def __init__(
        self,
        gate_type: str = "pilot-promotion",
        card_id: str = KEY,
        option_id: str = "PROMOTE_TO_SCALE",
        summary: dict[str, Any] | None = None,
    ) -> None:
        self.gate_type, self.card_id, self.option_id = gate_type, card_id, option_id
        self.scientific_summary = summary if summary is not None else {}


class FakeInterpretation:
    def __init__(self, count: int) -> None:
        self.requested_scale_candidates = count


class ValidationExecutionAuthority:
    pass


class ScientistPilotAuthority:
    pass


class FakeDossier:
    def __init__(self, count: int = 30, authority: Any = None) -> None:
        self.proposed_interpretation = FakeInterpretation(count)
        self.execution_authority = authority or ScientistPilotAuthority()


class FakeBridge:
    """Serves a checksum-verified published promotion authority, or none."""

    def __init__(
        self,
        dossier: Any = None,
        contract: dict | None = None,
        contract_sha256: str | None = None,
    ) -> None:
        self._dossier, self._contract = dossier, contract
        self._sha = contract_sha256

    def current_pilot_dossier(self):
        return self._dossier

    def project_latest(self, kind: str):
        if kind != "phase34-scale-authority" or self._contract is None:
            return None
        return {
            "contract_type": "Gate4PromotionAuthority",
            "contract_sha256": self._sha or contract_digest(self._contract),
            "dependencies": {},
            "ref": "fixture-ref",
        }

    def document(self, ref: str):
        return self._contract


class FakeSession:
    def __init__(self, card: Any = None, bridge: FakeBridge | None = None) -> None:
        self._card, self.bridge = card, bridge or FakeBridge()

    def current(self):
        return None, self._card, "revision"


def fake_native_session(monkeypatch, session: Any) -> None:
    """Serve a read-only native session without a real scientific project."""
    from contextlib import contextmanager

    @contextmanager
    def fake_session(self, project, *, write=False):
        yield session

    monkeypatch.setattr(NativeGateway, "session", fake_session)


def fake_native_gate(monkeypatch, card: Any, bridge: FakeBridge) -> None:
    fake_native_session(monkeypatch, FakeSession(card=card, bridge=bridge))


def approve_request(**overrides):
    values: dict[str, Any] = {
        "request_id": "approve-request-00001",
        "revision": "0" * 64,
        "action": "approve",
        "card_id": KEY,
    }
    values.update(overrides)
    return ActionRequest.model_validate(values)


def test_intent_charges_only_production_scale_promotions():
    session = FakeSession(card=FakeCard(), bridge=FakeBridge(dossier=FakeDossier(30)))
    intent = final_design_intent(session, approve_request(), "user-" + "0" * 32)
    assert intent == FinalDesignIntent(KEY, 30, "user-" + "0" * 32)
    # Non-promote selections, other gates, test fixtures and validation pilots
    # never spend the balance (Pilot is excluded by contract).
    other_option = FakeSession(card=FakeCard(option_id="RUN_ANOTHER_PILOT"))
    assert final_design_intent(other_option, approve_request(), "user-" + "2" * 32) is None
    other_gate = FakeSession(card=FakeCard(gate_type="target-confirmation"))
    assert final_design_intent(other_gate, approve_request(), "user-" + "2" * 32) is None
    test_only = FakeSession(card=FakeCard(summary={"test_only_control_flow_fixture": True}))
    assert final_design_intent(test_only, approve_request(), "user-" + "2" * 32) is None
    validation = FakeSession(
        card=FakeCard(), bridge=FakeBridge(dossier=FakeDossier(6, ValidationExecutionAuthority()))
    )
    assert final_design_intent(validation, approve_request(), "user-" + "2" * 32) is None
    stale_card = FakeSession(
        card=FakeCard(card_id=KEY2), bridge=FakeBridge(dossier=FakeDossier(30))
    )
    assert final_design_intent(stale_card, approve_request(), "user-" + "2" * 32) is None


def test_intent_recovers_authoritative_reservation_for_resumes():
    contract = {
        "gate4_card_id": KEY,
        "requested_scale_candidates": 25,
        "authorizes_production_compute": True,
        "human_actor": "account:user-" + "1" * 32,
    }
    bridge = FakeBridge(contract=contract)
    resume = approve_request(action="resume", card_id=None)
    intent = final_design_intent(FakeSession(bridge=bridge), resume, "user-" + "2" * 32)
    assert intent is not None
    assert (intent.authority_key, intent.amount, intent.subject_id) == (
        KEY,
        25,
        "user-" + "1" * 32,
    )
    # A duplicate approval of the already-applied card reuses the same authority.
    duplicate = final_design_intent(
        FakeSession(bridge=bridge), approve_request(), "user-" + "2" * 32
    )
    assert duplicate is not None and duplicate.authority_key == KEY
    # Other cards and validated non-production authorities never match.
    foreign = final_design_intent(
        FakeSession(bridge=bridge), approve_request(card_id=KEY2), "user-" + "2" * 32
    )
    assert foreign is None
    no_compute = FakeBridge(contract={**contract, "authorizes_production_compute": False})
    assert final_design_intent(FakeSession(bridge=no_compute), resume, "user-" + "2" * 32) is None


def test_intent_fails_closed_on_unverifiable_authority():
    resume = approve_request(action="resume", card_id=None)
    contract = {
        "gate4_card_id": KEY,
        "requested_scale_candidates": 25,
        "authorizes_production_compute": True,
        "human_actor": "account:user-" + "1" * 32,
    }
    tampered = FakeBridge(
        contract={**contract, "requested_scale_candidates": 1}, contract_sha256=KEY2
    )
    with pytest.raises(ProductError) as denied:
        final_design_intent(FakeSession(bridge=tampered), resume, "user-" + "2" * 32)
    assert denied.value.code == "final_designs_unverified"
    bad_card = FakeBridge(contract={**contract, "gate4_card_id": "not-a-card"})
    with pytest.raises(ProductError) as denied:
        final_design_intent(FakeSession(bridge=bad_card), resume, "user-" + "2" * 32)
    assert denied.value.code == "final_designs_unverified"
    bad_amount = FakeBridge(contract={**contract, "requested_scale_candidates": "25"})
    with pytest.raises(ProductError) as denied:
        final_design_intent(FakeSession(bridge=bad_amount), resume, "user-" + "2" * 32)
    assert denied.value.code == "final_designs_unverified"
    wrong_kind = FakeBridge(contract=contract)
    wrong_kind.project_latest = lambda kind: (
        {"contract_type": "OtherContract", "contract_sha256": KEY2, "ref": "r"}
        if kind == "phase34-scale-authority"
        else None
    )
    with pytest.raises(ProductError) as denied:
        final_design_intent(FakeSession(bridge=wrong_kind), resume, "user-" + "2" * 32)
    assert denied.value.code == "final_designs_unverified"


def test_intent_fails_closed_on_malformed_production_evidence():
    # A promote approval with unreadable or malformed dossier evidence blocks
    # the request instead of bypassing the charge.
    missing = FakeSession(card=FakeCard(), bridge=FakeBridge(dossier=None))
    with pytest.raises(ProductError) as denied:
        final_design_intent(missing, approve_request(), "user-" + "2" * 32)
    assert denied.value.code == "final_designs_unverified"
    malformed = FakeSession(card=FakeCard(), bridge=FakeBridge(dossier=FakeDossier(30)))
    malformed.bridge._dossier.proposed_interpretation.requested_scale_candidates = "30"
    with pytest.raises(ProductError) as denied:
        final_design_intent(malformed, approve_request(), "user-" + "2" * 32)
    assert denied.value.code == "final_designs_unverified"


def test_unreadable_actor_requires_persisted_reservation():
    resume = approve_request(action="resume", card_id=None)
    contract = {
        "gate4_card_id": KEY,
        "requested_scale_candidates": 25,
        "authorizes_production_compute": True,
        "human_actor": "local-scientist",
    }
    bridge = FakeBridge(contract=contract)
    intent = final_design_intent(FakeSession(bridge=bridge), resume, "user-" + "2" * 32)
    assert intent is not None and intent.subject_id is None


# ------------------------------------------------------- settlement planning


def plan_row() -> dict[str, Any]:
    return {"id": "fdr-fixture", "authority_key": KEY}


def plan_project(**overrides) -> dict[str, Any]:
    project: dict[str, Any] = {
        "authority": None,
        "pools": [],
        "receipt_pools": {},
        "scale_jobs_active": False,
    }
    project.update(overrides)
    return project


def plan_receipts(**overrides) -> dict[str, Any]:
    receipts: dict[str, Any] = {
        "manifest_sha256": "f" * 64,
        "candidates": 30,
        "resumable": 0,
        "failed": 0,
        "native_determined": True,
    }
    receipts.update(overrides)
    return receipts


def test_planner_settles_the_newest_pool_including_negative_candidates():
    pools = [
        {"card_id": KEY, "contract_sha256": "c" * 64, "candidates": 12, "resumable": True},
        {"card_id": KEY, "contract_sha256": "d" * 64, "candidates": 28, "resumable": False},
        {"card_id": KEY2, "contract_sha256": "e" * 64, "candidates": 9, "resumable": False},
    ]
    decision, payload = plan_final_design_action(
        plan_row(), plan_project(pools=pools), {"card_response": {"delivered": True}}
    )
    assert decision == "settle"
    assert payload == {"campaign_sha256": "d" * 64, "delivered": 28}


def test_planner_holds_live_resumable_and_uncertain_campaigns():
    row = plan_row()
    resumable = plan_project(
        pools=[{"card_id": KEY, "contract_sha256": "c" * 64, "candidates": 5, "resumable": True}]
    )
    assert plan_final_design_action(row, resumable, {}) == (
        "hold",
        {"reason": "resumable_batches"},
    )
    live = plan_project(
        pools=[{"card_id": KEY, "contract_sha256": "c" * 64, "candidates": 5, "resumable": False}],
        scale_jobs_active=True,
    )
    assert plan_final_design_action(row, live, {}) == ("hold", {"reason": "native_scale_active"})
    incomplete_receipts = plan_project(
        authority={"card_id": KEY},
        receipt_pools={KEY: plan_receipts(candidates=12, resumable=1)},
    )
    assert plan_final_design_action(row, incomplete_receipts, {}) == (
        "hold",
        {"reason": "campaign_incomplete"},
    )
    operationally_failed = plan_project(
        authority={"card_id": KEY},
        receipt_pools={KEY: plan_receipts(candidates=12, failed=1)},
    )
    # An inconclusive campaign is recoverable-by-contract, never no-delivery proof.
    assert plan_final_design_action(row, operationally_failed, {}) == (
        "hold",
        {"reason": "campaign_incomplete"},
    )
    undetermined = plan_project(
        authority={"card_id": KEY},
        receipt_pools={KEY: plan_receipts(native_determined=False)},
    )
    # Completed batches with technically invalid / evidence-unknown outcomes are
    # not verified scientifically negative deliveries.
    assert plan_final_design_action(row, undetermined, {}) == (
        "hold",
        {"reason": "evidence_undetermined"},
    )
    in_flight_jobs = plan_project(
        authority={"card_id": KEY},
        receipt_pools={KEY: plan_receipts()},
        scale_jobs_active=True,
    )
    assert plan_final_design_action(row, in_flight_jobs, {}) == (
        "hold",
        {"reason": "native_scale_active"},
    )
    assert plan_final_design_action(
        row, plan_project(), {"card_response": None, "request_state": "interrupted"}
    ) == ("hold", {"reason": "request_in_flight"})
    assert plan_final_design_action(
        row, plan_project(), {"card_response": None, "request_state": "succeeded"}
    ) == ("hold", {"reason": "uncertain"})
    assert plan_final_design_action(
        row,
        plan_project(),
        {"card_response": None, "request_state": None, "admission_active": True},
    ) == ("hold", {"reason": "request_in_flight"})


def test_planner_charges_complete_native_zero_pass_from_durable_receipts():
    row = plan_row()
    # Complete durable NATIVE population, every candidate a verified FAIL, and
    # NO published pool: full charge from the checksum-bound manifest receipts.
    complete = plan_project(
        authority={"card_id": KEY},
        receipt_pools={KEY: plan_receipts(candidates=30)},
    )
    assert plan_final_design_action(row, complete, {}) == (
        "settle",
        {"campaign_sha256": "f" * 64, "delivered": 30},
    )


def test_planner_settles_superseded_campaign_before_considering_release():
    row = plan_row()
    # Delayed reconciliation: a complete all-FAIL campaign was superseded by a
    # newer Gate-4 round (newer authority AND newer manifest). The old designs
    # were produced: settle them, never refund them.
    superseded_complete = plan_project(
        authority={"card_id": KEY2},
        receipt_pools={KEY: plan_receipts(candidates=24)},
    )
    assert plan_final_design_action(row, superseded_complete, {}) == (
        "settle",
        {"campaign_sha256": "f" * 64, "delivered": 24},
    )
    # Abandoned mid-flight: the verified retained partial population is final.
    superseded_partial = plan_project(
        authority={"card_id": KEY2},
        receipt_pools={KEY: plan_receipts(candidates=9, resumable=1, failed=1)},
    )
    assert plan_final_design_action(row, superseded_partial, {}) == (
        "settle",
        {"campaign_sha256": "f" * 64, "delivered": 9},
    )
    # Supersession never turns technical/unknown outcomes into designs.
    superseded_undetermined = plan_project(
        authority={"card_id": KEY2},
        receipt_pools={KEY: plan_receipts(native_determined=False)},
    )
    assert plan_final_design_action(row, superseded_undetermined, {}) == (
        "hold",
        {"reason": "evidence_undetermined"},
    )
    # Missing/corrupted artifact evidence holds instead of settling.
    corrupted = plan_project(
        authority={"card_id": KEY},
        receipt_pools={KEY: {"unverified": True, "manifest_sha256": "f" * 64}},
    )
    assert plan_final_design_action(row, corrupted, {}) == (
        "hold",
        {"reason": "receipts_unverified"},
    )


def test_planner_releases_only_with_authoritative_proof():
    row = plan_row()
    superseded_unregistered = plan_project(authority={"card_id": KEY2})
    # Superseded with NO registered campaign of its own: nothing was produced.
    assert plan_final_design_action(row, superseded_unregistered, {}) == (
        "release",
        {"reason": "superseded_authority"},
    )
    assert plan_final_design_action(
        row, plan_project(), {"card_response": None, "request_state": "failed"}
    ) == ("release", {"reason": "approval_not_applied"})
    applied = plan_project()
    assert plan_final_design_action(
        row, applied, {"card_response": {"delivered": True}, "request_state": "failed"}
    ) == ("hold", {"reason": "awaiting_campaign_outcome"})


# ------------------------------------------------------- scoped service gate


@pytest.fixture
def scoped_fixture(tmp_path: Path):
    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    (tmp_path / "models.yaml").write_text(
        "default:\n  provider: openai\n  model: fixture-model\n  secret_env: FIXTURE_KEY\n"
    )
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    store = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    admin = store.bootstrap_admin("admin", PASSWORD, "管理员")
    alice = store.register("alice", PASSWORD, "Alice")
    bob = store.register("bob", PASSWORD, "Bob")
    for user in (alice, bob):
        store.update_user(admin, user.id, status="active")
    team = store.create_team(alice, "Team")
    invite = store.invite(alice, team["id"], "bob", role="admin")
    store.respond_invitation(bob, invite["id"], accept=True)
    launched: list[str] = []
    runtime = MultiUserRuntime(
        context,
        store,
        lambda scoped: NativeGateway(scoped, tmp_path / "models.yaml"),
        launcher=lambda admission, _service: launched.append(admission.id),
    )
    return runtime, store, admin, alice, bob, team["id"], launched


def test_exhausted_balance_blocks_before_any_scale_side_effect(scoped_fixture, monkeypatch):
    runtime, _store, _admin, alice, _bob, team, launched = scoped_fixture
    with runtime.bind(alice, team) as service:
        assert isinstance(service, ScopedProductService)
        ensure(runtime.resources, alice, team, key=KEY2, project="workbench-other", amount=20)
        fake_native_gate(monkeypatch, FakeCard(), FakeBridge(dossier=FakeDossier(15)))
        submitted: list[str] = []
        monkeypatch.setattr(
            ProductService,
            "submit",
            lambda self, project, request: (
                submitted.append(request.request_id) or {"id": request.request_id}
            ),
        )
        request = approve_request()
        with pytest.raises(ProductError) as denied:
            service.submit("workbench-1", request)
        assert denied.value.code == "final_designs_exhausted"
        assert submitted == [] and launched == []
        journal = service.journal()
        try:
            assert journal.get(request.request_id) is None
        finally:
            journal.close()
        latest = runtime.resources.usage(alice, team)["admissions"][0]
        assert latest["state"] == "failed"


def test_submit_and_retry_reuse_one_authoritative_reservation(scoped_fixture, monkeypatch):
    runtime, _store, _admin, alice, bob, team, _launched = scoped_fixture
    with runtime.bind(alice, team) as service:
        fake_native_gate(monkeypatch, FakeCard(), FakeBridge(dossier=FakeDossier(10)))
        monkeypatch.setattr(
            ProductService,
            "submit",
            lambda self, project, request: {"id": request.request_id, "state": "succeeded"},
        )
        request = approve_request()
        service.submit("workbench-1", request)
        service.submit("workbench-1", request)
        balance = runtime.resources.final_designs_balance(alice.id)
        assert (balance["reserved"], balance["delivered"]) == (10, 0)

        journal = service.journal()
        try:
            journal.reserve(
                "workbench-1", {"operation": "action", **request.model_dump(mode="json")}
            )
            journal.update(request.request_id, "failed", {"code": "fixture"})
        finally:
            journal.close()
        retried: list[str] = []
        monkeypatch.setattr(
            ProductService,
            "retry",
            lambda self, request_id: (
                retried.append(request_id) or {"id": request_id, "state": "succeeded"}
            ),
        )
        # Another team admin performs the recovery; the charge stays with Alice.
        with runtime.bind(bob, team) as recovering:
            recovering.retry(request.request_id)
        assert retried == [request.request_id]
        entries = runtime.resources.final_designs_entries(scope_id=team)
        assert len(entries) == 1
        assert entries[0]["subject_id"] == alice.id


def test_retry_is_blocked_when_balance_is_insufficient(scoped_fixture, monkeypatch):
    runtime, _store, _admin, alice, _bob, team, _launched = scoped_fixture
    with runtime.bind(alice, team) as service:
        ensure(runtime.resources, alice, team, key=KEY2, project="workbench-other", amount=25)
        fake_native_gate(monkeypatch, FakeCard(), FakeBridge(dossier=FakeDossier(20)))
        request = approve_request()
        journal = service.journal()
        try:
            journal.reserve(
                "workbench-1", {"operation": "action", **request.model_dump(mode="json")}
            )
            journal.update(request.request_id, "failed", {"code": "fixture"})
        finally:
            journal.close()
        resumed: list[str] = []
        monkeypatch.setattr(
            ProductService,
            "retry",
            lambda self, request_id: resumed.append(request_id) or {"id": request_id},
        )
        with pytest.raises(ProductError) as denied:
            service.retry(request.request_id)
        assert denied.value.code == "final_designs_exhausted"
        assert resumed == []


# ------------------------------------------------------ visibility & transport


def test_usage_blocks_respect_personal_and_team_visibility(quota_fixture):
    store, ledger, admin, alice, _bob, team = quota_fixture
    ensure(ledger, alice, alice.id, project="workbench-personal", amount=12)
    ensure(ledger, alice, team, project="workbench-team", key=KEY2, amount=8)
    personal = ledger.usage(alice, alice.id)["final_designs"]
    assert personal["kind"] == "personal"
    assert personal["allowance"] == 30 and personal["remaining"] == 10
    assert {entry["project_id"] for entry in personal["entries"]} == {
        "workbench-personal",
        "workbench-team",
    }
    team_view = ledger.usage(alice, team)["final_designs"]
    assert team_view["kind"] == "team"
    assert "allowance" not in team_view and "remaining" not in team_view
    assert (team_view["reserved"], team_view["delivered"]) == (8, 0)
    assert [entry["project_id"] for entry in team_view["entries"]] == ["workbench-team"]
    foreign = ledger.usage(admin, alice.id)["final_designs"]
    assert foreign["kind"] == "personal" and foreign["remaining"] == 10
    actions = [event["action"] for event in store.audit(admin)]
    assert "admin.final_designs.read" in actions


def test_admin_aggregate_reports_subject_balances(quota_fixture):
    _store, ledger, admin, alice, _bob, _team = quota_fixture
    row, _ = ensure(ledger, alice, alice.id, amount=20)
    ledger.settle_final_designs(row["id"], campaign_sha256=KEY, delivered=16)
    report = ledger.final_designs_admin(admin)
    assert report["rule"] == FINAL_DESIGN_RULE
    entry = next(subject for subject in report["subjects"] if subject["subject_id"] == alice.id)
    assert (entry["reserved"], entry["delivered"], entry["remaining"]) == (0, 16, 14)
    assert entry["username"] == "alice"
    assert report["entries"][0]["state"] == "settled"


def test_worker_config_carries_captured_stage_budgets(tmp_path, monkeypatch):
    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    (tmp_path / "models.yaml").write_text(
        "default:\n  provider: openai\n  model: fixture-model\n  secret_env: FIXTURE_KEY\n"
    )
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    store = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    admin = store.bootstrap_admin("admin", PASSWORD, "管理员")
    alice = store.register("alice", PASSWORD, "Alice")
    store.update_user(admin, alice.id, status="active")

    class Probe:
        def snapshots(self):
            return ()

    from easydesign.product import resource_supervisor

    runtime = MultiUserRuntime(
        context, store, lambda scoped: NativeGateway(scoped, tmp_path / "models.yaml")
    )
    control = resource_supervisor.ResourceSupervisor(runtime, probe=Probe())
    admission, _ = control.ledger.reserve(
        alice,
        alice.id,
        "create-request-00001",
        {"operation": "create"},
        stage_budgets={"pilot": 5, "scale": 7},
    )

    class FakePopen:
        def __init__(self, argv, **_kwargs) -> None:
            self.argv, self.pid = argv, 4242

    monkeypatch.setattr(resource_supervisor.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(resource_supervisor, "process_identity", lambda _pid: "fixture-start")
    with runtime.bind(alice, alice.id) as service:
        control.launch(admission, service)
    config = json.loads(
        (
            context.runtime_root / "state/accounts/worker-config" / (admission.id + ".json")
        ).read_text()
    )
    assert config["stage_budgets"] == {"pilot": 5, "scale": 7}
    assert stage_budgets_from_config(config) == {"pilot": 5, "scale": 7}
    assert control.ledger.get(admission.id).state == "queued"


# ------------------------------------------------- fail-closed classification


class FlakySession:
    """First read fails; every later read would succeed."""

    def __init__(self) -> None:
        self.bridge = FakeBridge(dossier=FakeDossier(10))
        self.calls = 0

    def current(self):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient native read failure")
        return None, FakeCard(), "revision"


def test_transient_classification_failure_blocks_dispatch(scoped_fixture, monkeypatch):
    runtime, _store, _admin, alice, _bob, team, launched = scoped_fixture
    flaky = FlakySession()
    with runtime.bind(alice, team) as service:
        fake_native_session(monkeypatch, flaky)
        submitted: list[str] = []
        monkeypatch.setattr(
            ProductService,
            "submit",
            lambda self, project, request: (
                submitted.append(request.request_id) or {"id": request.request_id}
            ),
        )
        request = approve_request()
        with pytest.raises(ProductError) as denied:
            service.submit("workbench-1", request)
        # The later read works, yet this request must not dispatch anything:
        # no native acceptance, no journal row, no worker launch.
        assert denied.value.code == "final_designs_unverified"
        assert flaky.calls == 1 and submitted == [] and launched == []
        journal = service.journal()
        try:
            assert journal.get(request.request_id) is None
        finally:
            journal.close()
        assert runtime.resources.usage(alice, team)["admissions"][0]["state"] == "failed"
        # A clean retry with the now-readable state proceeds normally.
        service.submit("workbench-1", request)
        assert submitted == [request.request_id]
        assert runtime.resources.final_designs_balance(alice.id)["reserved"] == 10


def test_unreadable_original_actor_blocks_without_persisted_row(scoped_fixture, monkeypatch):
    runtime, _store, _admin, alice, bob, team, _launched = scoped_fixture
    contract = {
        "gate4_card_id": KEY,
        "requested_scale_candidates": 25,
        "authorizes_production_compute": True,
        "human_actor": "local-scientist",
    }
    resume = approve_request(action="resume", card_id=None)
    with runtime.bind(bob, team) as service:
        fake_native_gate(monkeypatch, None, FakeBridge(contract=contract))
        resumed: list[str] = []
        monkeypatch.setattr(
            ProductService,
            "submit",
            lambda self, project, request: (
                resumed.append(request.request_id) or {"id": request.request_id}
            ),
        )
        with pytest.raises(ProductError) as denied:
            service.submit("workbench-1", resume)
        assert denied.value.code == "final_designs_actor_unverified"
        assert resumed == []
        # With the persisted reservation the same recovery proceeds, and the
        # charge keeps Alice as the billed person instead of the retried admin.
        ensure(
            runtime.resources,
            alice,
            team,
            project="workbench-1",
            amount=25,
            subject_id=alice.id,
        )
        service.submit("workbench-1", resume)
        assert resumed == [resume.request_id]
        assert runtime.resources.final_designs_entries(scope_id=team)[0]["subject_id"] == (alice.id)


def test_ordinary_non_scale_approvals_are_unaffected(scoped_fixture, monkeypatch):
    runtime, _store, _admin, alice, _bob, team, launched = scoped_fixture
    with runtime.bind(alice, team) as service:
        fake_native_gate(monkeypatch, FakeCard(gate_type="target-confirmation"), FakeBridge())
        submitted: list[str] = []
        monkeypatch.setattr(
            ProductService,
            "submit",
            lambda self, project, request: (
                submitted.append(request.request_id) or {"id": request.request_id}
            ),
        )
        service.submit("workbench-1", approve_request())
        assert submitted == [approve_request().request_id]
        assert runtime.resources.final_designs_balance(alice.id)["reserved"] == 0
        assert runtime.resources.usage(alice, team)["admissions"][0]["state"] == "reserved"


def test_same_request_retry_reactivates_against_original_actor(scoped_fixture, monkeypatch):
    runtime, _store, _admin, alice, bob, team, _launched = scoped_fixture
    request = approve_request()
    # Alice's approve was charged but never applied natively; reconciliation
    # released it as approval_not_applied BEFORE any authority publication.
    row, _ = ensure(
        runtime.resources,
        alice,
        team,
        project="workbench-1",
        amount=10,
        request_id=request.request_id,
        subject_id=alice.id,
    )
    runtime.resources.release_final_designs(row["id"], "approval_not_applied")
    # The original submit really reached command authorization (its compute
    # command keeps Alice as the actor a same-request retry must preserve).
    runtime.resources.reserve(
        alice,
        team,
        request.request_id,
        {"project": "workbench-1", "request": request.model_dump(mode="json")},
    )
    with runtime.bind(alice, team) as service:
        journal = service.journal()
        try:
            journal.reserve(
                "workbench-1", {"operation": "action", **request.model_dump(mode="json")}
            )
            journal.update(request.request_id, "failed", {"code": "fixture"})
        finally:
            journal.close()
    fake_native_gate(monkeypatch, FakeCard(), FakeBridge(dossier=FakeDossier(10)))
    monkeypatch.setattr(
        ProductService,
        "retry",
        lambda self, request_id: {"id": request_id, "state": "succeeded"},
    )
    # Bob, another team admin, recovers Alice's exact request: the released row
    # must reactivate against ALICE, never against the retrying administrator.
    with runtime.bind(bob, team) as recovering:
        recovering.retry(request.request_id)
    revived = runtime.resources.final_designs_row(team, "workbench-1", KEY)
    assert revived["state"] == "reserved" and revived["subject_id"] == alice.id
    # A genuinely new, independently authorized approval on a different Gate-4
    # card bills its own approver.
    new_request = approve_request(request_id="approve-request-00002", card_id=KEY2)
    fake_native_gate(monkeypatch, FakeCard(card_id=KEY2), FakeBridge(dossier=FakeDossier(5)))
    monkeypatch.setattr(
        ProductService,
        "submit",
        lambda self, project, request: {"id": request.request_id, "state": "succeeded"},
    )
    with runtime.bind(bob, team) as acting:
        acting.submit("workbench-1", new_request)
    fresh = runtime.resources.final_designs_row(team, "workbench-1", KEY2)
    assert fresh["state"] == "reserved" and fresh["subject_id"] == bob.id


def test_terminally_released_reservation_cannot_authorize_dispatch(scoped_fixture, monkeypatch):
    runtime, _store, _admin, alice, _bob, team, launched = scoped_fixture
    row, _ = ensure(
        runtime.resources, alice, team, project="workbench-1", amount=10, subject_id=alice.id
    )
    runtime.resources.release_final_designs(row["id"], "superseded_authority")
    fake_native_gate(monkeypatch, FakeCard(), FakeBridge(dossier=FakeDossier(10)))
    submitted: list[str] = []
    monkeypatch.setattr(
        ProductService,
        "submit",
        lambda self, project, request: (
            submitted.append(request.request_id) or {"id": request.request_id}
        ),
    )
    with pytest.raises(ProductError) as denied:
        with runtime.bind(alice, team) as service:
            service.submit("workbench-1", approve_request())
    assert denied.value.code == "final_designs_released_authority"
    assert submitted == [] and launched == []


# --------------------------------------- real-controller reconciliation


SCALE_THREAD = "quota-scale-thread"


def _native_evidence_observations(
    run_root: Path, campaign, batch, *, tag: str, source_run_id: str, determined: bool
):
    """TRUE native FAIL evidence inside its declared source run.

    Artifacts live in the real indexed run the receipt declares, so the
    controller's ``ref.verify(run_root)`` check passes for valid evidence and
    fails for corrupted files. ``determined`` False models a native run that
    could not decide (native_pass unknown), which the native runtime treats as
    operationally inconclusive.
    """
    from easydesign.agent.phase3_native_contracts import (
        NativeCandidateEvidence,
        NativeFilterDecision,
        NativeFilterProfile,
        NativeFilterRule,
    )
    from easydesign.agent.phase34_contracts import (
        ScaleCandidateLineageV3,
        ScaleCandidateObservation,
        ScaleCandidateValidity,
    )
    from easydesign.core import ArtifactRef, canonical_model_sha256

    evidence_dir = run_root / f"fixture-native-evidence-{tag}"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    config_file = evidence_dir / "filter-config.json"
    config_file.write_text('{"fixture": true}\n')
    profile = NativeFilterProfile(
        configuration={"fixture": True},
        configuration_ref=ArtifactRef.from_file(
            run_root=evidence_dir,
            relative_path=config_file.name,
            artifact_id="filter-config",
            role="test",
            file_format="json",
        ),
        rules=(
            NativeFilterRule(feature="fixture-confidence", lower_is_better=True, threshold=0.5),
        ),
    )
    profile_sha256 = canonical_model_sha256(profile)
    observations = []
    for ordinal in (1, 2):
        sequence = f"EVQLVESGGGLV{ordinal}TPGAG"
        candidate_id = "candidate-" + f"{ordinal:032x}"
        passed = False if determined else None
        value = 0.9 if determined else None
        artifact = evidence_dir / f"evidence-{ordinal}.json"
        artifact.write_text('{"native": "fixture"}\n')
        evidence = NativeCandidateEvidence(
            candidate_id=candidate_id,
            profile_sha256=profile_sha256,
            native_pass=passed,
            decisions=(
                NativeFilterDecision(
                    feature="fixture-confidence",
                    threshold=0.5,
                    lower_is_better=True,
                    value=value,
                    passed=passed,
                ),
            ),
            metrics={"designed_chain_sequence": sequence, "fixture_confidence": value},
        )
        observations.append(
            ScaleCandidateObservation(
                lineage=ScaleCandidateLineageV3(
                    campaign_id=campaign.campaign_id,
                    source_run_id=source_run_id,
                    batch_id=batch.batch_id,
                    shard_id=batch.batch_id,
                    candidate_id=candidate_id,
                    strategy_id="strategy-fixture",
                    strategy_ordinal=ordinal,
                    generation_task_id="task-" + f"{ordinal:032x}",
                    generation_attempt=1,
                    sequence_sha256=hashlib.sha256(sequence.encode()).hexdigest(),
                    artifact_refs=(
                        ArtifactRef.from_file(
                            run_root=run_root,
                            relative_path=f"{evidence_dir.name}/{artifact.name}",
                            artifact_id=f"fixture-{ordinal}",
                            role="test",
                            file_format="json",
                        ),
                    ),
                ),
                validity=(
                    ScaleCandidateValidity.VALID_EVALUATED
                    if determined
                    else ScaleCandidateValidity.INVALID_EXECUTION_PRODUCT
                ),
                development_score=0.1 if determined else None,
                failure_reason=None if determined else "native filter undetermined",
                native_evidence=evidence,
                native_profile=profile,
            )
        )
    return observations


def publish_scale_campaign(
    context: WorkspaceContext, scope_id: str, alice, *, card: str, tag: str, receipts: str
) -> None:
    """Publish a REAL Gate-4 authority + Scale manifest (+ batch receipts).

    Uses the native APIs end to end (contract publication, checksum-bound batch
    receipts with verified scoped artifacts). No global candidate pool is ever
    published, matching complete all-FAIL/undetermined campaigns or
    operationally incomplete ones.
    """
    from easydesign.agent.phase34_batches import (
        ScaleBatchReceipt,
        ScaleBatchStore,
        partition_campaign,
    )
    from easydesign.agent.phase34_contracts import (
        ExecutionMode,
        ExecutionProjection,
        Gate4PromotionAuthority,
        ScaleCampaignSpecification,
    )
    from easydesign.agent.phase34_runtime import Phase34Runtime
    from easydesign.agent.session_store import SessionStore
    from easydesign.core import canonical_model_sha256
    from easydesign.orchestration.research import initialize_research_project
    from tests.agent_support import structure

    native = receipts in {"native-fail", "native-unknown"}
    policy = "boltzgen-native-v1" if native else "legacy-independent"
    project_id = "workbench-scale"
    scoped = context.with_execution_scope(ExecutionScope(scope_id=scope_id, actor_id=alice.id))
    scoped.ensure_layout()
    with scoped.activate():
        root = scoped.projects_root / project_id
        if not (root / "PROJECT.yaml").is_file():
            source = scoped.runtime_root / "tmp/quota-input.pdb"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(structure("A"))
            initialize_research_project(project_root=root, target=source)
        store = SessionStore(root)
        try:
            if not store.db.execute("SELECT 1 FROM threads WHERE id=?", (SCALE_THREAD,)).fetchone():
                store.thread(SCALE_THREAD, "quota-fixture-fingerprint", "Fixture scale goal")
            # A REAL indexed source run for receipt lineage: deterministic local
            # target preparation, exactly like the native Gate fixture.
            from easydesign.agent.tools import TargetBridge
            from tests.agent_support import terminal as terminal_mark

            target_bridge = TargetBridge(root, SCALE_THREAD, store)
            try:
                run_root, run_manifest = target_bridge.run()
            except Exception:
                target_bridge.prepare_target()
                terminal_mark(target_bridge)
                run_root, run_manifest = target_bridge.run()
            source_run_id = run_manifest.run_id
            bridge = Phase34Runtime(
                root,
                SCALE_THREAD,
                store,
                through="handoff",
                prediction_backend="protenix-v2",
                pilot_candidate_budget=30,
                scale_candidate_budget=30,
                product_auto_continue=True,
            )
            authority = Gate4PromotionAuthority(
                authority_id="auth-" + tag * 20,
                gate4_card_id=card,
                pilot_dossier_sha256="2" * 64,
                selected_strategy_ids=("strategy-fixture",),
                requested_scale_candidates=2,
                production_strategy_allocations={"strategy-fixture": 2},
                authority_scope="scientist-approved",
                human_actor="account:" + alice.id,
                authorizes_scientific_scale=True,
                authorizes_production_compute=True,
                evidence_policy=policy,
            )
            bridge.publish_contract(
                kind="phase34-scale-authority",
                contract=authority,
                dependencies={"pilot": "2" * 64},
            )
            if receipts == "not-started":
                return  # A real authority with no campaign or delivered evidence yet.
            campaign = ScaleCampaignSpecification(
                campaign_id="scale-" + tag * 20,
                promotion_authority=authority,
                execution=ExecutionProjection(
                    mode=ExecutionMode.PRODUCTION,
                    requested_production_candidates=2,
                    execution_candidates=2,
                    uses_real_generation_backend=True,
                    uses_real_prediction_backend=False,
                    purpose="fixture durable population accounting",
                ),
                strategy_allocations={"strategy-fixture": 2},
                generation_backend="fixture-gen",
                prediction_backend="protenix-v2",
                allocation_policy="fixture",
                evidence_policy=policy,
            )
            manifest = partition_campaign(project_id, campaign, batch_size=100)
            bridge.publish_contract(
                kind="phase34-scale-batch-manifest",
                contract=manifest,
                dependencies={"promotion": canonical_model_sha256(authority)},
            )
            batch = manifest.batches[0]
            journal = ScaleBatchStore(root / "agent/phase34-scale" / campaign.campaign_id, manifest)
            if native:
                journal.append(
                    ScaleBatchReceipt(
                        manifest_sha256=journal.digest,
                        batch_id=batch.batch_id,
                        state="completed",
                        source_run_id=source_run_id,
                        candidates=tuple(
                            _native_evidence_observations(
                                run_root,
                                campaign,
                                batch,
                                tag=tag,
                                source_run_id=source_run_id,
                                determined=receipts == "native-fail",
                            )
                        ),
                    )
                )
            elif receipts == "legacy-complete":
                from easydesign.agent.phase34_contracts import (
                    ScaleCandidateLineageV3,
                    ScaleCandidateObservation,
                    ScaleCandidateValidity,
                )
                from easydesign.core import ArtifactRef

                evidence_dir = run_root / f"fixture-native-evidence-{tag}"
                evidence_dir.mkdir(parents=True, exist_ok=True)
                observations = []
                for ordinal in (1, 2):
                    evidence = evidence_dir / f"evidence-{ordinal}.json"
                    evidence.write_text('{"fixture": true}\n')
                    observations.append(
                        ScaleCandidateObservation(
                            lineage=ScaleCandidateLineageV3(
                                campaign_id=campaign.campaign_id,
                                source_run_id=source_run_id,
                                batch_id=batch.batch_id,
                                shard_id=batch.batch_id,
                                candidate_id="candidate-" + f"{ordinal:032x}",
                                strategy_id="strategy-fixture",
                                strategy_ordinal=ordinal,
                                generation_task_id="task-" + f"{ordinal:032x}",
                                generation_attempt=1,
                                sequence_sha256=hashlib.sha256(
                                    f"SEQ{ordinal}".encode()
                                ).hexdigest(),
                                artifact_refs=(
                                    ArtifactRef.from_file(
                                        run_root=run_root,
                                        relative_path=f"{evidence_dir.name}/{evidence.name}",
                                        artifact_id=f"fixture-{ordinal}",
                                        role="test",
                                        file_format="json",
                                    ),
                                ),
                            ),
                            validity=ScaleCandidateValidity.INVALID_EXECUTION_PRODUCT,
                            failure_reason="fixture zero-evaluable retention",
                        )
                    )
                journal.append(
                    ScaleBatchReceipt(
                        manifest_sha256=journal.digest,
                        batch_id=batch.batch_id,
                        state="completed",
                        source_run_id=source_run_id,
                        candidates=tuple(observations),
                    )
                )
            elif receipts == "failed":
                journal.append(
                    ScaleBatchReceipt(
                        manifest_sha256=journal.digest,
                        batch_id=batch.batch_id,
                        state="failed",
                        source_run_id=source_run_id,
                        operational_failures=("fixture worker ended",),
                    )
                )
            # receipts == "resumable": the batch journal stays empty.
        finally:
            store.close()


def build_scale_campaign(context: WorkspaceContext, scope_id: str, alice, *, receipts: str) -> str:
    publish_scale_campaign(context, scope_id, alice, card=KEY, tag="1", receipts=receipts)
    return "workbench-scale"


@pytest.fixture
def scale_workspace(tmp_path: Path, monkeypatch):
    from easydesign.orchestration.profile import initialize_runtime_profile
    from easydesign.product.resource_supervisor import ResourceSupervisor

    (tmp_path / "easydesign-workspace.yaml").write_text(
        'schema_version: "0.1"\nworkspace_id: quota-scale-accounting\n'
    )
    (tmp_path / "models.yaml").write_text(
        "default:\n  provider: openai\n  model: fixture-model\n  secret_env: FIXTURE_KEY\n"
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    initialize_runtime_profile(context.profile_path)
    store = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    admin = store.bootstrap_admin("admin", PASSWORD, "管理员")
    alice = store.register("alice", PASSWORD, "Alice")
    store.update_user(admin, alice.id, status="active")
    team = store.create_team(alice, "Scale Team")

    class Probe:
        def snapshots(self):
            return ()

    runtime = MultiUserRuntime(
        context, store, lambda scoped: NativeGateway(scoped, tmp_path / "models.yaml")
    )
    control = ResourceSupervisor(runtime, probe=Probe())
    return control, runtime, admin, alice, team["id"], context


def test_reconciliation_charges_complete_native_all_fail_without_pool(scale_workspace):
    """Complete NATIVE all-FAIL evidence, zero passing candidates, NO pool event."""
    control, runtime, _admin, alice, team, context = scale_workspace
    project_id = build_scale_campaign(context, team, alice, receipts="native-fail")
    runtime.resources.ensure_final_designs(
        alice, team, project_id, "approve-request-00001", KEY, 2, subject_id=alice.id
    )
    control.tick()
    settled = runtime.resources.final_designs_row(team, project_id, KEY)
    assert settled["state"] == "settled"
    assert settled["delivered"] == 2
    assert re.fullmatch(r"[0-9a-f]{64}", settled["campaign_sha256"] or "")
    balance = runtime.resources.final_designs_balance(alice.id)
    assert (balance["reserved"], balance["delivered"], balance["remaining"]) == (0, 2, 28)


@pytest.mark.parametrize("receipts", ["not-started", "native-fail"])
def test_launch_interleaves_with_real_settlement_without_refund_or_double_charge(
    scale_workspace, monkeypatch, receipts
):
    control, runtime, admin, alice, team, context = scale_workspace
    project_id = build_scale_campaign(context, team, alice, receipts=receipts)
    request_id = "settlement-launch-window"
    reservation, _ = runtime.resources.ensure_final_designs(
        alice, team, project_id, request_id, KEY, 2, subject_id=alice.id
    )
    admission, _ = runtime.resources.reserve(
        alice,
        team,
        request_id,
        {"operation": "create"},
        dispatch_channel="scoped_worker",
    )
    with runtime.bind(alice, team) as service:
        journal = service.journal()
        try:
            journal.reserve(project_id, {"request_id": request_id, "operation": "create"})
        finally:
            journal.close()
    reached, finish_settlement = threading.Event(), threading.Event()
    method = "settle_final_designs" if receipts == "native-fail" else "note_final_designs_hold"
    original = getattr(runtime.resources, method)

    def paused_ledger_decision(*args, **kwargs):
        # Keep real checksum-verified native facts and the real ledger operation;
        # only pause at the decision's database boundary.
        reached.set()
        assert finish_settlement.wait(10), "Fixture settlement was not released"
        return original(*args, **kwargs)

    def launch():
        with runtime.bind(alice, team) as service:
            control.launch(admission, service)

    monkeypatch.setattr(runtime.resources, method, paused_ledger_decision)
    monkeypatch.setattr(
        "easydesign.product.resource_supervisor.subprocess.Popen",
        lambda *a, **k: pytest.fail("Scientific spawn"),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        reconciling = pool.submit(control.tick)
        try:
            assert reached.wait(10)
            assert runtime.resources.final_designs_balance(alice.id)["reserved"] == 2
            pool.submit(launch).result(timeout=3)
            assert runtime.resources.get(admission.id).state == "queued"
            assert not reconciling.done()
        finally:
            finish_settlement.set()
        reconciling.result(timeout=10)
    control.tick()  # Repeat observation must not charge or refund again.
    row = runtime.resources.final_designs_row(team, project_id, KEY)
    balance = runtime.resources.final_designs_balance(alice.id)
    charged = [
        event
        for event in runtime.accounts.audit(admin)
        if event["action"] == "final_designs.settle" and event["target_id"] == reservation["id"]
    ]
    if receipts == "not-started":
        assert row["state"] == "reserved" and row["reason"] == "request_in_flight"
        assert (balance["reserved"], balance["delivered"], len(charged)) == (2, 0, 0)
    else:
        assert row["state"] == "settled" and row["delivered"] == 2
        assert (balance["reserved"], balance["delivered"], len(charged)) == (0, 2, 1)


def test_reconciliation_holds_native_undetermined_evidence(scale_workspace):
    """Completed batches whose native outcome is UNKNOWN are not a delivery."""
    control, runtime, _admin, alice, team, context = scale_workspace
    project_id = build_scale_campaign(context, team, alice, receipts="native-unknown")
    runtime.resources.ensure_final_designs(
        alice, team, project_id, "approve-request-00001", KEY, 2, subject_id=alice.id
    )
    control.tick()
    held = runtime.resources.final_designs_row(team, project_id, KEY)
    assert held["state"] == "reserved"
    assert held["reason"] == "evidence_undetermined"
    assert runtime.resources.final_designs_balance(alice.id)["reserved"] == 2


def test_reconciliation_holds_legacy_zero_evaluable_population(scale_workspace):
    """Technically invalid outputs are not verified negative deliveries."""
    control, runtime, _admin, alice, team, context = scale_workspace
    project_id = build_scale_campaign(context, team, alice, receipts="legacy-complete")
    runtime.resources.ensure_final_designs(
        alice, team, project_id, "approve-request-00001", KEY, 2, subject_id=alice.id
    )
    control.tick()
    held = runtime.resources.final_designs_row(team, project_id, KEY)
    assert held["state"] == "reserved"
    assert held["reason"] == "evidence_undetermined"
    assert runtime.resources.final_designs_balance(alice.id)["reserved"] == 2


def test_reconciliation_holds_resumable_campaign_without_pool(scale_workspace):
    control, runtime, _admin, alice, team, context = scale_workspace
    project_id = build_scale_campaign(context, team, alice, receipts="resumable")
    runtime.resources.ensure_final_designs(
        alice, team, project_id, "approve-request-00001", KEY, 2, subject_id=alice.id
    )
    control.tick()
    held = runtime.resources.final_designs_row(team, project_id, KEY)
    assert held["state"] == "reserved"
    assert held["reason"] == "campaign_incomplete"
    assert runtime.resources.final_designs_balance(alice.id)["reserved"] == 2


def test_reconciliation_holds_operationally_failed_campaign_without_pool(scale_workspace):
    """An inconclusive event is recoverable evidence, never no-delivery proof."""
    control, runtime, _admin, alice, team, context = scale_workspace
    project_id = build_scale_campaign(context, team, alice, receipts="failed")
    runtime.resources.ensure_final_designs(
        alice, team, project_id, "approve-request-00001", KEY, 2, subject_id=alice.id
    )
    control.tick()
    held = runtime.resources.final_designs_row(team, project_id, KEY)
    assert held["state"] == "reserved"
    assert held["reason"] == "campaign_incomplete"
    assert runtime.resources.final_designs_balance(alice.id)["reserved"] == 2


def test_delayed_reconciliation_never_refunds_superseded_negative_campaign(scale_workspace):
    """Old complete all-FAIL campaign, newer authority AND newer manifest, no
    pool event for the old campaign, and the controller reconciles only after
    everything exists: the old produced designs are CHARGED, not refunded."""
    control, runtime, _admin, alice, team, context = scale_workspace
    project_id = build_scale_campaign(context, team, alice, receipts="native-fail")
    publish_scale_campaign(context, team, alice, card=KEY2, tag="2", receipts="resumable")
    runtime.resources.ensure_final_designs(
        alice, team, project_id, "approve-old-request-0001", KEY, 2, subject_id=alice.id
    )
    control.tick()
    settled = runtime.resources.final_designs_row(team, project_id, KEY)
    assert settled["state"] == "settled"
    assert settled["delivered"] == 2
    assert re.fullmatch(r"[0-9a-f]{64}", settled["campaign_sha256"] or "")
    balance = runtime.resources.final_designs_balance(alice.id)
    assert (balance["reserved"], balance["delivered"], balance["remaining"]) == (0, 2, 28)


def test_superseded_native_unknown_outcome_stays_held(scale_workspace):
    """A newer approval cannot turn unknown native results into designs."""
    control, runtime, _admin, alice, team, context = scale_workspace
    project_id = build_scale_campaign(context, team, alice, receipts="native-unknown")
    publish_scale_campaign(context, team, alice, card=KEY2, tag="2", receipts="resumable")
    runtime.resources.ensure_final_designs(
        alice, team, project_id, "approve-old-request-0001", KEY, 2, subject_id=alice.id
    )
    control.tick()
    held = runtime.resources.final_designs_row(team, project_id, KEY)
    assert held["state"] == "reserved"
    assert held["reason"] == "evidence_undetermined"
    assert runtime.resources.final_designs_balance(alice.id)["reserved"] == 2


def test_corrupted_artifact_evidence_holds_settlement(scale_workspace):
    """Corrupted evidence inside the declared source run must hold, not settle."""
    control, runtime, _admin, alice, team, context = scale_workspace
    project_id = build_scale_campaign(context, team, alice, receipts="native-fail")
    from easydesign.orchestration.local_project import resolve_project_run

    scoped = context.with_execution_scope(ExecutionScope(scope_id=team, actor_id=alice.id))
    with scoped.activate():
        summary = resolve_project_run(scoped.projects_root / project_id, required=True)
        assert summary is not None
        evidence = summary.path / "fixture-native-evidence-1" / "evidence-1.json"
        assert evidence.is_file()
        evidence.write_text('{"corrupted": true}\n')
    runtime.resources.ensure_final_designs(
        alice, team, project_id, "approve-request-00001", KEY, 2, subject_id=alice.id
    )
    control.tick()
    held = runtime.resources.final_designs_row(team, project_id, KEY)
    assert held["state"] == "reserved"
    assert held["reason"] == "receipts_unverified"
    assert runtime.resources.final_designs_balance(alice.id)["reserved"] == 2


# ----------------------------------------------------------- HTTP integration


@pytest.fixture
def http_fixture(tmp_path: Path):
    import threading

    import httpx

    from easydesign.product.account_server import MultiUserServer

    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    (tmp_path / "models.yaml").write_text(
        "default:\n  provider: openai\n  model: fixture-model\n  secret_env: FIXTURE_KEY\n"
    )
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    store = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    admin = store.bootstrap_admin("admin", PASSWORD, "管理员")
    alice = store.register("alice", PASSWORD, "Alice")
    store.update_user(admin, alice.id, status="active")
    runtime = MultiUserRuntime(
        context, store, lambda scoped: NativeGateway(scoped, tmp_path / "models.yaml")
    )
    server = MultiUserServer(runtime, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, runtime, store, admin, alice, httpx
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_admin_final_designs_route_is_admin_only_audited_and_shaped(http_fixture):
    import json as json_module

    server, runtime, store, admin, alice, httpx = http_fixture
    ensure(runtime.resources, alice, alice.id, amount=12)
    origin = f"http://127.0.0.1:{server.server_port}"

    with httpx.Client(
        base_url=origin, headers={"Origin": origin}, timeout=10, trust_env=False
    ) as anonymous:
        login = anonymous.post(
            "/api/v1/accounts/login", json={"username": "alice", "password": PASSWORD}
        )
        assert login.status_code == 200
        alice_headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        assert (
            anonymous.get("/api/v1/admin/final-designs", headers=alice_headers).status_code == 403
        )
    with httpx.Client(
        base_url=origin, headers={"Origin": origin}, timeout=10, trust_env=False
    ) as admin_client:
        login = admin_client.post(
            "/api/v1/accounts/login", json={"username": "admin", "password": PASSWORD}
        )
        assert login.status_code == 200
        admin_client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        response = admin_client.get("/api/v1/admin/final-designs")
        assert response.status_code == 200
        payload = response.json()
    assert payload["rule"] == FINAL_DESIGN_RULE
    subject = next(item for item in payload["subjects"] if item["subject_id"] == alice.id)
    assert subject["username"] == "alice"
    assert (subject["allowance"], subject["reserved"], subject["delivered"]) == (30, 12, 0)
    assert subject["remaining"] == 18
    entry = payload["entries"][0]
    assert entry["state"] == "reserved"
    assert set(entry) == {
        "id",
        "scope_id",
        "project_id",
        "request_id",
        "authority_key",
        "subject_id",
        "amount",
        "delivered",
        "state",
        "campaign_sha256",
        "reason",
        "created_at",
        "updated_at",
    }
    actions = [
        json_module.loads(event["details"]).get("target") if event["details"] else None
        for event in store.audit(admin)
        if event["action"] == "admin.final_designs.read"
    ]
    assert actions
