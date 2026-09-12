"""Dossier authority and framework memory tests; all evidence here is synthetic."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from easydesign.agent.context_policy import context_usage, research_memory
from easydesign.agent.contracts import AgentBoundaryError, EvidenceBinding
from easydesign.agent.phase2 import SITE_EVIDENCE
from easydesign.agent.session_store import identity
from easydesign.agent.site_dossier import SiteResearchHandoff, persist_dossier, site_dossier
from easydesign.core import ArtifactIntegrityError
from tests.agent_support import scripted_config


def handoff() -> SiteResearchHandoff:
    return SiteResearchHandoff(
        candidates=[
            {
                "name": "Synthetic structural candidate",
                "hotspot_label_seq_ids": [1, 2, 3],
                "rationale": "Test the scientific boundary, not biological efficacy.",
            }
        ],
        unresolved_questions=["No actual binding or functional experiment was performed."],
    )


def bind(bridge: Any) -> Any:
    evidence = bridge.read_site_evidence()
    return SITE_EVIDENCE.set(
        EvidenceBinding.model_validate({key: evidence[key] for key in EvidenceBinding.model_fields})
    )


def test_dossier_keeps_opposing_passages_failures_and_original_bytes(site_bridge: Any) -> None:
    b = site_bridge
    source = b.persist("synthetic-source", {"text": "Synthetic source, no scientific acceptance"})
    cards = [
        {
            "card_id": "passage-" + name,
            "provider": "Europe PMC",
            "identifier": name,
            "passage": text,
            "source_refs": [source],
            "source_verified": True,
            "evidence_level": "primary-abstract",
            "primary_eligible": True,
            "does_not_support": ["Binding efficacy or exact epitope"],
        }
        for name, text in [
            ("support", "Synthetic positive evidence for hypothesis A."),
            ("opposition", "Synthetic evidence contradicting hypothesis A."),
        ]
    ]
    query = {
        "query_id": "synthetic-query",
        "topic": "function",
        "status": "UNRESOLVED",
        "question": "Synthetic assay evidence",
        "cards": cards,
        "errors": [{"reason": "full text unavailable", "status": 404}],
    }
    ref = b.persist("evidence-research", query)
    b.store.event(b.thread, "evidence-view", {"target_binding": identity(b.binding()), "ref": ref})
    source_path = b.project / source["relative_path"]
    before = source_path.read_bytes()
    token = bind(b)
    try:
        dossier = persist_dossier(b, handoff(), "synthetic-execution")
        assert {c["passage"] for c in dossier["focused_passages"]} == {c["passage"] for c in cards}
        assert dossier["research_outcomes"][0]["errors"] == query["errors"]
        assert dossier["approved_target"] == b.read_site_evidence()["approved_target"]
        assert b.current_site() is None and b.approved_site() is None
        assert source_path.read_bytes() == before
        event = b.store.events(b.thread)[-1]["payload"]
        assert b.document(event["ref"]) == dossier
        source_path.write_text("SYNTHETIC integrity failure")
        with pytest.raises(ArtifactIntegrityError):
            site_dossier(b, handoff())
    finally:
        SITE_EVIDENCE.reset(token)


def test_dossier_rejects_missing_or_stale_delegation(site_bridge: Any) -> None:
    with pytest.raises(AgentBoundaryError, match="delegated Target binding"):
        site_dossier(site_bridge, handoff())
    token = bind(site_bridge)
    try:
        current = SITE_EVIDENCE.get()
        SITE_EVIDENCE.set(current.model_copy(update={"evidence_id": "other-project"}))
        with pytest.raises(AgentBoundaryError, match="delegated Target binding"):
            site_dossier(site_bridge, handoff())
    finally:
        SITE_EVIDENCE.reset(token)


def test_soft_working_target_and_model_aware_hard_guard() -> None:
    config = scripted_config()
    model = SimpleNamespace(profile=None)
    usage = context_usage(model, config, "site", [HumanMessage(content="x" * 67000)])
    assert usage["soft_target_exceeded"] and usage["hard_limit_chars"] == 100000
    with pytest.raises(AgentBoundaryError, match="hard context guard"):
        context_usage(model, config, "site", [HumanMessage(content="x" * 99000)], 1001)
    with pytest.raises(AgentBoundaryError, match="hard context guard"):
        context_usage(
            SimpleNamespace(profile={"max_input_tokens": 4096}),
            config,
            "site",
            [HumanMessage(content="x" * 20000)],
        )


@pytest.mark.asyncio
async def test_framework_summary_preserves_trace_and_consumes_shared_budget(
    bridge: Any,
    tmp_path: Path,
) -> None:
    config = scripted_config().model_copy(update={"max_input_chars": 4000})
    execution = bridge.store.begin_execution(bridge.thread, "Synthetic framework summary")
    model = FakeListChatModel(
        responses=["Fallible synthetic working memory; sources remain authoritative."]
    )
    backend = FilesystemBackend(root_dir=tmp_path / "memory", virtual_mode=True)
    middleware = research_memory(bridge, config, model, backend, execution["execution_id"])
    messages: list[Any] = [HumanMessage(content="Synthetic original goal")]
    for i in range(10):
        messages.extend(
            [
                AIMessage(
                    content="", tool_calls=[{"id": str(i), "name": "read_evidence", "args": {}}]
                ),
                ToolMessage(
                    content=f"SYNTHETIC evidence {i} " + "x" * 1800,
                    name="read_evidence",
                    tool_call_id=str(i),
                ),
            ]
        )
    original = [m.model_dump() for m in messages]
    received = []

    async def handler(request: Any) -> Any:
        received.extend(request.messages)
        bridge.store.reserve_model_call(bridge.thread, "site", 32, execution["execution_id"])
        return ModelResponse(result=[AIMessage(content="Synthetic response")])

    result = await middleware.awrap_model_call(
        ModelRequest(
            model=model,
            system_message=SystemMessage(content="Synthetic research"),
            messages=messages,
            state={"messages": messages},
            tools=[],
        ),
        handler,
    )
    assert [m.model_dump() for m in messages] == original
    assert len(received) < len(messages)
    event = result.command.update["_summarization_event"]
    retained = tmp_path / "memory" / event["file_path"].lstrip("/")
    assert retained.is_file() and "SYNTHETIC evidence 0" in retained.read_text()
    events = bridge.store.events(bridge.thread)
    assert len([e for e in events if e["kind"] == "model-call"]) == 2
    assert len([e for e in events if e["kind"] == "framework-summary-call"]) == 1
    assert len([e for e in events if e["kind"] == "framework-summary-response"]) == 1
