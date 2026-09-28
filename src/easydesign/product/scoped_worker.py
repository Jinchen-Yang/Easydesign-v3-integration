"""Account-scoped detached worker; preserves the original scientific actor on retry."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import sqlite3
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from easydesign.agent.session_store import confined
from easydesign.execution_scope import EXECUTION_SCOPE_ENV
from easydesign.runtime_guard import LOCAL_WRITE_ROOTS_ENV, apply_local_write_sandbox
from easydesign.workspace_context import WorkspaceContext

from .accounts import AccountStore, AccountUser
from .artifacts import immutable_json
from .contracts import ProductError
from .domain import NativeGateway
from .resource_control import ACTIVE_ADMISSIONS
from .service import ProductService


def open_authority_connection(path: Path) -> tuple[sqlite3.Connection, tuple[int, int]]:
    """Pre-open a live WAL reader, never a writable account database handle."""
    info = path.stat()
    identity = (info.st_dev, info.st_ino)
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5, isolation_level=None)
    try:
        db.row_factory = sqlite3.Row
        db.execute("SELECT id FROM admissions LIMIT 1").fetchall()
        current = path.stat()
        if (current.st_dev, current.st_ino) != identity:
            raise RuntimeError("Account authority changed while opening")
    except BaseException:
        db.close()
        raise
    return db, identity


def _admission_still_active(db_path: Path, grant_id: str) -> bool:
    """Read-only liveness probe; a worker never writes account authority."""
    try:
        db = sqlite3.connect(
            db_path.as_uri() + "?mode=ro", uri=True, timeout=5, isolation_level=None
        )
    except sqlite3.Error:
        return True  # Fail closed toward waiting, never toward self-cancellation.
    try:
        row = db.execute("SELECT state FROM admissions WHERE id=?", (grant_id,)).fetchone()
    except sqlite3.Error:
        return True
    finally:
        db.close()
    if row is None:
        return True
    return str(row[0]) in ACTIVE_ADMISSIONS


def _dispatch_authorized(
    db: sqlite3.Connection,
    authority: AccountStore,
    actor: AccountUser,
    config: dict[str, Any],
    *,
    execution: bool = False,
) -> bool:
    """A late durable worker must never execute a failed/cancelled attempt."""
    try:
        info = authority.path.stat()
        if (info.st_dev, info.st_ino) != config["_authority_identity"]:
            return False
        row = db.execute(
            "SELECT state,kind FROM admissions WHERE id=? AND dispatch_channel='scoped_worker'",
            (config["grant_id"],),
        ).fetchone()
        if row is None or row["state"] not in (
            {"running"} if execution else {"starting", "running"}
        ):
            return False
        authority.scope_in(
            db, actor, config["scope_id"], edit=True, execute=row["kind"] == "scientific"
        )
        epoch = db.execute("SELECT auth_version FROM users WHERE id=?", (actor.id,)).fetchone()
        if config.get("auth_version") is not None and (
            epoch is None or epoch[0] != config["auth_version"]
        ):
            return False
        return True
    except (OSError, sqlite3.Error, ProductError):
        return False


def stage_budgets_from_config(config: dict[str, Any]) -> dict[str, int | None] | None:
    """Validated transport of controller-captured budgets; never admin re-reads."""
    raw = config.get("stage_budgets")
    if not isinstance(raw, dict):
        return None
    return {
        key: value if type(value) is int else None
        for key, value in raw.items()
        if key in {"pilot", "scale"}
    }


class SecretFilter(logging.Filter):
    def __init__(self, names: list[str]) -> None:
        super().__init__()
        self.values = tuple(
            os.environ[name] for name in names if len(os.environ.get(name, "")) >= 8
        )

    def clean(self, text: str) -> str:
        for value in self.values:
            text = text.replace(value, "[REDACTED]")
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.clean(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = self.clean("".join(traceback.format_exception(*record.exc_info)))
            record.exc_info = None
        return True


def main() -> int:
    initial = WorkspaceContext.discover()
    if initial.execution_scope is None:
        raise RuntimeError("Scoped worker has no controller scope")
    base = initial.base_context()
    config_path = confined(base.runtime_root / "state/accounts/worker-config", Path(sys.argv[1]))
    config = json.loads(config_path.read_text())
    scope = initial.execution_scope
    if (
        config["grant_id"] != scope.grant_id
        or config["scope_id"] != scope.scope_id
        or config["actor_id"] != scope.actor_id
    ):
        raise RuntimeError("Worker configuration does not match its scope")
    logging.basicConfig(level=logging.INFO)
    for handler in logging.getLogger().handlers:
        handler.addFilter(SecretFilter(config["secret_names"]))
    durable = config.get("dispatch_protocol") == "durable-v1"
    account_db = base.runtime_root / "state/accounts/accounts.sqlite"
    if durable:
        authority = AccountStore(account_db, read_only=True)
        actor = authority.user(config["actor_id"])
        # WAL readers may need to open the shared-memory sidecar read/write.
        # Establish its handle before Landlock, keeping the database itself
        # mode=ro. No account database write authority enters the worker.
        authority_db, config["_authority_identity"] = open_authority_connection(account_db)
    environment = initial.child_environment()
    apply_local_write_sandbox(
        [Path(p) for p in environment[LOCAL_WRITE_ROOTS_ENV].split(os.pathsep)]
    )
    gateway = NativeGateway(
        initial,
        confined(base.root, base.root / config["models"]),
        prediction_backend=config["prediction_backend"],
    )
    service = ProductService(gateway, actor="account:" + config["scientific_actor_id"])
    assignment = confined(
        base.runtime_root / "state/account-assignments", base.root / config["assignment"]
    )
    lock_path = service.root / "workers" / (config["request_id"] + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        if durable:
            if not _dispatch_authorized(authority_db, authority, actor, config):
                return 0
            # Publish only after owning the request lock. The controller can
            # adopt this exact process if it died before recording Popen's PID.
            start = Path("/proc/self/stat").read_text().rpartition(") ")[2].split()[19]
            immutable_json(
                lock_path.parent / (config["grant_id"] + ".started.json"),
                {
                    "grant_id": config["grant_id"],
                    "request_id": config["request_id"],
                    "pid": os.getpid(),
                    "start": start,
                },
            )
        deadline = time.monotonic() + (60 if durable else 3600)
        while not assignment.is_file():
            if durable and not _dispatch_authorized(authority_db, authority, actor, config):
                return 0
            if not durable and not _admission_still_active(
                base.runtime_root / "state/accounts/accounts.sqlite", config["grant_id"]
            ):
                # The controller abandoned this admission (for example it crashed
                # between spawning us and publishing our PID). No assignment can
                # ever arrive; exit instead of holding the request for an hour.
                return 0
            journal = service.journal()
            try:
                record = journal.get(config["request_id"])
                if record is None or record["state"] not in {"accepted", "running", "interrupted"}:
                    return 0
                if time.monotonic() >= deadline:
                    if durable:
                        return 1  # The controller owns startup failure/retry projection.
                    journal.update(
                        config["request_id"],
                        "failed",
                        {
                            "code": "resource_wait_timeout",
                            "message": "等待空闲资源超时，可稍后恢复",
                        },
                    )
                    return 1
                if not durable:
                    journal.update(config["request_id"], "accepted", {"resource_waiting": True})
            finally:
                journal.close()
            time.sleep(1)
        allocated = json.loads(assignment.read_text())
        if allocated["grant_id"] != scope.grant_id:
            raise RuntimeError("Assignment identity mismatch")
        if allocated.get("cancelled"):
            if durable:
                return 0  # Never overwrite a new attempt's journal with an old cancellation.
            if allocated.get("code") == "admission_abandoned":
                # The controller lost this admission before publishing our PID.
                # Leave the journal untouched so the explicit resume path works.
                return 0
            journal = service.journal()
            try:
                journal.update(
                    config["request_id"],
                    "failed",
                    {
                        "code": "authorization_revoked",
                        "message": "执行前权限已撤销，未启动科学计算",
                    },
                )
            finally:
                journal.close()
            return 1
        scope_path = confined(
            base.runtime_root / "state/execution-scopes", base.root / allocated["scope_file"]
        )
        os.environ[EXECUTION_SCOPE_ENV] = str(scope_path)
        current = WorkspaceContext.discover()
        if current.execution_scope is None or current.execution_scope.grant_id != scope.grant_id:
            raise RuntimeError("Assigned execution scope mismatch")
        os.environ.update(current.child_environment())
        if durable:
            # Assignment is immutable but publication can precede the ledger
            # commit. Wait for that commit; a rollback/revocation never runs.
            while not _dispatch_authorized(authority_db, authority, actor, config, execution=True):
                if time.monotonic() >= deadline or not _dispatch_authorized(
                    authority_db, authority, actor, config
                ):
                    return 0
                time.sleep(0.1)
    gateway = NativeGateway(
        current,
        confined(base.root, base.root / config["models"]),
        prediction_backend=config["prediction_backend"],
    )
    ProductService(
        gateway,
        actor="account:" + config["scientific_actor_id"],
        stage_budgets=stage_budgets_from_config(config),
    ).run(config["request_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
