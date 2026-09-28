"""Authenticated, content-only Doudou chat boundary for the Easy product UI."""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from .contracts import ProductError
from .rabbit_capacity import ChatTicket, RabbitCapacity, RabbitCapacityLimits

ChatProvider = Callable[[dict[str, Any]], Iterator[dict[str, Any]]]
_STAGES = {"Idle", "Target", "Site", "Design", "Pilot", "Scale", "Candidates"}
_STATUSES = {"idle", "draft", "running", "paused", "complete"}
_ERRORS = {"credentials", "rate_limit", "timeout", "interrupted", "unavailable"}


def validate_chat_request(value: Any) -> dict[str, Any]:
    """Discard undeclared fields and reject role/context injection."""
    if not isinstance(value, dict) or value.get("locale") not in {"zh", "en"}:
        raise ProductError("invalid_request", "Chat request is invalid", 400)
    raw_messages = value.get("messages")
    if not isinstance(raw_messages, list) or not 1 <= len(raw_messages) <= 17:
        raise ProductError("invalid_request", "Chat request is invalid", 400)
    messages: list[dict[str, str]] = []
    total = 0
    for message in raw_messages:
        if not isinstance(message, dict):
            raise ProductError("invalid_request", "Chat request is invalid", 400)
        role, content = message.get("role"), message.get("content")
        if (
            role not in {"user", "assistant"}
            or not isinstance(content, str)
            or not content.strip()
            or len(content) > 8000
        ):
            raise ProductError("invalid_request", "Chat request is invalid", 400)
        total += len(content)
        messages.append({"role": role, "content": content})
    if total > 32000 or messages[-1]["role"] != "user" or len(messages[-1]["content"]) > 4000:
        raise ProductError("invalid_request", "Chat request is invalid", 400)
    raw_context = value.get("context")
    if not isinstance(raw_context, dict):
        raise ProductError("invalid_request", "Chat request is invalid", 400)
    stage, status, goal = (
        raw_context.get("stage"),
        raw_context.get("status"),
        raw_context.get("goal"),
    )
    if (
        stage not in _STAGES
        or status not in _STATUSES
        or not isinstance(goal, str)
        or len(goal) > 1200
    ):
        raise ProductError("invalid_request", "Chat request is invalid", 400)
    return {
        "locale": value["locale"],
        "messages": messages,
        "context": {"stage": stage, "status": status, "goal": goal},
    }


