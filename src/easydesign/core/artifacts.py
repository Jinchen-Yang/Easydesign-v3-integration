"""Artifact 身份、路径安全和文件完整性契约。"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import ArtifactIntegrityError, ArtifactNotFoundError, PathPolicyError
from .hashing import sha256_file, verify_sha256

ID_PATTERN = r"^[a-z0-9][a-z0-9._-]{0,127}$"
STAGE_PATTERN = r"^0[1-7]-[a-z0-9][a-z0-9-]*$"
ATTEMPT_PATTERN = r"^attempt-[0-9]{4,}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


def _validate_relative_path(value: str) -> str:
    if "\\" in value:
        raise ValueError("Artifact 路径必须使用 POSIX '/' 分隔符")
    if not value or value.startswith("/"):
        raise ValueError("Artifact 路径必须是非空相对路径")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Artifact 路径不能包含空段、'.' 或 '..'")
    normalized = PurePosixPath(value)
    if normalized.is_absolute() or str(normalized) != value:
        raise ValueError("Artifact 路径不是规范 POSIX 相对路径")
    return value


def resolve_run_relative_path(run_root: Path, relative_path: str) -> Path:
    """在 run 根目录内安全解析路径，并阻止 symlink/path traversal 逃逸。"""

    _validate_relative_path(relative_path)
    root = run_root.resolve()
    candidate = (root / Path(relative_path)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise PathPolicyError(
            f"Artifact 路径逃出 run 根目录: root={root}, relative={relative_path}"
        ) from error
    return candidate


class ArtifactRef(BaseModel):
    """一个 run 内 artifact 的稳定逻辑引用。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    artifact_id: str = Field(pattern=ID_PATTERN)
    role: str = Field(pattern=ID_PATTERN)
    relative_path: str
    file_format: str = Field(pattern=ID_PATTERN)
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(ge=0)
    producer_stage: str | None = Field(default=None, pattern=STAGE_PATTERN)
    producer_attempt: str | None = Field(default=None, pattern=ATTEMPT_PATTERN)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        return _validate_relative_path(value)

    @field_validator("sha256")
    @classmethod
    def normalize_sha256(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def validate_producer_pair(self) -> Self:
        if (self.producer_stage is None) != (self.producer_attempt is None):
            raise ValueError("producer_stage 和 producer_attempt 必须同时存在或同时为空")
        return self

    def resolve(self, run_root: Path) -> Path:
        """把相对路径解析到指定 run 根目录。"""

        return resolve_run_relative_path(run_root, self.relative_path)

    def verify(self, run_root: Path) -> Path:
        """验证文件存在、大小和 SHA-256，成功后返回解析路径。"""

        path = self.resolve(run_root)
        if not path.is_file():
            raise ArtifactNotFoundError(f"Artifact 文件不存在: {path}")
        actual_size = path.stat().st_size
        if actual_size != self.size_bytes:
            raise ArtifactIntegrityError(
                f"Artifact 大小不一致: path={path}, expected={self.size_bytes}, "
                f"actual={actual_size}"
            )
        verify_sha256(path, self.sha256)
        return path

    @classmethod
    def from_file(
        cls,
        *,
        run_root: Path,
        relative_path: str,
        artifact_id: str,
        role: str,
        file_format: str,
        producer_stage: str | None = None,
        producer_attempt: str | None = None,
    ) -> Self:
        """从 run 内已有文件创建带 checksum 的引用。"""

        path = resolve_run_relative_path(run_root, relative_path)
        if not path.is_file():
            raise ArtifactNotFoundError(f"Artifact 文件不存在: {path}")
        return cls(
            artifact_id=artifact_id,
            role=role,
            relative_path=relative_path,
            file_format=file_format,
            sha256=sha256_file(path),
            size_bytes=path.stat().st_size,
            producer_stage=producer_stage,
            producer_attempt=producer_attempt,
        )
