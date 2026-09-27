"""Account, session and team authority for the multi-user product transport.

Scientific authority remains in the native Gate contracts. No caller-provided
role, project label or browser surface grants access through this module.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .contracts import ProductError

PASSWORD_ITERATIONS = 600_000
SESSION_SECONDS = 7 * 24 * 60 * 60
USER_FIELDS = (
    "id",
    "username",
    "display_name",
    "role",
    "status",
    "must_change_password",
    "created_at",
    "updated_at",
)


class AccountUser(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    username: str
    display_name: str
    role: Literal["admin", "user"]
    status: Literal["pending", "active", "suspended", "rejected"]
    must_change_password: bool
    created_at: float
    updated_at: float


class ScopeAccess(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: Literal["personal", "team"]
    name: str
    role: Literal["owner", "admin", "member", "observer"]
    can_edit: bool = True
    can_execute: bool


class ResourceLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_active_jobs: int = Field(default=1, ge=0, le=64)
    max_active_chats: int = Field(default=2, ge=0, le=64)
    max_gpu_devices: int = Field(default=1, ge=1, le=64)
    max_upload_bytes: int = Field(default=32 * 1024**2, ge=1024, le=32 * 1024**2)
    max_stored_upload_bytes: int = Field(default=10 * 1024**3, ge=1024, le=10 * 1024**4)
    max_candidates_per_job: int = Field(default=50_000, ge=1, le=1_000_000)


@dataclass(frozen=True)
class LoginSession:
    user: AccountUser
    token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    expires_at: float


def _password_hash(password: str) -> str:
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ProductError("invalid_password", "密码长度必须为 12–256 个字符", 400)
    salt = secrets.token_bytes(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return "$".join(
        (
            "pbkdf2-sha256",
            str(PASSWORD_ITERATIONS),
            base64.b64encode(salt).decode(),
            base64.b64encode(hashed).decode(),
        )
    )


def _password_matches(password: str, encoded: str) -> bool:
    if not isinstance(password, str) or len(password) > 256:
        return False
    try:
        algorithm, iterations, salt_text, expected_text = encoded.split("$")
        count = int(iterations)
        if algorithm != "pbkdf2-sha256" or not 100_000 <= count <= 2_000_000:
            return False
        salt = base64.b64decode(salt_text, validate=True)
        expected = base64.b64decode(expected_text, validate=True)
        if len(salt) != 16 or len(expected) != 32:
            return False
        observed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, count)
        return hmac.compare_digest(observed, expected)
    except (ValueError, TypeError):
        return False


def _username(value: str) -> tuple[str, str]:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,63}", value):
        raise ProductError(
            "invalid_username", "用户名须为 3–64 位字母、数字、点、横线或下划线", 400
        )
    return value, value.casefold()


def _label(value: str, maximum: int = 100) -> str:
    if not isinstance(value, str):
        raise ProductError("invalid_label", "名称格式不正确", 400)
    selected = value.strip()
    if not selected or len(selected) > maximum or any(ord(c) < 32 for c in selected):
        raise ProductError("invalid_label", "名称为空、过长或包含控制字符", 400)
    return selected


def _user(row: sqlite3.Row) -> AccountUser:
    return AccountUser.model_validate({key: row[key] for key in USER_FIELDS})


class AccountStore:
    """Thread-safe identity authority with per-operation transactions and revocation."""

    def __init__(
        self, path: Path, *, clock: Callable[[], float] = time.time, read_only: bool = False
    ) -> None:
        self.path, self.clock, self.read_only = Path(path).absolute(), clock, read_only
        if self.path.is_symlink():
            raise ProductError("invalid_account_state", "账户数据库不能是符号链接", 503)
        if not read_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            tables = {
                row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if tables:
                if "account_schema" not in tables:
                    raise ProductError("unknown_account_schema", "账户数据库格式不受支持", 503)
                versions = [row[0] for row in db.execute("SELECT version FROM account_schema")]
                if versions != [1]:
                    raise ProductError("unknown_account_schema", "账户数据库版本不受支持", 503)
            if read_only:
                if not tables:
                    raise ProductError("setup_required", "账户数据库尚未初始化", 503)
                self._dummy_hash = ""
                return
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS account_schema (version INTEGER PRIMARY KEY);
                INSERT OR IGNORE INTO account_schema VALUES(1);
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL, username_key TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL, password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin','user')),
                    status TEXT NOT NULL
                        CHECK(status IN ('pending','active','suspended','rejected')),
                    must_change_password INTEGER NOT NULL DEFAULT 0,
                    auth_version INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    auth_version INTEGER NOT NULL, created_at REAL NOT NULL,
                    expires_at REAL NOT NULL, revoked_at REAL
                );
                CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
                CREATE TABLE IF NOT EXISTS teams (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    created_by TEXT NOT NULL REFERENCES users(id),
                    status TEXT NOT NULL CHECK(status IN ('active','suspended')),
                    created_at REAL NOT NULL, updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memberships (
                    team_id TEXT NOT NULL REFERENCES teams(id),
                    user_id TEXT NOT NULL REFERENCES users(id),
                    role TEXT NOT NULL CHECK(role IN ('admin','member')),
                    status TEXT NOT NULL CHECK(status IN ('active','removed')),
                    created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    PRIMARY KEY(team_id,user_id)
                );
                CREATE TABLE IF NOT EXISTS invitations (
                    id TEXT PRIMARY KEY, team_id TEXT NOT NULL REFERENCES teams(id),
                    user_id TEXT NOT NULL REFERENCES users(id), role TEXT NOT NULL,
                    invited_by TEXT NOT NULL REFERENCES users(id),
                    status TEXT NOT NULL
                        CHECK(status IN ('pending','accepted','declined','revoked')),
                    created_at REAL NOT NULL, updated_at REAL NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS pending_team_invitation
                    ON invitations(team_id,user_id) WHERE status='pending';
                CREATE TABLE IF NOT EXISTS resource_limits (
                    subject_id TEXT PRIMARY KEY, limits_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS rate_limits (
                    bucket TEXT PRIMARY KEY, attempts INTEGER NOT NULL, window_start REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, actor_id TEXT,
                    action TEXT NOT NULL, scope_id TEXT, target_id TEXT,
                    details TEXT NOT NULL, created_at REAL NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events
                    BEGIN SELECT RAISE(ABORT,'audit events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events
                    BEGIN SELECT RAISE(ABORT,'audit events are append-only'); END;
                COMMIT;
            """)
        self.path.chmod(0o600)
        self._dummy_hash = _password_hash(secrets.token_urlsafe(32))

    @contextmanager
    def db(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        if write and self.read_only:
            raise ProductError("read_only_identity", "执行进程不能修改账户管理数据", 403)
        db = sqlite3.connect(
            self.path.as_uri() + "?mode=ro" if self.read_only else str(self.path),
            uri=self.read_only,
            timeout=20,
            isolation_level=None,
        )
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=20000")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.commit()
        except Exception:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    def audit_record(
        self,
        db: sqlite3.Connection,
        actor: str | None,
        action: str,
        *,
        target: str | None = None,
        scope: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        db.execute(
            "INSERT INTO audit_events(actor_id,action,scope_id,target_id,details,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (
                actor,
                action,
                scope,
                target,
                json.dumps(details or {}, ensure_ascii=False),
                self.clock(),
            ),
        )

    def live_user(
        self, db: sqlite3.Connection, actor: AccountUser, *, password_change: bool = False
    ) -> AccountUser:
        row = db.execute("SELECT * FROM users WHERE id=?", (actor.id,)).fetchone()
        if row is None or row["status"] != "active":
            raise ProductError("unauthorized", "账户不可用，请重新登录", 401)
        if row["must_change_password"] and not password_change:
            raise ProductError("password_change_required", "请先修改临时密码", 403)
        return _user(row)

    def require_admin(self, db: sqlite3.Connection, actor: AccountUser) -> AccountUser:
        user = self.live_user(db, actor)
        if user.role != "admin":
            raise ProductError("forbidden", "此操作需要系统管理员权限", 403)
        return user

    def has_admin(self) -> bool:
        with self.db() as db:
            return (
                db.execute("SELECT 1 FROM users WHERE role='admin' LIMIT 1").fetchone() is not None
            )

    def user(self, user_id: str) -> AccountUser:
        with self.db() as db:
            row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if row is None:
                raise ProductError("not_found", "账户不存在", 404)
            return _user(row)

    def _insert_user(
        self,
        db: sqlite3.Connection,
        username: str,
        password_hash: str,
        display_name: str,
        *,
        role: str,
        status: str,
    ) -> AccountUser:
        name, key = _username(username)
        if db.execute("SELECT 1 FROM users WHERE username_key=?", (key,)).fetchone():
            raise ProductError("username_unavailable", "用户名不可用", 409)
        user_id, now = "user-" + uuid4().hex, self.clock()
        db.execute(
            "INSERT INTO users(id,username,username_key,display_name,password_hash,role,status,"
            "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                user_id,
                name,
                key,
                _label(display_name or name),
                password_hash,
                role,
                status,
                now,
                now,
            ),
        )
        db.execute(
            "INSERT INTO resource_limits VALUES(?,?)", (user_id, ResourceLimits().model_dump_json())
        )
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        assert row is not None
        return _user(row)

    def bootstrap_admin(self, username: str, password: str, display_name: str) -> AccountUser:
        hashed = _password_hash(password)
        with self.db(write=True) as db:
            if db.execute("SELECT 1 FROM users WHERE role='admin' LIMIT 1").fetchone():
                raise ProductError("already_initialized", "管理员已初始化，不能再次引导", 409)
            user = self._insert_user(
                db, username, hashed, display_name, role="admin", status="active"
            )
            self.audit_record(db, user.id, "account.bootstrap", target=user.id)
            return user

    def register(
        self, username: str, password: str, display_name: str, *, peer: str = "local"
    ) -> AccountUser:
        _username(username)
        with self.db(write=True) as db:
            if db.execute("SELECT 1 FROM users WHERE role='admin' LIMIT 1").fetchone() is None:
                raise ProductError("setup_required", "管理员尚未初始化", 503)
            bucket = self._bucket("register", peer)
            self._check_rate(db, bucket, maximum=20, window=3600)
            self._record_attempt(db, bucket, window=3600)
        hashed = _password_hash(password)
        with self.db(write=True) as db:
            user = self._insert_user(
                db, username, hashed, display_name, role="user", status="pending"
            )
            self.audit_record(db, user.id, "account.register", target=user.id)
            return user

    @staticmethod
    def _bucket(*parts: str) -> str:
        return hashlib.sha256(json.dumps(parts).encode()).hexdigest()

    def _check_rate(
        self, db: sqlite3.Connection, bucket: str, *, maximum: int, window: int
    ) -> None:
        row = db.execute("SELECT * FROM rate_limits WHERE bucket=?", (bucket,)).fetchone()
        if row and row["window_start"] > self.clock() - window and row["attempts"] >= maximum:
            raise ProductError("rate_limited", "尝试次数过多，请稍后重试", 429)

    def _record_attempt(self, db: sqlite3.Connection, bucket: str, *, window: int) -> None:
        now = self.clock()
        db.execute(
            "INSERT INTO rate_limits VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET "
            "attempts=CASE WHEN window_start<=? THEN 1 ELSE attempts+1 END, "
            "window_start=CASE WHEN window_start<=? THEN ? ELSE window_start END",
            (bucket, now, now - window, now - window, now),
        )

    @staticmethod
    def csrf_token(token: str) -> str:
        return hmac.new(token.encode(), b"easydesign-account-csrf-v1", hashlib.sha256).hexdigest()

    def login(self, username: str, password: str, *, peer: str) -> LoginSession:
        if not isinstance(username, str) or len(username) > 64:
            raise ProductError("invalid_credentials", "用户名或密码错误", 401)
        bucket = self._bucket("login", username.casefold(), peer)
        peer_bucket = self._bucket("login-peer", peer)
        with self.db(write=True) as db:
            self._check_rate(db, peer_bucket, maximum=120, window=60)
            self._record_attempt(db, peer_bucket, window=60)
        failure: ProductError | None = None
        session: LoginSession | None = None
        with self.db(write=True) as db:
            self._check_rate(db, bucket, maximum=5, window=15 * 60)
            row = db.execute(
                "SELECT * FROM users WHERE username_key=?", (username.casefold(),)
            ).fetchone()
            matches = _password_matches(password, row["password_hash"] if row else self._dummy_hash)
            if row is None or not matches:
                self._record_attempt(db, bucket, window=15 * 60)
                self.audit_record(
                    db, None, "session.rejected", details={"reason": "invalid_credentials"}
                )
                failure = ProductError("invalid_credentials", "用户名或密码错误", 401)
            elif row["status"] != "active":
                self.audit_record(
                    db, row["id"], "session.rejected", details={"reason": row["status"]}
                )
                failure = ProductError("account_" + row["status"], "账户尚未获批或已被停用", 403)
            else:
                token, now = secrets.token_urlsafe(32), self.clock()
                db.execute(
                    "INSERT INTO sessions VALUES(?,?,?,?,?,NULL)",
                    (
                        hashlib.sha256(token.encode()).hexdigest(),
                        row["id"],
                        row["auth_version"],
                        now,
                        now + SESSION_SECONDS,
                    ),
                )
                db.execute(
                    "UPDATE rate_limits SET attempts=0,window_start=? WHERE bucket=?", (now, bucket)
                )
                self.audit_record(db, row["id"], "session.login", target=row["id"])
                session = LoginSession(
                    _user(row), token, self.csrf_token(token), now + SESSION_SECONDS
                )
        if failure:
            raise failure
        assert session is not None
        return session

    def authenticate(self, token: str) -> AccountUser:
        if not isinstance(token, str) or not 32 <= len(token) <= 128:
            raise ProductError("unauthorized", "请登录", 401)
        with self.db() as db:
            row = db.execute(
                "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
                "WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>? "
                "AND s.auth_version=u.auth_version AND u.status='active'",
                (hashlib.sha256(token.encode()).hexdigest(), self.clock()),
            ).fetchone()
            if row is None:
                raise ProductError("unauthorized", "会话已失效，请重新登录", 401)
            return _user(row)

    def logout(self, token: str) -> None:
        key = hashlib.sha256(token.encode()).hexdigest()
        with self.db(write=True) as db:
            row = db.execute(
                "SELECT user_id,revoked_at FROM sessions WHERE token_hash=?", (key,)
            ).fetchone()
            if row and row["revoked_at"] is None:
                db.execute(
                    "UPDATE sessions SET revoked_at=? WHERE token_hash=?", (self.clock(), key)
                )
                self.audit_record(db, row["user_id"], "session.logout", target=row["user_id"])

    def users(self, actor: AccountUser) -> list[dict[str, Any]]:
        with self.db() as db:
            admin = self.require_admin(db, actor)
            rows = [
                _user(row).model_dump()
                for row in db.execute("SELECT * FROM users ORDER BY created_at,id")
            ]
            self.audit_record(db, admin.id, "admin.users.read")
            return rows

    def update_user(
        self,
        actor: AccountUser,
        user_id: str,
        *,
        status: str | None = None,
        role: str | None = None,
    ) -> AccountUser:
        if status not in {None, "pending", "active", "suspended", "rejected"} or role not in {
            None,
            "admin",
            "user",
        }:
            raise ProductError("invalid_account_update", "账户状态或角色不合法", 400)
        with self.db(write=True) as db:
            admin = self.require_admin(db, actor)
            row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if row is None:
                raise ProductError("not_found", "账户不存在", 404)
            next_status, next_role = status or row["status"], role or row["role"]
            if (
                row["status"] == "active"
                and row["role"] == "admin"
                and (next_status != "active" or next_role != "admin")
            ):
                count = db.execute(
                    "SELECT count(*) FROM users WHERE role='admin' AND status='active'"
                ).fetchone()[0]
                if count <= 1:
                    raise ProductError("last_admin", "必须保留至少一名有效系统管理员", 409)
            if (next_status, next_role) != (row["status"], row["role"]):
                db.execute(
                    "UPDATE users SET status=?,role=?,auth_version=auth_version+1,updated_at=? "
                    "WHERE id=?",
                    (next_status, next_role, self.clock(), user_id),
                )
                self.audit_record(
                    db,
                    admin.id,
                    "account.update",
                    target=user_id,
                    details={"status": next_status, "role": next_role},
                )
            changed = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            assert changed is not None
            return _user(changed)

    def reset_password(self, actor: AccountUser, user_id: str, password: str) -> None:
        hashed = _password_hash(password)
        with self.db(write=True) as db:
            admin = self.require_admin(db, actor)
            if db.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone() is None:
                raise ProductError("not_found", "账户不存在", 404)
            db.execute(
                "UPDATE users SET password_hash=?,must_change_password=1,"
                "auth_version=auth_version+1,updated_at=? WHERE id=?",
                (hashed, self.clock(), user_id),
            )
            self.audit_record(db, admin.id, "account.password_reset", target=user_id)

    def change_password(self, actor: AccountUser, current: str, password: str) -> None:
        hashed = _password_hash(password)
        with self.db(write=True) as db:
            user = self.live_user(db, actor, password_change=True)
            row = db.execute("SELECT password_hash FROM users WHERE id=?", (user.id,)).fetchone()
            if row is None or not _password_matches(current, row["password_hash"]):
                raise ProductError("invalid_credentials", "当前密码不正确", 403)
            db.execute(
                "UPDATE users SET password_hash=?,must_change_password=0,"
                "auth_version=auth_version+1,updated_at=? WHERE id=?",
                (hashed, self.clock(), user.id),
            )
            self.audit_record(db, user.id, "account.password_change", target=user.id)

    def scope(
        self,
        actor: AccountUser,
        scope_id: str | None = None,
        *,
        execute: bool = False,
        edit: bool = False,
    ) -> ScopeAccess:
        with self.db() as db:
            return self.scope_in(db, actor, scope_id, execute=execute, edit=edit)

    def scope_in(
        self,
        db: sqlite3.Connection,
        actor: AccountUser,
        scope_id: str | None = None,
        *,
        execute: bool = False,
        edit: bool = False,
    ) -> ScopeAccess:
        user = self.live_user(db, actor)
        scope_id = scope_id or user.id
        if scope_id == user.id:
            return ScopeAccess(
                id=user.id, kind="personal", name="个人工作区", role="owner", can_execute=True
            )
        row = db.execute(
            "SELECT t.id,t.name,m.role FROM teams t JOIN memberships m ON m.team_id=t.id "
            "WHERE t.id=? AND t.status='active' AND m.user_id=? AND m.status='active'",
            (scope_id, user.id),
        ).fetchone()
        if row is None:
            if user.role == "admin":
                owner = db.execute(
                    "SELECT id,display_name FROM users WHERE id=?", (scope_id,)
                ).fetchone()
                team = db.execute("SELECT id,name FROM teams WHERE id=?", (scope_id,)).fetchone()
                if owner is not None or team is not None:
                    if execute or edit:
                        raise ProductError(
                            "read_only_scope", "管理员查看权限不允许修改或推进他人的科学项目", 403
                        )
                    return ScopeAccess(
                        id=scope_id,
                        kind="personal" if owner is not None else "team",
                        name=owner["display_name"] if owner is not None else team["name"],
                        role="observer",
                        can_edit=False,
                        can_execute=False,
                    )
            raise ProductError("not_found", "工作区不存在或无访问权限", 404)
        can_execute = row["role"] == "admin"
        if execute and not can_execute:
            raise ProductError("team_admin_required", "科学审批和计算启动需要团队管理员权限", 403)
        return ScopeAccess(
            id=row["id"], kind="team", name=row["name"], role=row["role"], can_execute=can_execute
        )

    def scopes(self, actor: AccountUser) -> list[dict[str, Any]]:
        with self.db() as db:
            user = self.live_user(db, actor)
            ids = [
                row[0]
                for row in db.execute(
                    "SELECT team_id FROM memberships WHERE user_id=? AND status='active'",
                    (user.id,),
                )
            ]
            values = [self.scope_in(db, user).model_dump()]
            for scope_id in ids:
                team = db.execute("SELECT status FROM teams WHERE id=?", (scope_id,)).fetchone()
                if team and team["status"] == "active":
                    values.append(self.scope_in(db, user, scope_id).model_dump())
            return values

    def create_team(self, actor: AccountUser, name: str) -> dict[str, Any]:
        name = _label(name)
        with self.db(write=True) as db:
            user = self.live_user(db, actor)
            team_id, now = "team-" + uuid4().hex, self.clock()
            db.execute(
                "INSERT INTO teams VALUES(?,?,?,'active',?,?)", (team_id, name, user.id, now, now)
            )
            db.execute(
                "INSERT INTO memberships VALUES(?,?,'admin','active',?,?)",
                (team_id, user.id, now, now),
            )
            limits = ResourceLimits(
                max_active_jobs=2, max_gpu_devices=2, max_stored_upload_bytes=100 * 1024**3
            )
            db.execute(
                "INSERT INTO resource_limits VALUES(?,?)", (team_id, limits.model_dump_json())
            )
            self.audit_record(db, user.id, "team.create", target=team_id, scope=team_id)
            return {"id": team_id, "name": name, "status": "active", "role": "admin"}

    def _team_admin(self, db: sqlite3.Connection, actor: AccountUser, team_id: str) -> AccountUser:
        user = self.live_user(db, actor)
        team = db.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
        if team is None:
            raise ProductError("not_found", "团队不存在", 404)
        if user.role == "admin":
            return user
        access = self.scope_in(db, user, team_id)
        if access.role != "admin":
            raise ProductError("team_admin_required", "此操作需要团队管理员权限", 403)
        return user

    def team(self, actor: AccountUser, team_id: str) -> dict[str, Any]:
        with self.db() as db:
            user = self.live_user(db, actor)
            # Only ACTIVE membership counts: a suspended team hides its roster
            # from ordinary members; administration inspection stays audited.
            member = db.execute(
                "SELECT 1 FROM memberships m JOIN teams t ON t.id=m.team_id "
                "WHERE m.team_id=? AND m.user_id=? AND m.status='active' "
                "AND t.status='active'",
                (team_id, user.id),
            ).fetchone()
            if member is None and user.role != "admin":
                self.scope_in(db, user, team_id)  # Raises not_found for outsiders.
            if member is None:
                # Administration observation of someone else's team is audited,
                # exactly like read-only project scope access.
                self.audit_record(db, user.id, "admin.team.read", scope=team_id, target=team_id)
            row = db.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
            if row is None:
                raise ProductError("not_found", "团队不存在", 404)
            members = [
                dict(item)
                for item in db.execute(
                    "SELECT m.user_id,u.username,u.display_name,u.status AS account_status,"
                    "m.role,m.status FROM memberships m JOIN users u ON u.id=m.user_id "
                    "WHERE m.team_id=? ORDER BY m.created_at",
                    (team_id,),
                )
            ]
            return {**dict(row), "members": members}

    def all_teams(self, actor: AccountUser) -> list[dict[str, Any]]:
        with self.db() as db:
            admin = self.require_admin(db, actor)
            rows = [dict(row) for row in db.execute("SELECT * FROM teams ORDER BY created_at,id")]
            self.audit_record(db, admin.id, "admin.teams.read")
            return rows

    def update_team(
        self,
        actor: AccountUser,
        team_id: str,
        *,
        name: str | None = None,
        status: str | None = None,
    ) -> None:
        if status not in {None, "active", "suspended"}:
            raise ProductError("invalid_status", "团队状态不合法", 400)
        with self.db(write=True) as db:
            user = self._team_admin(db, actor, team_id)
            if status is not None:
                self.require_admin(db, user)
            row = db.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
            assert row is not None
            db.execute(
                "UPDATE teams SET name=?,status=?,updated_at=? WHERE id=?",
                (
                    _label(name) if name is not None else row["name"],
                    status or row["status"],
                    self.clock(),
                    team_id,
                ),
            )
            self.audit_record(db, user.id, "team.update", target=team_id, scope=team_id)

    def invite(
        self, actor: AccountUser, team_id: str, username: str, *, role: str = "member"
    ) -> dict[str, Any]:
        if role not in {"member", "admin"}:
            raise ProductError("invalid_role", "团队角色不合法", 400)
        _, key = _username(username)
        with self.db(write=True) as db:
            user = self._team_admin(db, actor, team_id)
            target = db.execute(
                "SELECT * FROM users WHERE username_key=? AND status='active'", (key,)
            ).fetchone()
            if target is None:
                raise ProductError("account_unavailable", "只能邀请已启用的账户", 404)
            member = db.execute(
                "SELECT * FROM memberships WHERE team_id=? AND user_id=?", (team_id, target["id"])
            ).fetchone()
            if member and member["status"] == "active":
                raise ProductError("already_member", "该用户已是团队成员", 409)
            previous = db.execute(
                "SELECT * FROM invitations WHERE team_id=? AND user_id=? AND status='pending'",
                (team_id, target["id"]),
            ).fetchone()
            if previous:
                if previous["role"] != role:
                    raise ProductError("invitation_conflict", "已有不同角色的待处理邀请", 409)
                return dict(previous)
            invitation_id, now = "invite-" + uuid4().hex, self.clock()
            db.execute(
                "INSERT INTO invitations VALUES(?,?,?,?,?,'pending',?,?)",
                (invitation_id, team_id, target["id"], role, user.id, now, now),
            )
            self.audit_record(
                db,
                user.id,
                "team.invite",
                scope=team_id,
                target=target["id"],
                details={"role": role},
            )
            row = db.execute("SELECT * FROM invitations WHERE id=?", (invitation_id,)).fetchone()
            assert row is not None
            return dict(row)

    def invitations(self, actor: AccountUser) -> list[dict[str, Any]]:
        with self.db() as db:
            user = self.live_user(db, actor)
            return [
                dict(row)
                for row in db.execute(
                    "SELECT i.*,t.name AS team_name FROM invitations i "
                    "JOIN teams t ON t.id=i.team_id WHERE i.user_id=? AND i.status='pending' "
                    "AND t.status='active' ORDER BY i.created_at",
                    (user.id,),
                )
            ]

    def respond_invitation(
        self, actor: AccountUser, invitation_id: str, *, accept: bool
    ) -> dict[str, Any]:
        with self.db(write=True) as db:
            user = self.live_user(db, actor)
            row = db.execute(
                "SELECT i.* FROM invitations i JOIN teams t ON t.id=i.team_id "
                "WHERE i.id=? AND i.user_id=? AND t.status='active'",
                (invitation_id, user.id),
            ).fetchone()
            if row is None:
                raise ProductError("not_found", "邀请不存在或不属于当前用户", 404)
            state = "accepted" if accept else "declined"
            if row["status"] != "pending":
                if row["status"] == state:
                    return dict(row)
                raise ProductError("invitation_consumed", "邀请已经处理", 409)
            now = self.clock()
            if accept:
                db.execute(
                    "INSERT INTO memberships VALUES(?,?,?,'active',?,?) "
                    "ON CONFLICT(team_id,user_id) DO UPDATE SET role=excluded.role,"
                    "status='active',updated_at=excluded.updated_at",
                    (row["team_id"], user.id, row["role"], now, now),
                )
            db.execute(
                "UPDATE invitations SET status=?,updated_at=? WHERE id=?",
                (state, now, invitation_id),
            )
            self.audit_record(
                db, user.id, "team.invitation." + state, scope=row["team_id"], target=invitation_id
            )
            return {**dict(row), "status": state, "updated_at": now}

    def set_member(
        self,
        actor: AccountUser,
        team_id: str,
        user_id: str,
        *,
        role: str | None = None,
        remove: bool = False,
    ) -> None:
        if (remove and role is not None) or (not remove and role not in {"admin", "member"}):
            raise ProductError("invalid_membership_update", "成员变更格式不正确", 400)
        with self.db(write=True) as db:
            if remove and user_id == actor.id:
                user = self.live_user(db, actor)
                self.scope_in(db, user, team_id)
            else:
                user = self._team_admin(db, actor, team_id)
            row = db.execute(
                "SELECT m.*,u.status AS account_status FROM memberships m "
                "JOIN users u ON u.id=m.user_id "
                "WHERE m.team_id=? AND m.user_id=? AND m.status='active'",
                (team_id, user_id),
            ).fetchone()
            if row is None:
                raise ProductError("not_found", "团队成员不存在", 404)
            if (
                row["role"] == "admin"
                and row["account_status"] == "active"
                and (remove or role != "admin")
            ):
                count = db.execute(
                    "SELECT count(*) FROM memberships m JOIN users u ON u.id=m.user_id "
                    "WHERE m.team_id=? AND m.role='admin' AND m.status='active' "
                    "AND u.status='active'",
                    (team_id,),
                ).fetchone()[0]
                if count <= 1:
                    raise ProductError("last_team_admin", "必须保留至少一名有效团队管理员", 409)
            db.execute(
                "UPDATE memberships SET role=?,status=?,updated_at=? WHERE team_id=? AND user_id=?",
                (
                    role or row["role"],
                    "removed" if remove else "active",
                    self.clock(),
                    team_id,
                    user_id,
                ),
            )
            self.audit_record(
                db,
                user.id,
                "team.member.update",
                scope=team_id,
                target=user_id,
                details={"role": role or row["role"], "removed": remove},
            )

    def limits(self, actor: AccountUser, subject_id: str | None = None) -> ResourceLimits:
        with self.db() as db:
            user = self.live_user(db, actor)
            subject_id = subject_id or user.id
            if user.role != "admin" and subject_id != user.id:
                self.scope_in(db, user, subject_id)
            row = db.execute(
                "SELECT limits_json FROM resource_limits WHERE subject_id=?", (subject_id,)
            ).fetchone()
            if row is None:
                raise ProductError("not_found", "资源额度未配置", 404)
            if user.role == "admin" and subject_id != user.id:
                # Administration inspection of someone else's quotas is audited.
                self.audit_record(db, user.id, "admin.quota.read", target=subject_id)
            return ResourceLimits.model_validate_json(row["limits_json"])

    def set_limits(self, actor: AccountUser, subject_id: str, limits: ResourceLimits) -> None:
        with self.db(write=True) as db:
            user = self.require_admin(db, actor)
            result = db.execute(
                "UPDATE resource_limits SET limits_json=? WHERE subject_id=?",
                (limits.model_dump_json(), subject_id),
            )
            if result.rowcount != 1:
                raise ProductError("not_found", "资源归属不存在", 404)
            self.audit_record(
                db, user.id, "quota.update", target=subject_id, details=limits.model_dump()
            )

    def audit(
        self, actor: AccountUser, *, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        with self.db() as db:
            self.require_admin(db, actor)
            rows = db.execute(
                "SELECT * FROM audit_events ORDER BY seq DESC LIMIT ? OFFSET ?",
                (min(max(limit, 1), 100), max(offset, 0)),
            )
            return [{**dict(row), "details": json.loads(row["details"])} for row in rows]
