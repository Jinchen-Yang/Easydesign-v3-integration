"""Pydantic 契约模型的规范 JSON 序列化。"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .errors import ManifestStateError, SerializationError

ModelT = TypeVar("ModelT", bound=BaseModel)


def _json_data(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude_none=False)


def canonical_json_bytes(model: BaseModel) -> bytes:
    """生成稳定、排序、无多余空白的 UTF-8 JSON bytes。"""

    try:
        text = json.dumps(
            _json_data(model),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise SerializationError(f"模型无法规范 JSON 序列化: {error}") from error
    return text.encode("utf-8")


def canonical_model_sha256(model: BaseModel) -> str:
    """计算模型规范 JSON 的 SHA-256。"""

    return hashlib.sha256(canonical_json_bytes(model)).hexdigest()


def dump_model(model: BaseModel, path: Path) -> Path:
    """原子写入人类可读 JSON；目标已存在时拒绝覆盖。"""

    if path.exists():
        raise ManifestStateError(f"不可覆盖已存在的 manifest: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        content = json.dumps(
            _json_data(model),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise SerializationError(f"模型无法 JSON 序列化: {error}") from error

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.link(temporary_path, path)
        temporary_path.unlink()
    except FileExistsError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise ManifestStateError(f"不可覆盖已存在的 manifest: {path}") from error
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise SerializationError(f"Manifest 写入失败: path={path}, error={error}") from error
    return path


def load_model(path: Path, model_type: type[ModelT]) -> ModelT:
    """从 JSON 文件读取并严格校验契约模型。"""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SerializationError(f"Manifest JSON 读取失败: path={path}, error={error}") from error
    try:
        return model_type.model_validate(raw)
    except ValidationError as error:
        raise SerializationError(f"Manifest 模型校验失败: path={path}, error={error}") from error
