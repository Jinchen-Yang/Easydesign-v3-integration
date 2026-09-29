"""Durable HTTP request identity; scientific jobs remain in the native ledgers."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .artifacts import digest
from .contracts import ProductError


class RequestJournal:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, project TEXT NOT NULL, "
            "hash TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL, "
            "result TEXT, created REAL NOT NULL, updated REAL NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS project_labels "
            "(project TEXT PRIMARY KEY, title TEXT NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS product_projects ("
            "id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, title TEXT NOT NULL, "
            "goal TEXT NOT NULL, thread TEXT NOT NULL, input_id TEXT, state TEXT NOT NULL, "
            "detail TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, surface TEXT, "
            "target_input TEXT)"
        )
        columns = {
            str(row["name"])
            for row in self.db.execute("PRAGMA table_info(product_projects)")
        }
        if "surface" not in columns:
            self.db.execute("ALTER TABLE product_projects ADD COLUMN surface TEXT")
        if "projection" not in columns:
            self.db.execute("ALTER TABLE product_projects ADD COLUMN projection TEXT")
        if "target_input" not in columns:
            self.db.execute("ALTER TABLE product_projects ADD COLUMN target_input TEXT")
        if "deleted_at" not in columns:
            self.db.execute("ALTER TABLE product_projects ADD COLUMN deleted_at REAL")
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def get(self, request_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        result["result"] = json.loads(result["result"]) if result["result"] else None
        return result

    def reserve(self, project: str, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        request_id = payload["request_id"]
        body_hash = digest({"project": project, "payload": payload})
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            previous = self.get(request_id)
            if previous:
                if previous["hash"] != body_hash:
                    raise ProductError(
                        "idempotency_conflict", "This request identity has a different payload", 409
                    )
                return previous, False
            active = self.db.execute(
                "SELECT id FROM requests WHERE project=? AND state IN ('accepted','running') "
                "AND (json_extract(payload,'$.operation')='conversation')=?",
                (project, payload.get("operation") == "conversation"),
            ).fetchone()
            if active:
                raise ProductError("project_busy", "An accepted action is still active", 409)
            now = time.time()
            self.db.execute(
                "INSERT INTO requests VALUES(?,?,?,?,?,NULL,?,?)",
                (request_id, project, body_hash, json.dumps(payload), "accepted", now, now),
            )
        saved = self.get(request_id)
        assert saved is not None
        return saved, True

    def retry(self, request_id: str) -> bool:
        """Claim a retry atomically within its conversation or scientific lane."""
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.get(request_id)
            if row is None:
                raise ProductError("not_found", "Unknown request", 404)
            conversation = row["payload"].get("operation") == "conversation"
            if row["state"] not in {"interrupted", "failed"}:
                return False
            active = self.db.execute(
                "SELECT id FROM requests WHERE project=? AND id<>? "
                "AND state IN ('accepted','running') "
                "AND (json_extract(payload,'$.operation')='conversation')=?",
                (row["project"], request_id, conversation),
            ).fetchone()
            if active:
                raise ProductError("project_busy", "An accepted action is still active", 409)
            self.db.execute(
                "UPDATE requests SET state='accepted',result=?,updated=? WHERE id=?",
                (json.dumps({"recovery": True}), time.time(), request_id),
            )
            return True

    def update(self, request_id: str, state: str, result: dict[str, Any]) -> None:
        with self.db:
            self.db.execute(
                "UPDATE requests SET state=?,result=?,updated=? WHERE id=?",
                (state, json.dumps(result), time.time(), request_id),
            )

    @staticmethod
    def _project_value(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = dict(row)
        value["detail"] = json.loads(value["detail"])
        value["projection"] = (
            json.loads(value["projection"]) if value.get("projection") else None
        )
        value["target_input"] = (
            json.loads(value["target_input"]) if value.get("target_input") else None
        )
        return value

    def register_project(
        self,
        project: str,
        *,
        request_id: str,
        title: str,
        goal: str,
        thread: str,
        input_id: str | None,
        surface: str | None,
        target_input: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], bool]:
        """Persist product identity before a scientific target/config exists."""
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            previous = self._project_value(
                self.db.execute(
                    "SELECT * FROM product_projects WHERE id=? OR request_id=?",
                    (project, request_id),
                ).fetchone()
            )
            expected = {
                "id": project,
                "request_id": request_id,
                "title": title,
                "goal": goal,
                "thread": thread,
                "input_id": input_id,
                "surface": surface,
                "target_input": target_input,
            }
            if previous is not None:
                if any(previous[key] != value for key, value in expected.items()):
                    raise ProductError(
                        "idempotency_conflict",
                        "This project identity is already bound to different bootstrap input",
                        409,
                    )
                return previous, False
            now = time.time()
            self.db.execute(
                "INSERT INTO product_projects("
                "id,request_id,title,goal,thread,input_id,state,detail,created,updated,surface,"
                "projection,target_input) VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
                (
                    project,
                    request_id,
                    title,
                    goal,
                    thread,
                    input_id,
                    "project_created",
                    "{}",
                    now,
                    now,
                    surface,
                    json.dumps(target_input) if target_input is not None else None,
                ),
            )
        saved = self.project(project)
        assert saved is not None
        return saved, True

    def project(
        self, project: str, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        suffix = "" if include_deleted else " AND deleted_at IS NULL"
        return self._project_value(
            self.db.execute(
                "SELECT * FROM product_projects WHERE id=?" + suffix, (project,)
            ).fetchone()
        )

    def projects(self) -> list[dict[str, Any]]:
        return [
            value
            for row in self.db.execute(
                "SELECT * FROM product_projects WHERE deleted_at IS NULL "
                "ORDER BY updated DESC,id"
            )
            if (value := self._project_value(row)) is not None
        ]

    def delete_easy_project(self, project: str) -> dict[str, Any]:
        """Hide an idle Easy project while retaining its scientific workspace."""
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self._project_value(
                self.db.execute(
                    "SELECT * FROM product_projects WHERE id=? AND deleted_at IS NULL",
                    (project,),
                ).fetchone()
            )
            if row is None or row.get("surface") != "easy":
                raise ProductError("not_found", "Unknown Easy project", 404)
            active = self.db.execute(
                "SELECT 1 FROM requests WHERE project=? AND state IN ('accepted','running')",
                (project,),
            ).fetchone()
            projection = row.get("projection")
            if active or (
                isinstance(projection, dict)
                and projection.get("status") in {"running", "incomplete"}
            ):
                raise ProductError(
                    "project_busy", "A running design cannot be deleted", 409
                )
            deleted_at = time.time()
            self.db.execute(
                "UPDATE product_projects SET deleted_at=?,updated=? WHERE id=?",
                (deleted_at, deleted_at, project),
            )
        return {"id": project, "deleted": True, "recoverable": True}

    def update_project(self, project: str, state: str, detail: dict[str, Any]) -> None:
        with self.db:
            changed = self.db.execute(
                "UPDATE product_projects SET state=?,detail=?,updated=?,projection=NULL "
                "WHERE id=? AND deleted_at IS NULL",
                (state, json.dumps(detail), time.time(), project),
            ).rowcount
        if changed != 1:
            raise ProductError("not_found", "Unknown product project", 404)

    def rename_project(self, project: str, title: str) -> None:
        with self.db:
            row = self.db.execute(
                "SELECT projection FROM product_projects WHERE id=?", (project,)
            ).fetchone()
            projection = json.loads(row[0]) if row and row[0] else None
            if isinstance(projection, dict):
                projection["title"] = title
            changed = self.db.execute(
                "UPDATE product_projects SET title=?,updated=?,projection=? "
                "WHERE id=? AND deleted_at IS NULL",
                (
                    title,
                    time.time(),
                    json.dumps(projection) if projection is not None else None,
                    project,
                ),
            ).rowcount
        if changed != 1:
            raise ProductError("not_found", "Unknown product project", 404)

    def update_projection(self, project: str, projection: dict[str, Any]) -> None:
        """Persist the small product-list view, never the scientific workspace."""
        encoded = json.dumps(projection, separators=(",", ":"), ensure_ascii=False)
        with self.db:
            changed = self.db.execute(
                "UPDATE product_projects SET projection=?,updated=? "
                "WHERE id=? AND deleted_at IS NULL AND "
                "COALESCE(projection,'')<>?",
                (encoded, time.time(), project, encoded),
            ).rowcount
            if changed == 0 and self.db.execute(
                "SELECT 1 FROM product_projects WHERE id=? AND deleted_at IS NULL", (project,)
            ).fetchone() is None:
                raise ProductError("not_found", "Unknown product project", 404)

    def for_project(self, project: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT id FROM requests WHERE project=? ORDER BY created DESC LIMIT ?",
            (project, limit),
        ).fetchall()
        return [value for row in rows if (value := self.get(row[0])) is not None]
