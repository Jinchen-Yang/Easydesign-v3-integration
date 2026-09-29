"""Product admission and process recovery; Native Runtime still owns scientific jobs."""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import math
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from easydesign.backends.executors.local_multi_gpu import NvidiaSmiProbe
from easydesign.execution_scope import ExecutionScope, load_scope
from easydesign.workspace_context import WorkspaceContext

from .artifacts import immutable_json
from .contracts import ProductError
from .device_pool import ProductDevicePool
from .journal import RequestJournal
from .resource_control import Admission, contract_digest
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


def plan_final_design_action(
    row: dict[str, Any],
    project: dict[str, Any],
    row_facts: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Decide one held reservation from authoritative native facts only.

    A completed HTTP request is never campaign completion: reservations hold
    while native work is live, queued, resumable or uncertain, and release only
    on provable abandonment or never-applied approval. ``phase34-scale-
    inconclusive`` is NOT no-delivery evidence. Delivery is charged from the
    published checksum-verified pool, or — when no pool exists — from the
    checksum-bound batch receipts of the reservation's own campaign: a fully
    complete native campaign with complete evidence (all-FAIL qualifies) settles
    in full, while technically invalid, evidence-unknown or operationally
    incomplete campaigns hold as recoverable. A superseded campaign settles its
    verified retained population BEFORE any release is considered, so designs a
    controller missed while down are never refunded by a newer Gate-4 round.
    """
    pools = [p for p in project["pools"] if p["card_id"] == row["authority_key"]]
    if pools:
        pool = pools[-1]
        if pool["resumable"]:
            return "hold", {"reason": "resumable_batches"}
        if project["scale_jobs_active"]:
            return "hold", {"reason": "native_scale_active"}
        return "settle", {
            "campaign_sha256": pool["contract_sha256"],
            "delivered": pool["candidates"],
        }
    if project["scale_jobs_active"]:
        return "hold", {"reason": "native_scale_active"}
    authority = project["authority"]
    superseded = authority is not None and authority["card_id"] != row["authority_key"]
    receipts = project["receipt_pools"].get(row["authority_key"])
    if receipts is not None:
        if receipts.get("unverified"):
            # Missing or corrupted artifact evidence is unreadable, not absent.
            return "hold", {"reason": "receipts_unverified"}
        if superseded and receipts["native_determined"]:
            # Abandonment is proved by a newer promotion: this campaign can
            # never dispatch again, so its verified retained population —
            # complete or not — is the final delivery.
            return "settle", {
                "campaign_sha256": receipts["manifest_sha256"],
                "delivered": receipts["candidates"],
            }
        if receipts["resumable"] or receipts["failed"]:
            # Operationally incomplete or inconclusive: recoverable by contract,
            # never proof of no delivery.
            return "hold", {"reason": "campaign_incomplete"}
        if not receipts["native_determined"]:
            # Technical/unknown outcomes never become verified final designs —
            # not even through supersession abandonment. A newer approval
            # cannot convert unknown results into delivered designs.
            return "hold", {"reason": "evidence_undetermined"}
        # Complete durable native population (all-FAIL qualifies): charge in
        # full from the checksum-bound manifest and its batch receipts.
        return "settle", {
            "campaign_sha256": receipts["manifest_sha256"],
            "delivered": receipts["candidates"],
        }
    if superseded:
        # A newer Gate-4 promotion replaced this authority and this authority
        # never registered a campaign: nothing was ever produced under it.
        return "release", {"reason": "superseded_authority"}
    response = row_facts.get("card_response")
    if response is None or not response.get("delivered"):
        if row_facts.get("admission_active") or row_facts.get("request_state") in {
            "accepted",
            "running",
            "interrupted",
        }:
            return "hold", {"reason": "request_in_flight"}
        if row_facts.get("request_state") == "succeeded":
            return "hold", {"reason": "uncertain"}
        return "release", {"reason": "approval_not_applied"}
    return "hold", {"reason": "awaiting_campaign_outcome"}


class ResourceSupervisor:
    def __init__(
        self,
        runtime: MultiUserRuntime,
        *,
        allowed_devices: tuple[int, ...] | None = None,
        probe: Any = None,
        poll_seconds: float = 1.0,
        max_conversation_workers: int = 8,
        startup_timeout_seconds: float = 30.0,
    ) -> None:
        self.runtime = runtime
        self.context = runtime.context
        self.ledger = runtime.resources
        self.pool = ProductDevicePool(self.context, allowed_devices=allowed_devices)
        self.probe = probe or NvidiaSmiProbe()
        self.poll_seconds = poll_seconds
        if type(max_conversation_workers) is not int or not 1 <= max_conversation_workers <= 64:
            raise ValueError("max_conversation_workers must be between 1 and 64")
        if not math.isfinite(startup_timeout_seconds) or not 1 <= startup_timeout_seconds <= 60:
            raise ValueError("startup_timeout_seconds must be between 1 and 60")
        self.max_conversation_workers = max_conversation_workers
        self.startup_timeout_seconds = startup_timeout_seconds
        self._stop = threading.Event()
        self._tick_lock = threading.Lock()
        # Fixed storage for current and historical grants. Collisions only
        # serialize unrelated preparations; they never drop an admission.
        self._grant_locks = tuple(threading.RLock() for _ in range(128))
        self._thread: threading.Thread | None = None
        self._controller_lock: Any = None

    def start(self) -> None:
        if self._controller_lock is not None:
            return
        path = self.context.runtime_root / "state/accounts/supervisor.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+b")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            raise ProductError("controller_busy", "该工作区已有资源控制器", 409) from None
        self._controller_lock = handle
        try:
            # The HTTP server becomes ready after start() returns. Reclaim only
            # confirmed dead Web owners first, independent of slow GPU/native
            # observations in the background loop; never run scientific work here.
            for admission in self.ledger.active():
                if admission.dispatch_channel == "web_stream":
                    self.ledger.reconcile_web_stream_owner(admission.id)
        except BaseException:
            handle.close()
            self._controller_lock = None
            raise
        self._stop.clear()
        self.runtime.launcher = self.launch
        self._thread = threading.Thread(
            target=self._loop, name="account-resource-admission", daemon=True
        )
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=20)
            if self._thread.is_alive():
                raise ProductError("controller_busy", "资源控制器仍在安全收尾", 409)
        if self._controller_lock is not None:
            self._controller_lock.close()
            self._controller_lock = None
        # Detached scientific work is deliberately not signalled here.

    def launch(self, admission: Admission, service: ScopedProductService) -> None:
        """Commit executable intent; a queued request consumes no worker process."""
        # Direct callers need the same fence as HTTP callers: a visible config
        # must not let tick claim this grant before the queued commit below.
        with self._grant_lock(admission.id):
            current = self.ledger.get(admission.id)
            if (
                current.worker_pid is not None
                and process_identity(current.worker_pid) == current.worker_start
            ):
                return
            if current.state not in {"reserved", "queued"}:
                raise ProductError("admission_conflict", "当前资源记录不允许重复启动", 409)
            if current.state == "queued" and self._config_path(current).is_file():
                return
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
                # Stage budgets captured once at command authorization; the worker
                # never re-reads mutable admin settings for a frozen thread.
                "stage_budgets": self.ledger.command_budgets(current.scope_id, current.request_id),
                "dispatch_protocol": "durable-v1",
                "auth_version": current.auth_version,
            }
            immutable_json(self._config_path(current), config)
            self.ledger.transition(current.id, "queued", reason="waiting_for_resources")

    def _grant_lock(self, grant_id: str) -> threading.RLock:
        index = hashlib.sha256(grant_id.encode()).digest()[0] % len(self._grant_locks)
        return self._grant_locks[index]

    def _config_path(self, admission: Admission) -> Path:
        return self.context.runtime_root / "state/accounts/worker-config" / (admission.id + ".json")

    def _spawn(self, admission: Admission) -> Admission:
        config_path = self._config_path(admission)
        config = json.loads(config_path.read_text())
        initial = self.context.with_execution_scope(
            ExecutionScope(
                scope_id=admission.scope_id,
                actor_id=admission.actor_id,
                grant_id=admission.id,
                purpose="interactive",
                max_gpu_devices=max(1, admission.gpu_slots),
                max_candidates_per_job=admission.max_candidates,
            )
        )
        allowed = {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "LD_LIBRARY_PATH"}
        allowed.update(config["secret_names"])
        environment = {name: value for name, value in os.environ.items() if name in allowed}
        environment.update(initial.child_environment())
        environment.update(PYTHONUNBUFFERED="1", CUDA_DEVICE_ORDER="PCI_BUS_ID")
        log_path = initial.runtime_root / "logs/product" / (admission.id + ".log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab") as log:
            process = subprocess.Popen(
                [sys.executable, "-B", "-m", "easydesign.product.scoped_worker", str(config_path)],
                cwd=self.context.root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        start = process_identity(process.pid)
        if start is None:
            raise ProductError("worker_start_failed", "执行进程未能启动", 503)
        return self.ledger.transition(
            admission.id, "starting", worker_pid=process.pid, worker_start=start
        )

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
        # Dispatch ownership and GPU observations span the whole tick. Only
        # preparation/reconciliation of the same grant must exclude launch.
        with self._tick_lock, self._dispatch_lock():
            # One GPU observation per poll is shared by every queued admission.
            memo: list[Any] = []
            for admission in self.ledger.active():
                with self._grant_lock(admission.id):
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
            # Still inside the tick/controller fence. Launch only changes
            # reserved -> queued (both active), not scientific delivery facts.
            self._reconcile_final_designs()

    @contextmanager
    def _dispatch_lock(self) -> Iterator[None]:
        if self._controller_lock is not None:
            yield
            return
        path = self.context.runtime_root / "state/accounts/supervisor.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ProductError("controller_busy", "该工作区已有资源控制器", 409) from None
            yield

    def _final_designs_project_facts(
        self, scope_id: str, subject_id: str, project_id: str, authority_keys: set[str]
    ) -> dict[str, Any] | None:
        scoped = self.context.with_execution_scope(
            ExecutionScope(scope_id=scope_id, actor_id=subject_id, purpose="interactive")
        )
        # Native bridges discover the ambient workspace; activation keeps every
        # verified read inside this reservation's scope, exactly like a bound
        # product service.
        with scoped.activate():
            gateway = self.runtime.gateway_factory(scoped)
            with gateway.session(project_id) as session:
                bridge = session.bridge
                project_latest = getattr(bridge, "project_latest", None)
                if project_latest is None:
                    return None

                def verified_document(event: dict[str, Any]) -> dict[str, Any]:
                    # Settlement must read checksum-verified contracts; a document
                    # that does not match its published identity defers (holds).
                    contract: Any = bridge.document(event["ref"])
                    if not isinstance(contract, dict) or (
                        contract_digest(contract) != event.get("contract_sha256")
                    ):
                        raise ProductError(
                            "final_designs_unverified", "契约校验和不匹配，暂缓结算", 503
                        )
                    return contract

                authority_event = project_latest("phase34-scale-authority")
                authority = None
                if authority_event is not None:
                    contract = verified_document(authority_event)
                    authority = {
                        "card_id": contract.get("gate4_card_id"),
                        "contract_sha256": authority_event.get("contract_sha256"),
                    }
                manifests: dict[str, dict[str, Any]] = {}
                for event in bridge.store.events(bridge.thread):
                    if event["kind"] == "phase34-scale-batch-manifest":
                        contract = verified_document(event["payload"])
                        card_id = contract["campaign"]["promotion_authority"]["gate4_card_id"]
                        # Latest manifest event per reserved authority: a
                        # superseded round's manifest stays chargeable evidence.
                        manifests[card_id] = {
                            "contract_sha256": event["payload"].get("contract_sha256"),
                            "contract": contract,
                        }
                receipt_pools: dict[str, dict[str, Any]] = {}
                for key in authority_keys:
                    found = manifests.get(key)
                    if found is None:
                        continue
                    try:
                        population = self._receipt_population(bridge, found["contract"])
                        receipt_pools[key] = {
                            **population,
                            "manifest_sha256": found["contract_sha256"],
                        }
                    except Exception:
                        # Missing or corrupted evidence keeps the reservation
                        # held with a truthful reason instead of settling.
                        receipt_pools[key] = {
                            "unverified": True,
                            "manifest_sha256": found["contract_sha256"],
                        }
                pools: list[dict[str, Any]] = []
                for event in bridge.store.events(bridge.thread):
                    if event["kind"] == "phase34-global-candidate-pool":
                        contract = verified_document(event["payload"])
                        pools.append(
                            {
                                "card_id": contract["campaign"]["promotion_authority"][
                                    "gate4_card_id"
                                ],
                                "contract_sha256": event["payload"].get("contract_sha256"),
                                # Delivered unit: every retained pool candidate,
                                # scientifically negative results included.
                                "candidates": len(contract.get("candidates") or ()),
                                "resumable": bool(contract.get("resumable_batch_ids")),
                            }
                        )
                controller = getattr(bridge, "controller", None)
                if controller is None:
                    # Without the durable job controller, liveness is uncertain;
                    # the caller defers this project and reservations stay held.
                    raise ProductError("native_state_unavailable", "原生执行状态暂时无法核对", 409)
                scale_jobs_active = any(
                    str(job.status) in {"queued", "running", "dispatching", "drain-requested"}
                    and (getattr(job, "run_id", None) or "").startswith("scale-v3-")
                    for job in controller.list(project_id=bridge.project_id)
                )
                responses = {
                    key: (bridge.store.response(bridge.thread, key) if key else None)
                    for key in authority_keys
                }
                return {
                    "authority": authority,
                    "pools": pools,
                    "receipt_pools": receipt_pools,
                    "scale_jobs_active": scale_jobs_active,
                    "responses": responses,
                }

    @staticmethod
    def _receipt_population(bridge: Any, manifest_contract: dict[str, Any]) -> dict[str, Any]:
        """Verified durable Scale population from the native batch receipt API.

        Reads the checksum-bound manifest journal exactly as the native runtime
        does and verifies every retained candidate's artifact refs against the
        run declared by its receipt (the same ``bridge.run``/``ref.verify``
        pattern ``finalize_scale_inputs`` uses). Any inconsistency raises and
        the reservation stays held. Never scans artifact directories and never
        mutates native evidence: a missing manifest journal is unreadable
        state, not something to recreate. ``native_determined`` reuses the
        native completeness criterion from ``finalize_scale_inputs``: only a
        fully populated native campaign whose every candidate carries complete
        evidence counts as scientifically determined (an all-FAIL population
        qualifies); technical/unknown outcomes and legacy zero-evaluable
        populations do not.
        """
        from easydesign.agent.phase34_batches import ScaleBatchManifest, ScaleBatchStore
        from easydesign.agent.phase34_contracts import ExecutionMode
        from easydesign.agent.session_store import confined

        campaign_id = manifest_contract["campaign"]["campaign_id"]
        root = confined(bridge.project, bridge.project / "agent/phase34-scale" / campaign_id)
        if not (root / "manifest.json").is_file():
            raise ProductError("final_designs_unverified", "Scale 批次台账缺失，暂缓结算", 503)
        manifest = ScaleBatchManifest.model_validate(manifest_contract)
        journal = ScaleBatchStore(root, manifest)
        pool = journal.pool()
        synthetic = pool.campaign.execution.mode is ExecutionMode.SYNTHETIC_STRESS
        for batch_id in pool.completed_batch_ids:
            receipt = journal.read(batch_id)
            if receipt is None:
                continue
            for candidate in receipt.candidates:
                if not receipt.source_run_id:
                    # Real Scale candidates must declare their source run, the
                    # same boundary the native finalizer enforces.
                    if not synthetic:
                        raise ProductError(
                            "final_designs_unverified", "Scale 候选缺少来源 run", 503
                        )
                    continue
                run_root, _unused = bridge.run(receipt.source_run_id)
                for ref in candidate.lineage.artifact_refs:
                    ref.verify(run_root)
        candidates = pool.candidates
        native = pool.campaign.evidence_policy == "boltzgen-native-v1"
        complete_evidence = bool(candidates) and all(
            item.native_evidence is not None and item.native_evidence.native_pass is not None
            for item in candidates
        )
        return {
            "candidates": len(candidates),
            "resumable": len(pool.resumable_batch_ids),
            "failed": len(pool.failed_batch_ids),
            "native_determined": native and complete_evidence,
        }

    def _reconcile_final_designs(self) -> None:
        rows = self.ledger.reserved_final_designs()
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in rows:
            groups.setdefault((row["scope_id"], row["project_id"]), []).append(row)
        for (scope_id, project_id), entries in groups.items():
            journal: RequestJournal | None = None
            try:
                facts = self._final_designs_project_facts(
                    scope_id,
                    entries[0]["subject_id"],
                    project_id,
                    {row["authority_key"] for row in entries},
                )
                if facts is None:
                    continue
                # The request journal lives in the scope-remapped runtime root.
                scoped = self.context.with_execution_scope(
                    ExecutionScope(
                        scope_id=scope_id,
                        actor_id=entries[0]["subject_id"],
                        purpose="interactive",
                    )
                )
                journal = RequestJournal(scoped.runtime_root / "state/product/requests.sqlite")
                for row in entries:
                    request = journal.get(row["request_id"])
                    row_facts = {
                        "card_response": facts["responses"].get(row["authority_key"]),
                        "request_state": None if request is None else request["state"],
                        "admission_active": self.ledger.request_admission_active(
                            scope_id, row["request_id"]
                        ),
                    }
                    decision, payload = plan_final_design_action(row, facts, row_facts)
                    try:
                        if decision == "settle":
                            self.ledger.settle_final_designs(
                                row["id"],
                                campaign_sha256=payload["campaign_sha256"],
                                delivered=payload["delivered"],
                            )
                        elif decision == "release":
                            self.ledger.release_final_designs(row["id"], payload["reason"])
                        else:
                            self.ledger.note_final_designs_hold(row["id"], payload["reason"])
                    except ProductError as error:
                        if error.code not in {
                            "campaign_mismatch",
                            "final_designs_already_settled",
                            "final_designs_not_held",
                        }:
                            raise
                        self.ledger.note_final_designs_hold(row["id"], error.code)
            except Exception:
                # Unreadable native state stays held; observation trouble must
                # never release or settle a reservation on guesswork.
                logging.getLogger(__name__).warning(
                    "Final-design reconciliation deferred: %s/%s", scope_id, project_id
                )
            finally:
                if journal is not None:
                    journal.close()

    def _tick_one(self, admission: Admission, memo: list[Any]) -> None:
        if admission.dispatch_channel == "web_stream":
            self.ledger.reconcile_web_stream_owner(admission.id)
            return  # Only quota recovery; Web streaming still owns execution.
        context, service = self._service(admission)
        # Serialize cross-store preparation/cancellation/retry with dispatch.
        # A still-running HTTP prepare is never mistaken for an abandoned intent.
        path = service.root / "commands" / (admission.request_id + ".lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            admission = self.ledger.get(admission.id)
            if admission.state in {"failed", "cancelled", "released"}:
                return
            self._reconcile_one(admission, memo, context, service)

    def _reconcile_one(
        self,
        admission: Admission,
        memo: list[Any],
        context: WorkspaceContext,
        service: ProductService,
    ) -> None:
        if admission.dispatch_channel == "scoped_worker" and admission.state == "reserved":
            config_path = self._config_path(admission)
            if config_path.is_file():
                config = json.loads(config_path.read_text())
                if (
                    any(
                        config.get(key) != getattr(admission, key)
                        for key in ("scope_id", "request_id", "actor_id", "scientific_actor_id")
                    )
                    or config.get("grant_id") != admission.id
                    or config.get("dispatch_protocol") != "durable-v1"
                ):
                    raise ProductError("allocation_conflict", "执行配置身份不匹配", 409)
                journal = service.journal()
                try:
                    record = journal.get(admission.request_id)
                finally:
                    journal.close()
                if record is None or record["state"] != "accepted":
                    self._finish_unstarted(admission, "request_not_ready", service)
                    return
                admission = self.ledger.transition(
                    admission.id, "queued", reason="waiting_for_resources"
                )
            else:
                if (
                    self.runtime.accounts.clock() - admission.created_at
                    > self.startup_timeout_seconds
                ):
                    self._finish_unstarted(admission, "submission_incomplete", service)
                return
        if admission.state == "starting" and admission.worker_pid is None:
            receipt_path = service.root / "workers" / (admission.id + ".started.json")
            if receipt_path.is_file():
                receipt = json.loads(receipt_path.read_text())
                if (
                    receipt.get("grant_id") != admission.id
                    or receipt.get("request_id") != admission.request_id
                    or type(receipt.get("pid")) is not int
                    or not isinstance(receipt.get("start"), str)
                ):
                    raise ProductError("allocation_conflict", "启动回执身份不匹配", 409)
                if process_identity(receipt["pid"]) == receipt["start"]:
                    try:
                        command = (
                            Path(f"/proc/{receipt['pid']}/cmdline").read_bytes().split(b"\0")[:-1]
                        )
                    except OSError:
                        return  # Unobservable process identity is not dispatch authority.
                    expected = [
                        os.fsencode(sys.executable),
                        b"-B",
                        b"-m",
                        b"easydesign.product.scoped_worker",
                        os.fsencode(self._config_path(admission)),
                    ]
                    if command != expected:
                        raise ProductError("allocation_conflict", "启动回执进程身份不匹配", 409)
                    admission = self.ledger.transition(
                        admission.id,
                        "starting",
                        worker_pid=receipt["pid"],
                        worker_start=receipt["start"],
                    )
            if admission.worker_pid is None:
                if (
                    self.runtime.accounts.clock() - admission.updated_at
                    > self.startup_timeout_seconds
                ):
                    self._finish_unstarted(admission, "worker_start_timeout", service)
                return
        pending = admission.worker_pid is None and admission.state == "queued"
        if pending and self._config_path(admission).is_file():
            if not self._authorized(admission):
                self._finish_unstarted(admission, "authorization_revoked", service, cancelled=True)
                return
            request_lock = service.root / "workers" / (admission.request_id + ".lock")
            request_lock.parent.mkdir(parents=True, exist_ok=True)
            with request_lock.open("a") as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return  # A legacy/orphan worker still owns this scientific request.
                journal = service.journal()
                try:
                    record = journal.get(admission.request_id)
                finally:
                    journal.close()
                if record is None or record["state"] != "accepted":
                    self.ledger.transition(admission.id, "held", reason="request_state_uncertain")
                    return
            # No process is created merely to wait for a GPU. Allocation and
            # dispatch retain the native device lease authority below.
            if admission.kind == "scientific":
                if not memo:
                    try:
                        memo.append(self.probe.snapshots())
                    except Exception:
                        return
                if self.pool.allocate(admission, memo[0]) is None:
                    return
            try:
                claimed = self.ledger.claim_start(
                    admission.id, max_conversation_workers=self.max_conversation_workers
                )
            except ProductError:
                self._finish_unstarted(admission, "authorization_revoked", service, cancelled=True)
                return
            if claimed is None:
                self.pool.release(admission.id)
                return
            admission = self._spawn(claimed)
        if admission.worker_pid is None:
            if admission.state == "held":
                return  # Quarantine is not an unpublished-worker timeout.
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
                if admission.dispatch_channel == "scoped_worker":
                    try:
                        self.ledger.start_execution(admission.id, scope.devices, lambda: None)
                    except ProductError:
                        self.ledger.transition(admission.id, "held", reason="authorization_revoked")
                else:
                    self.ledger.transition(admission.id, "running", devices=scope.devices)
            return
        if not self._authorized(admission):
            self._finish_unstarted(admission, "authorization_revoked", service, cancelled=True)
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
        assignment = {
            "grant_id": admission.id,
            "scope_file": str(context.execution_scope_path.relative_to(self.context.root)),
        }
        if admission.dispatch_channel == "scoped_worker":
            try:
                self.ledger.start_execution(
                    admission.id,
                    devices,
                    lambda: immutable_json(self.pool.assignment_path(admission.id), assignment),
                )
            except ProductError:
                self._finish_unstarted(admission, "authorization_revoked", service, cancelled=True)
        else:
            immutable_json(self.pool.assignment_path(admission.id), assignment)
            self.ledger.transition(admission.id, "running", devices=devices)

    def _authorized(self, admission: Admission) -> bool:
        try:
            self.ledger.authorize_dispatch(admission)
        except ProductError:
            return False
        return True

    def _finish_unstarted(
        self,
        admission: Admission,
        reason: str,
        service: ProductService,
        *,
        cancelled: bool = False,
    ) -> None:
        """Fence this attempt before freeing capacity; no execution assignment may exist."""
        assignment = self.pool.assignment_path(admission.id)
        if assignment.exists():
            self.ledger.transition(
                admission.id, "held", reason="assignment_requires_reconciliation"
            )
            return
        self.ledger.transition(admission.id, "cancelled" if cancelled else "failed", reason=reason)
        immutable_json(assignment, {"grant_id": admission.id, "cancelled": True, "code": reason})
        self.pool.release(admission.id)
        journal = service.journal()
        try:
            row = journal.get(admission.request_id)
            if row is not None and row["state"] in {"accepted", "running"}:
                journal.update(
                    admission.request_id,
                    "failed",
                    {
                        "code": reason,
                        "message": "未启动科学计算；请核对权限或恢复该请求",
                    },
                )
        finally:
            journal.close()

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
