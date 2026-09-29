"""One explicit workspace-local capacity file; defaults preserve conservative limits."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from easydesign.agent.session_store import confined

from .artifacts import confined_bytes
from .contracts import ProductError
from .rabbit_capacity import RabbitCapacityLimits
from .transport_policy import TransportPolicy


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class LoginSettings(Settings):
    max_concurrency: int = Field(default=8, ge=1, le=256)
    max_pending: int = Field(default=300, ge=0, le=4096)
    wait_timeout: float = Field(default=10.0, ge=0, le=120)


class HttpSettings(Settings):
    trusted_proxies: list[str] = Field(default_factory=list, max_length=256)
    real_ip_header: str = "X-Real-IP"
    max_connections: int = Field(default=384, ge=2, le=4096)
    max_readers: int = Field(default=16, ge=1, le=4096)
    read_wait_timeout: float = Field(default=10.0, ge=0, le=120)
    max_uploads: int = Field(default=4, ge=1, le=128)
    max_pending_uploads: int = Field(default=300, ge=0, le=4096)
    upload_wait_timeout: float = Field(default=10.0, ge=0, le=120)
    header_timeout: float = Field(default=10.0, gt=0, le=120)
    body_timeout: float = Field(default=60.0, gt=0, le=600)

    def policy(self) -> TransportPolicy:
        return TransportPolicy(
            **{**self.model_dump(), "trusted_proxies": tuple(self.trusted_proxies)}
        )


class QueueSettings(Settings):
    max_active_admissions: int = Field(default=300, ge=1, le=10000)
    max_conversation_workers: int = Field(default=8, ge=1, le=64)
    startup_timeout_seconds: float = Field(default=30.0, ge=1, le=60)


class CapacityConfig(Settings):
    http: HttpSettings = Field(default_factory=HttpSettings)
    login: LoginSettings = Field(default_factory=LoginSettings)
    ai: dict[str, Any] = Field(default_factory=dict)
    queue: QueueSettings = Field(default_factory=QueueSettings)
    web_history: list[str] = Field(default_factory=list, max_length=16)
    easy_web_history: list[str] = Field(default_factory=list, max_length=16)

    def validate_limits(self) -> None:
        self.http.policy()
        RabbitCapacityLimits(**self.ai)


def load_capacity_config(root: Path, path: Path | None) -> CapacityConfig:
    try:
        if path is None:
            result = CapacityConfig()
        else:
            declared = confined(root, root / path)
            result = CapacityConfig.model_validate_json(
                confined_bytes(root, declared.relative_to(root).as_posix(), maximum=65536)
            )
        result.validate_limits()
        for item in (*result.web_history, *result.easy_web_history):
            confined(root, root / item)
        return result
    except (ValueError, TypeError) as error:
        raise ProductError("invalid_capacity_config", "容量配置格式或限额无效", 400) from error
