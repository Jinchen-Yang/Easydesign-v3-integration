"""Doudou capacity contracts, using isolated providers (never paid model calls)."""

import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from easydesign.product.contracts import ProductError
from easydesign.product.rabbit_capacity import RabbitCapacityLimits
from easydesign.product.rabbit_chat import RabbitChatService, SubprocessChatProvider

PAYLOAD = {
    "locale": "en",
    "messages": [{"role": "user", "content": "Hello"}],
    "context": {"stage": "Idle", "status": "idle", "goal": ""},
}
IDENTITY = {"actor_id": "user-a", "scope_id": "scope-a", "request_id": "request-a"}


def test_queued_request_rechecks_permission_before_dispatch_without_spending_budget(
    tmp_path: Path,
) -> None:
    calls = []
    authorized = True

    def provider(request):
        calls.append(request)
        yield {"type": "delta", "text": "hello"}
        yield {"type": "done"}

    def authorize():
        if not authorized:
            raise ProductError("permission_denied", "private reason", 403)

    path = tmp_path / "authorization.sqlite"
    limits = RabbitCapacityLimits(max_active=1, max_total_requests=2)
    service = RabbitChatService(provider, limits=limits, ledger_path=path)
    active = service.events(PAYLOAD, **IDENTITY)
    assert next(active)["state"] == "running"
    assert next(active)["type"] == "delta"
    waiting_identity = dict(IDENTITY, actor_id="user-b", request_id="revoked-in-queue")
    waiting = service.events(PAYLOAD, **waiting_identity, authorize=authorize)
    assert next(waiting)["state"] == "queued"
    authorized = False
    assert list(active) == [{"type": "done"}]
    assert list(waiting)[-1] == {"type": "error", "code": "authorization_revoked"}
    assert service.request_status(**waiting_identity) == {
        "request_id": "revoked-in-queue",
        "state": "failed",
        "dispatched": False,
        "code": "authorization_revoked",
    }
    assert len(calls) == 1
    assert service.capacity_status()["dispatched_requests"] == 1
    service.close()
    restored = RabbitChatService(provider, limits=limits, ledger_path=path)
    try:
        assert restored.request_status(**waiting_identity)["code"] == "authorization_revoked"
        with pytest.raises(ProductError) as error:
            restored.events(PAYLOAD, **waiting_identity)
        assert error.value.code == "request_already_processed"
        assert list(restored.events(PAYLOAD, **dict(IDENTITY, request_id="replacement")))[-1] == {
            "type": "done"
        }
        assert len(calls) == 2
    finally:
        restored.close()


def test_dispatched_failure_is_not_replayed_even_after_restart(tmp_path: Path) -> None:
    calls = []

    def provider(request):
        calls.append(request)
        yield {"type": "error", "code": "timeout"}

    ledger = tmp_path / "chat.sqlite"
    service = RabbitChatService(provider, ledger_path=ledger)
    assert list(service.events(PAYLOAD, **IDENTITY))[-1] == {
        "type": "error",
        "code": "outcome_unknown",
    }
    assert service.request_status(**IDENTITY)["dispatched"] is True
    service.close()
    restored = RabbitChatService(provider, ledger_path=ledger)
    try:
        with pytest.raises(ProductError) as error:
            restored.events(PAYLOAD, **IDENTITY)
        assert error.value.code == "request_already_processed"
        assert len(calls) == 1
        assert restored.request_status(**IDENTITY)["state"] == "failed"
    finally:
        restored.close()


@pytest.mark.parametrize("action", ["cancel", "fail"])
def test_dispatch_guard_fails_closed_and_cannot_bypass_concurrent_cancellation(action):
    calls = []

    def provider(request):
        calls.append(request)
        yield {"type": "done"}

    service = RabbitChatService(provider)

    def authorize():
        if action == "cancel":
            service.cancel(**IDENTITY)
        else:
            raise RuntimeError("unavailable account database; do not disclose")

    try:
        result = list(service.events(PAYLOAD, **IDENTITY, authorize=authorize))
        expected = "cancelled" if action == "cancel" else "authorization_revoked"
        assert result[-1] == {"type": "error", "code": expected}
        assert service.request_status(**IDENTITY)["dispatched"] is False
        assert service.capacity_status()["dispatched_requests"] == 0
        assert calls == []
    finally:
        service.close()


