from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from easydesign.product.accounts import AccountStore, ResourceLimits
from easydesign.product.contracts import ProductError
from easydesign.product.resource_control import ResourceLedger

PASSWORD = "Fixture-password-2026!"


@pytest.fixture
def resource_fixture(tmp_path: Path):
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


def test_personal_and_team_quota_checks_are_atomic_across_concurrent_users(resource_fixture):
    store, ledger, admin, alice, bob, team = resource_fixture
    store.set_limits(admin, team, ResourceLimits(max_active_jobs=1))

    def submit(user):
        try:
            return ledger.reserve(user, team, "request-" + user.username * 5, {"action": "create"})[
                0
            ].id
        except ProductError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, (alice, bob)))
    assert results.count("quota_exceeded") == 1
    assert len(ledger.active()) == 1


def test_idempotent_retry_cannot_duplicate_or_transfer_a_reservation(resource_fixture):
    _store, ledger, _admin, alice, bob, team = resource_fixture
    request_id = "same-request-00000001"
    admission, created = ledger.reserve(alice, team, request_id, {"action": "approve"})
    assert created
    duplicate, created = ledger.reserve(alice, team, request_id, {"action": "approve"})
    assert duplicate == admission and not created
    with pytest.raises(ProductError):
        ledger.reserve(bob, team, request_id, {"action": "approve"})
    with pytest.raises(ProductError):
        ledger.reserve(alice, team, request_id, {"action": "reject"})
    ledger.transition(admission.id, "released")
    terminal, created = ledger.reserve(alice, team, request_id, {"action": "approve"})
    assert terminal.state == "released" and not created
    resumed, created = ledger.reserve(bob, team, request_id, {"action": "approve"}, retry=True)
    assert created and resumed.actor_id == bob.id and resumed.scientific_actor_id == alice.id


def test_personal_limit_cannot_be_evaded_by_switching_teams(resource_fixture):
    store, ledger, _admin, alice, _bob, team = resource_fixture
    second = store.create_team(alice, "Other Team")
    ledger.reserve(alice, team, "first-request-00001", {"operation": "create"})
    with pytest.raises(ProductError) as denied:
        ledger.reserve(alice, second["id"], "second-request-0001", {"operation": "create"})
    assert denied.value.code == "quota_exceeded"


def test_team_member_cannot_reserve_scientific_work_but_can_discuss(resource_fixture):
    store, ledger, _admin, alice, bob, team = resource_fixture
    store.set_member(alice, team, bob.id, role="member")
    with pytest.raises(ProductError):
        ledger.reserve(bob, team, "blocked-request-0001", {"action": "approve"})
    admission, _ = ledger.reserve(
        bob, team, "question-request-001", {"action": "message"}, kind="conversation"
    )
    assert admission.gpu_slots == 0


def test_read_only_admin_cannot_borrow_another_users_resources(resource_fixture):
    _store, ledger, admin, alice, _bob, _team = resource_fixture
    with pytest.raises(ProductError):
        ledger.reserve(admin, alice.id, "borrow-request-0001", {"action": "create"})
    with pytest.raises(ProductError):
        ledger.reserve_upload(admin, alice.id, "a" * 64, 1024)


def test_gpu_allocation_cannot_exceed_approved_slots(resource_fixture):
    _store, ledger, _admin, alice, _bob, _team = resource_fixture
    admission, _ = ledger.reserve(alice, alice.id, "gpu-request-0000001", {"action": "create"})
    with pytest.raises(ProductError):
        ledger.transition(admission.id, "running", devices=(0, 1))
    with pytest.raises(ProductError):
        ledger.transition(admission.id, "running", devices=(0, 0))
    running = ledger.transition(admission.id, "running", devices=(2,), worker_pid=12345)
    assert running.devices == (2,)
    ledger.transition(admission.id, "released")
    with pytest.raises(ProductError):
        ledger.transition(admission.id, "running")


def test_legacy_admission_schema_migrates_concurrently_without_changing_records(resource_fixture):
    store, ledger, _admin, alice, _bob, _team = resource_fixture
    admission, _ = ledger.reserve(
        alice,
        alice.id,
        "legacy-schema-request",
        {"action": "create"},
        stage_budgets={"pilot": 17, "scale": 29},
    )
    # Reconstruct the pre-dispatch-channel schema in this disposable database.
    with store.db(write=True) as db:
        db.execute("ALTER TABLE admissions DROP COLUMN dispatch_channel")
        db.execute("ALTER TABLE admissions DROP COLUMN auth_version")
        audit_before = [tuple(row) for row in db.execute("SELECT * FROM audit_events")]
    with ThreadPoolExecutor(max_workers=4) as pool:
        ledgers = list(pool.map(lambda _: ResourceLedger(store), range(8)))
    for migrated in ledgers:
        assert migrated.get(admission.id) == admission.model_copy(update={"auth_version": None})
        assert migrated.command_budgets(alice.id, admission.request_id) == {
            "pilot": 17,
            "scale": 29,
        }
    with store.db() as db:
        assert [tuple(row) for row in db.execute("SELECT * FROM audit_events")] == audit_before


def test_uploads_are_charged_once_and_team_data_is_shared_only_inside_the_scope(resource_fixture):
    store, ledger, admin, alice, bob, team = resource_fixture
    store.set_limits(admin, team, ResourceLimits(max_stored_upload_bytes=2048))
    key = "a" * 64
    reservation, created = ledger.reserve_upload(alice, team, key, 2048)
    assert created
    ledger.finish_upload(reservation, published=True)
    same, created = ledger.reserve_upload(bob, team, key, 2048)
    assert same == reservation and not created
    with pytest.raises(ProductError) as denied:
        ledger.reserve_upload(alice, team, "b" * 64, 1024)
    assert denied.value.code == "upload_quota_exceeded"
    private, created = ledger.reserve_upload(bob, bob.id, key, 2048)
    assert created and private != reservation
    assert ledger.usage(alice, team)["stored_upload_bytes"] == 2048
