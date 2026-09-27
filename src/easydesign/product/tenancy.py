"""Authenticated product façade over the canonical scientific ProductService."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from easydesign.execution_scope import ExecutionScope
from easydesign.workspace_context import WorkspaceContext

from .accounts import AccountStore, AccountUser, ScopeAccess
from .artifacts import ArtifactCatalog
from .contracts import ActionRequest, CreateProject, ProductError
from .domain import NativeGateway
from .lab_order import LabOrderCommand
from .resource_control import Admission, ResourceLedger, contract_digest
from .service import ProductService, upload_identity

# The Gate-4 promotion option identity checked by the native authority builder.
PROMOTE_TO_SCALE_OPTION = "PROMOTE_TO_SCALE"
FINAL_DESIGN_ACTIONS = frozenset({"approve", "override", "resume"})
_AUTHORITY_CONTRACT = "Gate4PromotionAuthority"
_ORIGINAL_ACTOR = re.compile(r"^account:(user-[0-9a-f]{32})$")


def _unverified(detail: str) -> ProductError:
    """Fail closed: an unverifiable classification blocks the request."""
    return ProductError(
        "final_designs_unverified", f"无法核实最终设计额度所需的审批状态：{detail}；已阻止请求", 503
    )


@dataclass(frozen=True)
class FinalDesignIntent:
    """One chargeable Scale promotion: its canonical identity and size.

    ``subject_id`` is None when the original billing person could not be read
    from canonical evidence; only a persisted matching reservation may then
    supply it — never the currently retrying administrator.
    """

    authority_key: str
    amount: int
    subject_id: str | None


def _published_intent(bridge: Any, request: ActionRequest) -> FinalDesignIntent | None:
    """Classify from the current, checksum-verified published authority.

    Covers retries, resumes and duplicate approvals of already-applied
    promotions: the native runtime only ever loads this latest authority, so it
    is the exact identity a continuation could dispatch under.
    """
    latest = getattr(bridge, "project_latest", None)
    if not callable(latest):
        # Explicitly known non-Scale stage: bridges without downstream contracts
        # can never publish a promotion authority.
        return None
    event = latest("phase34-scale-authority")
    if event is None:
        return None
    if not isinstance(event, dict) or event.get("contract_type") != _AUTHORITY_CONTRACT:
        raise _unverified("当前授权事件类型不匹配")
    reader = getattr(bridge, "document", None)
    if not callable(reader):
        raise _unverified("无法读取已发布的 Scale 授权")
    try:
        contract: Any = reader(event["ref"])
    except Exception as error:
        raise _unverified("授权文档暂时不可读") from error
    if not isinstance(contract, dict) or (
        contract_digest(contract) != event.get("contract_sha256")
    ):
        raise _unverified("授权文档校验和不匹配")
    if contract.get("authorizes_production_compute") is not True:
        # Validated non-production authority (validation/test rounds).
        return None
    if request.card_id is not None and request.card_id != contract.get("gate4_card_id"):
        return None
    authority_key = contract.get("gate4_card_id")
    if not isinstance(authority_key, str) or not re.fullmatch(r"[0-9a-f]{64}", authority_key):
        raise _unverified("授权缺少有效的 Gate-4 卡片身份")
    amount = contract.get("requested_scale_candidates")
    if type(amount) is not int or amount < 1:
        raise _unverified("授权的生产候选数量不合法")
    actor = _ORIGINAL_ACTOR.fullmatch(str(contract.get("human_actor") or ""))
    if actor is None:
        # Malformed/missing original actor: the reservation ledger must supply
        # the billed subject, or the request is blocked truthfully.
        return FinalDesignIntent(authority_key, amount, None)
    return FinalDesignIntent(authority_key, amount, actor.group(1))


def final_design_intent(
    session: Any, request: ActionRequest, fallback_subject: str
) -> FinalDesignIntent | None:
    """Classify whether this request can dispatch chargeable Scale work.

    Returns None only for explicitly known non-chargeable cases. Anything that
    cannot be reliably determined raises: a transient read failure now must
    block the request, because a later successful read could otherwise dispatch
    Scale with no reservation behind it.
    """
    if request.action not in FINAL_DESIGN_ACTIONS:
        return None
    bridge = session.bridge
    if request.action in {"approve", "override"}:
        try:
            card = session.current()[1]
        except Exception as error:
            raise _unverified("科学决策状态暂时无法读取") from error
        if card is not None and card.gate_type == "pilot-promotion":
            if request.card_id != card.card_id:
                # The approve targets another card (typically a duplicate of an
                # already-applied promotion); only the published authority bills.
                return _published_intent(bridge, request)
            summary = getattr(card, "scientific_summary", None) or {}
            if summary.get("test_only_control_flow_fixture") is True:
                return None
            if (request.selected_option_id or card.option_id) != PROMOTE_TO_SCALE_OPTION:
                return None
            dossier_reader = getattr(bridge, "current_pilot_dossier", None)
            dossier = dossier_reader() if callable(dossier_reader) else None
            if dossier is None:
                raise _unverified("缺少当前的 Pilot 证据档案")
            if (
                type(getattr(dossier, "execution_authority", None)).__name__
                == "ValidationExecutionAuthority"
            ):
                # Validation micro pilots never spend the final-design balance.
                return None
            amount = getattr(
                getattr(dossier, "proposed_interpretation", None),
                "requested_scale_candidates",
                None,
            )
            if type(amount) is not int or amount < 1:
                raise _unverified("Pilot 证据中的生产候选数量不合法")
            return FinalDesignIntent(card.card_id, amount, fallback_subject)
    return _published_intent(bridge, request)


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
        stage_budgets: dict[str, int | None] | None = None,
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
            stage_budgets=stage_budgets,
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

    def _authorize_final_designs(
        self, project: str, request: ActionRequest, admission: Admission
    ) -> None:
        """Hold the final-design charge before any Scale side effect.

        Covers first approval, duplicate approval, resume and retry: each either
        matches the current Gate-4 card or recovers the authoritative
        reservation from the checksum-verified promotion contract. The billed
        person is the admission's preserved scientific actor, so a same-request
        retry by another team admin can never reactivate a released row against
        themselves. An exhausted balance, an unverifiable classification, or a
        terminally released reservation fails before the native request is
        accepted.
        """
        if request.action not in FINAL_DESIGN_ACTIONS:
            return
        with self.gateway.session(project) as session:
            intent = final_design_intent(session, request, admission.scientific_actor_id)
        if intent is None:
            return
        subject = intent.subject_id
        if subject is None:
            # The original actor could not be read from canonical evidence:
            # only the persisted matching reservation may supply the billed
            # person, never the currently retrying administrator.
            persisted = self.resources.final_designs_row(
                self.scope_id, project, intent.authority_key
            )
            if persisted is None:
                raise ProductError(
                    "final_designs_actor_unverified",
                    "无法核实原始审批人，已阻止请求；请联系管理员核对最终设计台账",
                    409,
                )
            subject = persisted["subject_id"]
        held, _created = self.resources.ensure_final_designs(
            self.user,
            self.scope_id,
            project,
            request.request_id,
            intent.authority_key,
            intent.amount,
            subject_id=subject,
        )
        if held["state"] == "released":
            # A terminally released reservation is not a free pass to compute:
            # without a provably impossible dispatch, fail closed.
            raise ProductError(
                "final_designs_released_authority",
                "该 Gate-4 审批的最终设计预留已被终止，不能据此重新派发；请联系管理员核对台账",
                409,
            )

    def create(self, request: CreateProject) -> dict[str, Any]:
        payload = {"operation": "create", **request.model_dump(mode="json", exclude_none=True)}
        # Capture stage budgets once, at command authorization; the worker
        # receives them through its immutable config and never re-reads admin
        # settings for this command.
        stage_budgets = self.resources.stage_budgets_for(self.user, self.scope_id)
        with self._admit(request.request_id, payload, stage_budgets=stage_budgets):
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
        with self._admit(
            request.request_id, payload, conversation=conversation, retry=retry
        ) as admission:
            self._authorize_final_designs(project, request, admission)
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
            request = None
        else:
            request = dict(record["payload"])
            request.pop("operation", None)
            payload = {
                "project": record["project"],
                "request": ActionRequest.model_validate(request).model_dump(mode="json"),
            }
        with self._admit(request_id, payload, conversation=conversation, retry=True) as admission:
            if request is not None and not conversation:
                self._authorize_final_designs(
                    record["project"], ActionRequest.model_validate(request), admission
                )
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
