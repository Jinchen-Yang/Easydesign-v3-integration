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
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import yaml  # type: ignore[import-untyped]
from pydantic import TypeAdapter

from .contracts import AgentBoundaryError, DecisionCard, DecisionOutcome, Identifier
from .models import ModelConfig
from .session_store import SessionStore, confined

if TYPE_CHECKING:
    from .tools import TargetBridge


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="easydesign-agent", description="EasyDesign scientific Agent (v3)"
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
    result.add_argument(
        "--through",
        choices=("target", "site", "design", "pilot", "handoff"),
        default="design",
        help="Scientific scope; target retains the Phase 1 compatibility slice",
    )
    result.add_argument(
        "--prediction-backend",
        choices=("openfold3-af3-jax", "protenix-v2"),
        help="Exact downstream backend; otherwise use the sole installed backend",
    )
    result.add_argument(
        "--biology-context",
        type=Path,
        help="Explicit local biology/topology context; not writable by a model",
    )
    result.add_argument(
        "--native-strategy",
        type=Path,
        help=(
            "Scientist-provided project-local ResearchStrategy with native YAML v"
            "ariants; requires approved Gate 2"
        ),
    )
    result.add_argument("--target", type=Path, help="Local PDB/mmCIF input for a new project only")
    result.add_argument("--card", help="Exact card displayed by the prior process")
    result.add_argument("--decision", choices=("approve", "revise", "reject", "override"))
    result.add_argument(
        "--candidate",
        "--option",
        dest="candidate",
        help="Exact selectable candidate or scientific option ID from the displayed card",
    )
    result.add_argument("--instruction", help="Required trusted human instruction for REVISE")
    result.add_argument(
        "--revision-gate",
        choices=("target-structure", "site-hotspot", "design-specification"),
        help="Explicit revision target; default is the current Gate. Gate 3 may return to Site.",
    )
    result.add_argument(
        "--reason", help="Optional rejection reason; required rationale for OVERRIDE"
    )
    result.add_argument(
        "--acknowledgement", help="Explicit acknowledgement of displayed OVERRIDE warnings"
    )
    result.add_argument(
        "--interactive", action="store_true", help="Read scientist steering from the local terminal"
    )
    return result


