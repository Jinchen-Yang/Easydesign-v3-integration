"""Real harness loops over synthetic HTTP evidence; no scientific approval is fabricated."""

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import Field

from easydesign.agent.contracts import AgentBoundaryError, SourceSelectionRequired
from easydesign.agent.evidence_corpus import EvidenceCorpus
from easydesign.agent.evidence_research import (
    EvidenceResearch,
    ResearchConclusion,
    ResearchHttpClient,
    ResearchQuery,
)
from easydesign.agent.harness import RoleBoundary, create_harness
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.phase2_tools import PHASE2_ALLOWED
from easydesign.agent.session_store import SessionStore
from tests.agent_support import ScriptedModel, scripted_config

ACQUIRE = {
    "topic": "function",
    "question": "What does the assay show?",
    "operation": "primary-fulltext",
    "identifier": "PMC123",
}
RAW = (
    '<article article-type="research-article"><front><article-meta>'
    '<article-id pub-id-type="pmcid">PMC123</article-id></article-meta></front>'
    "<body><sec><title>Results</title><p>The assay showed inhibition under controlled conditions. "
    + "Independent control measurements limit interpretation. " * 80
    + "</p></sec></body></article>"
).encode()


class RecoveryModel(ScriptedModel):
    repeat_error: bool = False
    empty_search: bool = False
    repairs: list[dict[str, Any]] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        output = {"target": "TargetInterpretation", "site": "SiteIntent", "judge": "JudgeVerdict"}
        expected = PHASE2_ALLOWED[self.role] | (
            {output[self.role]} if self.role in output else set()
        )
        names = {t.name for t in tools}
        if self.role == "coordinator":
            expected -= {"read_file"}
        assert names <= expected and expected - names <= {
            "get_job_status",
            "prepare_target",
            "read_evidence_result",
            "analyze_receptor_context",
        }
        return self

    def answer(self, messages: Any) -> AIMessage:
        calls = {c["id"]: c for m in messages if isinstance(m, AIMessage) for c in m.tool_calls}
        results = [
            (calls[m.tool_call_id]["name"], m) for m in messages if isinstance(m, ToolMessage)
        ]
        if self.role == "coordinator":
            if not results:
                return self.call(
                    "task",
                    subagent_type="target-intelligence",
                    description="Inspect the requested source and its limitations.",
                )
            return AIMessage(
                content="Evidence inspection ended; no target or design approval was issued."
            )
        assert self.role == "target"
        if not results:
            return self.call("read_file", file_path="/skills/target-intelligence/SKILL.md")
        research = [m for name, m in results if name == "research_evidence"]
        if not research or results[-1][0] == "select_evidence":
            if self.empty_search:
                return self.call(
                    "research_evidence",
                    topic="function",
                    question="Is reliable evidence available?",
                    operation="literature-search",
                    query="synthetic evidence",
                )
            return self.call("research_evidence", **ACQUIRE)
        last = research[-1]
        if last.status == "error":
            required = json.loads(last.content)
            assert required["status"] == "REQUIRES_ACTION"
            assert required["error_code"] == "SOURCE_NOT_SELECTED"
            self.repairs.append(required)
            if self.repeat_error:
                return self.call("research_evidence", **ACQUIRE)
            return self.call(
                "select_evidence",
                provider=required["provider"],
                identifier=required["identifier"],
                need=required["evidence_need"],
                selection="SELECTED",
                reason="Inspect assay evidence requested for the current question",
            )
        if not self.empty_search and not any(name == "retrieve_evidence" for name, _ in results):
            return self.call(
                "retrieve_evidence",
                need="FUNCTIONAL_MECHANISM",
                question="assay control",
                source_id="EuropePMC:PMC123",
            )
        return self.call(
            "TargetInterpretation",
            **{
                "interpretation": [
                    "No reliable evidence found"
                    if self.empty_search
                    else "A focused assay passage was retrieved"
                ],
                "unresolved_identity": ["No biological target identity was approved"],
                "limitations": ["Source inspection alone cannot establish target efficacy"],
                "recommended_action": "Limit the conclusion to available evidence",
            },
        )


def source_transport(bridge: Any, monkeypatch: Any, *, empty: bool = False) -> list[Any]:
    requests = []

    def handle(request: Any) -> httpx.Response:
        requests.append(request)
        if empty:
            return httpx.Response(200, json={"resultList": {"result": []}})
        return httpx.Response(200, content=RAW)

    monkeypatch.setattr(
        EvidenceResearch,
        "client",
        lambda self, directory: ResearchHttpClient(
            evidence_dir=directory,
            cache_root=bridge.project / "http-cache",
            max_attempts=1,
            client=httpx.Client(transport=httpx.MockTransport(handle)),
        ),
    )
    return requests


async def inspect_with_harness(bridge: Any, *, repeat: bool = False, empty: bool = False) -> Any:
    # An exact named source remains an Agent selection, not inferred human approval.
    goal = "Inspect PMC123 without making any scientific approval."
    execution = bridge.store.begin_execution(bridge.thread, goal)
    models = {
        role: RecoveryModel(role=role, repeat_error=repeat, empty_search=empty)
        for role in PHASE2_ALLOWED
    }
    graph = create_harness(
        bridge,
        models,
        scripted_config(),
        MemorySaver(),
        goal,
        execution_id=execution["execution_id"],
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=goal)]},
        {"configurable": {"thread_id": bridge.thread}, "recursion_limit": 40},
    )
    return result, models, execution