def test_bounded_queue_and_unstarted_close_release_without_dispatch() -> None:
    calls = []

    def provider(request):
        calls.append(request)
        yield {"type": "delta", "text": "hello"}
        yield {"type": "done"}

    service = RabbitChatService(provider, limits=RabbitCapacityLimits(max_active=1, max_queued=1))
    first = service.events(PAYLOAD, **IDENTITY)
    assert next(first)["state"] == "running"
    assert next(first)["type"] == "delta"
    waiting_id = dict(IDENTITY, actor_id="user-b", request_id="request-b")
    waiting = service.events(PAYLOAD, **waiting_id)
    assert service.request_status(**waiting_id)["state"] == "queued"
    with pytest.raises(ProductError, match="queue") as error:
        service.events(PAYLOAD, **dict(IDENTITY, actor_id="user-c", request_id="request-c"))
    assert error.value.code == "queue_full"
    waiting.close()
    assert service.request_status(**waiting_id) == {
        "request_id": "request-b",
        "state": "cancelled",
        "dispatched": False,
        "code": "cancelled",
    }
    replacement = service.events(PAYLOAD, **dict(waiting_id, request_id="request-d"))
    replacement.close()
    assert list(first) == [{"type": "done"}]
    assert len(calls) == 1
    service.close()


def test_request_budget_reserves_pending_but_cancel_before_dispatch_does_not_spend(
    tmp_path: Path,
) -> None:
    calls = []

    def provider(request):
        calls.append(request)
        yield {"type": "done"}

    limits = RabbitCapacityLimits(max_total_requests=1)
    path = tmp_path / "budget.sqlite"
    service = RabbitChatService(provider, limits=limits, ledger_path=path)
    abandoned = service.events(PAYLOAD, **IDENTITY)
    with pytest.raises(ProductError) as error:
        service.events(PAYLOAD, **dict(IDENTITY, request_id="over-budget"))
    assert error.value.code == "budget_exhausted"
    abandoned.close()
    assert list(service.events(PAYLOAD, **dict(IDENTITY, request_id="replacement")))[-1] == {
        "type": "done"
    }
    service.close()
    service = RabbitChatService(provider, limits=limits, ledger_path=path)
    try:
        with pytest.raises(ProductError) as error:
            service.events(PAYLOAD, **dict(IDENTITY, request_id="after-restart"))
        assert error.value.code == "budget_exhausted"
        assert len(calls) == 1
    finally:
        service.close()


def test_rate_limited_request_waits_then_times_out_without_provider_call() -> None:
    now = [0.0]
    calls = []

    def provider(request):
        calls.append(request)
        yield {"type": "done"}

    service = RabbitChatService(
        provider,
        clock=lambda: now[0],
        limits=RabbitCapacityLimits(requests_per_minute=1, queue_timeout_seconds=5),
    )
    assert list(service.events(PAYLOAD, **IDENTITY))[-1] == {"type": "done"}
    waiting_id = dict(IDENTITY, request_id="wait-for-rate")
    waiting = service.events(PAYLOAD, **waiting_id)
    assert next(waiting)["state"] == "queued"
    now[0] = 6
    assert list(waiting) == [{"type": "error", "code": "queue_timeout"}]
    assert service.request_status(**waiting_id)["dispatched"] is False
    now[0] = 61
    assert list(service.events(PAYLOAD, **dict(IDENTITY, request_id="after-window")))[-1] == {
        "type": "done"
    }
    assert len(calls) == 2
    service.close()


def test_running_subprocess_cancel_stops_provider_before_freeing_capacity(tmp_path: Path) -> None:
    bridge = tmp_path / "provider_stub.py"
    bridge.write_text(
        "import json, sys, time\n"
        "json.load(sys.stdin)\n"
        "print(json.dumps({'type':'delta','text':'hello'}), flush=True)\n"
        "time.sleep(30)\n"
    )
    service = RabbitChatService(SubprocessChatProvider(bridge, tmp_path / "unused.env"))
    stream = service.events(PAYLOAD, **IDENTITY)
    assert next(stream)["state"] == "running"
    assert next(stream) == {"type": "delta", "text": "hello"}
    with ThreadPoolExecutor(max_workers=1) as pool:
        remaining = pool.submit(list, stream)
        assert service.cancel(**IDENTITY)["state"] == "cancelling"
        assert remaining.result(timeout=3) == [{"type": "error", "code": "cancelled"}]
    assert service.request_status(**IDENTITY)["state"] == "cancelled"
    service.close()