async def run_session(
    bridge: TargetBridge,
    config: ModelConfig,
    models: dict[str, Any],
    goal: str,
    *,
    decision: str | None = None,
    card_id: str | None = None,
    user: str | None = None,
    new_message: str | None = None,
    human_instruction: str | None = None,
    revision_gate: Any = None,
    optional_reason: str | None = None,
    explicit_acknowledgement: str | None = None,
    selected_option_id: str | None = None,
    technical_details: bool = False,
    emit: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langgraph.types import Command

    from .harness import create_harness, fingerprint

    store, thread = bridge.store, bridge.thread
    goal = store.thread(thread, fingerprint(config), goal)
    if decision is None and any(
        v is not None
        for v in (
            human_instruction,
            revision_gate,
            optional_reason,
            explicit_acknowledgement,
            selected_option_id,
        )
    ):
        raise AgentBoundaryError("Steering fields require an explicit decision action")
    if decision is not None and new_message is not None:
        raise AgentBoundaryError("Use REVISE with an instruction at the current gate")
    if new_message is not None and (not new_message.strip() or len(new_message) > 1500):
        raise AgentBoundaryError("A follow-up must contain 1–1500 characters")
    history = store.events(thread)
    execution = store.latest_execution(thread)
    cursor = history[-1]["seq"] if history else 0
    path = confined(store.root, store.root / "agent-checkpoints.sqlite")
    for suffix in ("-wal", "-shm", "-journal"):
        confined(store.root, Path(str(path) + suffix))
    # One model/tool round takes two graph steps; orchestration adds a few more.
    # The persisted model-call ledger remains the shared, stricter execution fuse.
    execution_config = {
        "configurable": {"thread_id": thread},
        "recursion_limit": max(100, 2 * config.max_model_calls + 10),
    }
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
                revision=DecisionOutcome.model_validate(execution["revision"])
                if execution and execution.get("revision")
                else None,
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
        # REVISE is delivered through the pending tool's Command(resume); its ToolMessage
        # records the trusted outcome in history without inserting a user message between
        # an AI tool call and its required tool response.
        pending_input = (
            execution is not None
            and execution.get("input_kind") != "steering-resume"
            and not any(m.id == execution["execution_id"] for m in state.values.get("messages", []))
        )
        interrupts = [i for task in state.tasks for i in task.interrupts]
        if interrupts:
            if new_message is not None:
                raise AgentBoundaryError(
                    "Use REVISE with a trusted instruction at the current card"
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
                store.respond(
                    thread,
                    card.card_id,
                    decision,
                    user,
                    human_instruction=human_instruction,
                    revision_gate=revision_gate,
                    optional_reason=optional_reason,
                    explicit_acknowledgement=explicit_acknowledgement,
                    selected_option_id=selected_option_id,
                )
                bridge.failpoint("after_response_intent")
            intent = store.response(thread, card.card_id)
            if intent is None:
                return {
                    "status": "awaiting-human-approval",
                    "thread": thread,
                    "card": card.model_dump(mode="json"),
                }
            if intent["response"] == "revise":
                execution = store.begin_revision(thread, card.card_id, goal)
                bridge.failpoint("after_revision_execution_intent")
            elif intent["response"] in {"approve", "override"}:
                from .phase2 import Phase2Bridge

                if isinstance(bridge, Phase2Bridge):
                    execution = store.begin_gate_execution(thread, card.card_id, goal)
                    bridge.failpoint("after_gate_execution_intent")
            inputs: Any = Command(resume={"card_id": card.card_id, "decision": intent["response"]})
        elif decision is not None:
            if card_id is None:
                raise AgentBoundaryError("A response requires its card")
            prior = store.response(thread, card_id)
            if (
                prior is None
                or user is None
                or prior["response"] != decision
                or prior["user"] != user
            ):
                raise AgentBoundaryError("No matching interrupted card; response rejected")
            store.respond(
                thread,
                card_id,
                decision,
                user,
                human_instruction=human_instruction,
                revision_gate=revision_gate,
                optional_reason=optional_reason,
                explicit_acknowledgement=explicit_acknowledgement,
                selected_option_id=selected_option_id,
            )
            return {
                "status": "already-delivered" if prior["delivered"] else "response-persisted",
                "thread": thread,
                "job": bridge.get_job_status(),
            }
        elif new_message is not None:
            if state.next or pending_input:
                raise AgentBoundaryError("Recover the unfinished turn before sending a new message")
            revision = None
            if execution and execution.get("revision"):
                previous = DecisionOutcome.model_validate(execution["revision"])
                if bridge.revision_is_current(previous):
                    revision = previous
            execution = store.begin_execution(thread, new_message, followup=True, revision=revision)
            bridge.failpoint("after_execution_intent")
            inputs = execution_input()
        elif state.next:
            inputs = None  # Recover interrupted execution with the same saver/thread.
        elif pending_input:
            inputs = execution_input()
        elif state.values:
            from .control_flow import next_action
            from .phase2 import Phase2Bridge

            if isinstance(bridge, Phase2Bridge) and next_action(bridge).tool is not None:
                # Resume unfinished authorized work in the SAME execution, including a
                # formerly ended graph. No new intent, approval or model budget.
                inputs = {"messages": []}
            else:
                messages = state.values.get("messages", [])
                return bridge.terminal_result(messages[-1].text if messages else "")
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
        result = bridge.terminal_result(message)
        if result["status"] == "finished":
            from .target_assessment import present_target

            result = present_target(result, bridge.target_submission_evidence())
        store.event(
            thread, "agent-terminal", {k: result[k] for k in ("status", "scientific_state")}
        )
        return result


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
        from .site_portfolio import is_portfolio_card

        ranked = is_portfolio_card(card)
        selected = next((o for o in card.options if o["option_id"] == card.option_id), None)
        value = {
            **value,
            "card": {
                "card_id": card.card_id,
                "question": card.question,
                "default_option" if ranked else "selected_option": selected["label"]
                if selected
                else None,
                "options": card.options
                if ranked
                else [
                    {
                        k: o[k]
                        for k in (
                            ("option_id", "label", "description", "eligible", "judge_status")
                            if card.gate_type in {"pilot-promotion", "wet-lab-handoff"}
                            else ("label", "description", "eligible")
                        )
                        if k in o
                    }
                    for o in card.options
                ],
                "evidence_refs": [ref.split("#sha256=")[0] for ref in card.evidence_refs],
                "limitations": card.limitations
                if technical_details
                else [summary for text in card.limitations if (summary := public_text(text))],
                "action": card.action,
                "gate_type": card.gate_type,
                "scientific_summary": card.scientific_summary,
                **(
                    {"judge_status": card.judge_status, "recommended_alternative": card.alternative}
                    if not ranked or technical_details
                    else {}
                ),
                "warnings": card.warnings,
                "human_actions": ["choose-candidate", "revise", "reject"]
                if ranked and any(o["eligible"] for o in card.options)
                else ["revise", "reject"]
                if card.judge_status == "BLOCKED"
                or (ranked and not any(o["eligible"] for o in card.options))
                else ["override", "revise", "reject"]
                if card.judge_status in {"DISCOURAGED", None}
                else ["approve", "revise", "reject"],
            },
        }
    print(json.dumps(value, ensure_ascii=False, indent=2), flush=True)


async def _drive(args: Any, bridge: Any, config: ModelConfig, goal: str) -> int:
    from .models import create_models

    models = create_models(config, downstream=hasattr(bridge, "downstream_scope"))
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
        human_instruction=args.instruction,
        revision_gate=args.revision_gate,
        optional_reason=args.reason,
        explicit_acknowledgement=args.acknowledgement,
        selected_option_id=args.candidate,
        technical_details=args.technical_details,
        emit=emit if args.stream else None,
    )
    _display(result, technical_details=args.technical_details)
    while args.interactive and result["status"] == "awaiting-human-approval":
        from .site_portfolio import is_portfolio_card

        current_card = DecisionCard.model_validate(result["card"])
        choices = {
            str(o["rank"]).lower(): str(o["option_id"])
            for o in current_card.options
            if is_portfolio_card(current_card) and o["eligible"]
        }
        selected_option_id = None
        prompt = (
            " / ".join([*choices, "revise", "reject"]) + " (Enter to detach): "
            if is_portfolio_card(current_card)
            else "approve / revise / reject / override (Enter to detach): "
        )
        response = (await asyncio.to_thread(input, prompt)).strip().lower()
        if not response:
            break
        if response in choices:
            selected_option_id, response = choices[response], "approve"
        elif is_portfolio_card(current_card) and response not in {"revise", "reject"}:
            print("Choose a displayed selectable rank, revise or reject.", flush=True)
            continue
        if response not in {"approve", "revise", "reject", "override"}:
            print("Please enter approve, revise, reject or override.", flush=True)
            continue
        instruction = acknowledgement = reason = revision_gate = None
        if response == "revise":
            instruction = await asyncio.to_thread(input, "Revision instruction: ")
            if result["card"]["gate_type"] == "design-specification":
                destination = (
                    (
                        await asyncio.to_thread(
                            input, "Revise design or return to site selection? (design / site): "
                        )
                    )
                    .strip()
                    .lower()
                )
                if destination not in {"", "design", "site"}:
                    print("Please choose design or site; no decision was applied.", flush=True)
                    continue
                revision_gate = "site-hotspot" if destination == "site" else None
        if response == "override":
            acknowledgement = await asyncio.to_thread(input, "Acknowledge the displayed warnings: ")
            reason = await asyncio.to_thread(input, "Scientific rationale for proceeding: ")
        if response == "reject":
            reason = (await asyncio.to_thread(input, "Reason (optional): ")).strip() or None
        result = await run_session(
            bridge,
            config,
            models,
            goal,
            decision=response,
            card_id=result["card"]["card_id"],
            user=local_user,
            human_instruction=instruction,
            revision_gate=revision_gate,
            explicit_acknowledgement=acknowledgement,
            optional_reason=reason,
            selected_option_id=selected_option_id,
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
        if args.native_strategy is not None and (
            args.operation == "status" or args.through not in {"design", "pilot", "handoff"}
        ):
            raise AgentBoundaryError(
                "Native strategy import requires start/resume with --through design"
            )
        if args.operation == "status" and args.biology_context is not None:
            raise AgentBoundaryError("status cannot import biology context")
        if args.operation != "start" and args.thread is None:
            raise AgentBoundaryError("resume/status requires --thread")
        if args.operation == "start" and not args.goal:
            raise AgentBoundaryError("start requires an explicit --goal")
        if args.message is not None and (args.operation != "resume" or args.decision is not None):
            raise AgentBoundaryError(
                "--message is supported on resume after a completed/rejected turn"
            )
        if args.decision is None and any(
            v is not None
            for v in (args.instruction, args.revision_gate, args.reason, args.acknowledgement)
        ):
            raise AgentBoundaryError("Steering fields require --decision")
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
            if args.through == "target":
                bridge: TargetBridge = TargetBridge(root, thread, store)
                if args.biology_context is not None:
                    raise AgentBoundaryError("Biology context belongs to the Site scope")
            else:
                from .design import DesignBridge
                from .phase2 import Phase2Bridge

                if args.through in {"pilot", "handoff"}:
                    from easydesign.orchestration.profile import load_runtime_profile

                    from .phase34_runtime import Phase34Runtime

                    selected_backend = args.prediction_backend
                    if selected_backend is None:
                        backends = load_runtime_profile().profile.backends
                        available = [
                            name
                            for name, installed in (
                                ("openfold3-af3-jax", backends.openfold3_af3_jax),
                                ("protenix-v2", backends.protenix_v2),
                            )
                            if installed is not None
                        ]
                        if len(available) != 1:
                            raise AgentBoundaryError(
                                "Specify --prediction-backend for the Pilot plan; "
                                "runtime selection is ambiguous or unavailable"
                            )
                        selected_backend = available[0]
                    phase2: Phase2Bridge = Phase34Runtime(
                        root,
                        thread,
                        store,
                        through=args.through,
                        prediction_backend=selected_backend,
                    )
                else:
                    phase2 = (
                        DesignBridge(root, thread, store)
                        if args.through == "design"
                        else Phase2Bridge(root, thread, store, through="site")
                    )
                bridge = phase2
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
                if args.biology_context is not None:
                    phase2.import_biology(args.biology_context.resolve(strict=True))
                if args.native_strategy is not None:
                    from .native_strategy import import_native

                    import_native(bridge, args.native_strategy.resolve(strict=True))
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
