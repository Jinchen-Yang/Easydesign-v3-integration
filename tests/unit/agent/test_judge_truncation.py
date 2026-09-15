"""Actual SDK recovery must submit under unchanged budgets and stage checks."""

import json
from typing import Any

import pytest
from pydantic import BaseModel

from easydesign.agent.contracts import AgentBoundaryError, EmptyArguments, JudgeVerdict
from easydesign.agent.harness import RoleBoundary
from easydesign.agent.models import LLMConfig, ModelConfig, create_models
from easydesign.agent.phase2 import Phase2Bridge


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong_stage", [False, True])
async def test_truncated_judge_uses_compact_sdk_recovery_without_approving(
    bridge: Any, monkeypatch: Any, wrong_stage: bool
) -> None:
    import anthropic
    import httpx2 as httpx
    from langchain.agents import create_agent
    from langchain.agents.structured_output import ToolStrategy
    from langchain_core.tools import StructuredTool

    requests = []

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
                        "id": f"verdict-{len(requests)}",
                        "name": "JudgeVerdict",
                        "input": {
                            "verdict": "assessed" if wrong_stage else "ready-to-ask",
                            "reasons": ["SYNTHETIC bounded control can be reviewed."],
                            "limitations": ["No biological efficacy established."],
                        },
                    }
                ],
                "stop_reason": "max_tokens" if first else "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 100, "output_tokens": 8192 if first else 60},
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
    model = create_models(cfg)["judge"]
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    monkeypatch.setattr(
        b,
        "judge_evidence",
        lambda: {
            "gate_type": "design-specification",
            "status": "awaiting-human-approval",
            "request_identity": "synthetic-current-design",
        },
    )
    eid = b.store.begin_execution(b.thread, "Review a bounded control")["execution_id"]
    boundary = RoleBoundary(b, "judge", cfg, "Synthetic review", execution_id=eid)

    class FileArguments(BaseModel):
        file_path: str

    tools = [
        StructuredTool.from_function(
            lambda **kwargs: pytest.fail("Recovery must not execute an action/read"),
            name=name,
            description="Unused scoped read",
            args_schema=FileArguments if name == "read_file" else EmptyArguments,
        )
        for name in sorted(boundary.allowed)
    ]
    graph = create_agent(
        model,
        tools=tools,
        middleware=[boundary],
        system_prompt="Submit the bounded review",
        response_format=ToolStrategy(JudgeVerdict, handle_errors=boundary.contract_error),
    )
    try:
        if wrong_stage:
            with pytest.raises(AgentBoundaryError, match="repair budget exhausted"):
                await graph.ainvoke({"messages": [{"role": "user", "content": "SYNTHETIC"}]})
        else:
            # The SDK test deliberately has no delegated evidence authority. A valid
            # recovered verdict passes preflight but cannot bypass that boundary.
            with pytest.raises(AgentBoundaryError, match="runtime-delegated evidence snapshot"):
                await graph.ainvoke({"messages": [{"role": "user", "content": "SYNTHETIC"}]})
        assert len(requests) == (3 if wrong_stage else 2)
        assert requests[0]["thinking"]["type"] == "enabled"
        assert requests[0]["output_config"] == {"effort": "high"}
        for request in requests[1:]:
            assert request["thinking"] == {"type": "disabled"}
            assert not request.get("output_config", {}).get("effort")
            assert request["tool_choice"] == {"type": "any"}
            assert [t["name"] for t in request["tools"]] == ["JudgeVerdict"]
            assert "output recovery" in str(request["messages"])
        assert all(r["max_tokens"] == 8192 for r in requests)
        assert model.thinking == {"type": "enabled", "budget_tokens": 1024}
        assert model.output_config == {"effort": "high"}
        events = b.store.events(b.thread)
        assert sum(e["kind"] == "submission-preflight-passed" for e in events) == (
            0 if wrong_stage else 1
        )
        assert sum(e["kind"] == "model-call" for e in events) == len(requests)
        assert sum(e["kind"] == "contract-repair" for e in events) == len(requests) - 1
        assert not any(e["kind"] in {"decision-card", "human-response"} for e in events)
        assert not b._jobs()
    finally:
        await client.aclose()
