"""Human-readable and JSONL audit logs for UI filesystem operations."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from easydesign.workspace_context import WorkspaceContext

from .path_refs import path_ref_for


class UiAuditLogger:
    """Emit portable operation records and current-machine diagnostics."""

    def __init__(self, workspace: WorkspaceContext) -> None:
        self.workspace = workspace
        self.log_root = workspace.runtime_root / "logs"
        self.log_root.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("easydesign.ui.audit")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        if not any(
            bool(getattr(handler, "_easydesign_ui_audit", False))
            for handler in self.logger.handlers
        ):
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(logging.INFO)
            handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            cast(Any, handler)._easydesign_ui_audit = True
            self.logger.addHandler(handler)

    def _jsonl_path(self, now: datetime) -> Path:
        return self.log_root / ("ui-operations-" + now.strftime("%Y%m%d") + ".jsonl")

    def _path_fields(self, prefix: str, path: Path) -> dict[str, str]:
        resolved = self.workspace.assert_write_path(path)
        if prefix:
            return {
                f"{prefix}_path_ref": path_ref_for(self.workspace, resolved),
                f"{prefix}_resolved_path": str(resolved),
            }
        return {
            "path_ref": path_ref_for(self.workspace, resolved),
            "resolved_path": str(resolved),
        }

    @staticmethod
    def _terminal_value(value: Any) -> str:
        if isinstance(value, str) and any(char.isspace() for char in value):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def event(
        self,
        event: str,
        *,
        path: Path | None = None,
        from_path: Path | None = None,
        to_path: Path | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        """Append one audit event and mirror it to the UI server terminal."""

        now = datetime.now(tz=UTC)
        record: dict[str, Any] = {
            "ts": now.isoformat(),
            "event": event,
        }
        for key, value in fields.items():
            if value is not None:
                record[key] = value
        if path is not None:
            record.update(self._path_fields("", path))
        if from_path is not None:
            record.update(self._path_fields("from", from_path))
        if to_path is not None:
            record.update(self._path_fields("to", to_path))

        with self._jsonl_path(now).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

        ordered_keys = (
            "operation_id",
            "project_id",
            "upload_token",
            "filename",
            "size_bytes",
            "sha256",
            "status",
            "path_ref",
            "resolved_path",
            "from_path_ref",
            "from_resolved_path",
            "to_path_ref",
            "to_resolved_path",
            "message",
            "failure_reason",
        )
        pieces = [f"UI-AUDIT event={event}"]
        for key in ordered_keys:
            if key in record:
                pieces.append(f"{key}={self._terminal_value(record[key])}")
        self.logger.info(" ".join(pieces))
        return record
