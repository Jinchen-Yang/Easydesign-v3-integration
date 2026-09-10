"""Independent asyncio CLI. The v2 easydesign console remains available."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import pwd
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml  # type: ignore[import-untyped]
from pydantic import TypeAdapter

from .contracts import AgentBoundaryError, DecisionCard, Identifier
from .models import ModelConfig
from .session_store import SessionStore, confined


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="easydesign-agent", description="EasyDesign target agent (Phase 1)"
    )
    result.add_argument("operation", choices=("start", "resume", "status"))
    result.add_argument("project", type=Path)
    result.add_argument(
        "--models",
        type=Path,
        default=Path("config/llm.yaml"),
        help="ModelConfig YAML/JSON; secret environment names only",
    )
    result.add_argument("--thread", help="Existing thread identity for resume/status")
    result.add_argument("--goal", help="Researcher's explicit local target goal")
    result.add_argument("--message", help="New user clarification after a completed/rejected turn")
    result.add_argument(
        "--technical-details", action="store_true", help="Show diagnostic identities and references"
    )
    result.add_argument(
        "--stream", action="store_true", help="Emit bounded progress events to stderr"
    )
    result.add_argument("--target", type=Path, help="Local PDB/mmCIF input for a new project only")
    result.add_argument("--card", help="Exact card displayed by the prior process")
    result.add_argument("--decision", choices=("approve", "reject"))
    result.add_argument(
        "--interactive", action="store_true", help="Read approve/reject from the local terminal"
    )
    return result


async def run_session(
    bridge: Any,
    config: ModelConfig,
    models: dict[str, Any],
    goal: str,
    *,
    decision: str | None = None,
    card_id: str | None = None,
    user: str | None = None,
    new_message: str | None = None,
    technical_details: bool = False,
    emit: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langgraph.types import Command

    from .harness import create_harness, fingerprint

    store, thread = bridge.store, bridge.thread
    goal = store.thread(thread, fingerprint(config), goal)
    if new_message is not None and (not new_message.strip() or len(new_message) > 1500):
        raise AgentBoundaryError("A follow-up must contain 1–1500 characters")
    history = store.events(thread)
    execution = store.latest_execution(thread)
    cursor = history[-1]["seq"] if history else 0
    path = confined(store.root, store.root / "agent-checkpoints.sqlite")
    for suffix in ("-wal", "-shm", "-journal"):
        confined(store.root, Path(str(path) + suffix))
    execution_config = {"configurable": {"thread_id": thread}, "recursion_limit": 100}
    async with AsyncSqliteSaver.from_conn_string(str(path)) as saver:

        def assemble() -> Any:
            return create_harness(
                bridge,
                models,
                config,
                saver,
                goal,
                current_user_message=execution["current_user_message"] if execution else goal,
                execution_id=execution["execution_id"] if execution else None,
                technical_details=technical_details,
            )

        def execution_input() -> dict[str, Any]:
            assert execution is not None
            return {
                "messages": [
                    {
                        "role": "user",
                        "id": execution["execution_id"],
                        "content": execution["current_user_message"],
                    }
                ]
            }

        graph = assemble()
        state = await graph.aget_state(execution_config)
        # The same input ID makes an intent durable even if the process stops before a checkpoint.
        pending_input = execution is not None and not any(
            m.id == execution["execution_id"] for m in state.values.get("messages", [])
        )
        interrupts = [i for task in state.tasks for i in task.interrupts]
        if interrupts:
            if new_message is not None:
                raise AgentBoundaryError(
                    "Reject the current card before proposing a changed selection"
                )
            if len(interrupts) != 1:
                raise AgentBoundaryError("Only one scientific decision at a time is supported")
            card = DecisionCard.model_validate(interrupts[0].value)
            store.card(thread, card.card_id)
            if decision is not None:
                if card_id != card.card_id or user is None:
                    raise AgentBoundaryError(
                        "Response must bind the currently displayed card and local user"
                    )
                store.respond(thread, card.card_id, decision, user)
                bridge.failpoint("after_response_intent")
            intent = store.response(thread, card.card_id)
            if intent is None:
                return {
                    "status": "awaiting-human-approval",
                    "thread": thread,
                    "card": card.model_dump(mode="json"),
                }
            inputs: Any = Command(resume={"card_id": card.card_id, "decision": intent["response"]})
        elif decision is not None:
            if card_id is None:
                raise AgentBoundaryError("A response requires its card")
            prior = store.response(thread, card_id)
            if prior is None or prior["response"] != decision or prior["user"] != user:
                raise AgentBoundaryError("No matching interrupted card; response rejected")
            return {
                "status": "already-delivered" if prior["delivered"] else "response-persisted",
                "thread": thread,
                "job": bridge.get_job_status(),
            }
        elif new_message is not None:
            if state.next or pending_input:
                raise AgentBoundaryError("Recover the unfinished turn before sending a new message")
            execution = store.begin_execution(thread, new_message, followup=True)
            bridge.failpoint("after_execution_intent")
            inputs = execution_input()
        elif state.next:
            inputs = None  # Recover interrupted execution with the same saver/thread.
        elif pending_input:
            inputs = execution_input()
        elif state.values:
            messages = state.values.get("messages", [])
            return {
                "status": "finished",
                "thread": thread,
                "message": messages[-1].text if messages else "",
                "job": bridge.get_job_status(),
            }
        else:
            execution = store.begin_execution(thread, goal)
            bridge.failpoint("after_execution_intent")
            inputs = execution_input()
        if execution is None:
            raise AgentBoundaryError("Checkpoint has no compatible persisted agent execution")
        graph = assemble()
        async for _update in graph.astream(inputs, execution_config, stream_mode="updates"):
            if emit is not None:
                for event in store.events(thread):
                    if event["seq"] > cursor:
                        emit(event)
                        cursor = event["seq"]
        state = await graph.aget_state(execution_config)
        interrupts = [i for task in state.tasks for i in task.interrupts]
        if interrupts:
            card = DecisionCard.model_validate(interrupts[0].value)
            return {
                "status": "awaiting-human-approval",
                "thread": thread,
                "card": card.model_dump(mode="json"),
            }
        messages = state.values.get("messages", [])
        message = messages[-1].text if messages else ""
        store.event(thread, "assistant", {"text": message})
        return {
            "status": "finished",
            "thread": thread,
            "message": message,
            "job": bridge.get_job_status(),
        }


def public_text(text: str) -> str:
    """Keep diagnostics in stored messages; ordinary display omits implementation rows."""
    rows = [
        line
        for line in text.splitlines()
        if not re.search(
            r"\b(?:assessment_id|evidence_id|request_identity|producer_attempt|schema_version|"
            r"fallback_used|sha256|sha-256|checksum)\b",
            line,
            re.IGNORECASE,
        )
    ]
    result = "\n".join(rows)
    result = re.sub(r"\b(?:judge|job)-[a-zA-Z0-9_.-]+\b", "", result)
    return re.sub(r"\b[0-9a-f]{32,64}\b", "", result, flags=re.IGNORECASE).strip()


def public_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": event["kind"],
        **{
            key: event["payload"][key]
            for key in ("role", "name", "call", "verdict")
            if key in event["payload"]
        },
    }


def _display(value: dict[str, Any], *, technical_details: bool = False) -> None:
    value = dict(value)
    if not technical_details and value.get("status") != "failed":
        if "message" in value:
            value["message"] = public_text(value["message"]) or "处理完成；验证详情已保留。"
        if "job" in value:
            value["job"] = {k: v for k, v in value["job"].items() if k in {"status", "phase"}}
        if "events" in value:
            value["events"] = [public_event(e) for e in value["events"]]
    if "card" in value:
        card = DecisionCard.model_validate(value["card"])
        selected = next(o for o in card.options if o["option_id"] == card.option_id)
        value = {
            **value,
            "card": {
                "card_id": card.card_id,
                "question": card.question,
                "selected_option": selected["label"],
                "options": [
                    {k: o[k] for k in ("label", "description", "eligible")} for o in card.options
                ],
                "evidence_refs": [ref.split("#sha256=")[0] for ref in card.evidence_refs],
                "limitations": card.limitations
                if technical_details
                else [summary for text in card.limitations if (summary := public_text(text))],
                "action": card.action,
            },
        }
    print(json.dumps(value, ensure_ascii=False, indent=2), flush=True)


async def _drive(args: Any, bridge: Any, config: ModelConfig, goal: str) -> int:
    from .models import create_models

    models = create_models(config)
    local_user = f"uid:{os.getuid()}:{pwd.getpwuid(os.getuid()).pw_name}"

    def emit(event: dict[str, Any]) -> None:
        print(
            json.dumps(
                event if args.technical_details else public_event(event), ensure_ascii=False
            ),
            file=sys.stderr,
            flush=True,
        )

    result = await run_session(
        bridge,
        config,
        models,
        goal,
        decision=args.decision,
        card_id=args.card,
        user=local_user,
        new_message=args.message,
        technical_details=args.technical_details,
        emit=emit if args.stream else None,
    )
    _display(result, technical_details=args.technical_details)
    while args.interactive and result["status"] == "awaiting-human-approval":
        response = (
            (await asyncio.to_thread(input, "approve / reject (Enter to detach): ")).strip().lower()
        )
        if not response:
            break
        if response not in {"approve", "reject"}:
            print("Please enter approve or reject.", flush=True)
            continue
        result = await run_session(
            bridge,
            config,
            models,
            goal,
            decision=response,
            card_id=result["card"]["card_id"],
            user=local_user,
            technical_details=args.technical_details,
            emit=emit if args.stream else None,
        )
        _display(result, technical_details=args.technical_details)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        from easydesign.orchestration.local_project import resolve_project_path
        from easydesign.orchestration.research import initialize_research_project
        from easydesign.workspace_context import WorkspaceContext

        from .harness import fingerprint
        from .tools import TargetBridge

        config = ModelConfig.model_validate(yaml.safe_load(args.models.read_text()))
        if args.operation != "start" and args.thread is None:
            raise AgentBoundaryError("resume/status requires --thread")
        if args.operation == "start" and not args.goal:
            raise AgentBoundaryError("start requires an explicit --goal")
        if args.message is not None and (args.operation != "resume" or args.decision is not None):
            raise AgentBoundaryError(
                "--message is supported on resume after a completed/rejected turn"
            )
        if args.goal and len(args.goal) > 1500:
            raise AgentBoundaryError("Please keep the target goal within 1500 characters")
        if args.operation != "start" and args.target is not None:
            raise AgentBoundaryError("An input cannot be replaced during resume")
        thread = TypeAdapter(Identifier).validate_python(args.thread or f"thread-{uuid4().hex}")
        context = WorkspaceContext.discover()
        root = resolve_project_path(args.project, must_exist=False)
        confined(context.projects_root, root)
        if not root.exists():
            if args.operation != "start" or args.target is None:
                raise AgentBoundaryError("New projects require start, --goal and --target")
            if args.target.suffix.lower() not in {".pdb", ".cif", ".mmcif"}:
                raise AgentBoundaryError("Only explicit local PDB/mmCIF input is supported")
            initialize_research_project(project_root=root, target=args.target.resolve(strict=True))
        elif args.target is not None:
            raise AgentBoundaryError("Existing project input is immutable; omit --target")
        store = SessionStore(root)
        try:
            goal = store.thread(thread, fingerprint(config), args.goal)
            bridge = TargetBridge(root, thread, store)
            if args.operation == "status":
                _display(
                    {
                        "thread": thread,
                        "events": store.events(thread),
                        "job": bridge.get_job_status(),
                    },
                    technical_details=args.technical_details,
                )
                return 0
            # Separate CLI lifetime lock: scientific commands take the short ledger writer lock.
            with confined(store.root, store.root / "agent-session.lock").open("a") as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise AgentBoundaryError("Another agent CLI owns this project") from error
                return asyncio.run(_drive(args, bridge, config, goal))
        finally:
            store.close()
    except KeyboardInterrupt:
        _display(
            {
                "status": "detached",
                "message": "Agent observation stopped; scientific workers were not stopped.",
            }
        )
        return 130
    except Exception as error:
        # Provider errors can embed request bodies or credentials; expose only the class.
        safe = str(error) if isinstance(error, AgentBoundaryError) else type(error).__name__
        _display({"status": "failed", "category": type(error).__name__, "message": safe})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