@pytest.mark.parametrize("failure", ["timeout", "interrupted", "unavailable"])
def test_unknown_upstream_result_cannot_trigger_old_browser_blind_retry(failure: str) -> None:
    def provider(request):
        yield {"type": "error", "code": failure}

    service = RabbitChatService(provider)
    events = list(service.events(PAYLOAD, **IDENTITY))
    # The previous deployed browser only retries these three old codes.
    assert events[-1]["code"] not in {"timeout", "interrupted", "unavailable"}
    assert events[-1] == {"type": "error", "code": "outcome_unknown"}
    assert service.request_status(**IDENTITY)["code"] == "outcome_unknown"
    service.close()


def test_durable_ledger_has_only_one_live_owner_and_releases_after_close(tmp_path: Path) -> None:
    path = tmp_path / "owned.sqlite"
    owner = RabbitChatService(ledger_path=path)
    with pytest.raises(ProductError) as error:
        RabbitChatService(ledger_path=path)
    assert error.value.code == "chat_ledger_in_use"
    owner.close()
    replacement = RabbitChatService(ledger_path=path)
    replacement.close()
    replacement.close()
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("dispatch", [False, True])
def test_crashed_owner_is_recovered_as_terminal_without_replaying(
    tmp_path: Path, dispatch: bool
) -> None:
    path = tmp_path / "crash.sqlite"
    script = (
        "import os,sys\nfrom pathlib import Path\n"
        "from easydesign.product.rabbit_chat import RabbitChatService\n"
        "def provider(request):\n    yield {'type':'delta','text':'started'}\n"
        "service=RabbitChatService(provider, ledger_path=Path(sys.argv[1]))\n"
        f"stream=service.events({PAYLOAD!r}, **{IDENTITY!r})\n"
        + ("next(stream)\nnext(stream)\n" if dispatch else "")
        + "os._exit(0)\n"
    )
    subprocess.run([sys.executable, "-c", script, str(path)], check=True, timeout=5)
    service = RabbitChatService(lambda _: iter(()), ledger_path=path)
    try:
        status = service.request_status(**IDENTITY)
        assert status == {
            "request_id": IDENTITY["request_id"],
            "state": "failed",
            "dispatched": dispatch,
            "code": "outcome_unknown" if dispatch else "interrupted",
        }
        with pytest.raises(ProductError) as error:
            service.events(PAYLOAD, **IDENTITY)
        assert error.value.code == "request_already_processed"
    finally:
        service.close()


@pytest.mark.parametrize("link_kind", ["file", "directory", "hardlink"])
def test_ledger_rejects_indirect_paths_without_changing_target(
    tmp_path: Path, link_kind: str
) -> None:
    target = tmp_path / "unrelated"
    target.mkdir()
    original = target / "sentinel.sqlite"
    original.write_bytes(b"not an application database")
    before = original.read_bytes(), original.stat().st_mode
    alias = tmp_path / "alias.sqlite"
    if link_kind == "file":
        alias.symlink_to(original)
    elif link_kind == "directory":
        directory_alias = tmp_path / "linked-dir"
        directory_alias.symlink_to(target, target_is_directory=True)
        alias = directory_alias / "sentinel.sqlite"
    else:
        alias.hardlink_to(original)
    with pytest.raises(ValueError, match="ledger"):
        RabbitChatService(ledger_path=alias)
    assert (original.read_bytes(), original.stat().st_mode) == before


def test_closing_stream_after_terminal_preserves_completed_and_is_idempotent() -> None:
    closed = []

    def provider(request):
        try:
            yield {"type": "done"}
        finally:
            closed.append(True)

    service = RabbitChatService(provider)
    stream = service.events(PAYLOAD, **IDENTITY)
    assert next(stream)["state"] == "running"
    assert next(stream) == {"type": "done"}
    stream.close()
    assert closed == [True]
    assert service.request_status(**IDENTITY)["state"] == "completed"
    service.close()
    stream.close()


