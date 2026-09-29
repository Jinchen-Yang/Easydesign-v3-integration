from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from easydesign.product.accounts import AccountStore
from easydesign.product.contracts import ProductError

PASSWORD = "Fixture-password-2026!"


@pytest.fixture
def accounts(tmp_path: Path):
    clock = [1_800_000_000.0]
    store = AccountStore(tmp_path / "accounts.sqlite", clock=lambda: clock[0])
    admin = store.bootstrap_admin("admin", PASSWORD, "平台管理员")
    alice = store.register("alice", PASSWORD, "Alice")
    bob = store.register("bob", PASSWORD, "Bob")
    for user in (alice, bob):
        store.update_user(admin, user.id, status="active")
    return store, admin, store.user(alice.id), store.user(bob.id), clock


def test_registration_allows_immediate_login_and_passwords_are_not_public(tmp_path: Path):
    store = AccountStore(tmp_path / "accounts.sqlite")
    admin = store.bootstrap_admin("admin", PASSWORD, "管理员")
    registered = store.register("Alice", PASSWORD, "Alice")
    assert registered.status == "active"
    session = store.login("ALICE", PASSWORD, peer="fixture")
    assert store.authenticate(session.token).id == registered.id
    assert session.csrf_token and session.csrf_token != session.token
    assert PASSWORD not in json.dumps(store.users(admin))
    with sqlite3.connect(store.path) as db:
        rows = db.execute("SELECT password_hash FROM users").fetchall()
        assert all(PASSWORD not in row[0] for row in rows)
        assert len({row[0] for row in rows}) == 2
        assert db.execute("SELECT token_hash FROM sessions").fetchone()[0] != session.token


@pytest.mark.parametrize("status", ["pending", "suspended", "rejected"])
def test_open_registration_does_not_bypass_account_restrictions(accounts, status):
    store, admin, alice, _bob, _clock = accounts
    store.update_user(admin, alice.id, status=status)
    with pytest.raises(ProductError) as rejected:
        store.login("alice", PASSWORD, peer="fixture")
    assert rejected.value.code == "account_" + status


def test_password_reset_and_disable_revoke_sessions(accounts):
    store, admin, alice, _bob, _clock = accounts
    session = store.login("alice", PASSWORD, peer="fixture")
    store.update_user(admin, alice.id, status="suspended")
    with pytest.raises(ProductError):
        store.authenticate(session.token)
    store.update_user(admin, alice.id, status="active")
    with pytest.raises(ProductError):
        store.authenticate(session.token)
    store.reset_password(admin, alice.id, "Temporary-new-password!")
    fresh = store.login("alice", "Temporary-new-password!", peer="fixture")
    assert fresh.user.must_change_password
    with pytest.raises(ProductError) as denied:
        store.scope(fresh.user)
    assert denied.value.code == "password_change_required"
    store.change_password(fresh.user, "Temporary-new-password!", "Chosen-next-password!")
    with pytest.raises(ProductError):
        store.authenticate(fresh.token)
    assert not store.login(
        "alice", "Chosen-next-password!", peer="fixture"
    ).user.must_change_password


def test_sessions_expire_and_logout_only_revokes_its_own_session(accounts):
    store, _admin, _alice, _bob, clock = accounts
    first = store.login("alice", PASSWORD, peer="fixture")
    second = store.login("alice", PASSWORD, peer="fixture")
    store.logout(first.token)
    with pytest.raises(ProductError):
        store.authenticate(first.token)
    assert store.authenticate(second.token).username == "alice"
    clock[0] += 8 * 24 * 3600
    with pytest.raises(ProductError):
        store.authenticate(second.token)


def test_session_renewal_slides_expiry_only_in_the_second_half(accounts):
    store, _admin, _alice, _bob, clock = accounts
    start = clock[0]
    session = store.login("alice", PASSWORD, peer="fixture")
    # Fresh session: more than half the TTL remains; renewal stays a no-op
    # so steady traffic adds no per-request write load.
    assert store.renew(session.token) is None
    clock[0] = start + 4 * 24 * 3600
    renewed = store.renew(session.token)
    assert renewed == pytest.approx(start + 4 * 24 * 3600 + 7 * 24 * 3600)
    # Inside the renewed window (more than half the new TTL left) it is a no-op.
    clock[0] = start + 7 * 24 * 3600
    assert store.renew(session.token) is None
    # Active use keeps the session alive past the original 7-day horizon.
    clock[0] = start + 9 * 24 * 3600
    assert store.authenticate(session.token).username == "alice"


def test_session_renewal_never_resurrects_revoked_or_invalidated_sessions(accounts):
    store, admin, alice, _bob, clock = accounts
    session = store.login("alice", PASSWORD, peer="fixture")
    clock[0] += 4 * 24 * 3600
    store.logout(session.token)
    assert store.renew(session.token) is None
    invalidated = store.login("alice", PASSWORD, peer="fixture")
    clock[0] += 4 * 24 * 3600
    store.reset_password(admin, alice.id, "Temporary-new-password!")
    assert store.renew(invalidated.token) is None
    with pytest.raises(ProductError):
        store.authenticate(invalidated.token)
    # Unknown or malformed tokens are ignored rather than raising.
    assert store.renew("x" * 40) is None


