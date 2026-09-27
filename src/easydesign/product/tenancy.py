"""Authenticated product façade over the canonical scientific ProductService."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from easydesign.execution_scope import ExecutionScope
from easydesign.workspace_context import WorkspaceContext

from .accounts import AccountStore, AccountUser, ScopeAccess
from .artifacts import ArtifactCatalog
from .contracts import ActionRequest, CreateProject, ProductError
from .domain import NativeGateway
from .lab_order import LabOrderCommand
from .resource_control import Admission, ResourceLedger
from .service import ProductService, upload_identity


class ScopedCatalog(ArtifactCatalog):
    def __init__(self, native: ArtifactCatalog, check: Callable[[], ScopeAccess]) -> None:
        super().__init__(native.workspace, native.root)
        self.check = check

    def read(self, token: str) -> tuple[bytes, str]:
        self.check()
        return super().read(token)


class ScopedProductService(ProductService):
    """Keep native science unchanged; enforce actor/scope rights before native writes."""

    def __init__(
        self,
        gateway: NativeGateway,
        *,
        accounts: AccountStore,
        resources: ResourceLedger,
        user: AccountUser,
        scope_id: str,
        launcher: Callable[[Admission, ScopedProductService], None] | None,
    ) -> None:
        self.accounts, self.resources = accounts, resources
        self.user, self.scope_id = user, scope_id
        self.admission_launcher = launcher
        self._current_admission: Admission | None = None
        super().__init__(gateway, actor="account:" + user.id, launcher=self._launch_admission)
        self.catalog = ScopedCatalog(self.catalog, lambda: self.access())

    def access(self, *, edit: bool = False, execute: bool = False) -> ScopeAccess:
        return self.accounts.scope(self.user, self.scope_id, edit=edit, execute=execute)

    def _launch_admission(self, request_id: str) -> None:
        admission = self._current_admission
        if (
            admission is None
            or admission.request_id != request_id
            or self.admission_launcher is None
        ):
            raise ProductError("admission_required", "缺少有效的资源准入记录", 409)
        self.admission_launcher(admission, self)

    @contextmanager
    def _admit(
        self,
        request_id: str,
        payload: dict[str, Any],
        *,
        conversation: bool = False,
        retry: bool = False,
    ) -> Iterator[Admission]:
        self.access(edit=True, execute=not conversation)
        if self.admission_launcher is None:
            raise ProductError("compute_unavailable", "计算服务尚未配置，请联系管理员", 503)
        admission, created = self.resources.reserve(
            self.user,
            self.scope_id,
            request_id,
            payload,
            kind="conversation" if conversation else "scientific",
            retry=retry,
        )
        self._current_admission = admission
        try:
            yield admission
        except BaseException:
            if created and self.resources.get(admission.id).state == "reserved":
                self.resources.transition(admission.id, "failed", reason="native_request_rejected")
            raise
        finally:
            self._current_admission = None

    def create(self, request: CreateProject) -> dict[str, Any]:
        payload = {"operation": "create", **request.model_dump(mode="json", exclude_none=True)}
        with self._admit(request.request_id, payload):
            return super().create(request)

    def submit(self, project: str, request: ActionRequest) -> dict[str, Any]:
        conversation = request.action == "message"
        payload = {"project": project, "request": request.model_dump(mode="json")}
        command = self.resources.command(self.scope_id, request.request_id)
        if command is not None and command["actor_id"] != self.user.id:
            raise ProductError(
                "idempotency_conflict", "请求编号属于另一操作人，请使用明确的恢复入口", 409
            )
        journal = self.journal()
        try:
            previous = journal.get(request.request_id)
        finally:
            journal.close()
        retry = previous is not None and previous["state"] in {"failed", "interrupted"}
        with self._admit(request.request_id, payload, conversation=conversation, retry=retry):
            return super().submit(project, request)

    def retry(self, request_id: str) -> dict[str, Any]:
        self.access()
        # request() reconciles an accepted request whose transport worker is gone
        # into "interrupted"; without it a resume-only client could never relaunch.
        row = self.request(request_id)
        conversation = row["kind"] == "conversation"
        self.access(edit=True, execute=not conversation)
        if row["state"] not in {"failed", "interrupted"}:
            return row
        journal = self.journal()
        try:
            record = journal.get(request_id)
        finally:
            journal.close()
        assert record is not None
        if record["payload"].get("operation") == "create":
            payload = record["payload"]
        else:
            request = dict(record["payload"])
            request.pop("operation", None)
            payload = {
                "project": record["project"],
                "request": ActionRequest.model_validate(request).model_dump(mode="json"),
            }
        with self._admit(request_id, payload, conversation=conversation, retry=True):
            return super().retry(request_id)

    def upload(self, filename: str, data: bytes) -> dict[str, Any]:
        self.access(edit=True)
        # Canonical identity first: requests that are rejected before any byte
        # is stored never reach the quota ledger, and identical bytes under
        # different filenames are one reservation, matching the storage key.
        key, _suffix = upload_identity(filename, data)
        reservation, _created = self.resources.reserve_upload(
            self.user, self.scope_id, key, len(data)
        )
        try:
            result = super().upload(filename, data)
        except BaseException:
            # Retained (still charged): bytes were stored and stay quarantined
            # until an explicit, verified maintenance action.
            self.resources.finish_upload(reservation, published=False)
            raise
        self.resources.finish_upload(reservation, published=True)
        return result

    def rename(self, project: str, title: str) -> dict[str, Any]:
        self.access(edit=True)
        with self.accounts.db(write=True) as db:
            self.accounts.audit_record(
                db, self.user.id, "project.rename", scope=self.scope_id, target=project
            )
        return super().rename(project, title)

    def apply_lab_order(self, project: str, command: LabOrderCommand) -> dict[str, Any]:
        self.access(edit=True, execute=True)
        return super().apply_lab_order(project, command)


class MultiUserRuntime:
    def __init__(
        self,
        context: WorkspaceContext,
        accounts: AccountStore,
        gateway_factory: Callable[[WorkspaceContext], NativeGateway],
        *,
        launcher: Callable[[Admission, ScopedProductService], None] | None = None,
    ) -> None:
        if context.execution_scope is not None:
            raise ValueError("The product controller requires an unscoped workspace")
        self.context, self.accounts, self.gateway_factory = context, accounts, gateway_factory
        self.resources = ResourceLedger(accounts)
        self.launcher = launcher

    @contextmanager
    def bind(self, user: AccountUser, scope_id: str) -> Iterator[ScopedProductService]:
        access = self.accounts.scope(user, scope_id)
        context = self.context.with_execution_scope(
            ExecutionScope(
                scope_id=access.id,
                actor_id=user.id,
            )
        )
        context.ensure_layout()
        with context.activate():
            gateway = self.gateway_factory(context)
            service = ScopedProductService(
                gateway,
                accounts=self.accounts,
                resources=self.resources,
                user=user,
                scope_id=scope_id,
                launcher=self.launcher,
            )
            yield service