def test_upstream_429_cools_new_requests_without_retrying_dispatched_request() -> None:
    now = [0.0]
    calls = []

    def provider(request):
        calls.append(request)
        yield {"type": "error", "code": "rate_limit"}

    service = RabbitChatService(provider, clock=lambda: now[0])
    assert list(service.events(PAYLOAD, **IDENTITY))[-1] == {"type": "error", "code": "rate_limit"}
    other = dict(IDENTITY, request_id="after-429")
    stream = service.events(PAYLOAD, **other)
    assert next(stream)["state"] == "queued"
    assert len(calls) == 1
    now[0] = 2.1
    assert list(stream)[-1] == {"type": "error", "code": "rate_limit"}
    assert len(calls) == 2
    with pytest.raises(ProductError) as error:
        service.events(PAYLOAD, **IDENTITY)
    assert error.value.code == "request_already_processed"
    service.close()


def test_fair_turns_and_user_pending_limit_cover_all_scopes() -> None:
    def provider(request):
        yield {"type": "delta", "text": "working"}
        yield {"type": "done"}

    service = RabbitChatService(provider, limits=RabbitCapacityLimits(max_active=1))
    first = service.events(PAYLOAD, **IDENTITY)
    next(first)
    next(first)
    same_user_id = dict(IDENTITY, scope_id="other-scope", request_id="second-a")
    same_user = service.events(PAYLOAD, **same_user_id)
    other_user_id = dict(IDENTITY, actor_id="user-b", request_id="first-b")
    other_user = service.events(PAYLOAD, **other_user_id)
    with pytest.raises(ProductError) as error:
        service.events(PAYLOAD, **dict(same_user_id, request_id="third-a"))
    assert error.value.code == "user_limit"
    assert list(first)[-1] == {"type": "done"}
    assert service.request_status(**other_user_id)["state"] == "running"
    assert service.request_status(**same_user_id)["state"] == "queued"
    assert list(other_user)[-1] == {"type": "done"}
    assert list(same_user)[-1] == {"type": "done"}
    service.close()


def test_expired_waiter_is_not_dispatched_when_another_request_finishes() -> None:
    now = [0.0]
    calls = []

    def provider(request):
        calls.append(request)
        yield {"type": "delta", "text": "working"}
        yield {"type": "done"}

    service = RabbitChatService(
        provider,
        clock=lambda: now[0],
        limits=RabbitCapacityLimits(
            max_active=1,
            queue_timeout_seconds=5,
        ),
    )
    first = service.events(PAYLOAD, **IDENTITY)
    next(first)
    next(first)
    waiting_id = dict(IDENTITY, actor_id="user-b", request_id="expired")
    waiting = service.events(PAYLOAD, **waiting_id)
    now[0] = 6
    list(first)
    assert service.request_status(**waiting_id)["state"] == "failed"
    assert list(waiting) == [{"type": "error", "code": "queue_timeout"}]
    assert len(calls) == 1
    service.close()


def test_shutdown_cancels_unstarted_stream_and_releases_ledger_owner(tmp_path: Path) -> None:
    path = tmp_path / "shutdown.sqlite"
    service = RabbitChatService(lambda _: iter(()), ledger_path=path)
    stream = service.events(PAYLOAD, **IDENTITY)
    service.close()
    stream.close()
    restored = RabbitChatService(ledger_path=path)
    assert restored.request_status(**IDENTITY) == {
        "request_id": "request-a",
        "state": "cancelled",
        "dispatched": False,
        "code": "cancelled",
    }
    restored.close()


@pytest.mark.parametrize(
    "event",
    [
        {"type": "delta", "text": "four"},
        {"type": "suggestions", "questions": ["four"]},
    ],
)
def test_configured_output_bound_stops_provider_without_leaking_oversized_text(event: dict) -> None:
    closed = []

    def provider(request):
        try:
            yield event
            yield {"type": "done"}
        finally:
            closed.append(True)

    service = RabbitChatService(provider, limits=RabbitCapacityLimits(max_output_chars=3))
    events = list(service.events(PAYLOAD, **IDENTITY))
    assert not any(event["type"] in {"delta", "suggestions"} for event in events)
    assert events[-1] == {"type": "error", "code": "outcome_unknown"}
    assert closed == [True]
    service.close()


@pytest.mark.parametrize(
    "identity",
    [
        {"actor_id": "user-a"},
        dict(IDENTITY, actor_id=""),
        dict(IDENTITY, scope_id=""),
        dict(IDENTITY, request_id=""),
        dict(IDENTITY, request_id="bad\nkey"),
    ],
)
def test_authenticated_identity_cannot_fall_back_to_unmetered_legacy(identity: dict) -> None:
    service = RabbitChatService(lambda _: iter(()))
    try:
        with pytest.raises(ProductError) as error:
            service.events(PAYLOAD, **identity)
        assert error.value.code == "invalid_request"
    finally:
        service.close()


