"""Authenticated, content-only Doudou chat boundary for the Easy product UI."""

from __future__ import annotations

import hashlib
import json
import os
import re
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
_LOCALIZATION_PURPOSE = "scientific-localization"


def validate_localization_request(value: Any) -> dict[str, Any]:
    """Accept bounded scientific prose, never arbitrary model instructions."""
    if not isinstance(value, dict) or value.get("locale") != "zh":
        raise ProductError("invalid_request", "Localization request is invalid", 400)
    raw_passages = value.get("passages")
    if not isinstance(raw_passages, list) or not 1 <= len(raw_passages) <= 48:
        raise ProductError("invalid_request", "Localization request is invalid", 400)
    passages: list[dict[str, str]] = []
    seen: set[str] = set()
    total = 0
    for raw in raw_passages:
        if not isinstance(raw, dict):
            raise ProductError("invalid_request", "Localization request is invalid", 400)
        identity, source = raw.get("id"), raw.get("text")
        if (
            not isinstance(identity, str)
            or not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,96}", identity)
            or identity in seen
            or not isinstance(source, str)
            or not source.strip()
            or len(source) > 8000
        ):
            raise ProductError("invalid_request", "Localization request is invalid", 400)
        seen.add(identity)
        total += len(source)
        passages.append({"id": identity, "text": source.strip()})
    if total > 32000:
        raise ProductError("invalid_request", "Localization request is invalid", 400)
    raw_context = value.get("context")
    if not isinstance(raw_context, dict):
        raise ProductError("invalid_request", "Localization request is invalid", 400)
    stage, goal = raw_context.get("stage"), raw_context.get("goal")
    if stage not in _STAGES or not isinstance(goal, str) or len(goal) > 1200:
        raise ProductError("invalid_request", "Localization request is invalid", 400)
    return {
        "purpose": _LOCALIZATION_PURPOSE,
        "locale": "zh",
        "passages": passages,
        "context": {"stage": stage, "goal": goal},
    }


def _protected_tokens(value: str) -> set[str]:
    """Identifiers whose mutation could change scientific meaning."""
    tokens = set(
        re.findall(
            r"(?<![\w])(?:[A-Z]{1,8}[A-Z0-9:+./-]*\d[A-Z0-9:+./-]*|\d+(?:\.\d+)?)(?![\w])",
            value,
        )
    )
    tokens.update(re.findall(r"\b(?:VHH|GPCR|PDB|AF3|AFO|CDR[123]?|ECL[123]?|ICL[123]?)\b", value))
    return tokens


def _requires_chinese(value: str) -> bool:
    if value.startswith(("site-", "candidate-", "arm-", "phase")):
        return False
    # Runtime warnings can be opaque, semicolon-delimited machine markers such
    # as ``region-A-has-2-spatial-components;user-members-preserved``.  They
    # must remain byte-for-byte auditable and should not make an otherwise
    # valid localization batch fail merely because they contain no Han text.
    if not re.search(r"\s", value) and re.fullmatch(r"[A-Za-z0-9_.:+/;-]+", value):
        return False
    return any(not word.isupper() for word in re.findall(r"[A-Za-z]{3,}", value))


def _contains_chinese(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value))


def _valid_translation(source: str, translated: Any) -> bool:
    return (
        isinstance(translated, str)
        and bool(translated.strip())
        and len(translated) <= max(80, len(source) * 4)
        and (not _requires_chinese(source) or bool(re.search(r"[\u3400-\u9fff]", translated)))
        and all(token in translated for token in _protected_tokens(source))
    )


def _parse_localization(text: str, passages: list[dict[str, str]]) -> dict[str, Any]:
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1] if "\n" in clean else ""
        clean = clean.rsplit("```", 1)[0].strip()
    try:
        value = json.loads(clean)
    except json.JSONDecodeError as error:
        raise ProductError(
            "localization_unavailable", "Academic Chinese is unavailable", 502
        ) from error
    raw_items = value.get("items") if isinstance(value, dict) else None
    if not isinstance(raw_items, list) or len(raw_items) != len(passages):
        raise ProductError("localization_unavailable", "Academic Chinese is unavailable", 502)
    source = {item["id"]: item["text"] for item in passages}
    localized: dict[str, str] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            raise ProductError("localization_unavailable", "Academic Chinese is unavailable", 502)
        identity, translated = item.get("id"), item.get("text")
        if identity not in source or identity in localized or not isinstance(translated, str):
            raise ProductError("localization_unavailable", "Academic Chinese is unavailable", 502)
        translated = translated.strip()
        if not _valid_translation(source[identity], translated):
            raise ProductError("localization_unavailable", "Academic Chinese is unavailable", 502)
        localized[identity] = translated
    if set(localized) != set(source):
        raise ProductError("localization_unavailable", "Academic Chinese is unavailable", 502)
    return {"locale": "zh-CN", "items": localized}


