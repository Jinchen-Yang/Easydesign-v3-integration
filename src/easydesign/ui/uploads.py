"""Persistent upload receipts and bounded repository-local staging."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from easydesign.core import ConfigurationError
from easydesign.core.hashing import sha256_file
from easydesign.orchestration.task_tracking import (
    atomic_dump_runtime_model,
    load_latest_runtime_model,
)
from easydesign.workspace_context import WorkspaceContext

from .models import UploadReceipt


class UploadStore:
    """Keep receipts across UI restarts without auto-deleting any bytes."""

    def __init__(
        self,
        workspace: WorkspaceContext,
        *,
        warning_bytes: int | None = None,
        blocking_bytes: int | None = None,
    ) -> None:
        warning_bytes = (
            workspace.declaration.upload_warning_bytes
            if warning_bytes is None
            else warning_bytes
        )
        blocking_bytes = (
            workspace.declaration.upload_blocking_bytes
            if blocking_bytes is None
            else blocking_bytes
        )
        if warning_bytes <= 0 or blocking_bytes <= warning_bytes:
            raise ConfigurationError("上传暂存容量阈值无效")
        self.workspace = workspace
        self.file_root = workspace.runtime_root / "tmp" / "ui-uploads"
        self.receipt_root = workspace.runtime_root / "state" / "ui" / "upload-receipts"
        self.file_root.mkdir(parents=True, exist_ok=True)
        self.receipt_root.mkdir(parents=True, exist_ok=True)
        self.warning_bytes = warning_bytes
        self.blocking_bytes = blocking_bytes

    def _receipt_path(self, token: str) -> Path:
        if not token.startswith("upload-") or "/" in token or "\\" in token:
            raise ConfigurationError("无效的 upload token")
        return self.receipt_root / token / "receipt.json"

    def _publish(self, receipt: UploadReceipt) -> UploadReceipt:
        atomic_dump_runtime_model(receipt, self._receipt_path(receipt.upload_token))
        return receipt

    def list(self) -> tuple[UploadReceipt, ...]:
        values: list[UploadReceipt] = []
        for path in self.receipt_root.glob("upload-*/receipt.json"):
            try:
                values.append(load_latest_runtime_model(path, UploadReceipt))
            except (OSError, ValueError):
                continue
        return tuple(sorted(values, key=lambda item: item.updated_at, reverse=True))

    def staged_bytes(self) -> int:
        return sum(
            item.size_bytes
            for item in self.list()
            if item.status in {
                "receiving",
                "ready",
                "failed",
                "cleanup-suggested",
            }
            and not item.referenced
        )

    def find_reusable(
        self,
        *,
        filename: str,
        size_bytes: int,
        sha256: str,
    ) -> UploadReceipt | None:
        """Return the existing verified pending upload instead of storing a duplicate."""

        for item in self.list():
            if (
                item.filename == filename
                and item.size_bytes == size_bytes
                and item.sha256 == sha256
                and item.status == "ready"
                and not item.referenced
            ):
                try:
                    self.resolve(item.upload_token)
                except ConfigurationError:
                    continue
                return item
        return None

    def capacity(self, incoming_size: int = 0) -> dict[str, int | bool]:
        current = self.staged_bytes()
        projected = current + max(0, incoming_size)
        return {
            "staged_bytes": current,
            "projected_bytes": projected,
            "warning_bytes": self.warning_bytes,
            "blocking_bytes": self.blocking_bytes,
            "warning": projected >= self.warning_bytes,
            "blocked": projected >= self.blocking_bytes,
        }

    def begin(
        self,
        *,
        filename: str,
        size_bytes: int,
        sha256: str,
        created_at: datetime | None = None,
    ) -> tuple[UploadReceipt, Path]:
        if Path(filename).name != filename or filename in {"", ".", ".."}:
            raise ConfigurationError("上传文件名必须是不含路径的 basename")
        if len(sha256) != 64 or any(value not in "0123456789abcdef" for value in sha256):
            raise ConfigurationError("浏览器上传 SHA-256 格式无效")
        capacity = self.capacity(size_bytes)
        if bool(capacity["blocked"]):
            raise ConfigurationError(
                "待处理上传已达到工作区配置的安全上限；"
                "请先查看精确清理建议并另行批准"
            )
        now = created_at or datetime.now(tz=UTC)
        token = f"upload-{uuid4().hex}"
        directory = self.file_root / token
        directory.mkdir(parents=True, exist_ok=False)
        target = directory / filename
        receipt = UploadReceipt(
            upload_token=token,
            filename=filename,
            size_bytes=size_bytes,
            sha256=sha256,
            status="receiving",
            relative_path=target.relative_to(self.workspace.root).as_posix(),
            created_at=now,
            updated_at=now,
        )
        self._publish(receipt)
        return receipt, target

    def load(self, token: str) -> UploadReceipt:
        path = self._receipt_path(token)
        if not path.is_file():
            raise ConfigurationError("未知或已失效的 upload token")
        return load_latest_runtime_model(path, UploadReceipt)

    def resolve(self, token: str, *, require_ready: bool = True) -> Path:
        receipt = self.load(token)
        if require_ready and receipt.status not in {"ready", "failed"}:
            raise ConfigurationError(
                f"上传已失效或当前不可用于创建项目: {receipt.status}"
            )
        path = (self.workspace.root / receipt.relative_path).resolve()
        self.workspace.assert_write_path(path)
        if not path.is_file():
            raise ConfigurationError("上传回执对应文件不存在")
        if path.stat().st_size != receipt.size_bytes or sha256_file(path) != receipt.sha256:
            raise ConfigurationError("上传回执与文件大小或 SHA-256 不一致")
        return path

    def ready(self, token: str, *, updated_at: datetime | None = None) -> UploadReceipt:
        current = self.load(token)
        path = self.resolve(token, require_ready=False)
        if path.stat().st_size != current.size_bytes or sha256_file(path) != current.sha256:
            raise ConfigurationError("上传完成后的 SHA-256 复核失败")
        return self._publish(
            current.model_copy(
                update={
                    "status": "ready",
                    "updated_at": updated_at or datetime.now(tz=UTC),
                }
            )
        )

    def relocate(
        self,
        token: str,
        *,
        path: Path,
        status: str,
        project_id: str | None = None,
        failure_reason: str | None = None,
        updated_at: datetime | None = None,
    ) -> UploadReceipt:
        current = self.load(token)
        resolved = self.workspace.assert_write_path(path)
        return self._publish(
            current.model_copy(
                update={
                    "status": status,
                    "relative_path": resolved.relative_to(self.workspace.root).as_posix(),
                    "project_id": project_id,
                    "referenced": status == "published",
                    "failure_reason": failure_reason,
                    "updated_at": updated_at or datetime.now(tz=UTC),
                }
            )
        )

    def suggested_cleanup(self, *, now: datetime | None = None) -> tuple[UploadReceipt, ...]:
        cutoff = (now or datetime.now(tz=UTC)) - timedelta(days=7)
        return tuple(
            item
            for item in self.list()
            if not item.referenced
            and item.updated_at < cutoff
            and item.status in {"ready", "failed", "cleanup-suggested"}
        )
