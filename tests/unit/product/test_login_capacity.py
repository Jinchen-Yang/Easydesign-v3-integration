from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from easydesign.product.accounts import AccountStore
from easydesign.product.contracts import ProductError

PASSWORD = "Concurrent-login-fixture!"


@pytest.fixture
def accounts(tmp_path: Path):
    store = AccountStore(tmp_path / "accounts.sqlite")
    admin = store.bootstrap_admin("admin", PASSWORD, "Administrator")
    alice = store.register("alice", PASSWORD, "Alice")
    bob = store.register("bob", PASSWORD, "Bob")
    for user in (alice, bob):
        store.update_user(admin, user.id, status="active")
    return store, admin, alice, bob


@pytest.fixture
def paused_password_check(monkeypatch):
    """Control the cryptographic boundary while still computing the real hash."""
    entered, release = threading.Event(), threading.Event()
    derive = hashlib.pbkdf2_hmac

    def paused(*args, **kwargs):
        result = derive(*args, **kwargs)
        if (
            threading.current_thread().name.startswith("login-check")
            and args[1] == PASSWORD.encode()
        ):
            entered.set()
            assert release.wait(10), "Password-check test did not release its worker"
        return result

    monkeypatch.setattr(hashlib, "pbkdf2_hmac", paused)
    yield entered, release
    release.set()


def test_password_check_does_not_block_another_accounts_update(accounts, paused_password_check):
    store, admin, _alice, bob = accounts
    entered, release = paused_password_check
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="login-check") as login_pool:
        login = login_pool.submit(store.login, "alice", PASSWORD, peer="shared-network")
        try:
            assert entered.wait(5)
            with ThreadPoolExecutor(max_workers=1) as writer_pool:
                update = writer_pool.submit(store.update_user, admin, bob.id, status="suspended")
                try:
                    assert update.result(timeout=2).status == "suspended"
                finally:
                    release.set()
        finally:
            release.set()
        assert store.authenticate(login.result(timeout=5).token).username == "alice"


@pytest.mark.parametrize("change", ["reset_password", "suspend", "suspend_then_reactivate"])
def test_inflight_login_cannot_issue_a_session_after_credentials_are_revoked(
    accounts, paused_password_check, change
):
    store, admin, alice, _bob = accounts
    entered, release = paused_password_check
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="login-check") as pool:
        login = pool.submit(store.login, "alice", PASSWORD, peer="shared-network")
        try:
            assert entered.wait(5)
            if change == "reset_password":
                store.reset_password(admin, alice.id, "A-new-fixture-password!")
            else:
                store.update_user(admin, alice.id, status="suspended")
                if change == "suspend_then_reactivate":
                    store.update_user(admin, alice.id, status="active")
        finally:
            release.set()
        with pytest.raises(ProductError) as rejected:
            login.result(timeout=5)
        assert rejected.value.code in {"invalid_credentials", "account_suspended"}
    assert not any(event["action"] == "session.login" for event in store.audit(admin))


def test_three_hundred_accounts_can_login_from_one_network(tmp_path: Path):
    # A frozen clock keeps this a rate-limit regression, not a timing-dependent
    # benchmark. Eight clients still use genuine production-strength hashing.
    store = AccountStore(tmp_path / "accounts.sqlite", clock=lambda: 1_800_000_000.0)
    admin = store.bootstrap_admin("admin", PASSWORD, "Administrator")

    def create(index):
        name = f"attendee-{index:03}"
        user = store.register(name, PASSWORD, name, peer=f"setup-{index}")
        store.update_user(admin, user.id, status="active")
        return name

    def login(name):
        session = store.login(name, PASSWORD, peer="one-conference-network")
        assert store.authenticate(session.token).username == name
        return session.token

    with ThreadPoolExecutor(max_workers=8) as pool:
        names = list(pool.map(create, range(300)))
        sessions = list(pool.map(login, names))
    assert len(set(sessions)) == 300


@pytest.mark.parametrize("pending", [0, 1])
def test_login_capacity_reports_overload_and_recovers_without_more_hash_workers(
    tmp_path: Path, paused_password_check, pending
):
    store = AccountStore(
        tmp_path / "accounts.sqlite",
        login_max_concurrency=1,
        login_max_pending=pending,
        login_wait_timeout=0,
    )
    store.bootstrap_admin("admin", PASSWORD, "Administrator")
    entered, release = paused_password_check
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="login-check") as pool:
        first = pool.submit(store.login, "admin", PASSWORD, peer="one-network")
        try:
            assert entered.wait(5)
            with pytest.raises(ProductError) as busy:
                store.login("admin", PASSWORD, peer="one-network")
            assert (busy.value.code, busy.value.status) == ("login_busy", 503)
        finally:
            release.set()
        assert store.authenticate(first.result(timeout=5).token).username == "admin"
    assert store.authenticate(store.login("admin", PASSWORD, peer="one-network").token)


