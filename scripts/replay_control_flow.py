"""Offline routing replay of a saved failed Coordinator checkpoint.

Reads the original scientific artifacts; only a cloned session ledger is writable.
The replay does not migrate old graph fingerprints or invoke scientific tools/models.
Actual specialist execution is covered by deterministic harness regressions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import yaml
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.message import add_messages

from easydesign.agent.harness import RuntimeCoordinator
from easydesign.agent.models import ModelConfig
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.session_store import SessionStore
from scripts.replay_research_budget import inventory


async def main() -> None:
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
    ledger = out / "ledger"
    (ledger / "metadata").mkdir(parents=True)
    with sqlite3.connect(f"file:{project}/metadata/agent.sqlite?mode=ro", uri=True) as source:
        with sqlite3.connect(ledger / "metadata/agent.sqlite") as destination:
            source.backup(destination)
    os.environ["EASYDESIGN_WORKSPACE"] = str(project.parents[2] / "easydesign-workspace.yaml")
    checkpoint_db = sqlite3.connect(
        f"file:{project}/metadata/agent-checkpoints.sqlite?mode=ro", uri=True
    )
    saver = SqliteSaver(checkpoint_db)
    checkpoint = saver.get_tuple({"configurable": {"thread_id": args.thread, "checkpoint_ns": ""}})
    assert checkpoint is not None
    history = saver.get_delta_channel_history(config=checkpoint.config, channels=["messages"])[
        "messages"
    ]
    messages = history.get("seed", [])
    for _, _, value in history["writes"]:
        messages = add_messages(messages, value)
    assert messages and "Gate 1" in messages[-1].text
    actions = []
    original_terminal = messages[-1].text
    for _ in range(2):
        store = SessionStore(ledger)
        try:
            prior = store.events(args.thread)
            execution = store.latest_execution(args.thread)
            bridge = Phase2Bridge(project, args.thread, store)
            assert bridge.read_evidence()["status"] == "succeeded"
            assert bridge.scientific_state()["scientific_state"] == "site-not-proposed"
            boundary = RuntimeCoordinator(
                bridge,
                "coordinator",
                config,
                execution["current_user_message"],
                execution_id=execution["execution_id"],
            )

            async def forbidden_provider(request: object) -> object:
                raise AssertionError("A provider must not select the workflow stage")

            response = await boundary.awrap_model_call(
                SimpleNamespace(messages=messages), forbidden_provider
            )
            action = response.result[0].tool_calls[0]
            assert action["name"] == "task"
            assert action["args"]["subagent_type"] == "site-mechanism"
            actions.append(action)
            added = store.events(args.thread)[len(prior) :]
            assert all(e["kind"] == "runtime-dispatch" for e in added)
        finally:
            store.close()
    checkpoint_db.close()
    assert actions[0] == actions[1]
    assert inventory(project) == before
    report = {
        "status": "OFFLINE_ROUTING_PASS",
        "checkpoint": checkpoint.config,
        "original_terminal": original_terminal,
        "execution_id": execution["execution_id"],
        "runtime_action": actions[0],
        "identical_after_ledger_restart": True,
        "provider_calls": 0,
        "scientific_tool_executions": 0,
        "original_files_unchanged": len(before),
        "max_model_calls": config.max_model_calls,
        "hard_input_chars": config.hard_input_chars,
        "scope": "Saved state routes to Site despite stale Gate 1 prose. No scientific "
        "completion or cross-version checkpoint migration is claimed.",
    }
    (out / "original-file-sha256.json").write_text(json.dumps(before, indent=2))
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
