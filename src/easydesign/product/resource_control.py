"""Atomic per-person and per-team product admission, distinct from scientific state."""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from .accounts import AccountStore, AccountUser, ResourceLimits, ScopeAccess
from .artifacts import digest
from .contracts import ProductError

ACTIVE_ADMISSIONS = ("reserved", "queued", "starting", "running", "held")


class Admission(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    scope_id: str
    request_id: str
    actor_id: str
    scientific_actor_id: str
    kind: Literal["scientific", "conversation"]
    state: str
    gpu_slots: int
    max_candidates: int
    devices: tuple[int, ...] = ()
    worker_pid: int | None = None
    worker_start: str | None = None
    created_at: float
    updated_at: float
    reason: str | None = None


def _admission(row: sqlite3.Row) -> Admission:
    value = dict(row)
    value["devices"] = tuple(json.loads(value.pop("devices_json")))
    return Admission.model_validate(value)


class ResourceLedger:
    """Reserve quotas before native side effects; retries cannot multiply admissions."""

    def __init__(self, accounts: AccountStore) -> None:
        self.accounts = accounts
        with accounts.db(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS compute_commands (
                scope_id TEXT NOT NULL, request_id TEXT NOT NULL, actor_id TEXT NOT NULL,
                kind TEXT NOT NULL, payload_hash TEXT NOT NULL, created_at REAL NOT NULL,
                PRIMARY KEY(scope_id,request_id)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS admissions (
                id TEXT PRIMARY KEY, scope_id TEXT NOT NULL, request_id TEXT NOT NULL,
                actor_id TEXT NOT NULL, scientific_actor_id TEXT NOT NULL, kind TEXT NOT NULL,
                state TEXT NOT NULL, gpu_slots INTEGER NOT NULL, max_candidates INTEGER NOT NULL,
                devices_json TEXT NOT NULL, worker_pid INTEGER, worker_start TEXT,
                created_at REAL NOT NULL, updated_at REAL NOT NULL, reason TEXT,
                FOREIGN KEY(scope_id,request_id) REFERENCES compute_commands(scope_id,request_id)
            )""")
            db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS one_active_admission
                ON admissions(scope_id,request_id)
                WHERE state IN ('reserved','queued','starting','running','held')""")
            db.execute("""CREATE TABLE IF NOT EXISTS upload_reservations (
                id TEXT PRIMARY KEY, scope_id TEXT NOT NULL, resource_key TEXT NOT NULL,
                actor_id TEXT NOT NULL, size_bytes INTEGER NOT NULL, state TEXT NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                UNIQUE(scope_id,resource_key)
            )""")

    def _limits(self, db: sqlite3.Connection, subject: str) -> ResourceLimits:
        row = db.execute(
            "SELECT limits_json FROM resource_limits WHERE subject_id=?", (subject,)
        ).fetchone()
        if row is None:
            raise ProductError("quota_unconfigured", "资源额度尚未配置", 409)
        return ResourceLimits.model_validate_json(row[0])

    def _subjects(self, actor: AccountUser, scope: ScopeAccess) -> tuple[str, ...]:
        return (actor.id,) if scope.kind == "personal" else (actor.id, scope.id)

    def reserve(
        self,
        actor: AccountUser,
        scope_id: str,
        request_id: str,
        payload: dict[str, Any],
        *,
        kind: Literal["scientific", "conversation"] = "scientific",
        gpu_slots: int = 1,
        retry: bool = False,
    ) -> tuple[Admission, bool]:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{16,96}", request_id):
            raise ProductError("invalid_request_id", "请求编号不合法", 400)
        if kind not in {"scientific", "conversation"} or gpu_slots < 0 or gpu_slots > 64:
            raise ProductError("invalid_resource_request", "资源请求不合法", 400)
        gpu_slots = gpu_slots if kind == "scientific" else 0
        if kind == "scientific" and gpu_slots < 1:
            raise ProductError("invalid_resource_request", "科学计算需要至少一个 GPU 槽位", 400)
        fingerprint = digest({"kind": kind, "gpu_slots": gpu_slots, "payload": payload})
        with self.accounts.db(write=True) as db:
            user = self.accounts.live_user(db, actor)
            scope = self.accounts.scope_in(
                db, user, scope_id, execute=kind == "scientific", edit=True
            )
            previous = db.execute(
                "SELECT * FROM compute_commands WHERE scope_id=? AND request_id=?",
                (scope_id, request_id),
            ).fetchone()
            if previous is not None:
                if previous["payload_hash"] != fingerprint or previous["kind"] != kind:
                    raise ProductError("idempotency_conflict", "请求编号已绑定其他操作", 409)
                if not retry and previous["actor_id"] != user.id:
                    raise ProductError("idempotency_conflict", "请求编号已绑定其他操作人", 409)
                row = db.execute(
                    "SELECT * FROM admissions WHERE scope_id=? AND request_id=? "
                    "ORDER BY created_at DESC,rowid DESC LIMIT 1",
                    (scope_id, request_id),
                ).fetchone()
                if row is not None and (row["state"] in ACTIVE_ADMISSIONS or not retry):
                    return _admission(row), False
            limits = [self._limits(db, subject) for subject in self._subjects(user, scope)]
            for subject, limit in zip(self._subjects(user, scope), limits, strict=True):
                field = "actor_id" if subject == user.id else "scope_id"
                usage = db.execute(
                    "SELECT count(*) AS jobs,COALESCE(SUM(gpu_slots),0) AS gpus "
                    f"FROM admissions WHERE {field}=? AND kind=? "
                    "AND state IN ('reserved','queued','starting','running','held')",
                    (subject, kind),
                ).fetchone()
                assert usage is not None
                allowed_jobs = (
                    limit.max_active_jobs if kind == "scientific" else limit.max_active_chats
                )
                if (
                    usage["jobs"] >= allowed_jobs
                    or usage["gpus"] + gpu_slots > limit.max_gpu_devices
                ):
                    raise ProductError(
                        "quota_exceeded", "个人或团队并发/算力额度不足，请等待或联系管理员", 409
                    )
            now = self.accounts.clock()
            if previous is None:
                db.execute(
                    "INSERT INTO compute_commands VALUES(?,?,?,?,?,?)",
                    (scope_id, request_id, user.id, kind, fingerprint, now),
                )
            grant_id = "grant-" + uuid4().hex
            scientific_actor = previous["actor_id"] if previous is not None else user.id
            db.execute(
                "INSERT INTO admissions VALUES(?,?,?,?,?,?,'reserved',?,?,?,NULL,NULL,?,?,NULL)",
                (
                    grant_id,
                    scope_id,
                    request_id,
                    user.id,
                    scientific_actor,
                    kind,
                    gpu_slots,
                    min(limit.max_candidates_per_job for limit in limits),
                    "[]",
                    now,
                    now,
                ),
            )
            self.accounts.audit_record(
                db,
                user.id,
                "resource.reserve",
                scope=scope_id,
                target=grant_id,
                details={"kind": kind, "gpu_slots": gpu_slots, "retry": retry},
            )
            row = db.execute("SELECT * FROM admissions WHERE id=?", (grant_id,)).fetchone()
            assert row is not None
            return _admission(row), True

    def get(self, grant_id: str) -> Admission:
        with self.accounts.db() as db:
            row = db.execute("SELECT * FROM admissions WHERE id=?", (grant_id,)).fetchone()
            if row is None:
                raise ProductError("not_found", "资源请求不存在", 404)
            return _admission(row)

    def command(self, scope_id: str, request_id: str) -> dict[str, Any] | None:
        with self.accounts.db() as db:
            row = db.execute(
                "SELECT * FROM compute_commands WHERE scope_id=? AND request_id=?",
                (scope_id, request_id),
            ).fetchone()
            return None if row is None else dict(row)

    def latest(self, scope_id: str, request_id: str) -> Admission | None:
        with self.accounts.db() as db:
            row = db.execute(
                "SELECT * FROM admissions WHERE scope_id=? AND request_id=? "
                "ORDER BY created_at DESC,rowid DESC LIMIT 1",
                (scope_id, request_id),
            ).fetchone()
            return None if row is None else _admission(row)

    def active(self) -> list[Admission]:
        with self.accounts.db() as db:
            return [
                _admission(row)
                for row in db.execute(
                    "SELECT * FROM admissions "
                    "WHERE state IN ('reserved','queued','starting','running','held') "
                    "ORDER BY created_at,rowid"
                )
            ]

    def transition(
        self,
        grant_id: str,
        state: str,
        *,
        devices: tuple[int, ...] | None = None,
        worker_pid: int | None = None,
        worker_start: str | None = None,
        reason: str | None = None,
    ) -> Admission:
        if state not in {*ACTIVE_ADMISSIONS, "released", "failed", "cancelled"}:
            raise ValueError("Invalid admission state")
        with self.accounts.db(write=True) as db:
            row = db.execute("SELECT * FROM admissions WHERE id=?", (grant_id,)).fetchone()
            if row is None:
                raise ProductError("not_found", "资源请求不存在", 404)
            if row["state"] not in ACTIVE_ADMISSIONS:
                if state == row["state"]:
                    return _admission(row)
                raise ProductError("admission_terminal", "终态资源记录不可重开", 409)
            assigned = tuple(json.loads(row["devices_json"])) if devices is None else devices
            if (
                len(set(assigned)) != len(assigned)
                or any(d < 0 for d in assigned)
                or len(assigned) > row["gpu_slots"]
            ):
                raise ProductError("invalid_allocation", "显卡分配超出获批额度", 409)
            db.execute(
                "UPDATE admissions SET state=?,devices_json=?,worker_pid=?,worker_start=?,"
                "updated_at=?,reason=? WHERE id=?",
                (
                    state,
                    json.dumps(assigned),
                    worker_pid if worker_pid is not None else row["worker_pid"],
                    worker_start if worker_start is not None else row["worker_start"],
                    self.accounts.clock(),
                    reason,
                    grant_id,
                ),
            )
            if state in {"released", "failed", "cancelled"}:
                self.accounts.audit_record(
                    db, row["actor_id"], "resource." + state, scope=row["scope_id"], target=grant_id
                )
            changed = db.execute("SELECT * FROM admissions WHERE id=?", (grant_id,)).fetchone()
            assert changed is not None
            return _admission(changed)

    def reserve_upload(
        self, actor: AccountUser, scope_id: str, resource_key: str, size_bytes: int
    ) -> tuple[str, bool]:
        if size_bytes <= 0 or not re.fullmatch(r"[0-9a-f]{64}", resource_key):
            raise ProductError("invalid_upload", "上传大小或身份无效", 400)
        with self.accounts.db(write=True) as db:
            user = self.accounts.live_user(db, actor)
            scope = self.accounts.scope_in(db, user, scope_id, edit=True)
            row = db.execute(
                "SELECT * FROM upload_reservations WHERE scope_id=? AND resource_key=?",
                (scope_id, resource_key),
            ).fetchone()
            if row is not None:
                if row["size_bytes"] != size_bytes:
                    raise ProductError("idempotency_conflict", "上传身份已绑定不同大小", 409)
                return row["id"], False
            for subject in self._subjects(user, scope):
                limit = self._limits(db, subject)
                field = "actor_id" if subject == user.id else "scope_id"
                used = db.execute(
                    f"SELECT COALESCE(SUM(size_bytes),0) FROM upload_reservations WHERE {field}=?",
                    (subject,),
                ).fetchone()[0]
                if (
                    size_bytes > limit.max_upload_bytes
                    or used + size_bytes > limit.max_stored_upload_bytes
                ):
                    raise ProductError("upload_quota_exceeded", "个人或团队上传额度不足", 413)
            identity, now = "upload-" + uuid4().hex, self.accounts.clock()
            db.execute(
                "INSERT INTO upload_reservations VALUES(?,?,?,?,?,'reserved',?,?)",
                (identity, scope_id, resource_key, user.id, size_bytes, now, now),
            )
            self.accounts.audit_record(
                db,
                user.id,
                "upload.reserve",
                scope=scope_id,
                target=identity,
                details={"size_bytes": size_bytes},
            )
            return identity, True

    def finish_upload(self, reservation_id: str, *, published: bool) -> None:
        # Failed bytes remain charged until an explicit, verified maintenance action;
        # an exception must never turn partially retained data into free storage.
        with self.accounts.db(write=True) as db:
            db.execute(
                "UPDATE upload_reservations SET state=?,updated_at=? "
                "WHERE id=? AND state='reserved'",
                ("published" if published else "retained", self.accounts.clock(), reservation_id),
            )

    def usage(self, actor: AccountUser, scope_id: str | None = None) -> dict[str, Any]:
        with self.accounts.db() as db:
            user = self.accounts.live_user(db, actor)
            scope = self.accounts.scope_in(db, user, scope_id)
            field, subject = (
                ("actor_id", user.id) if scope.kind == "personal" else ("scope_id", scope.id)
            )
            if scope.role == "observer":
                field, subject = "scope_id", scope.id
            grants = [
                _admission(row).model_dump(mode="json")
                for row in db.execute(
                    f"SELECT * FROM admissions WHERE {field}=? "
                    "ORDER BY created_at DESC,rowid DESC LIMIT 100",
                    (subject,),
                )
            ]
            used = db.execute(
                f"SELECT COALESCE(SUM(size_bytes),0) FROM upload_reservations WHERE {field}=?",
                (subject,),
            ).fetchone()[0]
            return {
                "scope": scope.model_dump(),
                "limits": self._limits(db, scope.id).model_dump(),
                "stored_upload_bytes": used,
                "admissions": grants,
            }

    def all_admissions(self, actor: AccountUser, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.accounts.db() as db:
            admin = self.accounts.require_admin(db, actor)
            rows = [
                _admission(row).model_dump(mode="json")
                for row in db.execute(
                    "SELECT * FROM admissions ORDER BY created_at DESC,rowid DESC LIMIT ?",
                    (min(max(limit, 1), 200),),
                )
            ]
            # Site-wide resource inspection by administration is audited.
            self.accounts.audit_record(db, admin.id, "admin.admissions.read")
            return rows
