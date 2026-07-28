"""本地产品会话存储；科学事实仍由 run manifests 提供。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from easydesign.core import ConfigurationError, dump_model
from easydesign.core.hashing import sha256_file
from easydesign.orchestration.task_tracking import (
    atomic_dump_runtime_model,
    load_latest_runtime_model,
)

from .models import DesignConfigRevision, DesignSession


class DesignSessionStore:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _session_root(self, session_id: str) -> Path:
        if not session_id.startswith("session-") or "/" in session_id or "\\" in session_id:
            raise ConfigurationError("无效的产品会话编号")
        return self.root / session_id

    def _path(self, session_id: str) -> Path:
        return self._session_root(session_id) / "session.json"

    def create(
        self,
        *,
        project_id: str,
        design_mode: str,
        execution_mode: str,
        created_at: datetime | None = None,
    ) -> DesignSession:
        if design_mode not in {"full-workflow", "stepwise", "developer-smoke"}:
            raise ConfigurationError("无效的产品设计模式")
        if execution_mode not in {"unattended", "review-gated"}:
            raise ConfigurationError("无效的产品运行方式")
        now = created_at or datetime.now(tz=UTC)
        session = DesignSession(
            session_id=f"session-{uuid4().hex[:16]}",
            project_id=project_id,
            design_mode=cast(
                Literal["full-workflow", "stepwise", "developer-smoke"],
                design_mode,
            ),
            execution_mode=cast(
                Literal["unattended", "review-gated"],
                execution_mode,
            ),
            created_at=now,
            updated_at=now,
        )
        root = self._session_root(session.session_id)
        root.mkdir()
        dump_model(session, root / "session.json")
        return session

    def load(self, session_id: str) -> DesignSession:
        path = self._path(session_id)
        if not path.is_file():
            raise ConfigurationError(f"产品会话不存在: {session_id}")
        return load_latest_runtime_model(path, DesignSession)

    def list(self) -> tuple[DesignSession, ...]:
        sessions = (
            load_latest_runtime_model(path, DesignSession)
            for path in self.root.glob("session-*/session.json")
        )
        return tuple(sorted(sessions, key=lambda item: item.updated_at, reverse=True))

    def _replace(self, value: DesignSession) -> None:
        path = self._path(value.session_id)
        atomic_dump_runtime_model(value, path)

    def add_config_revision(
        self,
        session_id: str,
        *,
        stage_number: int,
        config_path: Path,
        updated_at: datetime | None = None,
    ) -> DesignSession:
        current = self.load(session_id)
        revision = len(current.config_revisions) + 1
        directory = self._session_root(session_id) / "config-revisions"
        directory.mkdir(exist_ok=True)
        destination = directory / f"stage{stage_number:02d}-rev{revision:04d}.yaml"
        if destination.exists():
            raise ConfigurationError(f"产品配置 revision 已存在: {destination.name}")
        destination.write_bytes(config_path.read_bytes())
        record = DesignConfigRevision(
            revision=revision,
            stage_number=stage_number,
            relative_path=destination.relative_to(self._session_root(session_id)).as_posix(),
            sha256=sha256_file(destination),
            created_at=updated_at or datetime.now(tz=UTC),
        )
        next_value = current.model_copy(
            update={
                "current_stage": stage_number,
                "config_revisions": current.config_revisions + (record,),
                "updated_at": record.created_at,
            }
        )
        self._replace(next_value)
        return next_value

    def attach_run(
        self,
        session_id: str,
        *,
        run_key: str,
        status: str,
        stage_number: int,
        updated_at: datetime | None = None,
    ) -> DesignSession:
        current = self.load(session_id)
        now = updated_at or datetime.now(tz=UTC)
        lineage = (
            current.run_lineage
            if run_key in current.run_lineage
            else current.run_lineage + (run_key,)
        )
        next_value = current.model_copy(
            update={
                "current_stage": stage_number,
                "status": status,
                "run_lineage": lineage,
                "updated_at": now,
            }
        )
        self._replace(next_value)
        return next_value

    def update_status(
        self,
        session_id: str,
        *,
        status: str,
        current_stage: int | None = None,
        updated_at: datetime | None = None,
    ) -> DesignSession:
        current = self.load(session_id)
        now = updated_at or datetime.now(tz=UTC)
        updates: dict[str, object] = {"status": status, "updated_at": now}
        if current_stage is not None:
            updates["current_stage"] = current_stage
        next_value = current.model_copy(update=updates)
        self._replace(next_value)
        return next_value
