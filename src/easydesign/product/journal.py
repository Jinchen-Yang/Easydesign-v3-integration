"""Durable HTTP request identity; scientific jobs remain in the native ledgers."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .artifacts import digest
from .contracts import ProductError


def _enable_wal(db: sqlite3.Connection) -> None:
    """Switch the journal into WAL mode, tolerating the new-file bootstrap race.

    Concurrent first opens all try to flip the fresh database's journal mode
    at once, and SQLite reports that exclusive conversion as "database is
    locked" WITHOUT invoking the busy handler (journal-mode changes never
    do). A bounded retry converges: one peer commits the conversion — WAL is
    a persistent file flag — and every later attempt observes it and becomes
    a no-op. Only lock/busy errors are retried; everything else re-raises.
    """
    for attempt in range(6):
        if str(db.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal":
            return
        try:
            db.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError as error:
            text = str(error).lower()
            if attempt == 5 or ("lock" not in text and "busy" not in text):
                raise
            time.sleep(0.2 * (attempt + 1))
    raise AssertionError("unreachable WAL bootstrap retry loop")


def _schema_is_current(db: sqlite3.Connection) -> bool:
    """Inspect this connection's database without taking SQLite's writer lock."""
    tables = {
        str(row[0])
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('requests','project_labels','product_projects')"
        )
    }
    if tables != {"requests", "project_labels", "product_projects"}:
        return False
    columns = {str(row["name"]) for row in db.execute("PRAGMA table_info(product_projects)")}
    return {"surface", "projection"} <= columns


class RequestJournal:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=15)
        try:
            self.db.row_factory = sqlite3.Row
            _enable_wal(self.db)
            self.db.execute("PRAGMA synchronous=FULL")
            # Reading an initialized journal must not contend with its writer.
            # Check the opened database, not a path cache: a replaced database
            # can still require bootstrap or a legacy schema upgrade.
            if _schema_is_current(self.db):
                return
            # CREATE + the check-then-ALTER upgrade share one write transaction:
            # BEGIN IMMEDIATE serializes concurrent opens across threads and
            # processes (the busy timeout waits for a peer migration to commit,
            # so the re-read table_info observes the peer's columns instead of
            # colliding with a duplicate ALTER). executescript would COMMIT any
            # open transaction before running and break that serialization.
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS requests ("
                "id TEXT PRIMARY KEY, project TEXT NOT NULL, hash TEXT NOT NULL, "
                "payload TEXT NOT NULL, state TEXT NOT NULL, result TEXT, "
                "created REAL NOT NULL, updated REAL NOT NULL)"
            )
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS project_labels "
                "(project TEXT PRIMARY KEY, title TEXT NOT NULL)"
            )
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS product_projects ("
                "id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, title TEXT NOT NULL, "
                "goal TEXT NOT NULL, thread TEXT NOT NULL, input_id TEXT, state TEXT NOT NULL, "
                "detail TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, surface TEXT)"
            )
            columns = {
                str(row["name"]) for row in self.db.execute("PRAGMA table_info(product_projects)")
            }
            if "surface" not in columns:
                self.db.execute("ALTER TABLE product_projects ADD COLUMN surface TEXT")
            if "projection" not in columns:
                self.db.execute("ALTER TABLE product_projects ADD COLUMN projection TEXT")
            self.db.commit()
        except BaseException:
            self.db.close()
            raise

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
        value["projection"] = json.loads(value["projection"]) if value.get("projection") else None
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
                "projection) VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL)",
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
                ),
            )
        saved = self.project(project)
        assert saved is not None
        return saved, True

    def project(self, project: str) -> dict[str, Any] | None:
        return self._project_value(
            self.db.execute("SELECT * FROM product_projects WHERE id=?", (project,)).fetchone()
        )

    def projects(self) -> list[dict[str, Any]]:
        return [
            value
            for row in self.db.execute("SELECT * FROM product_projects ORDER BY updated DESC,id")
            if (value := self._project_value(row)) is not None
        ]

    def update_project(self, project: str, state: str, detail: dict[str, Any]) -> None:
        with self.db:
            changed = self.db.execute(
                "UPDATE product_projects SET state=?,detail=?,updated=?,projection=NULL WHERE id=?",
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
                "UPDATE product_projects SET title=?,updated=?,projection=? WHERE id=?",
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
                "UPDATE product_projects SET projection=? WHERE id=? AND "
                "COALESCE(projection,'')<>?",
                (encoded, project, encoded),
            ).rowcount
            if (
                changed == 0
                and self.db.execute(
                    "SELECT 1 FROM product_projects WHERE id=?", (project,)
                ).fetchone()
                is None
            ):
                raise ProductError("not_found", "Unknown product project", 404)

    def for_project(self, project: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT id FROM requests WHERE project=? ORDER BY created DESC LIMIT ?",
            (project, limit),
        ).fetchall()
        return [value for row in rows if (value := self.get(row[0])) is not None]
