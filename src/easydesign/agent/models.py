"""Explicit provider configuration using LangChain's public model factory."""

from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import Field, SecretStr, model_validator

from .contracts import AgentBoundaryError, StrictDTO

Role = Literal["coordinator", "target", "site", "binder", "judge"]


class LLMConfig(StrictDTO):
    provider: Literal["openai", "anthropic", "deepseek"]
    model: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$")
    secret_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,100}$")
    timeout_seconds: float = Field(default=90, ge=1, le=180)
    max_output_tokens: int = Field(default=2048, ge=128, le=8192)

    @model_validator(mode="after")
    def no_provider_prefix(self) -> LLMConfig:
        if ":" in self.model:
            raise ValueError("Specify provider separately from the model name")
        return self

    @property
    def harness_key(self) -> str:
        provider = "openai" if self.provider == "deepseek" else self.provider
        return f"{provider}:{self.model}"


class ModelConfig(StrictDTO):
    default: LLMConfig
    roles: dict[Role, LLMConfig] = Field(default_factory=dict)
    max_model_calls: int = Field(default=32, ge=1, le=100)
    max_input_chars: int = Field(default=60000, ge=4000, le=120000)

    def for_role(self, role: Role) -> LLMConfig:
        return self.roles.get(role, self.default)


def create_models(config: ModelConfig) -> dict[str, Any]:
    """Credentials live in SDK clients only, never DTOs, metadata or worker envs."""
    from langchain.chat_models import init_chat_model

    configs = {
        role: config.for_role(role) for role in ("coordinator", "target", "site", "binder", "judge")
    }
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
        if provider == "deepseek":
            provider = "openai"
            kwargs.update(
                base_url="https://api.deepseek.com",
                use_responses_api=False,
                extra_body={"thinking": {"type": "disabled"}},
            )
        models[role] = init_chat_model(selected.model, model_provider=provider, **kwargs)
    for name in secrets:
        os.environ.pop(name, None)
    return models
