"""Doudou request identity and dispatch ledger, separate from scientific model calls.

The ledger counts requests, not tokens or money. A dispatch record is committed
before entering a provider: an ambiguous outcome is never automatically retried.
Prompts and model responses are deliberately not persisted here.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import sqlite3
import stat
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .contracts import ProductError


@dataclass(frozen=True)
class RabbitCapacityLimits:
    """Engineering limits, not verified upstream throughput or a monetary budget.

    Request budgets count lifetime dispatches in this ledger; None disables that
    budget. Queue size does not promise completion before the waiting deadline.
    """

    max_active: int = 2
    max_queued: int = 300
    max_active_per_user: int = 1
    max_pending_per_user: int = 2
    requests_per_minute: int = 20
    requests_per_minute_per_user: int = 6
    queue_timeout_seconds: float = 120.0
    max_total_requests: int | None = None
    max_user_requests: int | None = None
    max_output_chars: int = 200000

    def __post_init__(self) -> None:
        for name in (
            "max_active",
            "max_active_per_user",
            "max_pending_per_user",
            "requests_per_minute",
            "requests_per_minute_per_user",
            "max_output_chars",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.max_queued) is not int or self.max_queued < 0:
            raise ValueError("max_queued must be a non-negative integer")
        if (
            isinstance(self.queue_timeout_seconds, bool)
            or not isinstance(self.queue_timeout_seconds, (int, float))
            or not math.isfinite(self.queue_timeout_seconds)
            or self.queue_timeout_seconds <= 0
        ):
            raise ValueError("queue_timeout_seconds must be finite and positive")
        for name in ("max_total_requests", "max_user_requests"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a non-negative integer or null")


@dataclass(eq=False)
class ChatTicket:
    actor: str
    scope: str
    key: str
    created: float
    state: str = "queued"
    dispatched: bool = False
    code: str | None = None
    cancellation: threading.Event = field(default_factory=threading.Event)


class RabbitCapacity:
    """Bounded round-robin admission; no provider or network I/O under the lock."""

    def __init__(
        self, limits: RabbitCapacityLimits, ledger_path: Path | None, clock: Callable[[], float]
    ) -> None:
        self.limits, self.clock = limits, clock
        self.condition = threading.Condition()
        self.ledger = RabbitRequestLedger(ledger_path)
        self.tickets: dict[tuple[str, str], ChatTicket] = {}
        self.queues: dict[str, deque[ChatTicket]] = {}
        self.turns: deque[str] = deque()
        self.last_turn: dict[str, int] = {}
        self.turn_number = 0
        self.closed = False
        self.cooldown_until = 0.0
        self.backoff_seconds = 2.0
        self.request_times = [
            (clock() - max(0.0, time.time() - at), actor) for at, actor in self.ledger.recent()
        ]

    def reserve(self, actor: str, scope: str, key: str, request: dict[str, Any]) -> ChatTicket:
        with self.condition:
            if self.closed:
                raise ProductError("unavailable", "Chat is stopping", 503)
            self.ledger.check_identity(actor, scope, key, request)
            self._pump()
            pending = list(self.tickets.values())
            reserved = [t for t in pending if not t.dispatched]
            if (
                self.limits.max_total_requests is not None
                and self.ledger.used() + len(reserved) >= self.limits.max_total_requests
            ) or (
                self.limits.max_user_requests is not None
                and self.ledger.used(actor) + sum(t.actor == actor for t in reserved)
                >= self.limits.max_user_requests
            ):
                raise ProductError("budget_exhausted", "Chat request budget is exhausted", 429)
            if sum(t.actor == actor for t in pending) >= self.limits.max_pending_per_user:
                raise ProductError("user_limit", "Your chat request limit has been reached", 429)
            active = sum(t.state in {"running", "cancelling"} for t in pending)
            queued = len(pending) - active
            can_start = (
                active < self.limits.max_active
                and self._rate_available(actor)
                and sum(t.actor == actor and t.state in {"running", "cancelling"} for t in pending)
                < self.limits.max_active_per_user
            )
            if queued >= self.limits.max_queued and not can_start:
                raise ProductError("queue_full", "Chat queue is full; try later", 429)
            self.ledger.reserve(actor, scope, key, request)
            ticket = ChatTicket(actor, scope, key, self.clock())
            self.tickets[scope, key] = ticket
            if actor not in self.queues:
                self.queues[actor] = deque()
                self.turns.append(actor)
            self.queues[actor].append(ticket)
            self._pump()
            return ticket

    def _pump(self) -> None:
        if self.closed:
            return
        changed = False
        for ticket in list(self.tickets.values()):
            if (
                ticket.state == "queued"
                and self.clock() - ticket.created >= self.limits.queue_timeout_seconds
            ):
                self._record_terminal(ticket, "failed", "queue_timeout")
                changed = True
        active = [t for t in self.tickets.values() if t.state in {"running", "cancelling"}]
        while self.turns and len(active) < self.limits.max_active:
            selected: ChatTicket | None = None
            for actor in sorted(self.turns, key=lambda user: self.last_turn.get(user, 0)):
                queue = self.queues[actor]
                if sum(
                    t.actor == actor for t in active
                ) < self.limits.max_active_per_user and self._rate_available(actor):
                    selected = queue.popleft()
                if selected is not None:
                    self.turns.remove(actor)
                    if queue:
                        self.turns.append(actor)
                    else:
                        del self.queues[actor]
                    self.turn_number += 1
                    self.last_turn[actor] = self.turn_number
                    break
            if selected is None:
                break
            selected.state = "running"
            self.ledger.update(selected.scope, selected.key, "running")
            active.append(selected)
            changed = True
        if changed:
            self.condition.notify_all()

    def _rate_available(self, actor: str) -> bool:
        now = self.clock()
        if now < self.cooldown_until:
            return False
        self.request_times = [(at, user) for at, user in self.request_times if now - at < 60]
        reserved = [t for t in self.tickets.values() if t.state == "running" and not t.dispatched]
        return (
            len(self.request_times) + len(reserved) < self.limits.requests_per_minute
            and sum(user == actor for _, user in self.request_times)
            + sum(t.actor == actor for t in reserved)
            < self.limits.requests_per_minute_per_user
        )

    def poll(self, ticket: ChatTicket) -> str:
        with self.condition:
            self._pump()
            return ticket.state

    def status(self, actor: str, scope: str, key: str) -> dict[str, Any]:
        with self.condition:
            result = self.ledger.status(actor, scope, key)
            if result["state"] == "queued" and self.cooldown_until > self.clock():
                result["retry_after"] = math.ceil(self.cooldown_until - self.clock())
            return result

    def snapshot(self) -> dict[str, Any]:
        with self.condition:
            self._pump()
            return {
                "limits": asdict(self.limits),
                "active": sum(t.state in {"running", "cancelling"} for t in self.tickets.values()),
                "queued": sum(t.state == "queued" for t in self.tickets.values()),
                "dispatched_requests": self.ledger.used(),
                "budget_unit": "dispatched_requests",
            }

    def dispatch(self, ticket: ChatTicket) -> bool:
        with self.condition:
            if ticket.cancellation.is_set():
                return False
            self.ledger.dispatch(ticket.scope, ticket.key, time.time())
            ticket.dispatched = True
            self.request_times.append((self.clock(), ticket.actor))
            return True

    def finish(self, ticket: ChatTicket, state: str, code: str | None = None) -> None:
        with self.condition:
            if (ticket.scope, ticket.key) not in self.tickets:
                return
            if code == "rate_limit":
                self.cooldown_until = max(self.cooldown_until, self.clock() + self.backoff_seconds)
                self.backoff_seconds = min(60.0, self.backoff_seconds * 2)
            elif state == "completed":
                self.backoff_seconds = 2.0
            self._record_terminal(ticket, state, code)
            self._pump()
            self.condition.notify_all()
            if self.closed and not self.tickets:
                self.ledger.close()

    def _record_terminal(self, ticket: ChatTicket, state: str, code: str | None) -> None:
        if ticket.state == "queued":
            self.queues[ticket.actor].remove(ticket)
            if not self.queues[ticket.actor]:
                del self.queues[ticket.actor]
                self.turns.remove(ticket.actor)
        ticket.state, ticket.code = state, code
        self.ledger.update(ticket.scope, ticket.key, state, code)
        del self.tickets[ticket.scope, ticket.key]
        if not any(t.actor == ticket.actor for t in self.tickets.values()):
            self.last_turn.pop(ticket.actor, None)

    def cancel(self, actor: str, scope: str, key: str) -> dict[str, Any]:
        with self.condition:
            self.ledger.status(actor, scope, key)
            ticket = self.tickets.get((scope, key))
            if ticket is not None:
                ticket.cancellation.set()
                if not ticket.dispatched:
                    self.finish(ticket, "cancelled", "cancelled")
                else:
                    ticket.state = "cancelling"
                    self.ledger.update(scope, key, "cancelling")
            return self.status(actor, scope, key)

    def abandon(self, ticket: ChatTicket) -> None:
        with self.condition:
            if (ticket.scope, ticket.key) in self.tickets:
                self.cancel(ticket.actor, ticket.scope, ticket.key)

    def close(self) -> None:
        with self.condition:
            if self.closed:
                return
            self.closed = True
            for ticket in list(self.tickets.values()):
                ticket.cancellation.set()
                if not ticket.dispatched:
                    self.finish(ticket, "cancelled", "cancelled")
                else:
                    ticket.state = "cancelling"
                    self.ledger.update(ticket.scope, ticket.key, "cancelling")
            if not self.tickets:
                self.ledger.close()


class RabbitRequestLedger:
    """Caller serializes access; durable identity survives process restarts."""

    def __init__(self, path: Path | None) -> None:
        self._file: int | None = None
        self._closed = False
        if path is not None:
            if any(item.is_symlink() for item in (path, *path.absolute().parents)):
                raise ValueError("Chat ledger path must not contain symbolic links")
            if path.exists():
                existing = path.stat()
                if not stat.S_ISREG(existing.st_mode) or existing.st_nlink != 1:
                    raise ValueError("Chat ledger must be a regular file with a single link")
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                os.close(descriptor)
                raise ValueError("Chat ledger must be a regular file with a single link")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                os.close(descriptor)
                raise ProductError(
                    "chat_ledger_in_use", "Chat ledger already has an owner", 503
                ) from error
            os.fchmod(descriptor, 0o600)
            self._file = descriptor
        try:
            self.db = sqlite3.connect(
                str(path) if path is not None else ":memory:", check_same_thread=False
            )
            self._initialize()
        except Exception:
            database = getattr(self, "db", None)
            if database is not None:
                database.close()
            if self._file is not None:
                os.close(self._file)
            raise

    def _initialize(self) -> None:
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS rabbit_requests (
                scope_id TEXT NOT NULL, request_id TEXT NOT NULL, actor_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL, state TEXT NOT NULL, dispatched INTEGER NOT NULL,
                code TEXT, dispatched_at REAL, PRIMARY KEY(scope_id, request_id)
            )
        """)
        self.db.execute(
            "UPDATE rabbit_requests SET state='failed', "
            "code=CASE WHEN dispatched=1 THEN 'outcome_unknown' ELSE 'interrupted' END "
            "WHERE state IN ('queued','running','cancelling')"
        )
        self.db.commit()

    def check_identity(self, actor: str, scope: str, key: str, request: dict[str, Any]) -> None:
        digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        previous = self.db.execute(
            "SELECT * FROM rabbit_requests WHERE scope_id=? AND request_id=?", (scope, key)
        ).fetchone()
        if previous is not None:
            code = (
                "request_already_processed"
                if previous["actor_id"] == actor and previous["fingerprint"] == digest
                else "idempotency_conflict"
            )
            raise ProductError(code, "Chat request ID has already been used", 409)

    def reserve(self, actor: str, scope: str, key: str, request: dict[str, Any]) -> None:
        self.check_identity(actor, scope, key, request)
        digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        self.db.execute(
            "INSERT INTO rabbit_requests VALUES (?, ?, ?, ?, 'queued', 0, NULL, NULL)",
            (scope, key, actor, digest),
        )
        self.db.commit()

    def status(self, actor: str, scope: str, key: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM rabbit_requests WHERE scope_id=? AND request_id=? AND actor_id=?",
            (scope, key, actor),
        ).fetchone()
        if row is None:
            raise ProductError("not_found", "Chat request was not found", 404)
        result = {"request_id": key, "state": row["state"], "dispatched": bool(row["dispatched"])}
        if row["code"]:
            result["code"] = row["code"]
        return result

    def update(self, scope: str, key: str, state: str, code: str | None = None) -> None:
        self.db.execute(
            "UPDATE rabbit_requests SET state=?, code=? WHERE scope_id=? AND request_id=?",
            (state, code, scope, key),
        )
        self.db.commit()

    def dispatch(self, scope: str, key: str, now: float) -> None:
        self.db.execute(
            "UPDATE rabbit_requests SET state='running', dispatched=1, dispatched_at=? "
            "WHERE scope_id=? AND request_id=?",
            (now, scope, key),
        )
        self.db.commit()

    def used(self, actor: str | None = None) -> int:
        query = "SELECT COUNT(*) FROM rabbit_requests WHERE dispatched=1"
        args: tuple[str, ...] = ()
        if actor is not None:
            query += " AND actor_id=?"
            args = (actor,)
        return int(self.db.execute(query, args).fetchone()[0])

    def recent(self) -> list[tuple[float, str]]:
        rows = self.db.execute(
            "SELECT dispatched_at, actor_id FROM rabbit_requests WHERE dispatched_at>?",
            (time.time() - 60,),
        ).fetchall()
        return [(float(row[0]), str(row[1])) for row in rows]

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.db.close()
        if self._file is not None:
            os.close(self._file)
