"""Explicit provider configuration using LangChain's public model factory."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any, Literal

from pydantic import Field, SecretStr, model_validator

from .contracts import AgentBoundaryError, StrictDTO

PHASE2_MODEL_CALL_LIMIT = 64
SUMMARY_OUTPUT_TOKEN_LIMIT = 1024


Role = Literal[
    "coordinator", "target", "site", "binder", "judge", "pilot-diagnosis", "final-selection"
]


class LLMConfig(StrictDTO):
    provider: Literal["openai", "anthropic", "deepseek"]
    model: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$")
    secret_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,100}$")
    timeout_seconds: float = Field(default=90, ge=1, le=180)
    max_output_tokens: int = Field(default=2048, ge=128, le=16384)
    reasoning_effort: Literal["none", "low", "high", "max"] = "none"

    @model_validator(mode="after")
    def no_provider_prefix(self) -> LLMConfig:
        if ":" in self.model:
            raise ValueError("Specify provider separately from the model name")
        if self.reasoning_effort != "none" and self.provider != "deepseek":
            raise ValueError("Reasoning mode is currently verified only for DeepSeek")
        return self

    @property
    def adapter_provider(self) -> str:
        if self.provider == "deepseek":
            return "anthropic" if self.reasoning_effort != "none" else "openai"
        return self.provider

    @property
    def harness_key(self) -> str:
        return f"{self.adapter_provider}:{self.model}"


class ModelConfig(StrictDTO):
    default: LLMConfig
    roles: dict[Role, LLMConfig] = Field(default_factory=dict)
    max_model_calls: int = Field(default=PHASE2_MODEL_CALL_LIMIT, ge=1, le=100)
    max_input_chars: int = Field(default=60000, ge=4000, le=120000)
    hard_input_chars: int = Field(default=100000, ge=4000, le=400000)

    @model_validator(mode="after")
    def working_set_below_guard(self) -> ModelConfig:
        if self.max_input_chars > self.hard_input_chars:
            raise ValueError("Working-set target cannot exceed the hard context guard")
        return self

    def for_role(self, role: Role) -> LLMConfig:
        return self.roles.get(role, self.default)


def request_metadata(role: str, body: dict[str, Any]) -> dict[str, Any]:
    """Validation transport metadata only; never messages, headers or tool arguments."""
    return {
        "role": role,
        **{
            key: body[key]
            for key in (
                "model",
                "tool_choice",
                "thinking",
                "max_tokens",
                "max_completion_tokens",
                "stream",
            )
            if key in body
        },
        "tool_names": [t.get("function", t).get("name") for t in body.get("tools", [])],
        "message_count": len(body.get("messages", [])),
    }


def compact_summary_model(
    model: Any, config: ModelConfig, *, role: Role = "site"
) -> Any:
    """Use the configured Site model for memory compression without costly reasoning.

    A framework summary is fallible working memory, not a scientific decision. It does not
    benefit from an extended reasoning trace and must not consume the full scientific output
    allowance. Keep the provider/model identity unchanged while bounding its visible output.
    """
    selected = config.for_role(role)
    limit = min(selected.max_output_tokens, SUMMARY_OUTPUT_TOKEN_LIMIT)
    update: dict[str, Any] = {}
    if selected.provider == "deepseek" and selected.reasoning_effort != "none":
        update.update(
            max_tokens=limit,
            thinking={"type": "disabled"},
            output_config={},
        )
    elif selected.provider == "deepseek":
        update["extra_body"] = {
            **(getattr(model, "extra_body", None) or {}),
            "thinking": {"type": "disabled"},
            "max_tokens": limit,
        }
    else:
        update["max_tokens"] = limit
    return model.model_copy(update=update)


def compact_judge_model(model: Any, config: ModelConfig) -> Any:
    """Finalize a truncated review without changing the configured scientific model.

    DeepSeek ignores Anthropic's thinking budget. A transient non-thinking copy
    reserves the unchanged output allowance for the typed review and permits the
    SDK's forced tool choice. The original client, profile and first call stay intact.
    """
    selected = config.for_role("judge")
    if selected.provider != "deepseek" or selected.reasoning_effort == "none":
        return model
    return model.model_copy(update={"thinking": {"type": "disabled"}, "output_config": {}})


def create_models(
    config: ModelConfig,
    *,
    request_observer: Callable[[dict[str, Any]], None] | None = None,
    downstream: bool = False,
) -> dict[str, Any]:
    """Credentials live in SDK clients only, never DTOs, metadata or worker envs."""
    from langchain.chat_models import init_chat_model

    configs = {
        role: config.for_role(role) for role in ("coordinator", "target", "site", "binder", "judge")
    }
    if downstream:
        configs.update(
            {role: config.for_role(role) for role in ("pilot-diagnosis", "final-selection")}
        )
    secrets: dict[str, SecretStr] = {}
    for selected in configs.values():
        value = os.environ.get(selected.secret_env)
        if not value:
            raise AgentBoundaryError(
                f"Missing credential environment variable: {selected.secret_env}"
            )
        secrets[selected.secret_env] = SecretStr(value)
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    models = {}
    for role, selected in configs.items():
        kwargs: dict[str, Any] = {
            "api_key": secrets[selected.secret_env],
            "timeout": selected.timeout_seconds,
            "max_tokens": selected.max_output_tokens,
            "max_retries": 0,
        }
        provider = selected.provider
        if provider == "openai":
            kwargs["base_url"] = "https://api.openai.com/v1"
        elif provider == "anthropic":
            kwargs["base_url"] = "https://api.anthropic.com"
        if provider == "deepseek" and selected.reasoning_effort != "none":
            # The existing Anthropic adapter preserves signed thinking blocks through
            # tool rounds. ChatOpenAI drops DeepSeek reasoning_content on round-trip.
            # Both formats use the same provider/account at an explicitly fixed endpoint.
            provider = "anthropic"
            kwargs.update(
                base_url="https://api.deepseek.com/anthropic",
                thinking={"type": "enabled", "budget_tokens": 1024},
                output_config={"effort": selected.reasoning_effort},
            )
        elif provider == "deepseek":
            provider = "openai"
            # ChatOpenAI rewrites its max_tokens argument to max_completion_tokens.
            # DeepSeek expects max_tokens; send that explicit vendor body field.
            kwargs.pop("max_tokens")
            kwargs.update(
                base_url="https://api.deepseek.com",
                use_responses_api=False,
                extra_body={
                    "thinking": {"type": "disabled"},
                    "max_tokens": selected.max_output_tokens,
                },
            )
        if request_observer is not None and provider == "openai":
            import httpx

            async def observe(request: httpx.Request, current_role: str = role) -> None:
                request_observer(request_metadata(current_role, json.loads(request.content)))

            kwargs["http_async_client"] = httpx.AsyncClient(event_hooks={"request": [observe]})
        models[role] = init_chat_model(selected.model, model_provider=provider, **kwargs)
    for name in secrets:
        os.environ.pop(name, None)
    return models
