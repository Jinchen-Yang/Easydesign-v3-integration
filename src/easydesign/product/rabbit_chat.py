"""Authenticated, content-only Doudou chat boundary for the Easy product UI."""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from .contracts import ProductError

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

    def __init__(self, script: Path, env_file: Path) -> None:
        self.script, self.env_file = script, env_file

    def __call__(self, request: dict[str, Any]) -> Iterator[dict[str, Any]]:
        process = subprocess.Popen(
            [sys.executable, "-u", str(self.script), str(self.env_file)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        selector = selectors.DefaultSelector()
        try:
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(json.dumps(request, ensure_ascii=False).encode())
            process.stdin.close()
            selector.register(process.stdout, selectors.EVENT_READ)
            deadline = time.monotonic() + 90
            pending = b""
            size = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    yield {"type": "error", "code": "timeout"}
                    return
                ready = selector.select(min(remaining, 0.5))
                if not ready:
                    if process.poll() is not None:
                        break
                    continue
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
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


class RabbitChatService:
    """Bound concurrent/cost exposure and expose only the public NDJSON contract."""

    def __init__(
        self,
        provider: ChatProvider | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.provider, self.clock = provider, clock
        self._lock = threading.Lock()
        self._active = 0
        self._requests: list[float] = []

    def status(self) -> dict[str, Any]:
        return {"configured": self.provider is not None, "model": "deepseek-flash"}

    def events(self, value: Any) -> Iterator[dict[str, Any]]:
        request = validate_chat_request(value)
        if self.provider is None:
            raise ProductError("not_configured", "Doudou chat is not configured", 503)
        now = self.clock()
        with self._lock:
            self._requests = [at for at in self._requests if now - at < 60]
            if self._active >= 2 or len(self._requests) >= 20:
                raise ProductError("rate_limit", "Doudou is busy; try again shortly", 429)
            self._active += 1
            self._requests.append(now)

        def generate() -> Iterator[dict[str, Any]]:
            terminal = False
            size = 0
            try:
                assert self.provider is not None
                for raw in self.provider(request):
                    event = public_event(raw)
                    if event is None:
                        continue
                    if event["type"] == "delta":
                        size += len(event["text"])
                        if size > 200000:
                            yield {"type": "error", "code": "unavailable"}
                            return
                    yield event
                    if event["type"] in {"done", "error"}:
                        terminal = True
                        return
                if not terminal:
                    yield {"type": "error", "code": "interrupted"}
            except Exception:
                yield {"type": "error", "code": "unavailable"}
            finally:
                with self._lock:
                    self._active -= 1

        return generate()
