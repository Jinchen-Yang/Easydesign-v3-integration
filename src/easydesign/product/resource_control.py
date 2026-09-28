"""Atomic per-person and per-team product admission, distinct from scientific state."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from .accounts import AccountStore, AccountUser, ResourceLimits, ScopeAccess
from .artifacts import digest
from .contracts import ProductError

ACTIVE_ADMISSIONS = ("reserved", "queued", "starting", "running", "held")
DispatchChannel = Literal["legacy", "scoped_worker", "web_stream"]


def _web_process_record(pid: int) -> tuple[str, str]:
    parts = Path(f"/proc/{pid}/stat").read_text().rpartition(") ")[2].split()
    if len(parts) < 20 or not parts[19].isdigit():
        raise ValueError("Unverifiable Web process identity")
    return parts[0], parts[19]


def contract_digest(document: Any) -> str | None:
    """Canonical digest of a persisted native contract document, if readable.

    Mirrors ``canonical_model_sha256`` over the already-serialized
    ``model_dump(mode="json")`` payload so published checksums can be verified
    without importing scientific model classes into the controller.
    """
    if not isinstance(document, dict):
        return None
    try:
        text = json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


FINAL_DESIGN_RULE = (
    "Per-person cumulative final-design allowance. The unit is one candidate of "
    "a Gate-4 approved production Scale campaign's verified durable population: "
    "the published, checksum-verified global candidate pool when review inputs "
    "are published, and otherwise the checksum-bound batch receipts of the "
    "campaign — in full once the campaign is complete with verified native "
    "evidence (an all-FAIL population counts as delivered negative results), "
    "or at its verified retained size when a newer promotion provably "
    "supersedes a campaign whose evidence is determined. Receipt settlement "
    "verifies every retained candidate's artifacts against its declared source "
    "run; missing or corrupted evidence holds. Pilot pools never count; Gate-5 "
    "panel revisions never add final designs. Technically invalid, unevaluated "
    "or evidence-unknown outcomes, and operationally incomplete or inconclusive "
    "campaigns, hold as recoverable — an inconclusive event is never "
    "no-delivery proof, and supersession never turns unknown results into "
    "verified designs. Release happens only for an authority that never "
    "registered a campaign and was superseded, or an approval that was provably "
    "never applied. Allowance changes affect future reservations only and never "
    "rewrite frozen plans or consumed totals."
)


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
    dispatch_channel: DispatchChannel = "legacy"
    auth_version: int | None = None


def _admission(row: sqlite3.Row) -> Admission:
    value = dict(row)
    value["devices"] = tuple(json.loads(value.pop("devices_json")))
    return Admission.model_validate(value)


class ResourceLedger:
    """Reserve quotas before native side effects; retries cannot multiply admissions."""

    def __init__(self, accounts: AccountStore, *, max_active_admissions: int = 300) -> None:
        if type(max_active_admissions) is not int or not 1 <= max_active_admissions <= 10000:
            raise ValueError("max_active_admissions must be between 1 and 10000")
        self.accounts = accounts
        self.max_active_admissions = max_active_admissions
        with accounts.db(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS compute_commands (
                scope_id TEXT NOT NULL, request_id TEXT NOT NULL, actor_id TEXT NOT NULL,
                kind TEXT NOT NULL, payload_hash TEXT NOT NULL, created_at REAL NOT NULL,
                PRIMARY KEY(scope_id,request_id)
            )""")
            # Pre-quota databases keep their rows; the nullable capture column is
            # added in place so stage budgets stay exactly-once per command.
            command_columns = {
                str(row[1]) for row in db.execute("PRAGMA table_info(compute_commands)")
            }
            if "budgets_json" not in command_columns:
                db.execute("ALTER TABLE compute_commands ADD COLUMN budgets_json TEXT")
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
            admission_columns = {str(row[1]) for row in db.execute("PRAGMA table_info(admissions)")}
            if "dispatch_channel" not in admission_columns:
                db.execute(
                    "ALTER TABLE admissions ADD COLUMN dispatch_channel TEXT NOT NULL "
                    "DEFAULT 'legacy'"
                )
            if "auth_version" not in admission_columns:
                db.execute("ALTER TABLE admissions ADD COLUMN auth_version INTEGER")
            db.execute("""CREATE TABLE IF NOT EXISTS upload_reservations (
                id TEXT PRIMARY KEY, scope_id TEXT NOT NULL, resource_key TEXT NOT NULL,
                actor_id TEXT NOT NULL, size_bytes INTEGER NOT NULL, state TEXT NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                UNIQUE(scope_id,resource_key)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS final_design_reservations (
                id TEXT PRIMARY KEY, scope_id TEXT NOT NULL, project_id TEXT NOT NULL,
                request_id TEXT NOT NULL, authority_key TEXT NOT NULL,
                subject_id TEXT NOT NULL, amount INTEGER NOT NULL, delivered INTEGER,
                state TEXT NOT NULL
                    CHECK(state IN ('reserved','settled','released')),
                campaign_sha256 TEXT, reason TEXT,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                UNIQUE(scope_id,project_id,authority_key)
            )""")
            db.execute("""CREATE INDEX IF NOT EXISTS final_designs_subject
                ON final_design_reservations(subject_id)""")
            db.execute("""CREATE INDEX IF NOT EXISTS final_designs_project
                ON final_design_reservations(scope_id,project_id)""")

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
        stage_budgets: dict[str, int | None] | None = None,
        dispatch_channel: DispatchChannel = "legacy",
    ) -> tuple[Admission, bool]:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{16,96}", request_id):
            raise ProductError("invalid_request_id", "请求编号不合法", 400)
        if kind not in {"scientific", "conversation"} or gpu_slots < 0 or gpu_slots > 64:
            raise ProductError("invalid_resource_request", "资源请求不合法", 400)
        if dispatch_channel not in {"legacy", "scoped_worker", "web_stream"}:
            raise ValueError("Invalid dispatch channel")
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
            active = db.execute(
                "SELECT count(*) FROM admissions "
                "WHERE state IN ('reserved','queued','starting','running','held') "
                "AND dispatch_channel!='web_stream'"
            ).fetchone()[0]
            if dispatch_channel != "web_stream" and active >= self.max_active_admissions:
                raise ProductError("queue_full", "当前等待队列已满，请稍后再试", 429)
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
                    "INSERT INTO compute_commands(scope_id,request_id,actor_id,kind,"
                    "payload_hash,created_at,budgets_json) VALUES(?,?,?,?,?,?,?)",
                    (
                        scope_id,
                        request_id,
                        user.id,
                        kind,
                        fingerprint,
                        now,
                        json.dumps(stage_budgets) if stage_budgets is not None else None,
                    ),
                )
            grant_id = "grant-" + uuid4().hex
            scientific_actor = previous["actor_id"] if previous is not None else user.id
            owner_pid, owner_start = None, None
            if dispatch_channel == "web_stream":
                # Persist ownership in the admission transaction itself: a crash
                # before the HTTP handler publishes 'running' must not strand quota.
                owner_pid = os.getpid()
                try:
                    _, owner_start = _web_process_record(owner_pid)
                except (OSError, ValueError) as error:
                    raise ProductError(
                        "web_owner_unavailable", "无法确认对话服务进程身份", 503
                    ) from error
            db.execute(
                "INSERT INTO admissions(id,scope_id,request_id,actor_id,scientific_actor_id,"
                "kind,state,gpu_slots,max_candidates,devices_json,worker_pid,worker_start,"
                "created_at,updated_at,reason,dispatch_channel,auth_version) "
                "VALUES(?,?,?,?,?,?,'reserved',?,?,?,?,?,?,?,NULL,?,?)",
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
                    owner_pid,
                    owner_start,
                    now,
                    now,
                    dispatch_channel,
                    db.execute("SELECT auth_version FROM users WHERE id=?", (user.id,)).fetchone()[
                        0
                    ],
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

    def reconcile_web_stream_owner(self, grant_id: str) -> Admission:
        """Release only a provably lost local owner; never dispatch or kill a stream."""
        admission = self.get(grant_id)
        if admission.dispatch_channel != "web_stream" or admission.state not in ACTIVE_ADMISSIONS:
            return admission
        if admission.worker_pid is None or admission.worker_start is None:
            # Historical ownerless rows have no safe death proof. They remain
            # visible for operator reconciliation, never expired by a timer.
            return admission
        try:
            state, identity = _web_process_record(admission.worker_pid)
            lost = state in {"Z", "X"} or identity != admission.worker_start
        except FileNotFoundError:
            # Distinguish a missing owner from an unavailable proc filesystem.
            try:
                _web_process_record(os.getpid())
            except (OSError, ValueError):
                return admission
            lost = True
        except (OSError, ValueError):
            return admission
        if not lost:
            return admission
        with self.accounts.db(write=True) as db:
            row = db.execute("SELECT * FROM admissions WHERE id=?", (grant_id,)).fetchone()
            assert row is not None
            current = _admission(row)
            if (
                current.dispatch_channel != "web_stream"
                or current.state not in ACTIVE_ADMISSIONS
                or (current.worker_pid, current.worker_start)
                != (admission.worker_pid, admission.worker_start)
            ):
                return current
            db.execute(
                "UPDATE admissions SET state='failed',reason='web_owner_lost',updated_at=? "
                "WHERE id=?",
                (self.accounts.clock(), grant_id),
            )
            self.accounts.audit_record(
                db,
                current.actor_id,
                "resource.failed",
                scope=current.scope_id,
                target=grant_id,
                details={"reason": "web_owner_lost", "dispatch_channel": "web_stream"},
            )
            row = db.execute("SELECT * FROM admissions WHERE id=?", (grant_id,)).fetchone()
            assert row is not None
            return _admission(row)

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

    def queue_position(self, admission_id: str) -> int | None:
        """Project only the rank, with membership and ordering from one read snapshot."""
        with self.accounts.db() as db:
            row = db.execute(
                "SELECT (SELECT COUNT(*)+1 FROM admissions AS waiting "
                "WHERE waiting.state='queued' AND waiting.kind=target.kind "
                # Match the existing partial-index predicate so retained terminal
                # history does not participate in the rank scan.
                "AND waiting.state IN ('reserved','queued','starting','running','held') "
                "AND (waiting.created_at<target.created_at OR "
                "(waiting.created_at=target.created_at AND waiting.rowid<target.rowid))) "
                "FROM admissions AS target WHERE target.id=? AND target.state='queued'",
                (admission_id,),
            ).fetchone()
            return None if row is None else int(row[0])

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

    def cancel_queued(self, actor: AccountUser, scope_id: str, request_id: str) -> Admission:
        """Cancel only unclaimed work; dispatch competes in this same SQLite transaction."""
        with self.accounts.db(write=True) as db:
            user = self.accounts.live_user(db, actor)
            self.accounts.scope_in(db, user, scope_id, edit=True)
            row = db.execute(
                "SELECT * FROM admissions WHERE scope_id=? AND request_id=? "
                "ORDER BY created_at DESC,rowid DESC LIMIT 1",
                (scope_id, request_id),
            ).fetchone()
            if row is None:
                raise ProductError("not_found", "请求不存在", 404)
            if row["actor_id"] != user.id:
                raise ProductError("forbidden", "只能取消本人尚未派发的请求", 403)
            if row["state"] == "cancelled" and row["reason"] == "queue_cancelled":
                return _admission(row)
            if (
                row["dispatch_channel"] != "scoped_worker"
                or row["state"] not in {"reserved", "queued"}
                or row["worker_pid"] is not None
            ):
                raise ProductError("queue_not_cancellable", "该请求已派发，不能从等待队列取消", 409)
            db.execute(
                "UPDATE admissions SET state='cancelled',reason='queue_cancelled',updated_at=? "
                "WHERE id=?",
                (self.accounts.clock(), row["id"]),
            )
            self.accounts.audit_record(
                db, user.id, "resource.cancelled", scope=scope_id, target=row["id"]
            )
            return _admission(
                db.execute("SELECT * FROM admissions WHERE id=?", (row["id"],)).fetchone()
            )

    def claim_start(self, grant_id: str, *, max_conversation_workers: int) -> Admission | None:
        """Atomically exclude cancellation, duplicate dispatch, and excess chat workers."""
        with self.accounts.db(write=True) as db:
            row = db.execute("SELECT * FROM admissions WHERE id=?", (grant_id,)).fetchone()
            if row is None or row["state"] != "queued" or row["worker_pid"] is not None:
                return None
            if row["dispatch_channel"] != "scoped_worker":
                return None
            admission = _admission(row)
            self._authorize_in(db, admission)
            if admission.kind == "conversation":
                busy = db.execute(
                    "SELECT count(*) FROM admissions WHERE kind='conversation' "
                    "AND dispatch_channel!='web_stream' "
                    "AND (state IN ('starting','running','held') "
                    "OR (state='queued' AND worker_pid IS NOT NULL))"
                ).fetchone()[0]
                if busy >= max_conversation_workers:
                    return None
            db.execute(
                "UPDATE admissions SET state='starting',updated_at=?,reason='worker_starting' "
                "WHERE id=?",
                (self.accounts.clock(), grant_id),
            )
            return _admission(
                db.execute("SELECT * FROM admissions WHERE id=?", (grant_id,)).fetchone()
            )

    def _authorize_in(self, db: sqlite3.Connection, admission: Admission) -> None:
        self.accounts.scope_in(
            db,
            self.accounts.user(admission.actor_id),
            admission.scope_id,
            edit=True,
            execute=admission.kind == "scientific",
        )
        epoch = db.execute(
            "SELECT auth_version FROM users WHERE id=?", (admission.actor_id,)
        ).fetchone()[0]
        if admission.auth_version is not None and admission.auth_version != epoch:
            raise ProductError("authorization_revoked", "接单后账户授权已变化，请重新确认请求", 403)

    def authorize_dispatch(self, admission: Admission) -> None:
        with self.accounts.db() as db:
            self._authorize_in(db, admission)

    def start_execution(
        self, grant_id: str, devices: tuple[int, ...], publish: Callable[[], None]
    ) -> None:
        """Assignment publication linearizes against account/team revocation.

        Durable workers wait for the committed running state, so a publication
        followed by transaction rollback is not execution authority.
        """
        with self.accounts.db(write=True) as db:
            row = db.execute("SELECT * FROM admissions WHERE id=?", (grant_id,)).fetchone()
            if row is None or row["state"] != "starting":
                raise ProductError("admission_conflict", "执行请求尚未领取或已结束", 409)
            admission = _admission(row)
            self._authorize_in(db, admission)
            if (
                len(set(devices)) != len(devices)
                or any(d < 0 for d in devices)
                or len(devices) > admission.gpu_slots
            ):
                raise ProductError("invalid_allocation", "显卡分配超出获批额度", 409)
            publish()
            db.execute(
                "UPDATE admissions SET state='running',devices_json=?,updated_at=?,reason=NULL "
                "WHERE id=?",
                (json.dumps(devices), self.accounts.clock(), grant_id),
            )

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
            if scope.kind == "personal":
                reserved_n, delivered_n = self._final_design_spent(db, scope.id)
                allowance = self._limits(db, scope.id).final_designs_allowance
                final_designs: dict[str, Any] = {
                    "kind": "personal",
                    "subject_id": scope.id,
                    "allowance": allowance,
                    "reserved": reserved_n,
                    "delivered": delivered_n,
                    "remaining": (
                        None if allowance is None else allowance - reserved_n - delivered_n
                    ),
                    "rule": FINAL_DESIGN_RULE,
                    "entries": self.final_designs_entries(subject_id=scope.id),
                }
            else:
                totals = db.execute(
                    "SELECT COALESCE(SUM(amount),0) AS reserved,"
                    "COALESCE(SUM(COALESCE(delivered,0)),0) AS delivered "
                    "FROM final_design_reservations WHERE scope_id=? AND state IN "
                    "('reserved','settled')",
                    (scope.id,),
                ).fetchone()
                final_designs = {
                    "kind": "team",
                    "scope_id": scope.id,
                    "reserved": int(totals["reserved"]),
                    "delivered": int(totals["delivered"]),
                    "rule": FINAL_DESIGN_RULE,
                    "entries": self.final_designs_entries(scope_id=scope.id),
                }
            if scope.role == "observer" and user.id != scope.id:
                # Administration inspection of foreign balances is audited.
                with self.accounts.db(write=True) as audit_db:
                    self.accounts.audit_record(
                        audit_db, user.id, "admin.final_designs.read", target=scope.id
                    )
            return {
                "scope": scope.model_dump(),
                "limits": self._limits(db, scope.id).model_dump(),
                "stored_upload_bytes": used,
                "admissions": grants,
                "final_designs": final_designs,
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

    def command_budgets(self, scope_id: str, request_id: str) -> dict[str, int | None] | None:
        """Stage budgets captured exactly once at command authorization."""
        with self.accounts.db() as db:
            row = db.execute(
                "SELECT budgets_json FROM compute_commands WHERE scope_id=? AND request_id=?",
                (scope_id, request_id),
            ).fetchone()
        if row is None or row["budgets_json"] is None:
            return None
        value = json.loads(row["budgets_json"])
        if not isinstance(value, dict):
            return None
        return {
            key: int(item) if isinstance(item, int) else None
            for key, item in value.items()
            if key in {"pilot", "scale"}
        }

    def stage_budgets_for(self, actor: AccountUser, scope_id: str) -> dict[str, int | None]:
        """Workflow stage defaults of the owning scope; None keeps native defaults."""
        with self.accounts.db() as db:
            user = self.accounts.live_user(db, actor)
            scope = self.accounts.scope_in(db, user, scope_id)
            limits = self._limits(db, scope.id)
            return {"pilot": limits.pilot_stage_budget, "scale": limits.scale_stage_budget}

    @staticmethod
    def _final_designs_row(db: sqlite3.Connection, row_id: str) -> sqlite3.Row:
        found: sqlite3.Row | None = db.execute(
            "SELECT * FROM final_design_reservations WHERE id=?", (row_id,)
        ).fetchone()
        if found is None:
            raise ProductError("not_found", "final-design reservation does not exist", 404)
        return found

    def _final_design_spent(self, db: sqlite3.Connection, subject_id: str) -> tuple[int, int]:
        row = db.execute(
            "SELECT COALESCE(SUM(CASE WHEN state='reserved' THEN amount ELSE 0 END),0) "
            "AS reserved,"
            "COALESCE(SUM(CASE WHEN state='settled' "
            "THEN COALESCE(delivered,0) ELSE 0 END),0) AS delivered "
            "FROM final_design_reservations WHERE subject_id=? AND state IN "
            "('reserved','settled')",
            (subject_id,),
        ).fetchone()
        assert row is not None
        return int(row["reserved"]), int(row["delivered"])

    def final_designs_balance(self, subject_id: str) -> dict[str, Any]:
        with self.accounts.db() as db:
            limits_row = db.execute(
                "SELECT limits_json FROM resource_limits WHERE subject_id=?", (subject_id,)
            ).fetchone()
            if limits_row is None:
                raise ProductError("quota_unconfigured", "resource limits unconfigured", 409)
            allowance = ResourceLimits.model_validate_json(limits_row[0]).final_designs_allowance
            reserved, delivered = self._final_design_spent(db, subject_id)
            return {
                "allowance": allowance,
                "reserved": reserved,
                "delivered": delivered,
                "remaining": None if allowance is None else allowance - reserved - delivered,
            }

    def ensure_final_designs(
        self,
        actor: AccountUser,
        scope_id: str,
        project_id: str,
        request_id: str,
        authority_key: str,
        amount: int,
        *,
        subject_id: str,
    ) -> tuple[dict[str, Any], bool]:
        """Idempotently hold the final-design charge for one Gate-4 approval.

        The key is scope-qualified: identical projects and approvals in distinct
        scopes are independent. An existing active row is returned unchanged so
        retries and team-admin recovery can never shift the billed person.
        """
        if not re.fullmatch(r"[0-9a-f]{64}", authority_key or ""):
            raise ProductError("invalid_authority", "Gate-4 approval identity invalid", 400)
        if type(amount) is not int or amount < 1:
            raise ProductError("invalid_final_designs_request", "final-design count invalid", 400)
        if not re.fullmatch(r"user-[0-9a-f]{32}", subject_id or ""):
            raise ProductError("invalid_final_designs_request", "billing person invalid", 400)
        with self.accounts.db(write=True) as db:
            user = self.accounts.live_user(db, actor)
            self.accounts.scope_in(db, user, scope_id, execute=True)
            row = db.execute(
                "SELECT * FROM final_design_reservations "
                "WHERE scope_id=? AND project_id=? AND authority_key=?",
                (scope_id, project_id, authority_key),
            ).fetchone()
            if row is not None:
                if row["state"] in ("reserved", "settled"):
                    return dict(row), False
                if row["reason"] != "approval_not_applied":
                    # Terminal no-delivery/superseded outcome: nothing to recharge.
                    return dict(row), False
            limits_row = db.execute(
                "SELECT limits_json FROM resource_limits WHERE subject_id=?",
                (subject_id,),
            ).fetchone()
            if limits_row is None:
                raise ProductError("quota_unconfigured", "资源额度尚未配置", 409)
            allowance = ResourceLimits.model_validate_json(limits_row[0]).final_designs_allowance
            if allowance is not None:
                reserved, delivered = self._final_design_spent(db, subject_id)
                remaining = allowance - reserved - delivered
                # Only active rows count as spent here; a row being reactivated is
                # released and therefore excluded from the sums above.
                if remaining < amount:
                    raise ProductError(
                        "final_designs_exhausted",
                        "Personal final-design balance insufficient (remaining "
                        f"{max(remaining, 0)} of {allowance}); contact an administrator "
                        "to adjust the allowance",
                        409,
                    )
            now = self.accounts.clock()
            if row is None:
                row_id = "fdr-" + uuid4().hex
                db.execute(
                    "INSERT INTO final_design_reservations VALUES"
                    "(?,?,?,?,?,?,?,NULL,'reserved',NULL,NULL,?,?)",
                    (
                        row_id,
                        scope_id,
                        project_id,
                        request_id,
                        authority_key,
                        subject_id,
                        amount,
                        now,
                        now,
                    ),
                )
                created = True
            else:
                row_id = row["id"]
                db.execute(
                    "UPDATE final_design_reservations SET state='reserved',request_id=?,"
                    "subject_id=?,amount=?,reason=NULL,updated_at=? WHERE id=?",
                    (request_id, subject_id, amount, now, row_id),
                )
                created = True
            self.accounts.audit_record(
                db,
                user.id,
                "final_designs.reserve",
                scope=scope_id,
                target=row_id,
                details={
                    "project": project_id,
                    "authority_key": authority_key,
                    "amount": amount,
                    "subject_id": subject_id,
                    "reactivated": row is not None,
                },
            )
            saved = self._final_designs_row(db, row_id)
            return dict(saved), created

    def settle_final_designs(
        self, row_id: str, *, campaign_sha256: str, delivered: int
    ) -> dict[str, Any]:
        """Charge the exact delivered pool size of the bound campaign, once."""
        if not re.fullmatch(r"[0-9a-f]{64}", campaign_sha256 or ""):
            raise ProductError("campaign_mismatch", "campaign identity invalid", 400)
        if type(delivered) is not int or delivered < 0:
            raise ProductError("invalid_final_designs_request", "delivered count invalid", 400)
        with self.accounts.db(write=True) as db:
            row = self._final_designs_row(db, row_id)
            if row["state"] == "settled":
                if row["campaign_sha256"] == campaign_sha256 and row["delivered"] == delivered:
                    return dict(row)
                raise ProductError("final_designs_already_settled", "charge already final", 409)
            if row["state"] != "reserved":
                raise ProductError("final_designs_not_held", "reservation is not active", 409)
            if row["campaign_sha256"] not in (None, campaign_sha256):
                raise ProductError("campaign_mismatch", "pool belongs to a different campaign", 409)
            db.execute(
                "UPDATE final_design_reservations SET state='settled',delivered=?,"
                "campaign_sha256=?,reason=NULL,updated_at=? WHERE id=?",
                (delivered, campaign_sha256, self.accounts.clock(), row_id),
            )
            self.accounts.audit_record(
                db,
                None,
                "final_designs.settle",
                scope=row["scope_id"],
                target=row_id,
                details={"campaign_sha256": campaign_sha256, "delivered": delivered},
            )
            return dict(self._final_designs_row(db, row_id))

    def release_final_designs(self, row_id: str, reason: str) -> dict[str, Any]:
        with self.accounts.db(write=True) as db:
            row = self._final_designs_row(db, row_id)
            if row["state"] != "reserved":
                raise ProductError("final_designs_not_held", "reservation is not active", 409)
            db.execute(
                "UPDATE final_design_reservations SET state='released',delivered=0,reason=?,"
                "updated_at=? WHERE id=?",
                (reason, self.accounts.clock(), row_id),
            )
            self.accounts.audit_record(
                db,
                None,
                "final_designs.release",
                scope=row["scope_id"],
                target=row_id,
                details={"reason": reason},
            )
            return dict(self._final_designs_row(db, row_id))

    def note_final_designs_hold(self, row_id: str, reason: str) -> None:
        """Truthful hold reporting only; never a state change or audit event."""
        with self.accounts.db(write=True) as db:
            db.execute(
                "UPDATE final_design_reservations SET reason=?,updated_at=? "
                "WHERE id=? AND state='reserved' AND COALESCE(reason,'')<>?",
                (reason, self.accounts.clock(), row_id, reason),
            )

    def reserved_final_designs(self) -> list[dict[str, Any]]:
        with self.accounts.db() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM final_design_reservations WHERE state='reserved' "
                    "ORDER BY created_at,rowid"
                )
            ]

    def request_admission_active(self, scope_id: str, request_id: str) -> bool:
        with self.accounts.db() as db:
            row = db.execute(
                "SELECT 1 FROM admissions WHERE scope_id=? AND request_id=? AND state IN "
                "('reserved','queued','starting','running','held') LIMIT 1",
                (scope_id, request_id),
            ).fetchone()
            return row is not None

    def final_designs_row(
        self, scope_id: str, project_id: str, authority_key: str
    ) -> dict[str, Any] | None:
        """The persisted reservation for one approval identity, if any."""
        with self.accounts.db() as db:
            row = db.execute(
                "SELECT * FROM final_design_reservations "
                "WHERE scope_id=? AND project_id=? AND authority_key=?",
                (scope_id, project_id, authority_key),
            ).fetchone()
            return None if row is None else dict(row)

    def final_designs_entries(
        self,
        *,
        subject_id: str | None = None,
        scope_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if subject_id is not None:
            clauses.append("subject_id=?")
            params.append(subject_id)
        if scope_id is not None:
            clauses.append("scope_id=?")
            params.append(scope_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(min(max(limit, 1), 200))
        with self.accounts.db() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM final_design_reservations "
                    f"{where} ORDER BY updated_at DESC,rowid DESC LIMIT ?",
                    params,
                )
            ]

    def final_designs_admin(self, actor: AccountUser) -> dict[str, Any]:
        """Site-wide aggregates for the admin console; foreign views are audited."""
        with self.accounts.db() as db:
            admin = self.accounts.require_admin(db, actor)
            subjects = {
                str(row[0])
                for row in db.execute("SELECT DISTINCT subject_id FROM final_design_reservations")
            }
            aggregate = []
            for subject_id in sorted(subjects):
                limits_row = db.execute(
                    "SELECT limits_json FROM resource_limits WHERE subject_id=?",
                    (subject_id,),
                ).fetchone()
                allowance = (
                    ResourceLimits.model_validate_json(limits_row[0]).final_designs_allowance
                    if limits_row is not None
                    else None
                )
                reserved_n, delivered_n = self._final_design_spent(db, subject_id)
                aggregate.append(
                    {
                        "subject_id": subject_id,
                        "allowance": allowance,
                        "reserved": reserved_n,
                        "delivered": delivered_n,
                        "remaining": (
                            None if allowance is None else allowance - reserved_n - delivered_n
                        ),
                    }
                )
            names = {
                str(row["id"]): (str(row["username"]), str(row["display_name"]))
                for row in db.execute("SELECT id,username,display_name FROM users")
            }
            self.accounts.audit_record(db, admin.id, "admin.final_designs.read")
            subjects_out: list[dict[str, Any]] = []
            for item in aggregate:
                found = names.get(str(item["subject_id"]))
                subjects_out.append(
                    {
                        **item,
                        "username": found[0] if found else None,
                        "display_name": found[1] if found else None,
                    }
                )
            return {
                "rule": FINAL_DESIGN_RULE,
                "entries": self.final_designs_entries(),
                "subjects": subjects_out,
            }