def public_event(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    kind = value.get("type")
    if kind == "delta" and isinstance(value.get("text"), str) and value["text"]:
        return {"type": "delta", "text": value["text"]}
    if kind == "suggestions" and isinstance(value.get("questions"), list):
        questions: list[str] = []
        for item in value["questions"]:
            if isinstance(item, str):
                question = " ".join(item.split()).strip()
                if 0 < len(question) <= 120 and question not in questions:
                    questions.append(question)
                if len(questions) == 3:
                    break
        return {"type": "suggestions", "questions": questions}
    if kind == "done":
        return {"type": "done"}
    if kind == "error":
        code = value.get("code")
        return {"type": "error", "code": code if code in _ERRORS else "unavailable"}
    return None


class SubprocessChatProvider:
    """Run the audited stdlib bridge locally on the credential host."""

    def __init__(
        self,
        script: Path,
        env_file: Path,
        *,
        environment: Callable[[], dict[str, str]] | None = None,
    ) -> None:
        self.script, self.env_file = script, env_file
        self.environment = environment

    def __call__(self, request: dict[str, Any]) -> Iterator[dict[str, Any]]:
        yield from self.stream(request, threading.Event())

    def stream(
        self, request: dict[str, Any], cancellation: threading.Event
    ) -> Iterator[dict[str, Any]]:
        if cancellation.is_set():
            return
        process = subprocess.Popen(
            [sys.executable, "-u", str(self.script), str(self.env_file)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=None if self.environment is None else self.environment(),
        )
        selector = selectors.DefaultSelector()
        try:
            assert process.stdin is not None and process.stdout is not None
            outgoing = json.dumps(request, ensure_ascii=False).encode()
            os.set_blocking(process.stdin.fileno(), False)
            selector.register(process.stdin, selectors.EVENT_WRITE)
            selector.register(process.stdout, selectors.EVENT_READ)
            deadline = time.monotonic() + 90
            pending = b""
            size = 0
            while True:
                if cancellation.is_set():
                    return
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    yield {"type": "error", "code": "timeout"}
                    return
                ready = selector.select(min(remaining, 0.5))
                if not ready:
                    if process.poll() is not None:
                        break
                    continue
                for selected, _ in ready:
                    if selected.fileobj is process.stdin:
                        written = os.write(process.stdin.fileno(), outgoing)
                        outgoing = outgoing[written:]
                        if not outgoing:
                            selector.unregister(process.stdin)
                            process.stdin.close()
                        continue
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        yield {"type": "error", "code": "interrupted"}
                        return
                    size += len(chunk)
                    if size > 200000:
                        yield {"type": "error", "code": "unavailable"}
                        return
                    pending += chunk
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        if not line.strip():
                            continue
                        try:
                            event = json.loads(line)
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            yield {"type": "error", "code": "unavailable"}
                            return
                        yield event
                        if isinstance(event, dict) and event.get("type") in {"done", "error"}:
                            return
            yield {"type": "error", "code": "interrupted"}
        finally:
            selector.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            if process.stdin is not None:
                process.stdin.close()
            if process.stdout is not None:
                process.stdout.close()


class RabbitChatService:
    """Bound request admission and expose only the public NDJSON contract.

    HTTP supplies trusted identity keywords; payload fields cannot choose a user.
    The production subprocess provider supports cooperative cancellation. Custom
    providers must finish/close before their occupied execution slot is released.
    """

    def __init__(
        self,
        provider: ChatProvider | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        ledger_path: Path | None = None,
        limits: RabbitCapacityLimits | None = None,
    ) -> None:
        self.provider, self.clock = provider, clock
        self.limits = limits or RabbitCapacityLimits()
        self._capacity = RabbitCapacity(self.limits, ledger_path, clock)

    def status(self) -> dict[str, Any]:
        return {"configured": self.provider is not None, "model": "deepseek-flash"}

    def capacity_status(self) -> dict[str, Any]:
        return self._capacity.snapshot()

    def close(self) -> None:
        self._capacity.close()

    def request_status(self, *, actor_id: str, scope_id: str, request_id: str) -> dict[str, Any]:
        return self._capacity.status(actor_id, scope_id, request_id)

    def cancel(self, *, actor_id: str, scope_id: str, request_id: str) -> dict[str, Any]:
        return self._capacity.cancel(actor_id, scope_id, request_id)

    def events(
        self,
        value: Any,
        *,
        actor_id: str | None = None,
        scope_id: str | None = None,
        request_id: str | None = None,
        authorize: Callable[[], None] | None = None,
    ) -> Iterator[dict[str, Any]]:
        request = validate_chat_request(value)
        identity = (actor_id, scope_id, request_id)
        if any(part is not None for part in identity) and (
            not all(
                isinstance(part, str)
                and part.strip()
                and len(part) <= 256
                and not any(ord(character) < 32 for character in part)
                for part in identity
            )
            or request_id is None
            or len(request_id) > 96
        ):
            raise ProductError("invalid_request", "Chat identity and request ID are required", 400)
        if self.provider is None:
            raise ProductError("not_configured", "Doudou chat is not configured", 503)
        actor, scope, key = (
            actor_id or "legacy",
            scope_id or "legacy",
            request_id or uuid.uuid4().hex,
        )
        ticket = self._capacity.reserve(actor, scope, key, request)

        def failure_code(code: str) -> str:
            if (
                actor_id is not None
                and ticket.dispatched
                and code in {"timeout", "interrupted", "unavailable"}
            ):
                return "outcome_unknown"
            return code

        def generate() -> Iterator[dict[str, Any]]:
            terminal = False
            size = 0
            state = "failed"
            code: str | None = "interrupted"
            provider_events: Iterator[dict[str, Any]] | None = None

            def close_provider() -> None:
                nonlocal provider_events
                closer = getattr(provider_events, "close", None)
                provider_events = None
                if closer is not None:
                    closer()

            try:
                assert self.provider is not None
                while self._capacity.poll(ticket) == "queued":
                    yield {"type": "status", **self._capacity.status(actor, scope, key)}
                    with self._capacity.condition:
                        if ticket.state == "queued":
                            self._capacity.condition.wait(0.5)
                if ticket.state not in {"running", "cancelling"}:
                    state, code = ticket.state, ticket.code
                    yield {"type": "error", "code": code}
                    return
                if actor_id is not None:
                    yield {"type": "status", "request_id": key, "state": "running"}
                if authorize is not None and not ticket.cancellation.is_set():
                    try:
                        # Revalidate trusted HTTP identity after waiting, immediately
                        # before durable dispatch. No capacity lock encloses account I/O.
                        authorize()
                    except Exception:
                        state, code = "failed", "authorization_revoked"
                        self._capacity.finish(ticket, state, code)
                        yield {"type": "error", "code": code}
                        return
                if not self._capacity.dispatch(ticket):
                    state, code = "cancelled", "cancelled"
                    yield {"type": "error", "code": code}
                    return
                stream = getattr(self.provider, "stream", None)
                provider_events = (
                    stream(request, ticket.cancellation)
                    if callable(stream)
                    else self.provider(request)
                )
                for raw in provider_events:
                    if ticket.cancellation.is_set():
                        break
                    event = public_event(raw)
                    if event is None:
                        continue
                    if event["type"] == "delta":
                        size += len(event["text"])
                    elif event["type"] == "suggestions":
                        size += sum(len(question) for question in event["questions"])
                    if size > self.limits.max_output_chars:
                        code = failure_code("unavailable")
                        close_provider()
                        self._capacity.finish(ticket, "failed", code)
                        yield {"type": "error", "code": code}
                        return
                    if event["type"] == "error":
                        event["code"] = failure_code(event["code"])
                    if event["type"] in {"done", "error"}:
                        terminal = True
                        state = "completed" if event["type"] == "done" else "failed"
                        code = event.get("code")
                        close_provider()
                        self._capacity.finish(ticket, state, code)
                        yield event
                        return
                    yield event
                if not terminal:
                    code = failure_code("interrupted")
                    if ticket.cancellation.is_set():
                        state, code = "cancelled", "cancelled"
                    close_provider()
                    self._capacity.finish(ticket, state, code)
                    yield {"type": "error", "code": code}
            except Exception:
                state = "failed"
                code = failure_code("unavailable")
                if ticket.cancellation.is_set():
                    state, code = "cancelled", "cancelled"
                close_provider()
                self._capacity.finish(ticket, state, code)
                yield {"type": "error", "code": code}
            finally:
                try:
                    close_provider()
                finally:
                    if ticket.cancellation.is_set():
                        state, code = "cancelled", "cancelled"
                    self._capacity.finish(ticket, state, code)

        return _ChatStream(generate(), self._capacity, ticket)


class _ChatStream(Iterator[dict[str, Any]]):
    """Even closing a never-started generator must release its admission."""

    def __init__(
        self, iterator: Iterator[dict[str, Any]], capacity: RabbitCapacity, ticket: ChatTicket
    ) -> None:
        self.iterator, self.capacity, self.ticket = iterator, capacity, ticket
        self.closed = False

    def __next__(self) -> dict[str, Any]:
        return next(self.iterator)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.capacity.abandon(self.ticket)
        close = getattr(self.iterator, "close", None)
        if close is not None:
            close()
