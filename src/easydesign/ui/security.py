"""短期 artifact token 与允许的 run 注册表。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from easydesign.core import ArtifactRef, PathPolicyError


class ArtifactTokenClaims(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_key: str
    relative_path: str
    sha256: str
    size_bytes: int = Field(ge=0)
    expires_at: int


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class ArtifactTokenSigner:
    """签发不暴露绝对路径、带过期时间和 HMAC 的 artifact token。"""

    def __init__(self, secret: bytes | None = None, *, lifetime_seconds: int = 3600) -> None:
        self._secret = secret if secret is not None else secrets.token_bytes(32)
        self._lifetime_seconds = lifetime_seconds

    @classmethod
    def from_file(
        cls,
        path: Path,
        *,
        lifetime_seconds: int = 3600,
    ) -> ArtifactTokenSigner:
        """Load or create a restart-stable local artifact token secret."""

        secret_path = path.expanduser().resolve()
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        if secret_path.exists():
            secret = secret_path.read_bytes()
        else:
            secret = secrets.token_bytes(32)
            try:
                with secret_path.open("xb") as handle:
                    handle.write(secret)
            except FileExistsError:
                secret = secret_path.read_bytes()
        if len(secret) < 32:
            raise PathPolicyError("Artifact token secret 文件内容非法")
        if os.name == "posix":
            try:
                os.chmod(secret_path, 0o600)
            except OSError as error:
                raise PathPolicyError("无法收紧 artifact token secret 文件权限") from error
        return cls(secret, lifetime_seconds=lifetime_seconds)

    def sign(self, run_key: str, artifact: ArtifactRef, *, now: int | None = None) -> str:
        issued = int(time.time()) if now is None else now
        claims = ArtifactTokenClaims(
            run_key=run_key,
            relative_path=artifact.relative_path,
            sha256=artifact.sha256,
            size_bytes=artifact.size_bytes,
            expires_at=issued + self._lifetime_seconds,
        )
        payload = json.dumps(
            claims.model_dump(mode="json"),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        signature = hmac.new(self._secret, payload, hashlib.sha256).digest()
        return f"{_encode(payload)}.{_encode(signature)}"

    def verify(self, token: str, *, now: int | None = None) -> ArtifactTokenClaims:
        try:
            payload_text, signature_text = token.split(".", maxsplit=1)
            payload = _decode(payload_text)
            signature = _decode(signature_text)
        except (ValueError, TypeError) as error:
            raise PathPolicyError("Artifact token 格式非法") from error
        expected = hmac.new(self._secret, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise PathPolicyError("Artifact token 签名无效")
        try:
            claims = ArtifactTokenClaims.model_validate_json(payload)
        except ValueError as error:
            raise PathPolicyError("Artifact token 内容非法") from error
        current = int(time.time()) if now is None else now
        if current > claims.expires_at:
            raise PathPolicyError("Artifact token 已过期")
        return claims


class UiRunRegistry:
    """只注册启动时显式 runs root 中由 run-index 声明的 run。"""

    def __init__(self, runs_root: Path) -> None:
        self.runs_root = runs_root.expanduser().resolve()
        self._runs: dict[str, Path] = {}

    def register(self, run_root: Path) -> str:
        root = run_root.expanduser().resolve()
        try:
            root.relative_to(self.runs_root)
        except ValueError as error:
            raise PathPolicyError("UI 只能注册配置 runs root 内的 run") from error
        key = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:24]
        existing = self._runs.get(key)
        if existing is not None and existing != root:
            raise PathPolicyError("Run key 冲突")
        self._runs[key] = root
        return key

    def resolve(self, run_key: str) -> Path:
        try:
            root = self._runs[run_key]
        except KeyError as error:
            raise PathPolicyError("未知或未注册的 run") from error
        resolved = root.resolve()
        try:
            resolved.relative_to(self.runs_root)
        except ValueError as error:
            raise PathPolicyError("Run 路径逃出允许的 runs root") from error
        return resolved
