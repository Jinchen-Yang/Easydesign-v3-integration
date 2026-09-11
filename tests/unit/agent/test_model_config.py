import json
from typing import Any

import pytest
from pydantic import ValidationError

from easydesign.agent.models import LLMConfig, ModelConfig, create_models


@pytest.mark.parametrize("provider", ["openai", "anthropic", "deepseek"])
def test_explicit_factory_and_no_secret_in_config(provider: str, monkeypatch: Any) -> None:
    calls = []
    monkeypatch.setenv("TEST_KEY", "test-secret-never-persist")
    monkeypatch.setattr(
        "langchain.chat_models.init_chat_model", lambda *a, **k: calls.append((a, k)) or object()
    )
    config = ModelConfig(
        default=LLMConfig(provider=provider, model="test-model", secret_env="TEST_KEY")
    )
    assert set(create_models(config)) == {"coordinator", "target", "site", "binder", "judge"}
    assert "test-secret" not in config.model_dump_json()
    assert calls[0][1]["max_retries"] == 0
    if provider == "deepseek":
        assert calls[0][1]["base_url"] == "https://api.deepseek.com"
        assert calls[0][1]["extra_body"] == {"thinking": {"type": "disabled"}, "max_tokens": 2048}
        assert "max_tokens" not in calls[0][1]


