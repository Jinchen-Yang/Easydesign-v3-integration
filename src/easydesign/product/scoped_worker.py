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

from .domain import NativeGateway
from .resource_control import ACTIVE_ADMISSIONS
from .service import ProductService


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
        deadline = time.monotonic() + 3600
        while not assignment.is_file():
            if not _admission_still_active(
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
                    journal.update(
                        config["request_id"],
                        "failed",
                        {
                            "code": "resource_wait_timeout",
                            "message": "等待空闲资源超时，可稍后恢复",
                        },
                    )
                    return 1
                journal.update(config["request_id"], "accepted", {"resource_waiting": True})
            finally:
                journal.close()
            time.sleep(1)
        allocated = json.loads(assignment.read_text())
        if allocated["grant_id"] != scope.grant_id:
            raise RuntimeError("Assignment identity mismatch")
        if allocated.get("cancelled"):
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