def test_full_waiting_queue_does_not_block_another_users_free_execution_slot() -> None:
    service = RabbitChatService(
        lambda _: iter([{"type": "done"}]), limits=RabbitCapacityLimits(max_active=2, max_queued=1)
    )
    first = service.events(PAYLOAD, **IDENTITY)
    second = service.events(PAYLOAD, **dict(IDENTITY, request_id="second-a"))
    other_id = dict(IDENTITY, actor_id="user-b", request_id="first-b")
    other = service.events(PAYLOAD, **other_id)
    assert service.request_status(**other_id)["state"] == "running"
    assert list(other)[-1] == {"type": "done"}
    first.close()
    second.close()
    service.close()


def test_capacity_snapshot_reports_request_limits_not_invented_cost_guarantees() -> None:
    service = RabbitChatService(lambda _: iter([{"type": "done"}]))
    assert service.status() == {"configured": True, "model": "deepseek-flash"}
    first = service.events(PAYLOAD, **IDENTITY)
    second = service.events(PAYLOAD, **dict(IDENTITY, request_id="pending"))
    status = service.capacity_status()
    assert status["active"] == 1 and status["queued"] == 1
    assert status["limits"]["requests_per_minute"] == 20
    assert status["limits"]["max_active"] == 2
    assert status["limits"]["queue_timeout_seconds"] == 120
    assert status["budget_unit"] == "dispatched_requests"
    assert status["dispatched_requests"] == 0
    first.close()
    second.close()
    service.close()


@pytest.mark.parametrize("failure", ["eof", "exception", "oversized"])
def test_closing_after_generated_terminal_error_does_not_rewrite_failure(failure: str) -> None:
    def provider(request):
        if failure == "exception":
            raise RuntimeError("private provider details")
        if failure == "oversized":
            yield {"type": "delta", "text": "too long"}

    service = RabbitChatService(provider, limits=RabbitCapacityLimits(max_output_chars=1))
    stream = service.events(PAYLOAD, **IDENTITY)
    next(stream)
    assert next(stream) == {"type": "error", "code": "outcome_unknown"}
    stream.close()
    assert service.request_status(**IDENTITY)["state"] == "failed"
    assert service.request_status(**IDENTITY)["code"] == "outcome_unknown"
    service.close()


@pytest.mark.parametrize(
    "settings",
    [
        {"max_active": 0},
        {"max_active": True},
        {"max_active": 1.0},
        {"max_queued": -1},
        {"max_queued": False},
        {"queue_timeout_seconds": float("nan")},
        {"queue_timeout_seconds": float("inf")},
        {"queue_timeout_seconds": True},
        {"queue_timeout_seconds": 0},
        {"max_total_requests": -1},
        {"max_user_requests": 1.5},
        {"max_output_chars": 0},
    ],
)
def test_capacity_configuration_fails_closed(settings: dict) -> None:
    with pytest.raises(ValueError):
        RabbitCapacityLimits(**settings)


def test_request_owner_and_payload_are_bound_without_leaking_status() -> None:
    service = RabbitChatService(lambda _: iter([{"type": "done"}]))
    stream = service.events(PAYLOAD, **IDENTITY)
    other = dict(IDENTITY, actor_id="another-user")
    for operation in (service.request_status, service.cancel):
        with pytest.raises(ProductError) as error:
            operation(**other)
        assert error.value.status == 404
    changed = dict(PAYLOAD, messages=[{"role": "user", "content": "changed"}])
    with pytest.raises(ProductError) as error:
        service.events(changed, **IDENTITY)
    assert error.value.code == "idempotency_conflict"
    assert list(stream)[-1] == {"type": "done"}
    service.close()


def test_per_user_rate_limit_survives_restart_without_blocking_other_users(tmp_path: Path) -> None:
    path = tmp_path / "user-rate.sqlite"
    limits = RabbitCapacityLimits(requests_per_minute_per_user=1)
    service = RabbitChatService(lambda _: iter([{"type": "done"}]), limits=limits, ledger_path=path)
    list(service.events(PAYLOAD, **IDENTITY))
    pending_id = dict(IDENTITY, scope_id="another-scope", request_id="second-a")
    pending = service.events(PAYLOAD, **pending_id)
    assert next(pending)["state"] == "queued"
    assert list(service.events(PAYLOAD, **dict(IDENTITY, actor_id="user-b", request_id="b")))[
        -1
    ] == {"type": "done"}
    pending.close()
    service.close()
    restored = RabbitChatService(lambda _: iter(()), limits=limits, ledger_path=path)
    pending = restored.events(PAYLOAD, **dict(pending_id, request_id="third-a"))
    assert next(pending)["state"] == "queued"
    pending.close()
    restored.close()


