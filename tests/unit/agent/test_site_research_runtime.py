from pathlib import Path
from typing import Any

import pytest
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from easydesign.agent.context_policy import context_usage, research_memory
from easydesign.agent.evidence_research import EvidenceResearch
from easydesign.agent.session_store import SessionStore, compact
from easydesign.agent.site_research_runtime import (
    receptor_kernel_message,
    refresh_site_research_activity,
    site_research_packet_message,
    site_research_state,
)
from tests.agent_support import scripted_config


def _empty_research() -> dict[str, Any]:
    return {
        "queries": [],
        "topics": {},
        "authority": "Synthetic durable research fixture.",
    }


def _kernel_research(site_bridge: Any) -> dict[str, Any]:
    binding = site_bridge.target_state()["binding"]
    value = {
        "identity": {"entry_name": "synthetic_human", "receptor_chain": "A"},
        "state": {"class": "inactive"},
        "membrane": {"method": "synthetic"},
        "topology": {"segments": ["ECL2"]},
        "chain_graph": {"target": "A"},
        "candidates": {"outer-pore": []},
        "warnings": ["Synthetic unit fixture"],
        "avoid": [],
        "approved_design_mapping": {"target_binding": binding},
    }
    ref = site_bridge.persist("research-receptor-analysis", value)
    return {
        "queries": [
            {
                "query_id": "synthetic-gpcr",
                "topic": "structure-complex",
                "question": "Synthetic receptor context",
                "status": "UNRESOLVED",
                "errors": [],
                "query": {"operation": "gpcrdb-context"},
                "cards": [
                    {
                        "card_id": "receptor-synthetic",
                        "provider": "EasyDesign GPCR kernel",
                        "source_refs": [ref],
                    }
                ],
            }
        ],
        "topics": {},
        "authority": "Synthetic durable research fixture.",
    }


def test_kernel_projection_is_runtime_owned_idempotent_and_restart_safe(
    site_bridge: Any, monkeypatch: Any
) -> None:
    research = _kernel_research(site_bridge)
    monkeypatch.setattr(EvidenceResearch, "snapshot", lambda _self, **_kwargs: research)
    execution = site_bridge.store.begin_execution(site_bridge.thread, "Synthetic Site lifecycle")
    eid = execution["execution_id"]

    first = receptor_kernel_message(site_bridge, eid)
    second = receptor_kernel_message(site_bridge, eid)
    assert first is not None and second is not None
    assert '"runtime_receptor_kernel"' in first.content
    assert '"card_id":"receptor-synthetic"' in first.content
    assert first.content == second.content

    state = refresh_site_research_activity(site_bridge, eid)
    assert state.kernel_card_id == "receptor-synthetic"
    assert "receptor-kernel-ready" in state.milestones
    assert "receptor-kernel-projected" in state.milestones
    events = site_bridge.store.events(site_bridge.thread)
    assert sum(
        event["kind"] == "tool-view"
        and event["payload"].get("tool_call_id") == "runtime-receptor-kernel-projection"
        for event in events
    ) == 1
    assert sum(
        event["kind"] == "site-research-lifecycle"
        and event["payload"].get("milestone") == "receptor-kernel-projected"
        for event in events
    ) == 1

    reopened = SessionStore(site_bridge.project)
    try:
        from easydesign.agent.phase2 import Phase2Bridge

        resumed = Phase2Bridge(site_bridge.project, site_bridge.thread, reopened)
        resumed_state = site_research_state(resumed, eid)
        assert resumed_state.kernel_card_id == state.kernel_card_id
        assert resumed_state.milestones == state.milestones
    finally:
        reopened.close()


def test_lifecycle_does_not_count_gate1_passages_as_site_reading(
    site_bridge: Any, monkeypatch: Any
) -> None:
    prior_thread_evidence = {
        "queries": [
            {
                "query_id": "gate1-passage",
                "query": {"operation": "primary-fulltext"},
                "cards": [{"card_id": "passage-gate1", "passage": "Target identity text"}],
            }
        ],
        "topics": {},
        "authority": "Synthetic Gate 1 evidence",
    }
    observed_execution_ids: list[str | None] = []

    def snapshot(_self: Any, *, execution_id: str | None = None) -> dict[str, Any]:
        observed_execution_ids.append(execution_id)
        return _empty_research() if execution_id is not None else prior_thread_evidence

    monkeypatch.setattr(EvidenceResearch, "snapshot", snapshot)
    eid = site_bridge.store.begin_execution(site_bridge.thread, "Fresh Site execution")[
        "execution_id"
    ]

    state = refresh_site_research_activity(site_bridge, eid)
    assert observed_execution_ids and all(item == eid for item in observed_execution_ids)
    assert state.focused_passage_count == 0
    assert "decision-relevant-reading" not in state.milestones


@pytest.mark.asyncio
async def test_site_context_admission_builds_runtime_packet_before_summary_guard(
    site_bridge: Any, monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        EvidenceResearch, "snapshot", lambda _self, **_kwargs: _empty_research()
    )
    config = scripted_config()
    execution = site_bridge.store.begin_execution(site_bridge.thread, "Synthetic admission")
    eid = execution["execution_id"]
    model = FakeListChatModel(responses=["Unused summary response"])
    memory = research_memory(
        site_bridge,
        config,
        model,
        FilesystemBackend(root_dir=tmp_path / "history", virtual_mode=True),
        eid,
    )
    messages = [HumanMessage(content="x" * 76000)]
    received: list[Any] = []

    async def handler(request: Any) -> Any:
        received.extend(request.messages)
        context_usage(model, config, "site", [request.system_message, *request.messages])
        site_bridge.store.reserve_model_call(
            site_bridge.thread, "site", config.max_model_calls, eid
        )
        return ModelResponse(result=[AIMessage(content="Continue")])

    await memory.awrap_model_call(
        ModelRequest(
            model=model,
            system_message=SystemMessage(content="Synthetic Site research"),
            messages=messages,
            state={"messages": messages},
            tools=[],
        ),
        handler,
    )
    assert len(received) == 1
    assert '"runtime_site_research_packet":"v1"' in received[0].content
    events = site_bridge.store.events(site_bridge.thread)
    assert sum(e["kind"] == "site-research-context-admission" for e in events) == 1
    assert not [e for e in events if e["kind"] == "framework-summary-call"]
    assert len([e for e in events if e["kind"] == "model-call"]) == 1
    assert not [e for e in events if e["kind"] == "auxiliary-model-call"]


def test_finalization_packet_does_not_replay_prior_tool_calls(
    site_bridge: Any, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        EvidenceResearch, "snapshot", lambda _self, **_kwargs: _empty_research()
    )
    eid = site_bridge.store.begin_execution(site_bridge.thread, "Synthetic finalization")[
        "execution_id"
    ]
    messages = [
        AIMessage(
            content="Candidate interpretation remains provisional.",
            tool_calls=[{"name": "research_evidence", "args": {"query": "old"}, "id": "old"}],
        ),
        ToolMessage(
            content=compact({"status": "complete", "raw": "x" * 20000}),
            name="research_evidence",
            tool_call_id="old",
        ),
    ]
    packet = site_research_packet_message(
        site_bridge, eid, messages, reading_closed=True
    )
    value = packet.content
    assert '"reading_closed":true' in value
    assert "Candidate interpretation remains provisional." in value
    assert "Every decision_questions item must include" in value
    assert "unresolved_questions is a list of plain strings" in value
    assert '"name":"research_evidence"' not in value
    assert '"args":{"query":"old"}' not in value
    assert len(value) < 60000
