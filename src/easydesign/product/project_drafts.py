"""Versioned collaboration drafts; saving a draft never starts scientific work."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from .contracts import ProductError


class ProjectDrafts:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS drafts (
                id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL,
                state TEXT NOT NULL, created_by TEXT NOT NULL, updated_by TEXT NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                start_request_id TEXT, project_id TEXT
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS draft_revisions (
                draft_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
                actor_id TEXT NOT NULL, created_at REAL NOT NULL,
                PRIMARY KEY(draft_id,revision)
            )""")

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        # Every operation owns one short-lived connection; a leaked handle would
        # eventually hold the write lock and block concurrent team collaboration.
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _value(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        return result

    def list(self) -> list[dict[str, Any]]:
        with self._db() as db:
            return [
                self._value(row)
                for row in db.execute("SELECT * FROM drafts ORDER BY updated_at DESC")
            ]

    def get(self, identity: str) -> dict[str, Any]:
        with self._db() as db:
            row = db.execute("SELECT * FROM drafts WHERE id=?", (identity,)).fetchone()
            if row is None:
                raise ProductError("not_found", "草稿不存在", 404)
            return self._value(row)

    def save(
        self,
        actor_id: str,
        payload: dict[str, Any],
        *,
        identity: str | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        now = time.time()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if identity is None:
                identity = "draft-" + uuid4().hex
                revision = 1
                db.execute(
                    "INSERT INTO drafts VALUES(?,?,?,'draft',?,?,?,?,NULL,NULL)",
                    (identity, revision, json.dumps(payload), actor_id, actor_id, now, now),
                )
            else:
                row = db.execute("SELECT * FROM drafts WHERE id=?", (identity,)).fetchone()
                if row is None:
                    raise ProductError("not_found", "草稿不存在", 404)
                if row["state"] != "draft":
                    raise ProductError("draft_frozen", "草稿已提交，不能覆盖已启动的科学输入", 409)
                if row["revision"] != expected_revision:
                    raise ProductError("stale_draft", "草稿已被其他成员更新，请重新加载", 409)
                revision = int(row["revision"]) + 1
                db.execute(
                    "UPDATE drafts SET revision=?,payload=?,updated_by=?,updated_at=? WHERE id=?",
                    (revision, json.dumps(payload), actor_id, now, identity),
                )
            db.execute(
                "INSERT INTO draft_revisions VALUES(?,?,?,?,?)",
                (identity, revision, json.dumps(payload), actor_id, now),
            )
        return self.get(identity)

    def claim(self, identity: str, revision: int, request_id: str) -> dict[str, Any]:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM drafts WHERE id=?", (identity,)).fetchone()
            if row is None:
                raise ProductError("not_found", "草稿不存在", 404)
            if row["revision"] != revision:
                raise ProductError("stale_draft", "启动前草稿已更新，请重新审阅", 409)
            if row["state"] != "draft":
                if row["start_request_id"] == request_id:
                    return self._value(row)
                raise ProductError("draft_already_started", "草稿已由另一请求启动", 409)
            db.execute(
                "UPDATE drafts SET state='starting',start_request_id=?,updated_at=? WHERE id=?",
                (request_id, time.time(), identity),
            )
        return self.get(identity)

    def finish_start(self, identity: str, request_id: str, project_id: str | None) -> None:
        with self._db() as db:
            db.execute(
                "UPDATE drafts SET state=?,project_id=?,updated_at=? "
                "WHERE id=? AND start_request_id=?",
                (
                    "started" if project_id else "draft",
                    project_id,
                    time.time(),
                    identity,
                    request_id,
                ),
            )
