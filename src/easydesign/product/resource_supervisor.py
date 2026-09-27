"""Product admission and process recovery; Native Runtime still owns scientific jobs."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from easydesign.backends.executors.local_multi_gpu import NvidiaSmiProbe
from easydesign.execution_scope import ExecutionScope, load_scope
from easydesign.workspace_context import WorkspaceContext

from .artifacts import immutable_json
from .contracts import ProductError
from .device_pool import ProductDevicePool
from .resource_control import Admission
from .service import ProductService
from .tenancy import MultiUserRuntime, ScopedProductService


def process_identity(pid: int | None) -> str | None:
    if pid is None:
        return None
    try:
        text = Path(f"/proc/{pid}/stat").read_text()
        parts = text.rpartition(") ")[2].split()
        if parts[0] == "Z":
            return None
        return parts[19]
    except (OSError, IndexError):
        return None


def native_active(service: ProductService, request_id: str) -> bool:
    journal = service.journal()
    try:
        record = journal.get(request_id)
    finally:
        journal.close()
    if record is None:
        return False
    project = record["project"]
    if not (service.context.projects_root / project / "PROJECT.yaml").is_file():
        return False
    with service.gateway.session(project) as session:
        controller = getattr(session.bridge, "controller", None)
        if controller is None:
            raise ProductError("native_state_unavailable", "原生执行状态暂时无法核对", 409)
        return any(
            str(job.status) in {"queued", "running", "dispatching", "drain-requested"}
            for job in controller.list(project_id=session.bridge.project_id)
        )


class ResourceSupervisor:
    def __init__(
        self,
        runtime: MultiUserRuntime,
        *,
        allowed_devices: tuple[int, ...] | None = None,
        probe: Any = None,
        poll_seconds: float = 1.0,
    ) -> None:
        self.runtime = runtime
        self.context = runtime.context
        self.ledger = runtime.resources
        self.pool = ProductDevicePool(self.context, allowed_devices=allowed_devices)
        self.probe = probe or NvidiaSmiProbe()
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._controller_lock: Any = None

    def start(self) -> None:
        path = self.context.runtime_root / "state/accounts/supervisor.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+b")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            raise ProductError("controller_busy", "该工作区已有资源控制器", 409) from None
        self._controller_lock = handle
        self.runtime.launcher = self.launch
        self._thread = threading.Thread(
            target=self._loop, name="account-resource-admission", daemon=True
        )
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=20)
        if self._controller_lock is not None:
            self._controller_lock.close()
        # Detached scientific work is deliberately not signalled here.

    def launch(self, admission: Admission, service: ScopedProductService) -> None:
        with self._lock:
            current = self.ledger.get(admission.id)
            if (
                current.worker_pid is not None
                and process_identity(current.worker_pid) == current.worker_start
            ):
                return
            if current.state not in {"reserved", "queued"}:
                raise ProductError("admission_conflict", "当前资源记录不允许重复启动", 409)
            initial = self.context.with_execution_scope(
                ExecutionScope(
                    scope_id=current.scope_id,
                    actor_id=current.actor_id,
                    grant_id=current.id,
                    purpose="interactive",
                    max_gpu_devices=max(1, current.gpu_slots),
                    max_candidates_per_job=current.max_candidates,
                )
            )
            initial.ensure_layout()
            model_config = service.gateway.config()
            secret_names = sorted(
                {p.secret_env for p in [model_config.default, *model_config.roles.values()]}
            )
            allowed_environment = {
                "PATH",
                "LANG",
                "LC_ALL",
                "LC_CTYPE",
                "TZ",
                "LD_LIBRARY_PATH",
            } | set(secret_names)
            environment = {
                name: value for name, value in os.environ.items() if name in allowed_environment
            }
            environment.update(initial.child_environment())
            environment["PYTHONUNBUFFERED"] = "1"
            environment["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
            config = {
                "grant_id": current.id,
                "scope_id": current.scope_id,
                "request_id": current.request_id,
                "actor_id": current.actor_id,
                "scientific_actor_id": current.scientific_actor_id,
                "models": str(service.gateway.models_path.relative_to(self.context.root)),
                "prediction_backend": service.gateway.prediction_backend,
                "assignment": str(
                    self.pool.assignment_path(current.id).relative_to(self.context.root)
                ),
                "secret_names": secret_names,
            }
            config_path = (
                self.context.runtime_root / "state/accounts/worker-config" / (current.id + ".json")
            )
            immutable_json(config_path, config)
            log_path = initial.runtime_root / "logs/product" / (current.id + ".log")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("ab") as log:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-B",
                        "-m",
                        "easydesign.product.scoped_worker",
                        str(config_path),
                    ],
                    cwd=self.context.root,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
            start = process_identity(process.pid)
            if start is None:
                self.ledger.transition(current.id, "failed", reason="worker_start_failed")
                raise ProductError("worker_start_failed", "执行进程未能启动", 503)
            self.ledger.transition(current.id, "queued", worker_pid=process.pid, worker_start=start)

    def _service(self, admission: Admission) -> tuple[WorkspaceContext, ProductService]:
        context = self.context.with_execution_scope(
            ExecutionScope(
                scope_id=admission.scope_id,
                actor_id=admission.actor_id,
                purpose="interactive",
            )
        )
        gateway = self.runtime.gateway_factory(context)
        return context, ProductService(gateway, actor="account:" + admission.scientific_actor_id)

    def tick(self) -> None:
        with self._lock:
            # One GPU observation per poll is shared by every queued admission.
            memo: list[Any] = []
            for admission in self.ledger.active():
                try:
                    self._tick_one(admission, memo)
                except ProductError as error:
                    if error.code == "allocation_conflict":
                        # A corrupt device/assignment identity must quarantine only
                        # its own admission; raising would starve every other queued
                        # request on this poll and on all later polls.
                        self.ledger.transition(
                            admission.id, "held", reason="allocation_identity_mismatch"
                        )
                    else:
                        raise

    def _tick_one(self, admission: Admission, memo: list[Any]) -> None:
        if admission.worker_pid is None:
            if self.runtime.accounts.clock() - admission.created_at > 30:
                self.ledger.transition(admission.id, "failed", reason="worker_not_published")
                # A controller crash between spawning a worker and publishing its
                # PID can leave an orphan waiting on this assignment. Publish an
                # abandonment marker so it exits promptly; the request journal is
                # deliberately untouched and stays recoverable through resume.
                assignment_path = self.pool.assignment_path(admission.id)
                if not assignment_path.exists():
                    immutable_json(
                        assignment_path,
                        {
                            "grant_id": admission.id,
                            "cancelled": True,
                            "code": "admission_abandoned",
                        },
                    )
            return
        alive = (
            admission.worker_start is not None
            and process_identity(admission.worker_pid) == admission.worker_start
        )
        if not alive:
            context, service = self._service(admission)
            try:
                with context.activate():
                    active = native_active(service, admission.request_id)
            except Exception:
                self.ledger.transition(admission.id, "held", reason="native_state_unavailable")
                return
            if active:
                self.ledger.transition(admission.id, "held", reason="native_job_still_active")
                return
            journal = service.journal()
            try:
                record = journal.get(admission.request_id)
            finally:
                journal.close()
            self.pool.release(admission.id)
            state = "released" if record and record["state"] == "succeeded" else "failed"
            self.ledger.transition(
                admission.id,
                state,
                reason=None if state == "released" else "worker_finished_without_success",
            )
            return
        if admission.state not in {"queued", "starting"}:
            return
        assignment_path = self.pool.assignment_path(admission.id)
        if assignment_path.is_file():
            assigned = json.loads(assignment_path.read_text())
            if assigned.get("grant_id") != admission.id:
                raise ProductError("allocation_conflict", "资源记录身份不匹配", 409)
            if assigned.get("cancelled"):
                self.pool.release(admission.id)
                self.ledger.transition(admission.id, "cancelled", reason="authorization_revoked")
            else:
                scope = load_scope(
                    runtime_root=self.context.runtime_root,
                    declaration_path=self.context.declaration_path,
                    path=self.context.root / assigned["scope_file"],
                )
                if scope.grant_id != admission.id:
                    raise ProductError("allocation_conflict", "执行身份与资源记录不匹配", 409)
                self.ledger.transition(admission.id, "running", devices=scope.devices)
            return
        try:
            actor = self.runtime.accounts.user(admission.actor_id)
            self.runtime.accounts.scope(
                actor,
                admission.scope_id,
                edit=True,
                execute=admission.kind == "scientific",
            )
        except ProductError:
            immutable_json(
                self.pool.assignment_path(admission.id),
                {
                    "grant_id": admission.id,
                    "cancelled": True,
                    "code": "authorization_revoked",
                },
            )
            self.pool.release(admission.id)
            self.ledger.transition(admission.id, "cancelled", reason="authorization_revoked")
            return
        devices: tuple[int, ...] = ()
        if admission.kind == "scientific":
            if not memo:
                try:
                    memo.append(self.probe.snapshots())
                except Exception:
                    # GPU observation failure must not block CPU-only conversations.
                    return
            allocation = self.pool.allocate(admission, memo[0])
            if allocation is None:
                return
            devices = allocation.devices
        scope = ExecutionScope(
            scope_id=admission.scope_id,
            actor_id=admission.actor_id,
            purpose="scientific" if devices else "conversation",
            grant_id=admission.id,
            devices=devices,
            max_gpu_devices=max(1, admission.gpu_slots),
            max_candidates_per_job=admission.max_candidates,
        )
        context = self.context.with_execution_scope(scope)
        assert context.execution_scope_path is not None
        immutable_json(
            self.pool.assignment_path(admission.id),
            {
                "grant_id": admission.id,
                "scope_file": str(context.execution_scope_path.relative_to(self.context.root)),
            },
        )
        self.ledger.transition(admission.id, "running", devices=devices)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                # Observation/admission trouble does not release devices or rewrite
                # scientific outcomes. The next bounded poll retries the controller.
                import logging

                logging.getLogger(__name__).warning("Resource admission temporarily unavailable")
            self._stop.wait(self.poll_seconds)