def test_simultaneous_admission_cannot_overspend_reserved_request_budget() -> None:
    calls = []

    def provider(request):
        calls.append(request)
        yield {"type": "done"}

    service = RabbitChatService(provider, limits=RabbitCapacityLimits(max_total_requests=1))

    def request(index):
        try:
            return service.events(
                PAYLOAD, actor_id=f"user-{index}", scope_id="scope", request_id=f"request-{index}"
            )
        except ProductError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(request, range(100)))
    admitted = [result for result in results if not isinstance(result, str)]
    assert len(admitted) == 1
    assert results.count("budget_exhausted") == 99
    assert list(admitted[0])[-1] == {"type": "done"}
    assert len(calls) == 1
    service.close()


def test_failed_provider_cleanup_cannot_record_a_successful_completion() -> None:
    def provider(request):
        try:
            yield {"type": "done"}
        finally:
            raise RuntimeError("private cleanup failure")

    service = RabbitChatService(provider)
    assert list(service.events(PAYLOAD, **IDENTITY))[-1] == {
        "type": "error",
        "code": "outcome_unknown",
    }
    assert service.request_status(**IDENTITY)["state"] == "failed"
    service.close()


def test_provider_exception_while_cancelling_preserves_cancelled_state() -> None:
    def provider(request):
        yield {"type": "delta", "text": "working"}
        raise RuntimeError("provider cancelled")

    service = RabbitChatService(provider)
    stream = service.events(PAYLOAD, **IDENTITY)
    next(stream)
    next(stream)
    service.cancel(**IDENTITY)
    assert list(stream) == [{"type": "error", "code": "cancelled"}]
    assert service.request_status(**IDENTITY)["state"] == "cancelled"
    service.close()


def test_cancel_is_bounded_even_when_bridge_stops_reading_request_input(tmp_path: Path) -> None:
    bridge = tmp_path / "unresponsive_provider.py"
    bridge.write_text("import time\ntime.sleep(8)\n")
    large = dict(
        PAYLOAD,
        messages=[{"role": "assistant", "content": "字" * 7000}] * 4
        + [{"role": "user", "content": "字" * 4000}],
    )
    service = RabbitChatService(SubprocessChatProvider(bridge, tmp_path / "unused.env"))
    stream = service.events(large, **IDENTITY)
    next(stream)
    with ThreadPoolExecutor(max_workers=1) as pool:
        remaining = pool.submit(list, stream)
        # Wait until dispatch is durable, then let the bridge fill its unread stdin pipe.
        deadline = time.monotonic() + 2
        while not service.request_status(**IDENTITY)["dispatched"]:
            assert time.monotonic() < deadline
            time.sleep(0.001)
        time.sleep(0.05)
        service.cancel(**IDENTITY)
        assert remaining.result(timeout=2) == [{"type": "error", "code": "cancelled"}]
    service.close()


def test_waiting_stream_heartbeats_do_not_wake_each_other_into_a_busy_loop() -> None:
    service = RabbitChatService(
        lambda _: iter([{"type": "done"}]), limits=RabbitCapacityLimits(max_active=1)
    )
    active = service.events(PAYLOAD, **IDENTITY)
    identities = [
        dict(IDENTITY, actor_id=f"waiting-{i}", request_id=f"waiting-{i}") for i in range(2)
    ]
    streams = [service.events(PAYLOAD, **identity) for identity in identities]
    start = threading.Barrier(3)
    counts = [0, 0]

    def consume(index):
        start.wait(timeout=3)
        for event in streams[index]:
            if event["type"] == "status":
                counts[index] += 1

    with ThreadPoolExecutor(max_workers=2) as pool:
        workers = [pool.submit(consume, index) for index in range(2)]
        start.wait(timeout=3)
        time.sleep(0.15)
        for identity in identities:
            service.cancel(**identity)
        for worker in workers:
            worker.result(timeout=3)
    active.close()
    service.close()
    assert max(counts) <= 8, f"Queued requests produced an unbounded heartbeat storm: {counts}"
