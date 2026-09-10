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
    assert set(create_models(config)) == {"coordinator", "target", "site", "judge"}
    assert "test-secret" not in config.model_dump_json()
    assert calls[0][1]["max_retries"] == 0
    if provider == "deepseek":
        assert calls[0][1]["base_url"] == "https://api.deepseek.com"
        assert calls[0][1]["extra_body"] == {"thinking": {"type": "disabled"}}


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
    with pytest.raises(ValidationError):
        ModelConfig.model_validate_json(
            json.dumps({"default": default.model_dump(), "roles": {"binder": judge.model_dump()}})
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
    assert "provider-test-secret" not in json.dumps(requests)
    sync.close()
    await async_client.aclose()
