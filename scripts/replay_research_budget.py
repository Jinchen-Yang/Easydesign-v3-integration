"""Offline budget probe from a saved Research checkpoint, in a separate ledger.

No provider or scientific tool is invoked. This checks continuation admission, not
scientific completion. Original checkpoint, approvals and evidence stay unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import yaml
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelResponse
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, messages_to_dict
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.message import add_messages

from easydesign.agent import harness
from easydesign.agent.context_policy import research_memory
from easydesign.agent.models import ModelConfig
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.session_store import SessionStore


class Captured(Exception):
    pass


class CaptureRequest(AgentMiddleware):
    async def awrap_model_call(self, request, handler):
        self.request = request
        raise Captured()


def inventory(project):
    return {
        str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(project.rglob("*"))
        if p.is_file() and not p.name.endswith("-shm")
    }


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--thread", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config/llm.yaml"))
    args = parser.parse_args()
    project, out = args.project.resolve(), args.output.resolve()
    if out.exists() or out.is_relative_to(project):
        raise ValueError("Use a new output directory outside the original project")
    before = inventory(project)
    config = ModelConfig.model_validate(yaml.safe_load(args.config.read_text()))
    out.mkdir(parents=True)
    ledger_project = out / "ledger"
    (ledger_project / "metadata").mkdir(parents=True)
    with sqlite3.connect(f"file:{project}/metadata/agent.sqlite?mode=ro", uri=True) as src:
        with sqlite3.connect(ledger_project / "metadata/agent.sqlite") as dst:
            src.backup(dst)
    store = SessionStore(ledger_project)
    eid = store.latest_execution(args.thread)["execution_id"]
    prior = store.events(args.thread)
    used = sum(e["kind"] == "model-call" and e["payload"].get("execution_id") == eid for e in prior)
    assert used == 32, "This probe requires the saved execution exhausted at 32"
    os.environ["EASYDESIGN_WORKSPACE"] = str(project.parents[2] / "easydesign-workspace.yaml")
    bridge = Phase2Bridge(project, args.thread, store)
    checkpoint_db = sqlite3.connect(
        f"file:{project}/metadata/agent-checkpoints.sqlite?mode=ro", uri=True
    )
    saver = SqliteSaver(checkpoint_db)
    namespaces = checkpoint_db.execute(
        "SELECT DISTINCT checkpoint_ns FROM checkpoints WHERE thread_id=? AND checkpoint_ns LIKE ?",
        (args.thread, "%|research:%"),
    ).fetchall()
    assert len(namespaces) == 1, "Choose an unambiguous saved Research execution"
    checkpoint = saver.get_tuple(
        {"configurable": {"thread_id": args.thread, "checkpoint_ns": namespaces[0][0]}}
    )
    history = saver.get_delta_channel_history(config=checkpoint.config, channels=["messages"])[
        "messages"
    ]
    messages = history.get("seed", [])
    for _, _, value in history["writes"]:
        messages = add_messages(messages, value)
    state = {**checkpoint.checkpoint["channel_values"], "messages": messages}
    assert state.get("_summarization_event") and messages
    model = FakeListChatModel(
        responses=["Synthetic offline summary; no new scientific conclusion."]
    )
    shutil.copytree(harness.skill_root(), out / "memory/skills")
    backend = FilesystemBackend(root_dir=out / "memory", virtual_mode=True)
    capture = CaptureRequest()
    goal = store.latest_execution(args.thread)["current_user_message"]
    # Obtain the production Research prompt/tool surface without executing tools.
    with patch.object(harness, "research_memory", return_value=capture):
        graph = harness.create_site_pipeline(bridge, model, config, backend, goal, goal, eid, None)
        try:
            await graph.ainvoke(
                {"messages": [HumanMessage(content=goal)], "structured_response": None}
            )
        except Captured:
            pass
    request = capture.request.override(messages=messages, state=state)
    captured_inputs = []

    async def stopped_provider(request):
        captured_inputs.append(
            {"system": request.system_message.text, "messages": messages_to_dict(request.messages)}
        )
        assert "continue_evidence" in {tool.name for tool in request.tools}
        return ModelResponse(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {"id": "offline-not-executed", "name": "read_site_evidence", "args": {}}
                    ],
                )
            ]
        )

    try:
        for _ in range(2):
            # Both native memory and role guard use the reconstructed persisted state.
            boundary = harness.RoleBoundary(
                bridge, "site", config, goal, goal, eid, site_stage="research"
            )

            async def guarded(req, boundary=boundary):
                return await boundary.awrap_model_call(req, stopped_provider)

            await research_memory(bridge, config, model, backend, eid).awrap_model_call(
                request, guarded
            )
            store.close()
            store = SessionStore(ledger_project)
            bridge.store = store
        events = store.events(args.thread)
        additions = events[len(prior) :]
        calls = [e["payload"] for e in additions if e["kind"] == "model-call"]
        assert [c["call"] for c in calls] == [33, 34]
        assert {c["execution_id"] for c in calls} == {eid}
        assert not any(
            e["kind"]
            in {
                "framework-summary-call",
                "evidence-research",
                "site-evidence-dossier",
                "site-proposal",
            }
            for e in additions
        )
        contexts = [e["payload"] for e in additions if e["kind"] == "model-context"]
        active = [e for e in prior if e["payload"].get("execution_id") == eid]
        original_roles = Counter(e["payload"]["role"] for e in active if e["kind"] == "model-call")
        summaries = sum(e["kind"] == "framework-summary-call" for e in active)
        report = {
            "status": "OFFLINE_ADMISSION_PASS",
            "checkpoint": checkpoint.config,
            "execution_id": eid,
            "limit": config.max_model_calls,
            "hard_input_chars": config.hard_input_chars,
            "original_execution": {
                "total": used,
                "by_role_including_summaries": dict(original_roles),
                "coordinator": original_roles["coordinator"],
                "scientific": used - original_roles["coordinator"] - summaries,
                "summaries": summaries,
                "repairs": dict(Counter(e["kind"] for e in active if "repair" in e["kind"])),
            },
            "offline_probe": {
                "admitted_calls": [c["call"] for c in calls],
                "scientific_handler_probes": len(calls),
                "coordinator_calls": 0,
                "summary_calls": 0,
                "repair_calls": 0,
                "provider_calls": 0,
                "scientific_tool_executions": 0,
                "input_chars": [c["input_chars_with_schemas"] for c in contexts],
            },
            "scope": (
                "Original Research input admitted at 33 and after reopen at 34; "
                "no scientific completion claimed."
            ),
        }
        (out / "admitted-inputs.json").write_text(
            json.dumps(captured_inputs, ensure_ascii=False, indent=2)
        )
        (out / "probe-events.json").write_text(json.dumps(additions, ensure_ascii=False, indent=2))
    finally:
        store.close()
        checkpoint_db.close()
    assert inventory(project) == before, "Original saved project changed"
    report["original_files_unchanged"] = len(before)
    (out / "original-file-sha256.json").write_text(json.dumps(before, indent=2))
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