@pytest.mark.parametrize(
    "field,value",
    [
        ("base_url", "https://attacker.invalid"),
        ("api_key", "secret"),
        ("max_output_tokens", 999999),
    ],
)
def test_endpoint_secret_and_unbounded_config_rejected(field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        LLMConfig.model_validate(
            {
                "provider": "deepseek",
                "model": "deepseek-flash",
                "secret_env": "TEST_KEY",
                field: value,
            }
        )


def test_role_switch_and_unknown_role() -> None:
    default = LLMConfig(provider="openai", model="one", secret_env="OPENAI_API_KEY")
    judge = LLMConfig(provider="anthropic", model="two", secret_env="ANTHROPIC_API_KEY")
    config = ModelConfig(default=default, roles={"judge": judge})
    assert config.for_role("target") == default
    assert config.for_role("judge") == judge
    assert ModelConfig(default=default, roles={"binder": judge}).for_role("binder") == judge
    with pytest.raises(ValidationError):
        ModelConfig.model_validate_json(
            json.dumps(
                {"default": default.model_dump(), "roles": {"unregistered": judge.model_dump()}}
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "anthropic", "deepseek"])
async def test_real_provider_adapter_preserves_typed_tool_contract(
    provider: str, monkeypatch: Any
) -> None:
    import socket

    if provider == "anthropic":
        import httpx2 as httpx
    else:
        import httpx
    from langchain.chat_models import init_chat_model
    from langchain_core.tools import StructuredTool

    from easydesign.agent.contracts import EmptyArguments

    requests = []

    def transport(request: Any) -> Any:
        payload = json.loads(request.content)
        requests.append(payload)
        if provider == "anthropic":
            response = {
                "id": "msg-test",
                "type": "message",
                "role": "assistant",
                "model": "test-model",
                "content": [
                    {"type": "tool_use", "id": "tool-test", "name": "prepare_target", "input": {}}
                ],
                "stop_reason": "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        else:
            response = {
                "id": "chat-test",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "tool-test",
                                    "type": "function",
                                    "function": {"name": "prepare_target", "arguments": "{}"},
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        return httpx.Response(200, json=response, request=request)

    sync = httpx.Client(transport=httpx.MockTransport(transport))
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(transport))

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Provider contract test attempted a real network connection")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    if provider == "anthropic":
        import anthropic

        original = anthropic.AsyncClient
        monkeypatch.setattr(
            anthropic,
            "AsyncClient",
            lambda **kwargs: original(**{**kwargs, "http_client": async_client}),
        )
    else:

        def factory(*args: Any, **kwargs: Any) -> Any:
            return init_chat_model(
                *args, **kwargs, http_client=sync, http_async_client=async_client
            )

        monkeypatch.setattr("langchain.chat_models.init_chat_model", factory)
    monkeypatch.setenv("TEST_KEY", "provider-test-secret")
    config = ModelConfig(
        default=LLMConfig(provider=provider, model="test-model", secret_env="TEST_KEY")
    )
    tool = StructuredTool.from_function(
        lambda: "unused",
        name="prepare_target",
        description="Prepare bound local target",
        args_schema=EmptyArguments,
    )
    model = create_models(config)["target"]
    response = await model.bind_tools([tool]).ainvoke("Prepare the explicitly bound local target")
    assert response.tool_calls[0]["name"] == "prepare_target"
    assert response.tool_calls[0]["args"] == {}
    assert len(requests) == 1
    if provider == "deepseek":
        assert requests[0]["max_tokens"] == config.default.max_output_tokens
        assert "max_completion_tokens" not in requests[0]
    elif provider == "openai":
        assert requests[0]["max_completion_tokens"] == config.default.max_output_tokens
    else:
        assert requests[0]["max_tokens"] == config.default.max_output_tokens
    assert "provider-test-secret" not in json.dumps(requests)
    sync.close()
    await async_client.aclose()


@pytest.mark.asyncio
async def test_site_finalization_filters_the_actual_sdk_tool_payload(
    bridge: Any, monkeypatch: Any
) -> None:
    import json

    import httpx
    from langchain.agents import create_agent
    from langchain.agents.structured_output import ToolStrategy
    from langchain.chat_models import init_chat_model
    from langchain_core.tools import StructuredTool

    from easydesign.agent.harness import RoleBoundary
    from easydesign.agent.phase2 import Phase2Bridge
    from easydesign.agent.phase2_tools import phase2_tools
    from easydesign.agent.site_contracts import SiteIntent

    requests = []

    def capture(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        raise RuntimeError("Captured SDK payload without network")

    client = httpx.AsyncClient(transport=httpx.MockTransport(capture))
    sync = httpx.Client(transport=httpx.MockTransport(capture))

    def factory(*args: Any, **kwargs: Any) -> Any:
        return init_chat_model(*args, **kwargs, http_client=sync, http_async_client=client)

    monkeypatch.setattr("langchain.chat_models.init_chat_model", factory)
    monkeypatch.setenv("TEST_KEY", "wire-test-secret")
    cfg = ModelConfig(
        default=LLMConfig(provider="deepseek", model="test-model", secret_env="TEST_KEY")
    )
    model = create_models(cfg)["site"]
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    eid = b.store.begin_execution(b.thread, "Finalize a bounded hypothesis")["execution_id"]
    for _ in range(cfg.max_model_calls - 8):
        b.store.reserve_model_call(b.thread, "site", cfg.max_model_calls, eid)
    boundary = RoleBoundary(b, "site", cfg, "Scientific test", execution_id=eid)
    site_tools = phase2_tools(b, "site") + [
        StructuredTool.from_function(lambda file_path: "", name="read_file", description="Skill")
    ]
    graph = create_agent(
        model,
        tools=site_tools,
        response_format=ToolStrategy(SiteIntent, handle_errors=boundary.contract_error),
        middleware=[boundary],
        system_prompt="Submit the test hypothesis",
    )
    with pytest.raises(Exception, match="Captured SDK payload|Connection error"):
        await graph.ainvoke(
            {"messages": [{"role": "user", "content": "Submit the available evidence"}]}
        )
    assert len(requests) == 1
    assert [t["function"]["name"] for t in requests[0]["tools"]] == ["SiteIntent"]
    assert requests[0]["tool_choice"] == {"type": "function", "function": {"name": "SiteIntent"}}
    assert requests[0]["max_tokens"] == 2048 and requests[0]["thinking"] == {"type": "disabled"}
    assert not b._jobs() and b.current_site() is None
    sync.close()
    await client.aclose()


def test_transport_metadata_excludes_credentials_messages_and_tool_arguments() -> None:
    import json

    from easydesign.agent.models import request_metadata

    body = {
        "model": "model-name",
        "max_tokens": 4096,
        "thinking": {"type": "disabled"},
        "tool_choice": {"type": "function", "function": {"name": "SiteIntent"}},
        "tools": [
            {
                "type": "function",
                "function": {"name": "SiteIntent", "parameters": {"secret": "schema-private"}},
            }
        ],
        "messages": [{"role": "user", "content": "private-source-text"}],
        "api_key": "credential-private",
        "headers": {"authorization": "credential-private"},
    }
    result = request_metadata("site", body)
    assert result["tool_names"] == ["SiteIntent"] and result["max_tokens"] == 4096
    assert result["message_count"] == 1 and "private" not in json.dumps(result)
