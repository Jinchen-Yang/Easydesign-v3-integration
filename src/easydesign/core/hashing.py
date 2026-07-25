"""Artifact SHA-256 计算与完整性验证。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .errors import ArtifactIntegrityError, ArtifactNotFoundError

DEFAULT_CHUNK_SIZE = 1024 * 1024


def sha256_bytes(value: bytes) -> str:
    """计算内存中协议响应或规范内容的 SHA-256。"""

    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    """流式计算文件 SHA-256，不把大文件一次性读入内存。"""

    if chunk_size <= 0:
        raise ValueError("chunk_size 必须为正整数")
    if not path.is_file():
        raise ArtifactNotFoundError(f"Artifact 文件不存在: {path}")

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: Path, expected: str) -> None:
    """验证文件 SHA-256，不一致时提供稳定异常。"""

    actual = sha256_file(path)
    if actual != expected.lower():
        raise ArtifactIntegrityError(
            f"Artifact SHA-256 不一致: path={path}, expected={expected}, actual={actual}"
        )