def test_admin_privilege_and_last_admin_are_checked_from_the_store(accounts):
    store, admin, alice, bob, _clock = accounts
    with pytest.raises(ProductError):
        store.update_user(alice, bob.id, role="admin")
    forged = alice.model_copy(update={"role": "admin"})
    with pytest.raises(ProductError):
        store.users(forged)
    with pytest.raises(ProductError) as last:
        store.update_user(admin, admin.id, status="suspended")
    assert last.value.code == "last_admin"
    with pytest.raises(ProductError):
        store.bootstrap_admin("second-admin", PASSWORD, "Unexpected bootstrap")


def test_team_invitation_is_private_until_accepted_and_removal_is_immediate(accounts):
    store, _admin, alice, bob, _clock = accounts
    team = store.create_team(alice, "Binder Team")
    invite = store.invite(alice, team["id"], "bob", role="member")
    with pytest.raises(ProductError):
        store.scope(bob, team["id"])
    assert store.invitations(bob)[0]["id"] == invite["id"]
    with pytest.raises(ProductError):
        store.respond_invitation(alice, invite["id"], accept=True)
    store.respond_invitation(bob, invite["id"], accept=True)
    access = store.scope(bob, team["id"])
    assert access.kind == "team" and access.can_edit and not access.can_execute
    with pytest.raises(ProductError):
        store.scope(bob, team["id"], execute=True)
    assert store.scope(alice, team["id"], execute=True).can_execute
    store.set_member(alice, team["id"], bob.id, role="admin")
    assert store.scope(bob, team["id"], execute=True).can_execute
    store.set_member(alice, team["id"], bob.id, remove=True)
    with pytest.raises(ProductError):
        store.scope(bob, team["id"])


def test_team_membership_keeps_private_data_private_and_admin_observation_is_read_only(accounts):
    store, admin, alice, bob, _clock = accounts
    team = store.create_team(alice, "Binder Team")
    invitation = store.invite(alice, team["id"], "bob")
    store.respond_invitation(bob, invitation["id"], accept=True)
    private = store.scope(alice)
    assert private.kind == "personal" and private.can_execute
    with pytest.raises(ProductError):
        store.scope(bob, private.id)
    observation = store.scope(admin, private.id)
    assert (
        observation.role == "observer" and not observation.can_edit and not observation.can_execute
    )
    with pytest.raises(ProductError):
        store.scope(admin, private.id, edit=True)
    with pytest.raises(ProductError):
        store.scope(admin, private.id, execute=True)
    with pytest.raises(ProductError):
        store.scope(admin, team["id"], execute=True)


def test_last_team_admin_cannot_be_removed(accounts):
    store, _admin, alice, _bob, _clock = accounts
    team = store.create_team(alice, "Binder Team")
    with pytest.raises(ProductError) as rejected:
        store.set_member(alice, team["id"], alice.id, role="member")
    assert rejected.value.code == "last_team_admin"


def test_registration_collision_is_atomic_and_case_insensitive(accounts):
    store, _admin, _alice, _bob, _clock = accounts

    def register(name):
        try:
            return store.register(name, PASSWORD, name).id
        except ProductError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(register, ("carol", "CAROL")))
    assert result.count("username_unavailable") == 1


def test_login_attempts_are_rate_limited_and_error_details_do_not_leak_passwords(accounts):
    store, _admin, _alice, _bob, clock = accounts
    for _ in range(5):
        with pytest.raises(ProductError) as denied:
            store.login("alice", "wrong-password", peer="limited-peer")
        assert denied.value.code == "invalid_credentials"
    with pytest.raises(ProductError) as limited:
        store.login("alice", PASSWORD, peer="limited-peer")
    assert limited.value.code == "rate_limited"
    clock[0] += 16 * 60
    assert store.login("alice", PASSWORD, peer="limited-peer").user.username == "alice"


def test_security_audit_is_append_only_and_excludes_credentials(accounts):
    store, admin, alice, _bob, _clock = accounts
    store.update_user(admin, alice.id, status="suspended")
    store.update_user(admin, alice.id, status="active")
    session = store.login("alice", PASSWORD, peer="fixture")
    store.logout(session.token)
    events = store.audit(admin)
    rendered = json.dumps(events)
    assert (
        PASSWORD not in rendered
        and session.token not in rendered
        and session.csrf_token not in rendered
    )
    assert {event["action"] for event in events} >= {
        "account.register",
        "account.update",
        "session.login",
        "session.logout",
    }
    with pytest.raises(ProductError):
        store.audit(alice)
    with sqlite3.connect(store.path) as db, pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE audit_events SET action='changed'")