def test_concurrent_invalid_credentials_cannot_bypass_account_failure_limit(accounts):
    store, _admin, _alice, _bob = accounts

    def attempt(_index):
        with pytest.raises(ProductError) as rejected:
            store.login("alice", "Incorrect-fixture-password!", peer="one-network")
        return rejected.value.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        errors = list(pool.map(attempt, range(16)))
    assert errors.count("invalid_credentials") == 5
    assert errors.count("rate_limited") == 11
    with pytest.raises(ProductError) as blocked:
        store.login("alice", PASSWORD, peer="one-network")
    assert blocked.value.code == "rate_limited"


def test_shared_source_failure_limit_still_blocks_password_spraying(tmp_path: Path):
    store = AccountStore(tmp_path / "accounts.sqlite", clock=lambda: 1_800_000_000.0)

    def attempt(index):
        with pytest.raises(ProductError) as rejected:
            store.login(f"unknown-{index}", PASSWORD, peer="one-network")
        return rejected.value.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        errors = list(pool.map(attempt, range(128)))
    assert errors.count("invalid_credentials") == 120
    assert errors.count("rate_limited") == 8


def test_successful_login_keeps_real_production_password_hash_strength(tmp_path: Path, monkeypatch):
    derive = hashlib.pbkdf2_hmac
    observed = []

    def record(algorithm, password, salt, iterations, *args, **kwargs):
        result = derive(algorithm, password, salt, iterations, *args, **kwargs)
        observed.append((algorithm, iterations, len(salt), len(result)))
        return result

    monkeypatch.setattr(hashlib, "pbkdf2_hmac", record)
    store = AccountStore(tmp_path / "accounts.sqlite")
    store.bootstrap_admin("admin", PASSWORD, "Administrator")
    session = store.login("admin", PASSWORD, peer="one-network")
    assert store.authenticate(session.token).username == "admin"
    assert observed
    assert all(sample == ("sha256", 600_000, 16, 32) for sample in observed)


def test_forced_password_change_does_not_block_another_accounts_update(
    accounts, paused_password_check
):
    store, admin, alice, bob = accounts
    store.reset_password(admin, alice.id, PASSWORD)
    session = store.login("alice", PASSWORD, peer="one-network")
    assert session.user.must_change_password
    entered, release = paused_password_check
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="login-check") as pool:
        change = pool.submit(
            store.change_password, session.user, PASSWORD, "A-chosen-fixture-password!"
        )
        try:
            assert entered.wait(5)
            with ThreadPoolExecutor(max_workers=1) as writer_pool:
                update = writer_pool.submit(store.update_user, admin, bob.id, status="suspended")
                try:
                    assert update.result(timeout=2).status == "suspended"
                finally:
                    release.set()
        finally:
            release.set()
        change.result(timeout=5)
    with pytest.raises(ProductError):
        store.authenticate(session.token)
    fresh = store.login("alice", "A-chosen-fixture-password!", peer="one-network")
    assert not fresh.user.must_change_password
    assert store.scope(fresh.user).can_execute


@pytest.mark.parametrize("change", ["reset_password", "suspend_then_reactivate", "change_password"])
def test_inflight_password_change_cannot_overwrite_newer_credentials(
    accounts, paused_password_check, change
):
    store, admin, _alice, _bob = accounts
    session = store.login("alice", PASSWORD, peer="one-network")
    entered, release = paused_password_check
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="login-check") as pool:
        pending = pool.submit(
            store.change_password, session.user, PASSWORD, "Stale-request-password!"
        )
        authoritative_password = PASSWORD
        try:
            assert entered.wait(5)
            if change == "reset_password":
                authoritative_password = "Admin-reset-password!"
                store.reset_password(admin, session.user.id, authoritative_password)
            elif change == "change_password":
                authoritative_password = "Newer-request-password!"
                store.change_password(session.user, PASSWORD, authoritative_password)
            else:
                store.update_user(admin, session.user.id, status="suspended")
                store.update_user(admin, session.user.id, status="active")
        finally:
            release.set()
        with pytest.raises(ProductError) as rejected:
            pending.result(timeout=5)
        assert rejected.value.code == "invalid_credentials"
    with pytest.raises(ProductError):
        store.authenticate(session.token)
    fresh = store.login("alice", authoritative_password, peer="one-network")
    assert fresh.user.must_change_password == (change == "reset_password")