@pytest.mark.asyncio
async def test_harness_repairs_selection_then_acquires_and_reads_durable_source(
    bridge: Any, monkeypatch: Any
) -> None:
    bridge = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    requests = source_transport(bridge, monkeypatch)
    result, models, execution = await inspect_with_harness(bridge)
    assert result["messages"][-1].text.startswith("Evidence inspection ended")
    assert len(models["target"].repairs) == 1 and len(requests) == 1
    events = bridge.store.events(bridge.thread)
    repairs = [e for e in events if e["kind"] == "prerequisite-repair"]
    selected = [e for e in events if e["kind"] == "evidence-selection"]
    acquired = [e for e in events if e["kind"] == "evidence-research"]
    assert events.index(repairs[0]) < events.index(selected[0]) < events.index(acquired[0])
    assert repairs[0]["payload"]["execution_id"] == execution["execution_id"]
    document = EvidenceCorpus(bridge).documents()[0]
    assert (bridge.project / document["source_refs"][0]["relative_path"]).read_bytes() == RAW
    assert any(e["kind"] == "evidence-view" and e["payload"]["cards_supplied"] > 0 for e in events)
    assert any(
        e["kind"] == "tool" and e["payload"]["focused_cards_in_model_result"] > 0 for e in events
    )
    assert not bridge._jobs()


@pytest.mark.asyncio
async def test_repair_limit_survives_restart_but_not_a_new_execution(
    bridge: Any, monkeypatch: Any
) -> None:
    bridge = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    requests = source_transport(bridge, monkeypatch)
    with pytest.raises(AgentBoundaryError, match="prerequisite repair budget exhausted"):
        await inspect_with_harness(bridge, repeat=True)
    repairs = [e for e in bridge.store.events(bridge.thread) if e["kind"] == "prerequisite-repair"]
    assert [e["payload"]["attempt"] for e in repairs] == [1, 2, 3, 4]
    assert not requests and not EvidenceCorpus(bridge).selections() and not bridge._jobs()
    reopened = SessionStore(bridge.project)
    try:
        resumed = Phase2Bridge(bridge.project, bridge.thread, reopened)
        old = reopened.latest_execution(bridge.thread)["execution_id"]
        request = SimpleNamespace(
            tool_call={"name": "research_evidence", "args": ACQUIRE, "id": "retry-after-restart"}
        )

        async def acquire(request: Any) -> Any:
            return EvidenceResearch(resumed).acquire(
                ResearchQuery.model_validate(ACQUIRE), role="target"
            )

        guard = RoleBoundary(
            resumed, "target", scripted_config(), "Inspect evidence", execution_id=old
        )
        with pytest.raises(AgentBoundaryError, match="prerequisite repair budget exhausted"):
            await guard.awrap_tool_call(request, acquire)
        new = reopened.begin_execution(bridge.thread, "Follow-up inspection", followup=True)[
            "execution_id"
        ]
        # An old graph cannot spend the fresh execution's allowance.
        with pytest.raises(AgentBoundaryError, match="not bound"):
            await guard.awrap_tool_call(request, acquire)
        guard = RoleBoundary(
            resumed, "target", scripted_config(), "Inspect evidence", execution_id=new
        )
        correction = json.loads((await guard.awrap_tool_call(request, acquire)).content)
        assert correction["repair_attempt"] == 1 and not requests
    finally:
        reopened.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("violation", ["forbidden-tool", "foreign-file", "disallowed-domain"])
async def test_hard_violations_never_become_prerequisite_repairs(
    bridge: Any, violation: str
) -> None:
    bridge = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = bridge.store.begin_execution(bridge.thread, "Inspect evidence")["execution_id"]
    guard = RoleBoundary(
        bridge, "target", scripted_config(), "Inspect evidence", execution_id=execution
    )
    name = (
        "request_scientific_decision"
        if violation == "forbidden-tool"
        else "read_file"
        if violation == "foreign-file"
        else "research_evidence"
    )
    request = SimpleNamespace(
        tool_call={
            "name": name,
            "args": {"file_path": "/foreign-project/private.json"},
            "id": "forbidden",
        }
    )
    invoked = []

    async def handler(request: Any) -> Any:
        invoked.append(request)
        with ResearchHttpClient(evidence_dir=bridge.project / "disallowed-source") as client:
            return client.request(
                "GET", "https://outside-policy.invalid/record", artifact_name="unreachable.json"
            )

    with pytest.raises(AgentBoundaryError) as error:
        await guard.awrap_tool_call(request, handler)
    assert error.value.category == "HARD_BOUNDARY_VIOLATION"
    assert bool(invoked) == (violation == "disallowed-domain")
    assert not any(e["kind"] == "prerequisite-repair" for e in bridge.store.events(bridge.thread))
    assert not bridge._jobs()


@pytest.mark.asyncio
async def test_no_evidence_is_a_nonfatal_scientific_state(bridge: Any, monkeypatch: Any) -> None:
    bridge = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    requests = source_transport(bridge, monkeypatch, empty=True)
    result, models, _ = await inspect_with_harness(bridge, empty=True)
    assert result["messages"][-1].text.startswith("Evidence inspection ended")
    research = EvidenceResearch(bridge)
    assert research.snapshot()["topics"]["function"] == "SEARCHED_NO_EVIDENCE"
    conclusion = ResearchConclusion(
        topic="function",
        status="SEARCHED_NO_EVIDENCE",
        limitations=["The bounded search found no reliable evidence"],
    )
    research.validate_conclusions([conclusion])
    assert len(requests) == 1 and not models["target"].repairs
    assert not issubclass(SourceSelectionRequired, AgentBoundaryError)
