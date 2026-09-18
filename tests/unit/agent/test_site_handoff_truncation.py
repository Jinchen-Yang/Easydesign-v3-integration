"""A truncated Site handoff must reserve the retry for its typed payload."""

import json
from typing import Any

import pytest
from pydantic import BaseModel

from easydesign.agent.contracts import EmptyArguments
from easydesign.agent.harness import SITE_RESEARCH_MODEL_CALL_LIMIT, RoleBoundary
from easydesign.agent.models import LLMConfig, ModelConfig, create_models
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.site_dossier import SiteResearchHandoff


@pytest.mark.asyncio
async def test_truncated_site_handoff_uses_nonthinking_typed_recovery(
    bridge: Any, monkeypatch: Any
) -> None:
    import anthropic
    import httpx2 as httpx
    from langchain.agents import create_agent
    from langchain.agents.structured_output import ToolStrategy
    from langchain_core.tools import StructuredTool

    requests = []
    handoff = SiteResearchHandoff(
        candidates=[
            {
                "name": "Synthetic extracellular candidate",
                "hotspot_label_seq_ids": [1, 2, 3],
                "rationale": "Exercise output recovery without a scientific claim.",
            }
        ],
        stopping_reason="Synthetic bounded research is sufficient for the recovery test.",
        unresolved_questions=["No biological efficacy was tested."],
    )

    def capture(request: Any) -> Any:
        requests.append(json.loads(request.content))
        first = len(requests) == 1
        return httpx.Response(
            200,
            request=request,
            json={
                "id": f"synthetic-{len(requests)}",
                "type": "message",
                "role": "assistant",
                "model": "deepseek-v4-pro",
                "content": []
                if first
                else [
                    {
                        "type": "tool_use",
                        "id": "handoff-recovery",
                        "name": "SiteResearchHandoff",
                        "input": handoff.model_dump(mode="json"),
                    }
                ],
                "stop_reason": "max_tokens" if first else "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 100, "output_tokens": 8192 if first else 200},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(capture))
    original_client = anthropic.AsyncClient
    monkeypatch.setattr(
        anthropic,
        "AsyncClient",
        lambda **kwargs: original_client(**{**kwargs, "http_client": client}),
    )
    monkeypatch.setenv("TEST_KEY", "synthetic-no-network-key")
    cfg = ModelConfig(
        default=LLMConfig(
            provider="deepseek",
            model="deepseek-v4-pro",
            secret_env="TEST_KEY",
            reasoning_effort="high",
            max_output_tokens=8192,
        )
    )
    model = create_models(cfg)["site"]
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    eid = b.store.begin_execution(b.thread, "Submit a bounded Site handoff")["execution_id"]
    for _ in range(SITE_RESEARCH_MODEL_CALL_LIMIT):
        b.store.reserve_model_call(b.thread, "site", cfg.max_model_calls, eid)
    boundary = RoleBoundary(
        b,
        "site",
        cfg,
        "Synthetic Site research",
        execution_id=eid,
        site_stage="research",
        domain_skills=False,
    )
    monkeypatch.setattr("easydesign.agent.harness.site_dossier", lambda *args: {})

    class Arguments(BaseModel):
        value: str | None = None

    tools = [
        StructuredTool.from_function(
            lambda **kwargs: pytest.fail("Finalization recovery must not execute action tools"),
            name=name,
            description="Unused Site action",
            args_schema=EmptyArguments if name == "read_site_evidence" else Arguments,
        )
        for name in sorted(boundary.allowed)
    ]
    graph = create_agent(
        model,
        tools=tools,
        middleware=[boundary],
        system_prompt="Submit the bounded Site handoff",
        response_format=ToolStrategy(SiteResearchHandoff, handle_errors=boundary.contract_error),
    )
    try:
        result = await graph.ainvoke({"messages": [{"role": "user", "content": "SYNTHETIC"}]})
        assert result["structured_response"] == handoff
        assert len(requests) == 2
        assert requests[0]["thinking"]["type"] == "enabled"
        assert requests[1]["thinking"] == {"type": "disabled"}
        assert not requests[1].get("output_config", {}).get("effort")
        assert requests[1]["tool_choice"] == {"type": "any"}
        assert [tool["name"] for tool in requests[1]["tools"]] == ["SiteResearchHandoff"]
        assert "output allowance" in str(requests[1]["messages"])
        assert all(request["max_tokens"] == 8192 for request in requests)
        assert model.thinking == {"type": "enabled", "budget_tokens": 1024}
        events = b.store.events(b.thread)
        assert sum(event["kind"] == "contract-repair" for event in events) == 1
        assert any(
            event["kind"] == "model-context"
            and event["payload"].get("compact_site_handoff_recovery")
            for event in events
        )
    finally:
        await client.aclose()