def _parse_localization_candidates(text: str, passages: list[dict[str, str]]) -> dict[str, str]:
    """Keep only complete, scientifically valid items from a provider attempt.

    A fast translation model may occasionally echo one passage or omit one item in
    an otherwise useful batch.  Those items must be retried, but valid translations
    should not be discarded or exposed before the full response is complete.
    """
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1] if "\n" in clean else ""
        clean = clean.rsplit("```", 1)[0].strip()
    try:
        value = json.loads(clean)
    except json.JSONDecodeError:
        return {}
    raw_items = value.get("items") if isinstance(value, dict) else None
    if not isinstance(raw_items, list):
        return {}
    source = {item["id"]: item["text"] for item in passages}
    localized: dict[str, str] = {}
    duplicates: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        identity, translated = item.get("id"), item.get("text")
        if identity not in source or not isinstance(translated, str):
            continue
        if identity in localized or identity in duplicates:
            localized.pop(identity, None)
            duplicates.add(identity)
            continue
        translated = translated.strip()
        if _valid_translation(source[identity], translated):
            localized[identity] = translated
    return localized


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
        cache_root: Path | None = None,
        ledger_path: Path | None = None,
        limits: RabbitCapacityLimits | None = None,
    ) -> None:
        self.provider, self.clock = provider, clock
        self.limits = limits or RabbitCapacityLimits()
        self._capacity = RabbitCapacity(self.limits, ledger_path, clock)
        self.cache_root = cache_root
        if self.cache_root is not None:
            self.cache_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._localization_cache: dict[str, dict[str, Any]] = {}

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

    def localize(
        self, value: Any, *, actor_id: str = "legacy", scope_id: str = "legacy"
    ) -> dict[str, Any]:
        request = validate_localization_request(value)
        if self.provider is None:
            raise ProductError("not_configured", "Academic Chinese is not configured", 503)
        key = hashlib.sha256(
            json.dumps(
                {"scope": scope_id, "request": request}, ensure_ascii=False, sort_keys=True
            ).encode()
        ).hexdigest()
        cache_path = self.cache_root / f"{key}.json" if self.cache_root is not None else None
        with self._lock:
            cached = self._localization_cache.get(key)
            if cached is None and cache_path is not None and cache_path.is_file():
                try:
                    candidate = json.loads(cache_path.read_text())
                    items = candidate.get("items")
                    sources = {item["id"]: item["text"] for item in request["passages"]}
                    valid_items = (
                        isinstance(items, dict)
                        and set(items) == set(sources)
                        and all(
                            _valid_translation(source, items[identity])
                            for identity, source in sources.items()
                        )
                    )
                    if candidate.get("source_sha256") == key and valid_items:
                        cached = candidate
                        self._localization_cache[key] = cached
                except (OSError, json.JSONDecodeError, AttributeError):
                    cached = None
            if cached is not None:
                return cached
        ticket = self._capacity.reserve(actor_id, scope_id, uuid.uuid4().hex, request)
        if self._capacity.poll(ticket) != "running":
            self._capacity.abandon(ticket)
            raise ProductError("rate_limit", "Academic Chinese is busy; try again shortly", 429)
        if not self._capacity.dispatch(ticket):
            self._capacity.abandon(ticket)
            raise ProductError("rate_limit", "Academic Chinese is busy; try again shortly", 429)
        succeeded = False
        try:
            sources = {item["id"]: item["text"] for item in request["passages"]}
            localized = {
                identity: source
                for identity, source in sources.items()
                if _contains_chinese(source) or not _requires_chinese(source)
            }
            pending = [item for item in request["passages"] if item["id"] not in localized]

            def translate(batch: list[dict[str, str]]) -> dict[str, str]:
                chunks: list[str] = []
                terminal = False
                provider_request = {**request, "passages": batch}
                assert self.provider is not None
                for raw in self.provider(provider_request):
                    event = public_event(raw)
                    if event is None:
                        continue
                    if event["type"] == "delta":
                        chunks.append(event["text"])
                        if sum(map(len, chunks)) > 200000:
                            raise ProductError(
                                "localization_unavailable",
                                "Academic Chinese is unavailable",
                                502,
                            )
                    elif event["type"] == "done":
                        terminal = True
                        break
                    elif event["type"] == "error":
                        raise ProductError(
                            "localization_unavailable", "Academic Chinese is unavailable", 502
                        )
                if not terminal:
                    raise ProductError(
                        "localization_unavailable", "Academic Chinese is unavailable", 502
                    )
                return _parse_localization_candidates("".join(chunks), batch)

            if pending:
                localized.update(translate(pending))
                unresolved = [item for item in pending if item["id"] not in localized]
                if unresolved:
                    localized.update(translate(unresolved))
            if set(localized) != set(sources) or not all(
                _valid_translation(source, localized.get(identity))
                for identity, source in sources.items()
            ):
                raise ProductError(
                    "localization_unavailable", "Academic Chinese is unavailable", 502
                )
            result = {"locale": "zh-CN", "items": localized}
            result["source_sha256"] = key
            with self._lock:
                self._localization_cache[key] = result
                if cache_path is not None and not cache_path.exists():
                    temporary = cache_path.with_suffix(
                        cache_path.suffix + f".{os.getpid()}.{threading.get_ident()}.tmp"
                    )
                    temporary.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True))
                    os.chmod(temporary, 0o600)
                    os.replace(temporary, cache_path)
            succeeded = True
            return result
        finally:
            self._capacity.finish(
                ticket,
                "completed" if succeeded else "failed",
                None if succeeded else "localization_unavailable",
            )


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
