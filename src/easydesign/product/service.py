"""Product requests, native project creation and detached local session execution."""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.harness import fingerprint
from easydesign.agent.phase34_contracts import WetLabHandoffPackage
from easydesign.agent.phase34_runtime import Phase34Runtime
from easydesign.agent.session_store import SessionStore
from easydesign.core import ArtifactRef, sha256_file
from easydesign.core.errors import ContractError
from easydesign.orchestration.research import initialize_research_project
from easydesign.orchestration.stage01_sources import (
    resolve_unique_reviewed_uniprot_seed,
)

from .artifacts import ArtifactCatalog, confined_bytes, digest, immutable_bytes, immutable_json
from .contracts import (
    ActionRequest,
    ArtifactTargetInput,
    CreateProject,
    DescriptionTargetInput,
    PDBTargetInput,
    ProductError,
    ProjectView,
    ProteinNameTargetInput,
    UniProtTargetInput,
    WorkbenchProjection,
)
from .conversation import answer, messages
from .domain import NativeGateway, decision_view
from .journal import RequestJournal
from .lab_order import LabOrderCommand, LabOrderStore, MockLabProvider
from .projection import (
    activity,
    activity_rows,
    activity_tasks,
    candidate_page,
    project_view,
    workbench,
)


class ProductService:
    def __init__(
        self,
        gateway: NativeGateway,
        *,
        actor: str = "local-scientist",
        launcher: Callable[[str], None] | None = None,
    ) -> None:
        self.gateway, self.context, self.actor = gateway, gateway.context, actor
        self.root = self.context.runtime_root / "state/product"
        self.root.mkdir(parents=True, exist_ok=True)
        self.catalog = ArtifactCatalog(self.context.root, self.root / "artifacts")
        self.launcher = launcher or self.launch
        self._cache_lock = threading.Lock()
        self._stable_snapshots: dict[str, dict[str, Any]] = {}
        self._compact_candidate_pages: dict[
            tuple[str, int, int, str | None, str | None], dict[str, Any]
        ] = {}

    def _invalidate_projection_cache(self, project: str) -> None:
        with self._cache_lock:
            self._stable_snapshots.pop(project, None)
            for key in [key for key in self._compact_candidate_pages if key[0] == project]:
                self._compact_candidate_pages.pop(key, None)

    def _remember_project_view(self, project: str, value: dict[str, Any]) -> None:
        journal = self.journal()
        try:
            if journal.project(project) is not None:
                journal.update_projection(project, value)
        finally:
            journal.close()

    def journal(self) -> RequestJournal:
        return RequestJournal(self.root / "requests.sqlite")

    def order_store(self) -> LabOrderStore:
        return LabOrderStore(
            self.root / "lab-orders.sqlite", self.root / "lab-order-receipts"
        )

    @staticmethod
    def _current_handoff(session: Any) -> WetLabHandoffPackage:
        bridge = session.bridge
        if not isinstance(bridge, Phase34Runtime):
            raise ProductError(
                "gate5_required", "A current Gate 5 handoff is required", 409
            )
        event = bridge.project_latest("phase34-wet-lab-handoff")
        if event is None:
            raise ProductError(
                "gate5_required", "A current Gate 5 handoff is required", 409
            )
        return WetLabHandoffPackage.model_validate(bridge.document(event["ref"]))

    def lab_order(self, project: str) -> dict[str, Any]:
        with self.gateway.session(project) as session:
            handoff = self._current_handoff(session)
        store = self.order_store()
        try:
            return store.view(project, handoff)
        finally:
            store.close()

    def apply_lab_order(self, project: str, command: LabOrderCommand) -> dict[str, Any]:
        self._invalidate_projection_cache(project)
        with self.gateway.session(project) as session:
            handoff = self._current_handoff(session)
        store = self.order_store()
        try:
            return store.apply(
                project=project,
                handoff=handoff,
                command=command,
                provider=MockLabProvider(),
            )
        finally:
            store.close()

    @staticmethod
    def public_request(row: dict[str, Any]) -> dict[str, Any]:
        return {
            **{key: row[key] for key in ("id", "project", "state", "result", "created", "updated")},
            "kind": row["payload"].get("operation", "action"),
        }

    @staticmethod
    def _thread(request_id: str) -> str:
        return "workbench-" + digest(request_id)[:24]

    @staticmethod
    def _activity(
        store: SessionStore,
        thread: str,
        event_type: str,
        *,
        task_id: str,
        title: str,
        status: str,
        summary: str,
        specialist: str | None = None,
        progress: dict[str, Any] | None = None,
        phase: str = "target",
    ) -> None:
        for event in reversed(store.events(thread)):
            if event["kind"] != "product-activity":
                continue
            payload = event["payload"]
            if (
                payload.get("task_id") == task_id
                and payload.get("type") == event_type
                and payload.get("status") == status
                and payload.get("summary") == summary
            ):
                return
        store.event(
            thread,
            "product-activity",
            {
                "type": event_type,
                "task_id": task_id,
                "title": title,
                "status": status,
                "summary": summary,
                "phase": phase,
                "specialist": specialist,
                **({"progress": progress} if progress else {}),
            },
        )

    @staticmethod
    def _failure_context(store: SessionStore, thread: str) -> dict[str, str]:
        specialist = "target-intelligence"
        for event in reversed(store.events(thread)):
            if event["kind"] not in {"runtime-action-timing", "runtime-dispatch"}:
                continue
            candidate = event["payload"].get("specialist")
            if candidate:
                specialist = str(candidate)
                break
        if specialist == "site-mechanism":
            return {
                "phase": "site",
                "task_id": "site-research",
                "title": "Site Intelligence",
                "specialist": "site",
                "project_message": (
                    "Site research paused; retained evidence and recovery state can be retried."
                ),
            }
        if specialist == "binder-strategy":
            return {
                "phase": "design",
                "task_id": "design-research",
                "title": "Design Intelligence",
                "specialist": "binder",
                "project_message": (
                    "Design research paused; retained evidence and recovery state can be retried."
                ),
            }
        return {
            "phase": "target",
            "task_id": "target-bootstrap",
            "title": "Target Intelligence",
            "specialist": "target",
            "project_message": (
                "Target research paused; retained evidence and recovery state can be retried."
            ),
        }

    def rename(self, project: str, title: str) -> dict[str, str]:
        title = title.strip()
        if not title or len(title) > 80:
            raise ProductError("invalid_title", "Use a project name between 1 and 80 characters")
        self._invalidate_projection_cache(project)
        journal = self.journal()
        try:
            registered = journal.project(project)
            deleted = journal.project(project, include_deleted=True)
            if registered is None and deleted is not None:
                raise ProductError("not_found", "Unknown project", 404)
            if registered is None:
                with self.gateway.session(project):
                    pass  # Verify an accessible native session without changing it.
            with journal.db:
                journal.db.execute(
                    "INSERT INTO project_labels VALUES(?,?) ON CONFLICT(project) "
                    "DO UPDATE SET title=excluded.title",
                    (project, title),
                )
            if registered is not None:
                journal.rename_project(project, title)
        finally:
            journal.close()
        return {"id": project, "title": title}

    def delete(self, project: str) -> dict[str, Any]:
        self._invalidate_projection_cache(project)
        journal = self.journal()
        try:
            return journal.delete_easy_project(project)
        finally:
            journal.close()

    def title(self, session: Any) -> str | None:
        journal = self.journal()
        try:
            label = journal.db.execute(
                "SELECT title FROM project_labels WHERE project=?",
                (session.project,),
            ).fetchone()
            if label:
                return str(label[0])
        finally:
            journal.close()
        row = session.bridge.store.db.execute(
            "SELECT payload FROM events WHERE kind='product-title' ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return json.loads(row[0])["title"] if row else None

    def _bootstrap_project_view(self, value: dict[str, Any]) -> ProjectView:
        root = self.context.projects_root / value["id"]
        last_activity = 0
        if (root / "metadata/agent.sqlite").is_file():
            store = SessionStore(root)
            try:
                row = store.db.execute(
                    "SELECT COALESCE(MAX(seq),0) FROM events WHERE thread=?",
                    (value["thread"],),
                ).fetchone()
                last_activity = int(row[0])
            finally:
                store.close()
        status = {
            "project_created": "running",
            "target_discovery_running": "running",
            "target_resolution_pending": "blocked",
            "target_decision_pending": "awaiting_scientist",
            "gate1_awaiting_scientist": "awaiting_scientist",
            "failed": "blocked",
        }.get(value["state"], "running")
        return ProjectView(
            id=value["id"],
            title=value["title"],
            goal=value["goal"],
            thread_id=value["thread"],
            phase="target",
            status=status,
            last_activity=last_activity,
            notice=(value["detail"].get("message") if value["state"] == "failed" else None),
        )

    def projects(
        self, offset: int = 0, limit: int = 30, *, surface: str | None = None
    ) -> dict[str, Any]:
        if surface not in {None, "professional", "easy"}:
            raise ProductError("invalid_filter", "Unknown product surface", 400)
        journal = self.journal()
        try:
            registered = {
                row["id"]: row
                for row in journal.projects()
                if surface is None or row.get("surface") == surface
            }
        finally:
            journal.close()
        names = (
            sorted(set(self.gateway.projects()) | set(registered))
            if surface is None
            else sorted(registered)
        )
        items = []
        for project in names:
            registered_project = registered.get(project)
            if surface is not None and registered_project is not None:
                cached = registered_project.get("projection")
                if isinstance(cached, dict):
                    view = ProjectView.model_validate(cached).model_copy(
                        update={
                            "title": registered_project["title"],
                            "goal": registered_project["goal"],
                        }
                    )
                    if view.status != "unavailable":
                        items.append(view.model_dump(mode="json"))
                    continue
            try:
                if (self.context.projects_root / project / "PROJECT.yaml").is_file():
                    with self.gateway.session(project) as session:
                        view = project_view(session, self.title(session))
                else:
                    view = self._bootstrap_project_view(registered[project])
                if registered_project is not None:
                    view = view.model_copy(
                        update={
                            "title": registered_project["title"],
                            "goal": registered_project["goal"],
                        }
                    )
                    self._remember_project_view(project, view.model_dump(mode="json"))
                items.append(view.model_dump(mode="json"))
            except (
                ProductError,
                AgentBoundaryError,
                ContractError,
                ValidationError,
                sqlite3.DatabaseError,
                OSError,
            ) as error:
                logging.getLogger(__name__).warning(
                    "Project projection unavailable: %s (%s)", project, type(error).__name__
                )
                if surface is not None:
                    # A surface-scoped user list contains usable product projects only.
                    # The canonical project remains intact and directly addressable for repair.
                    if registered_project is not None:
                        self._remember_project_view(
                            project,
                            ProjectView(
                                id=project,
                                title=registered_project["title"],
                                goal=registered_project["goal"],
                                thread_id=registered_project["thread"],
                                phase="target",
                                status="unavailable",
                                last_activity=0,
                                notice=(
                                    error.code
                                    if isinstance(error, ProductError)
                                    else "incompatible_session"
                                ),
                            ).model_dump(mode="json"),
                        )
                    continue
                items.append(
                    {
                        "id": project,
                        "title": project,
                        "goal": "",
                        "thread_id": None,
                        "phase": "target",
                        "status": "unavailable",
                        "last_activity": 0,
                        "validation_only": False,
                        "notice": error.code
                        if isinstance(error, ProductError)
                        else "incompatible_session",
                    }
                )
        items.sort(key=lambda item: (-int(item["last_activity"]), item["id"]))
        return {
            "total": len(items),
            "offset": offset,
            "limit": limit,
            "items": items[offset : offset + limit],
        }

    def _bootstrap_snapshot(self, registered: dict[str, Any]) -> dict[str, Any]:
        root = self.context.projects_root / registered["id"]
        store = SessionStore(root)
        try:
            events = activity_rows(store, registered["thread"], limit=100, recent=True)
            project = self._bootstrap_project_view(registered)
        finally:
            store.close()
        state = registered["state"]
        target_status = (
            "awaiting_scientist"
            if state in {"target_decision_pending", "gate1_awaiting_scientist"}
            else "blocked"
            if state in {"target_resolution_pending", "failed"}
            else "running"
        )
        milestones = [
            ("Interpret biological goal", state != "project_created"),
            (
                "Resolve target identity",
                state
                in {
                    "target_decision_pending",
                    "gate1_awaiting_scientist",
                    "scientific_project",
                },
            ),
            (
                "Survey structure inventory",
                state in {"target_decision_pending", "gate1_awaiting_scientist"},
            ),
            ("Scientist structure decision", state == "gate1_awaiting_scientist"),
        ]
        workflow: list[dict[str, Any]] = [
            {
                "id": "goal",
                "label": "Goal",
                "status": "complete",
                "gate": None,
                "subtasks": [{"label": "Research goal recorded", "status": "complete"}],
            },
            {
                "id": "target",
                "label": "Target",
                "status": target_status,
                "gate": 1,
                "subtasks": [
                    {"label": label, "status": "complete" if done else "waiting"}
                    for label, done in milestones
                ],
            },
            *[
                {
                    "id": phase,
                    "label": phase.title(),
                    "status": "locked",
                    "gate": gate,
                    "subtasks": [],
                }
                for phase, gate in (
                    ("site", 2),
                    ("design", 3),
                    ("pilot", 4),
                    ("scale", None),
                    ("candidates", 5),
                    ("handoff", None),
                )
            ],
        ]
        detail = registered["detail"]
        value = WorkbenchProjection(
            revision=digest(
                {
                    "project": registered["id"],
                    "state": state,
                    "cursor": project.last_activity,
                    "detail": detail,
                }
            ),
            project=project,
            workflow=workflow,
            current_action={
                "id": state,
                "stage": state,
                "message": detail.get("message")
                or "Target Intelligence is resolving identity and structure evidence.",
                "resumable": False,
            },
            specialists=[
                {
                    "role": "target",
                    "status": "failed" if state == "failed" else "running",
                }
            ],
            scientific_context={
                "target": detail.get("target_intent"),
                "structure": None,
                "sites": [],
                "arms": [],
                "authority": "unresolved",
            },
            decision=None,
            jobs=[],
            artifacts=[],
            recent_activity=events,
            tasks=activity_tasks(events),
            lifecycle=state,
            event_cursor=project.last_activity,
            candidates={
                "total": 0,
                "counts": {},
                "url": f"/api/v1/projects/{registered['id']}/candidates",
            },
            capabilities={
                "demo_controls": False,
                "lab_order": False,
                "decide": False,
                "message": False,
                "resume": False,
            },
        ).model_dump(mode="json")
        return value

    def snapshot(self, project: str) -> dict[str, Any]:
        journal = self.journal()
        try:
            registered = journal.project(project, include_deleted=True)
        finally:
            journal.close()
        if registered is not None and registered.get("deleted_at") is not None:
            raise ProductError("not_found", "Unknown project", 404)
        with self._cache_lock:
            cached = self._stable_snapshots.get(project)
        # A native turn can publish its awaiting-scientist action immediately
        # before the immutable decision card becomes visible to a concurrent
        # projection read.  That transitional shell is useful for a live poll,
        # but it is not a stable product state: caching it would hide the card
        # after it is committed and leave the UI permanently asking to refresh.
        cached_awaiting_without_card = (
            cached is not None
            and cached.get("project", {}).get("status") == "awaiting_scientist"
            and cached.get("decision") is None
        )
        if cached is not None and not cached_awaiting_without_card:
            return deepcopy(cached)
        if (
            registered is not None
            and not (self.context.projects_root / project / "PROJECT.yaml").is_file()
        ):
            value = self._bootstrap_snapshot(registered)
        else:
            with self.gateway.session(project) as session:
                value = workbench(session, self.catalog, self.title(session)).model_dump(
                    mode="json"
                )
            if registered is not None:
                value["lifecycle"] = registered["state"]
                if registered["state"] == "failed":
                    value["project"]["status"] = "blocked"
                    value["project"]["notice"] = registered["detail"].get("message")
        journal = self.journal()
        try:
            requests = [self.request(r["id"]) for r in journal.for_project(project)]
            value["conversation"].extend(messages(journal, project))
        finally:
            journal.close()
        value["requests"] = requests
        value["capabilities"]["message"] = value["capabilities"]["message"] and not any(
            r["kind"] == "conversation" and r["state"] in {"accepted", "running"} for r in requests
        )
        active = next(
            (
                r
                for r in requests
                if r["kind"] != "conversation" and r["state"] in {"accepted", "running"}
            ),
            None,
        )
        if active:
            value["project"]["status"] = "running"
            value["capabilities"]["resume"] = False
            value["capabilities"]["decide"] = False
            for phase in value["workflow"]:
                if phase["id"] == value["project"]["phase"]:
                    phase["status"] = "running"
        try:
            value["lab_order"] = self.lab_order(project)
        except ProductError as error:
            if error.code not in {"gate5_required", "no_agent_session", "not_found"}:
                raise
            value["lab_order"] = None
        value["capabilities"]["lab_order"] = value["lab_order"] is not None
        value["connection"] = "connected"
        self._remember_project_view(project, value["project"])
        active_request = any(
            request["state"] in {"accepted", "running"} for request in value["requests"]
        )
        stable_scientist_state = not (
            value["project"]["status"] == "awaiting_scientist"
            and value.get("decision") is None
        )
        if not active_request and stable_scientist_state and value["project"]["status"] in {
            "awaiting_scientist",
            "available",
            "complete",
            "blocked",
        }:
            with self._cache_lock:
                self._stable_snapshots[project] = deepcopy(value)
        return value

    def candidates(
        self,
        project: str,
        offset: int,
        limit: int,
        candidate: str | None = None,
        *,
        compact: bool = False,
        phase: str | None = None,
    ) -> dict[str, Any]:
        key = (project, offset, limit, candidate, phase)
        if compact:
            with self._cache_lock:
                cached = self._compact_candidate_pages.get(key)
            if cached is not None:
                return deepcopy(cached)
        with self.gateway.session(project) as session:
            value = candidate_page(
                session,
                self.catalog,
                offset,
                limit,
                candidate,
                compact=compact,
                phase=phase,
            ).model_dump(mode="json")
        if compact:
            # Candidate pages are cached only after the same server instance has
            # observed a stable snapshot with no active request. All product
            # mutations invalidate both caches before dispatch.
            with self._cache_lock:
                if project in self._stable_snapshots:
                    self._compact_candidate_pages[key] = deepcopy(value)
        return value

    def events(self, project: str, after: int, limit: int) -> dict[str, Any]:
        journal = self.journal()
        try:
            registered = journal.project(project)
        finally:
            journal.close()
        if (
            registered is not None
            and not (self.context.projects_root / project / "PROJECT.yaml").is_file()
        ):
            store = SessionStore(self.context.projects_root / project)
            try:
                items = activity_rows(store, registered["thread"], after, limit)
            finally:
                store.close()
        else:
            with self.gateway.session(project) as session:
                items = activity(session, after, limit)
        return {"items": items, "cursor": items[-1]["id"] if items else after}

    def upload(self, filename: str, data: bytes) -> dict[str, Any]:
        suffix = Path(filename).suffix.lower()
        structure_suffixes = {".pdb", ".cif", ".mmcif"}
        sequence_suffixes = {".fa", ".faa", ".fasta"}
        if (
            suffix not in structure_suffixes | sequence_suffixes
            or not 1 <= len(data) <= 32 * 1024**2
        ):
            raise ProductError(
                "invalid_input", "Provide a PDB/mmCIF structure or FASTA sequence under 32 MiB"
            )
        kind = "structure" if suffix in structure_suffixes else "sequence"
        key = digest({"sha256": hashlib.sha256(data).hexdigest(), "format": suffix})
        directory = self.root / "inputs" / key
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (("structure" + suffix) if kind == "structure" else "sequence.fasta")
        immutable_bytes(path, data)
        if kind == "structure":
            # Verify parseability before creating a formal project. No scientific inference.
            import gemmi

            try:
                structure = gemmi.read_structure(str(path))
                if len(structure) == 0 or not any(
                    len(chain) for model in structure for chain in model
                ):
                    raise ValueError("No coordinates")
            except Exception as error:
                raise ProductError(
                    "invalid_structure", "The supplied file has no readable coordinates"
                ) from error
            file_format = suffix[1:]
        else:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ProductError(
                    "invalid_sequence", "The FASTA file must be UTF-8 text"
                ) from error
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            headers = [line for line in lines if line.startswith(">")]
            if len(headers) > 1 or (headers and not lines[0].startswith(">")):
                raise ProductError("invalid_sequence", "Provide exactly one FASTA sequence")
            sequence = "".join(line for line in lines if not line.startswith(">"))
            sequence = re.sub(r"\s+", "", sequence).upper()
            if (
                not sequence
                or len(sequence) > 20_000
                or re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWY]+", sequence) is None
            ):
                raise ProductError(
                    "invalid_sequence",
                    "Provide one sequence of at most 20,000 standard amino acids",
                )
            file_format = "fasta"
        ref = ArtifactRef.from_file(
            run_root=directory,
            relative_path=path.name,
            artifact_id="uploaded-target",
            role="user-input",
            file_format=file_format,
        )
        immutable_json(directory / "manifest.json", ref.model_dump(mode="json"))
        return {
            "id": key,
            "sha256": ref.sha256,
            "size_bytes": ref.size_bytes,
            "format": file_format,
            "kind": kind,
        }

    def submit(self, project: str, request: ActionRequest) -> dict[str, Any]:
        self._invalidate_projection_cache(project)
        journal = self.journal()
        try:
            registered = journal.project(project, include_deleted=True)
            if registered is not None and registered.get("deleted_at") is not None:
                raise ProductError("not_found", "Unknown project", 404)
            previous = journal.get(request.request_id)
            payload = {
                "operation": "conversation" if request.action == "message" else "action",
                **request.model_dump(mode="json"),
            }
            if previous:
                row, _ = journal.reserve(project, payload)
                created = (
                    journal.retry(request.request_id)
                    if row["state"] in {"failed", "interrupted"}
                    else False
                )
                if created:
                    refreshed = journal.get(request.request_id)
                    assert refreshed is not None
                    row = refreshed
            else:
                with self.gateway.session(project, write=request.action != "message") as session:
                    session.check_action(request)
                    row, created = journal.reserve(project, payload)
        finally:
            journal.close()
        if created:
            self.launcher(row["id"])
        return self.public_request(row)

    def create(self, request: CreateProject) -> dict[str, Any]:
        typed = request.target_input
        artifact_id = (
            typed.artifact_id if isinstance(typed, ArtifactTargetInput) else request.input_id
        )
        if artifact_id is not None:
            path = self.root / "inputs" / artifact_id / "manifest.json"
            if not path.is_file():
                raise ProductError("input_missing", "The optional uploaded target is unavailable")
            ref = ArtifactRef.model_validate_json(confined_bytes(path.parent, path.name))
            if isinstance(typed, ArtifactTargetInput):
                allowed = (
                    {"pdb", "cif", "mmcif"}
                    if typed.kind == "structure"
                    else {"fasta", "fa", "faa", "sequence"}
                )
                if ref.file_format not in allowed:
                    raise ProductError(
                        "input_kind_mismatch",
                        "The uploaded target does not match the declared input type",
                    )
        project = "workbench-" + digest(request.request_id)[:24]
        thread = self._thread(request.request_id)
        journal = self.journal()
        try:
            row, created = journal.reserve(
                project,
                {
                    "operation": "create",
                    **request.model_dump(mode="json", exclude_none=True),
                },
            )
            registered, registered_now = journal.register_project(
                project,
                request_id=request.request_id,
                title=request.title,
                goal=request.goal,
                thread=thread,
                input_id=artifact_id,
                surface=request.surface,
                target_input=(typed.model_dump(mode="json") if typed is not None else None),
            )
        finally:
            journal.close()
        root = self.context.projects_root / project
        root.mkdir(parents=True, exist_ok=True)
        store = SessionStore(root)
        try:
            config = self.gateway.config()
            store.thread(thread, fingerprint(config), request.goal)
            if registered_now:
                store.event(thread, "product-title", {"title": request.title})
                self._activity(
                    store,
                    thread,
                    "task.created",
                    task_id="target-bootstrap",
                    title="Target Intelligence",
                    status="pending",
                    summary="Project persisted; target identity and structure remain unresolved.",
                    specialist="target",
                )
        finally:
            store.close()
        if created:
            self.launcher(row["id"])
        return self.public_request(row)

    def request(self, request_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{16,96}", request_id):
            raise ProductError("not_found", "Unknown request", 404)
        journal = self.journal()
        try:
            row = journal.get(request_id)
            if row is None:
                raise ProductError("not_found", "Unknown request", 404)
            if row["state"] in {"accepted", "running"} and time.time() - row["updated"] > 10:
                lock = self.root / "workers" / (request_id + ".lock")
                lock.parent.mkdir(exist_ok=True)
                with lock.open("a") as handle:
                    try:
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        pass
                    else:
                        journal.update(
                            request_id,
                            "interrupted",
                            {
                                "code": "worker_interrupted",
                                "message": "Transport worker stopped; resume this request "
                                "to reconcile native state.",
                            },
                        )
                        row = journal.get(request_id)
                        assert row is not None
            return self.public_request(row)
        finally:
            journal.close()

    def retry(self, request_id: str) -> dict[str, Any]:
        row = self.request(request_id)
        if row["state"] not in {"interrupted", "failed"}:
            return row
        self._invalidate_projection_cache(row["project"])
        journal = self.journal()
        try:
            claimed = journal.retry(request_id)
        finally:
            journal.close()
        if claimed:
            self.launcher(request_id)
        return self.request(request_id)

    def launch(self, request_id: str) -> None:
        config = {
            "models": str(self.gateway.models_path.relative_to(self.context.root)),
            "prediction_backend": self.gateway.prediction_backend,
            "actor": self.actor,
        }
        config_path = self.root / "config" / (digest(config) + ".json")
        immutable_json(config_path, config)
        logs = self.context.runtime_root / "logs/product"
        logs.mkdir(parents=True, exist_ok=True)
        with (logs / (request_id + ".log")).open("ab") as log:
            subprocess.Popen(
                [sys.executable, "-m", "easydesign.product.worker", str(config_path), request_id],
                cwd=self.context.root,
                env={
                    **os.environ,
                    "EASYDESIGN_WORKSPACE": str(self.context.root),
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )

    def run(self, request_id: str) -> None:
        locks = self.root / "workers"
        locks.mkdir(exist_ok=True)
        with (locks / (request_id + ".lock")).open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            journal = self.journal()
            row: dict[str, Any] | None = None
            try:
                row = journal.get(request_id)
                if row is None or row["state"] not in {"accepted", "running", "interrupted"}:
                    return
                recovering = row["state"] != "accepted" or bool(
                    (row["result"] or {}).get("recovery")
                )
                journal.update(request_id, "running", {"recovery": recovering})
                payload = dict(row["payload"])
                operation = payload.pop("operation")
                if operation == "create":
                    journal.update_project(
                        row["project"],
                        "target_discovery_running",
                        {
                            "message": (
                                "Target Intelligence is resolving identity and structure evidence."
                            )
                        },
                    )
                    result = self._create_and_start(
                        row["project"], CreateProject.model_validate(payload)
                    )
                    state = (
                        "gate1_awaiting_scientist"
                        if result.get("status") == "awaiting-human-approval"
                        else "scientific_project"
                        if result.get("status") == "finished"
                        else "target_resolution_pending"
                    )
                    journal.update_project(
                        row["project"],
                        state,
                        {
                            "message": result.get("message") or result.get("status", ""),
                            "scientific_state": result.get("scientific_state"),
                        },
                    )
                elif operation == "conversation":
                    result = answer(
                        self.gateway,
                        self.catalog,
                        journal,
                        row["project"],
                        ActionRequest.model_validate(payload),
                    )
                else:
                    request = ActionRequest.model_validate(payload)
                    if recovering:
                        # Native response intents/checkpoints own crash reconciliation. Do
                        # not demand the old view revision after its response was delivered.
                        result = self._recover(row["project"], request)
                    else:
                        result = self.gateway.execute(row["project"], request, self.actor)
                journal.update(
                    request_id,
                    "succeeded",
                    {
                        "status": result.get("status"),
                        "project": row["project"],
                        "scientific_state": result.get("scientific_state"),
                        **(
                            {
                                k: result[k]
                                for k in ("answer", "revision", "phase", "model", "usage")
                            }
                            if operation == "conversation"
                            else {}
                        ),
                    },
                )
            except Exception as error:
                logging.getLogger(__name__).exception(
                    "Native product request failed: %s", request_id
                )
                if row is not None and row["payload"].get("operation") == "create":
                    failure = {
                        "phase": "target",
                        "task_id": "target-bootstrap",
                        "title": "Target Intelligence",
                        "specialist": "target",
                        "project_message": (
                            "Scientific research paused; retained evidence and recovery state "
                            "can be retried."
                        ),
                    }
                    failed_store: SessionStore | None = None
                    try:
                        failed_store = SessionStore(
                            self.context.projects_root / row["project"]
                        )
                        failure = self._failure_context(
                            failed_store, self._thread(request_id)
                        )
                    except (OSError, sqlite3.DatabaseError):
                        logging.getLogger(__name__).exception(
                            "Could not inspect product failure context: %s", request_id
                        )
                    try:
                        journal.update_project(
                            row["project"],
                            "failed",
                            {
                                "code": type(error).__name__,
                                "message": (
                                    str(error)
                                    if isinstance(error, ProductError)
                                    else failure["project_message"]
                                ),
                            },
                        )
                    except ProductError:
                        pass
                    try:
                        if failed_store is None:
                            failed_store = SessionStore(
                                self.context.projects_root / row["project"]
                            )
                        try:
                            self._activity(
                                failed_store,
                                self._thread(request_id),
                                "task.failed",
                                task_id=failure["task_id"],
                                title=failure["title"],
                                status="failed",
                                summary=failure["project_message"],
                                specialist=failure["specialist"],
                                phase=failure["phase"],
                            )
                        finally:
                            failed_store.close()
                    except (OSError, sqlite3.DatabaseError):
                        logging.getLogger(__name__).exception(
                            "Could not record target bootstrap failure: %s", request_id
                        )
                journal.update(
                    request_id,
                    "failed",
                    {
                        "code": error.code
                        if isinstance(error, ProductError)
                        else type(error).__name__,
                        "message": str(error)
                        if isinstance(error, ProductError)
                        else "The request could not be completed. Please retry. "
                        "Evidence and recovery state are retained.",
                    },
                )
            finally:
                journal.close()

    def _create_and_start(self, project: str, request: CreateProject) -> dict[str, Any]:
        import asyncio

        from easydesign.agent.bootstrap import resolve_goal_target
        from easydesign.agent.cli import run_session
        from easydesign.agent.models import create_models

        root = self.context.projects_root / project
        store = SessionStore(root)
        # A real async provider client is loop-affine once its connection pool has
        # been used.  Goal bootstrap, native Runtime entry and post-job re-entry are
        # separate awaits in one product worker, so keep one Runner alive for all of
        # them instead of repeatedly creating and closing loops with asyncio.run().
        runner = asyncio.Runner()
        try:
            runner.get_loop()
            config = self.gateway.config()
            thread = self._thread(request.request_id)
            store.thread(thread, fingerprint(config), request.goal)
            models = (self.gateway.model_factory or create_models)(config, downstream=True)
            target_input = request.target_input
            artifact_id = (
                target_input.artifact_id
                if isinstance(target_input, ArtifactTargetInput)
                else request.input_id
            )
            ref: ArtifactRef | None = None
            if not (root / "PROJECT.yaml").is_file():
                self._activity(
                    store,
                    thread,
                    "task.started",
                    task_id="target-bootstrap",
                    title="Target Intelligence",
                    status="running",
                    summary=(
                        "Interpreting the biological goal and preparing verified source research."
                    ),
                    specialist="target",
                )
                if target_input is not None:
                    store.event(
                        thread,
                        "product-target-input",
                        {
                            "input": target_input.model_dump(mode="json"),
                            "binding_sha256": digest(target_input.model_dump(mode="json")),
                            "authority": "discovery-input-only",
                        },
                    )
                canonical_seed: dict[str, Any] | None = None
                if artifact_id is not None or isinstance(target_input, PDBTargetInput):
                    previous_seeds = [
                        event["payload"]["seed"]
                        for event in store.events(thread)
                        if event["kind"] == "product-canonical-target-seed"
                        and isinstance(event["payload"].get("seed"), dict)
                    ]
                    if previous_seeds:
                        canonical_seed = previous_seeds[-1]
                    else:
                        self._activity(
                            store,
                            thread,
                            "specialist.started",
                            task_id="canonical-target-seed",
                            title="Canonical target identity",
                            status="running",
                            summary=(
                                "Resolving a reviewed canonical identity before mapping the "
                                "submitted structural input."
                            ),
                            specialist="target",
                        )
                        intent = runner.run(
                            resolve_goal_target(
                                store=store,
                                thread=thread,
                                goal=request.goal,
                                model=models["target"],
                                config=config,
                            )
                        )
                        try:
                            canonical_seed = resolve_unique_reviewed_uniprot_seed(
                                evidence_dir=(
                                    root / "metadata" / "product-target-identity"
                                ),
                                query=intent.uniprot_query,
                                taxon_id=intent.taxon_id,
                            )
                        except ContractError as error:
                            raise ProductError(
                                "canonical_target_unresolved",
                                (
                                    "The submitted PDB, structure or sequence could not be "
                                    "bound to one reviewed canonical target identity: "
                                    f"{error}"
                                ),
                                422,
                            ) from error
                        store.event(
                            thread,
                            "product-canonical-target-seed",
                            {
                                "seed": canonical_seed,
                                "intent": intent.model_dump(mode="json"),
                                "authority": "stage01-input-only",
                            },
                        )
                        self._activity(
                            store,
                            thread,
                            "specialist.completed",
                            task_id="canonical-target-seed",
                            title="Canonical target identity",
                            status="completed",
                            summary=(
                                "A unique reviewed UniProt identity seed was recorded; native "
                                "Target preparation must still verify the submitted material."
                            ),
                            specialist="target",
                        )
                    if not isinstance(canonical_seed.get("accession"), str):
                        raise ProductError(
                            "canonical_target_unresolved",
                            "The persisted canonical target seed is incomplete",
                            409,
                        )
                if artifact_id is not None:
                    directory = self.root / "inputs" / artifact_id
                    ref = ArtifactRef.model_validate_json(
                        confined_bytes(directory, "manifest.json")
                    )
                    source = ref.verify(directory)
                    artifact_kind = (
                        target_input.kind
                        if isinstance(target_input, ArtifactTargetInput)
                        else "structure"
                    )
                    self._activity(
                        store,
                        thread,
                        "evidence.recorded",
                        task_id="target-input-seed",
                        title=f"Typed {artifact_kind} input",
                        status="completed",
                        summary=(
                            f"The user {artifact_kind} artifact and checksum were bound to this "
                            "project; scientific identity and Gate authority remain unresolved."
                        ),
                        specialist="target",
                    )
                    initialize_research_project(
                        project_root=root,
                        project_id=project,
                        target=source,
                        identity_uniprot=canonical_seed["accession"],
                        cache_mode="prefer-cache",
                        allow_existing_metadata=True,
                        quarantine_on_error=False,
                    )
                elif isinstance(target_input, PDBTargetInput):
                    initialize_research_project(
                        project_root=root,
                        project_id=project,
                        pdb_id=target_input.pdb_id.upper(),
                        chain=target_input.chain,
                        identity_uniprot=canonical_seed["accession"],
                        cache_mode="prefer-cache",
                        allow_existing_metadata=True,
                        quarantine_on_error=False,
                    )
                elif isinstance(target_input, UniProtTargetInput):
                    initialize_research_project(
                        project_root=root,
                        project_id=project,
                        uniprot=target_input.accession.upper(),
                        cache_mode="prefer-cache",
                        allow_existing_metadata=True,
                        quarantine_on_error=False,
                    )
                else:
                    if isinstance(target_input, DescriptionTargetInput):
                        interpretation_goal = target_input.description
                    elif isinstance(target_input, ProteinNameTargetInput):
                        interpretation_goal = (
                            f"Explicit target name: {target_input.name}. "
                            f"Explicit organism: {target_input.organism}. "
                            f"Design request: {request.goal}"
                        )
                    else:
                        interpretation_goal = request.goal
                    self._activity(
                        store,
                        thread,
                        "specialist.started",
                        task_id="goal-interpretation",
                        title="Goal interpretation",
                        status="running",
                        summary=(
                            "Resolving a bounded UniProt search input from the natural-language "
                            "goal."
                        ),
                        specialist="target",
                    )
                    intent = runner.run(
                        resolve_goal_target(
                            store=store,
                            thread=thread,
                            goal=interpretation_goal,
                            model=models["target"],
                            config=config,
                        )
                    )
                    self._activity(
                        store,
                        thread,
                        "specialist.completed",
                        task_id="goal-interpretation",
                        title="Goal interpretation",
                        status="completed",
                        summary=(
                            f"Prepared a discovery query for {intent.target_label} in "
                            f"{intent.organism}; identity is not yet authoritative."
                        ),
                        specialist="target",
                    )
                    journal = self.journal()
                    try:
                        journal.update_project(
                            project,
                            "target_discovery_running",
                            {
                                "message": "Target identity and structure research are running.",
                                "target_intent": intent.model_dump(mode="json"),
                            },
                        )
                    finally:
                        journal.close()
                    initialize_research_project(
                        project_root=root,
                        project_id=project,
                        uniprot_query=(
                            target_input.name
                            if isinstance(target_input, ProteinNameTargetInput)
                            else intent.uniprot_query
                        ),
                        taxon_id=intent.taxon_id,
                        cache_mode="prefer-cache",
                        allow_existing_metadata=True,
                        quarantine_on_error=False,
                    )
            bridge = Phase34Runtime(
                root,
                thread,
                store,
                through="handoff",
                prediction_backend=self.gateway.prediction_backend,
                pilot_candidate_budget=30 if request.surface == "easy" else None,
                scale_candidate_budget=30 if request.surface == "easy" else None,
                product_auto_continue=request.surface == "easy",
            )
            loaded = bridge.validate_project()
            if artifact_id is not None and ref is None:
                directory = self.root / "inputs" / artifact_id
                ref = ArtifactRef.model_validate_json(confined_bytes(directory, "manifest.json"))
            if ref is not None and (
                loaded.source_path is None or sha256_file(loaded.source_path) != ref.sha256
            ):
                raise ProductError(
                    "input_changed",
                    "Project source differs from the submitted target artifact",
                    409,
                )
            if not any(e["kind"] == "product-title" for e in store.events(thread)):
                store.event(thread, "product-title", {"title": request.title})
            with (root / "metadata/agent-session.lock").open("a") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = runner.run(
                    run_session(bridge, config, models, request.goal, user=self.actor)
                )
                deadline = time.monotonic() + 60 * 30
                observed_jobs: dict[str, str] = {}
                while result.get("status") not in {
                    "awaiting-human-approval",
                    "finished",
                    "rejected",
                }:
                    if (
                        not bridge.product_auto_continue
                        and result.get("scientific_state") == "site-not-proposed"
                    ):
                        break
                    jobs = bridge.controller.list(project_id=bridge.project_id)
                    active = [
                        job
                        for job in jobs
                        if str(job.status) in {"queued", "running", "dispatching"}
                    ]
                    for job in jobs:
                        status = str(job.status)
                        if observed_jobs.get(job.job_id) == status:
                            continue
                        observed_jobs[job.job_id] = status
                        visible_status = (
                            "completed"
                            if status == "succeeded"
                            else "failed"
                            if status in {"failed", "operational-failed", "lost", "drained"}
                            else "running"
                        )
                        self._activity(
                            store,
                            thread,
                            "job." + visible_status,
                            task_id="target-job-" + job.job_id,
                            title="Native Target preparation",
                            status=visible_status,
                            summary=f"Stage 1 scientific job is {status}.",
                            specialist="target",
                        )
                    if active:
                        if time.monotonic() >= deadline:
                            return {
                                **result,
                                "status": "incomplete-turn",
                                "scientific_state": "target-job-running",
                                "message": "Target preparation remains active and recoverable.",
                            }
                        time.sleep(2)
                        continue
                    prior = (
                        result.get("status"),
                        result.get("scientific_state"),
                        len(store.events(thread)),
                    )
                    result = runner.run(
                        run_session(bridge, config, models, request.goal, user=self.actor)
                    )
                    current = (
                        result.get("status"),
                        result.get("scientific_state"),
                        len(store.events(thread)),
                    )
                    if current == prior:
                        break
                if result.get("status") == "awaiting-human-approval":
                    self._activity(
                        store,
                        thread,
                        "gate.opened",
                        task_id="gate-1",
                        title="Scientist target decision",
                        status="blocked",
                        summary=(
                            "Target identity or structure evidence is ready for an explicit "
                            "Scientist decision."
                        ),
                        specialist="target",
                    )
                    self._activity(
                        store,
                        thread,
                        "task.completed",
                        task_id="target-bootstrap",
                        title="Target Intelligence",
                        status="completed",
                        summary=(
                            "Target identity and structure evidence reached an explicit "
                            "Scientist Gate."
                        ),
                        specialist="target",
                    )
                elif result.get("status") == "finished":
                    self._activity(
                        store,
                        thread,
                        "task.completed",
                        task_id="target-bootstrap",
                        title="Target Intelligence",
                        status="completed",
                        summary="Target preparation completed with native evidence receipts.",
                        specialist="target",
                    )
                return result
        finally:
            try:
                runner.close()
            finally:
                store.close()

    def _recover(self, project: str, request: ActionRequest) -> dict[str, Any]:
        import asyncio

        from easydesign.agent.cli import run_session
        from easydesign.agent.models import create_models

        with self.gateway.session(project, write=True) as session:
            b = session.bridge
            response = b.store.response(b.thread, request.card_id) if request.card_id else None
            started = next(
                (
                    e["payload"]
                    for e in reversed(b.store.events(b.thread))
                    if e["kind"] == "product-command-started"
                    and e["payload"].get("request_id") == request.request_id
                ),
                None,
            )
            config = self.gateway.config()
            models = (self.gateway.model_factory or create_models)(
                config, downstream=isinstance(b, Phase34Runtime)
            )
            if started and started["payload_hash"] != digest(request.model_dump(mode="json")):
                raise ProductError("idempotency_conflict", "Recovery request differs", 409)
            if response:
                # Validate the complete native response identity, including B/C choice and
                # revision instruction. Then resume its checkpoint without sending it twice.
                b.store.respond(
                    b.thread,
                    request.card_id,
                    request.action,
                    self.actor,
                    human_instruction=request.instruction if request.action == "revise" else None,
                    revision_gate=request.revision_target,
                    optional_reason=request.reason,
                    explicit_acknowledgement=request.acknowledgement,
                    selected_option_id=request.selected_option_id
                    if request.action in {"approve", "override"}
                    and decision_view(b.store.card(b.thread, request.card_id))["selectable_options"]
                    else None,
                )
            elif request.card_id or started is None:
                return session.execute(request, config, models, self.actor)
            elif request.action == "message":
                execution = b.store.latest_execution(b.thread)
                if (
                    execution is None
                    or execution["execution_id"] == started["previous_execution_id"]
                ):
                    return session.execute(request, config, models, self.actor)
                if execution["current_user_message"] != request.instruction:
                    raise ProductError(
                        "recovery_conflict", "Another native execution superseded this message", 409
                    )
            return asyncio.run(
                run_session(
                    b,
                    config,
                    models,
                    session.goal,
                    user=self.actor,
                    continuation_id=(
                        request.request_id if request.action == "resume" else None
                    ),
                )
            )
