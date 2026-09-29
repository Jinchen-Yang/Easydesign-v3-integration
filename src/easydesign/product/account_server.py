"""Account-aware HTTP transport; delegates scoped science to the existing Product API."""

from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import threading
from contextvars import ContextVar
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

from pydantic import ValidationError

from .accounts import AccountUser, ResourceLimits, ScopeAccess
from .artifacts import confined_bytes
from .contracts import CreateProject, ProductError
from .project_drafts import ProjectDrafts
from .rabbit_chat import RabbitChatService, validate_chat_request
from .resource_supervisor import process_identity
from .server import Handler, ProductServer
from .service import ProductService
from .tenancy import MultiUserRuntime, ScopedProductService
from .transport_policy import TransportPolicy

SESSION_COOKIE = "easydesign_identity"
_SERVICE: ContextVar[ScopedProductService | None] = ContextVar(
    "account_product_service", default=None
)


def _bound_service() -> ProductService:
    value = _SERVICE.get()
    if value is None:
        raise ProductError("scope_required", "请选择工作区", 400)
    return value


# Response fields declared to carry product API links. Every producer that adds a
# link-bearing field must be listed here, or scoped clients could fall back to the
# unscoped single-user API (which accounts cannot authorize).
SCOPED_LINK_KEYS = frozenset({"url", "details_url"})


def _scoped_urls(value: Any, scope: str) -> Any:
    if isinstance(value, list):
        return [_scoped_urls(item, scope) for item in value]
    if isinstance(value, dict):
        return {
            key: (
                f"/api/v1/scopes/{scope}" + item.removeprefix("/api/v1")
                if key in SCOPED_LINK_KEYS
                and isinstance(item, str)
                and item.startswith("/api/v1/")
                and not item.startswith("/api/v1/scopes/")
                else _scoped_urls(item, scope)
            )
            for key, item in value.items()
        }
    return value


class MultiUserServer(ProductServer):
    def __init__(
        self,
        runtime: MultiUserRuntime,
        *,
        port: int = 14983,
        web_root: Path | None = None,
        easy_web_root: Path | None = None,
        public_origin: str | None = None,
        rabbit_chat: RabbitChatService | None = None,
        transport_policy: TransportPolicy | None = None,
        web_history: tuple[Path, ...] = (),
        easy_web_history: tuple[Path, ...] = (),
    ) -> None:
        self.runtime = runtime
        self.accounts = runtime.accounts
        self.public_origin = None
        if public_origin:
            parsed = urlsplit(public_origin)
            if (
                parsed.scheme not in {"https", "http"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
            ):
                raise ValueError("public_origin must be an origin without credentials or a path")
            self.public_origin = f"{parsed.scheme}://{parsed.netloc}"
        # This base value is used only for static configuration. API access must
        # always resolve a request-bound scoped service; there is no global fallback.
        base = ProductService(
            runtime.gateway_factory(runtime.context), launcher=self._unbound_launch
        )
        policy = transport_policy or TransportPolicy()
        # Waiting readers already own one of ProductServer's bounded connections.
        # Keep this CPU/SQLite read cap independent of uploads, login and AI streams.
        self.read_slots = threading.BoundedSemaphore(policy.max_readers)
        super().__init__(
            base,
            port=port,
            web_root=web_root,
            easy_web_root=easy_web_root,
            token=secrets.token_urlsafe(32),
            service_provider=_bound_service,
            handler_type=AccountHandler,
            rabbit_chat=rabbit_chat,
            transport_policy=policy,
            web_history=web_history,
            easy_web_history=easy_web_history,
        )

    @staticmethod
    def _unbound_launch(_request_id: str) -> None:
        raise ProductError("scope_required", "必须在已授权工作区内启动计算", 403)


class AccountHandler(Handler):
    server: MultiUserServer
    account_user: AccountUser | None = None
    current_scope: ScopeAccess | None = None
    resource_tail: list[str] = []

    def host_guard(self) -> None:
        port = self.server.server_port
        origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
        if self.server.public_origin:
            origins.add(self.server.public_origin)
        hosts = {urlsplit(origin).netloc for origin in origins}
        if self.headers.get("Host", "") not in hosts:
            raise ProductError("invalid_host", "请求主机不在允许范围", 403)
        origin = self.headers.get("Origin")
        if origin is not None and origin not in origins:
            raise ProductError("invalid_origin", "拒绝跨站请求", 403)
        if self.command == "POST" and origin is None:
            raise ProductError("origin_required", "写操作需要同源请求", 403)

    def _token(self) -> str:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            return ""
        value = cookie.get(SESSION_COOKIE)
        return value.value if value is not None else ""

    def _principal(self) -> AccountUser:
        token = self._token()
        user = self.server.accounts.authenticate(token)
        supplied = self.headers.get("X-CSRF-Token")
        if self.command == "POST" or supplied is not None:
            if not supplied or not hmac.compare_digest(
                supplied, self.server.accounts.csrf_token(token)
            ):
                raise ProductError("csrf_failed", "会话校验失败，请刷新页面后重试", 403)
        return user

    def authenticated(self) -> bool:
        return getattr(self, "account_user", None) is not None

    def authorize_upload(self) -> None:
        current = self._principal()  # Fresh token, password version and CSRF validation.
        previous, scope = self.account_user, self.current_scope
        if previous is None or current.id != previous.id or scope is None:
            raise ProductError("unauthorized", "上传会话权限已变化", 403)
        if current.must_change_password:
            raise ProductError("password_change_required", "请先修改临时密码", 403)
        self.server.accounts.scope(current, scope.id, edit=True)

    def _cookie(self, token: str, *, clear: bool = False) -> str:
        secure = "; Secure" if (self.server.public_origin or "").startswith("https:") else ""
        return (
            f"{SESSION_COOKIE}={token}; Max-Age={0 if clear else 604800}; "
            f"HttpOnly; SameSite=Strict; Path=/{secure}"
        )

    def _fields(self, allowed: set[str], required: set[str] | None = None) -> dict[str, Any]:
        value = self.json_body()
        if not isinstance(value, dict) or set(value) - allowed or (required or set()) - set(value):
            raise ProductError("invalid_request", "请求字段不正确", 400)
        return value

    def _account_routes(self, tail: list[str], query: dict[str, list[str]]) -> bool:
        store = self.server.accounts
        if tail == ["accounts", "config"] and self.command == "GET":
            self.send(
                200,
                {
                    "mode": "multi-user",
                    "registration": "admin-review",
                    "setup_required": not store.has_admin(),
                    "compute_available": self.server.runtime.launcher is not None,
                },
            )
            return True
        if tail in (["accounts", "login"], ["accounts", "register"]) and self.command == "POST":
            fields = self._fields(
                {"username", "password", "display_name"}, {"username", "password"}
            )
            if tail[-1] == "register":
                user = store.register(
                    fields["username"],
                    fields["password"],
                    fields.get("display_name") or fields["username"],
                    peer=self.client_ip(),
                )
                self.send(201, {"user": user.model_dump(), "status": "pending-review"})
            else:
                session = store.login(fields["username"], fields["password"], peer=self.client_ip())
                previous = self._token()
                if previous:
                    store.logout(previous)
                self.send(
                    200,
                    {"user": session.user.model_dump(), "csrf_token": session.csrf_token},
                    cookie=self._cookie(session.token),
                )
            return True
        user = self._principal()
        self.account_user = user
        if tail == ["accounts", "me"] and self.command == "GET":
            self.send(
                200,
                {
                    "user": user.model_dump(),
                    "csrf_token": store.csrf_token(self._token()),
                    "scopes": [] if user.must_change_password else store.scopes(user),
                    "invitations": [] if user.must_change_password else store.invitations(user),
                },
            )
            return True
        if tail == ["accounts", "logout"] and self.command == "POST":
            self._fields(set())
            store.logout(self._token())
            self.send(200, {"status": "logged-out"}, cookie=self._cookie("", clear=True))
            return True
        if tail == ["accounts", "password"] and self.command == "POST":
            fields = self._fields(
                {"current_password", "password"}, {"current_password", "password"}
            )
            store.change_password(user, fields["current_password"], fields["password"])
            self.send(200, {"status": "password-changed"}, cookie=self._cookie("", clear=True))
            return True
        if tail == ["teams"]:
            if self.command == "GET":
                self.send(200, {"teams": [s for s in store.scopes(user) if s["kind"] == "team"]})
            else:
                fields = self._fields({"name"}, {"name"})
                self.send(201, {"team": store.create_team(user, fields["name"])})
            return True
        if len(tail) == 2 and tail[0] == "teams":
            if self.command == "GET":
                self.send(200, {"team": store.team(user, tail[1])})
            else:
                fields = self._fields({"name"}, {"name"})
                store.update_team(user, tail[1], name=fields["name"])
                self.send(200, {"team": store.team(user, tail[1])})
            return True
        if (
            len(tail) == 3
            and tail[0] == "teams"
            and tail[2] == "invitations"
            and self.command == "POST"
        ):
            fields = self._fields({"username", "role"}, {"username"})
            self.send(
                201,
                {
                    "invitation": store.invite(
                        user, tail[1], fields["username"], role=fields.get("role", "member")
                    )
                },
            )
            return True
        if (
            len(tail) == 4
            and tail[0] == "teams"
            and tail[2] == "members"
            and self.command == "POST"
        ):
            fields = self._fields({"role", "remove"})
            if "remove" in fields and not isinstance(fields["remove"], bool):
                raise ProductError("invalid_request", "成员操作格式不正确", 400)
            store.set_member(
                user, tail[1], tail[3], role=fields.get("role"), remove=fields.get("remove", False)
            )
            if fields.get("remove") and tail[3] == user.id:
                # Membership has already been removed. Reading the roster now
                # correctly fails closed, but must not turn a successful leave
                # into an HTTP failure or disclose the no-longer-visible team.
                self.send(200, {"status": "left-team"})
            else:
                self.send(200, {"team": store.team(user, tail[1])})
            return True
        if len(tail) == 2 and tail[0] == "invitations" and self.command == "POST":
            fields = self._fields({"accept"}, {"accept"})
            if not isinstance(fields["accept"], bool):
                raise ProductError("invalid_request", "邀请操作格式不正确", 400)
            self.send(
                200,
                {"invitation": store.respond_invitation(user, tail[1], accept=fields["accept"])},
            )
            return True
        if tail == ["admin", "users"] and self.command == "GET":
            self.send(200, {"users": store.users(user)})
            return True
        if len(tail) == 3 and tail[:2] == ["admin", "users"] and self.command == "POST":
            fields = self._fields({"status", "role"})
            changed = store.update_user(
                user, tail[2], status=fields.get("status"), role=fields.get("role")
            )
            self.send(200, {"user": changed.model_dump()})
            return True
        if (
            len(tail) == 4
            and tail[:2] == ["admin", "users"]
            and tail[3] == "password"
            and self.command == "POST"
        ):
            fields = self._fields({"password"}, {"password"})
            store.reset_password(user, tail[2], fields["password"])
            self.send(200, {"status": "password-reset", "must_change_password": True})
            return True
        if tail == ["admin", "teams"] and self.command == "GET":
            self.send(200, {"teams": store.all_teams(user)})
            return True
        if len(tail) == 3 and tail[:2] == ["admin", "teams"] and self.command == "POST":
            fields = self._fields({"status"}, {"status"})
            store.update_team(user, tail[2], status=fields["status"])
            self.send(200, {"team": store.team(user, tail[2])})
            return True
        if len(tail) == 2 and tail[0] == "quotas" and self.command == "GET":
            self.send(200, {"limits": store.limits(user, tail[1]).model_dump()})
            return True
        if len(tail) == 3 and tail[:2] == ["admin", "quotas"] and self.command == "POST":
            value = ResourceLimits.model_validate(self.json_body())
            store.set_limits(user, tail[2], value)
            self.send(200, {"limits": value.model_dump()})
            return True
        if tail == ["admin", "audit"] and self.command == "GET":
            offset = int(query.get("offset", ["0"])[0])
            self.send(200, {"events": store.audit(user, offset=offset)})
            return True
        if tail == ["admin", "admissions"] and self.command == "GET":
            self.send(200, {"admissions": self.server.runtime.resources.all_admissions(user)})
            return True
        if tail == ["admin", "final-designs"] and self.command == "GET":
            self.send(200, self.server.runtime.resources.final_designs_admin(user))
            return True
        if tail == ["health"] and self.command == "GET":
            self.send(200, {"status": "ready", "mode": "multi-user"})
            return True
        return False

    def _rabbit(self, user: AccountUser, scope_id: str) -> None:
        if self.command == "GET":
            self.send(200, self.server.rabbit_chat.status())
            return
        self.server.accounts.scope(user, scope_id, edit=True)
        payload = validate_chat_request(self.json_body())
        identities = self.headers.get_all("X-Request-ID", [])
        if len(identities) != 1:
            raise ProductError("invalid_request_id", "对话必须使用稳定的请求编号", 400)
        request_id = identities[0]
        resources = self.server.runtime.resources
        command = resources.command(scope_id, request_id)
        if command is not None and command["actor_id"] != user.id:
            raise ProductError("idempotency_conflict", "请求编号属于其他成员", 409)
        latest = resources.latest(scope_id, request_id)
        # Failed pre-admission attempts can retry this stable identity. The
        # durable AI ledger remains authoritative: an already dispatched ID
        # never starts another paid invocation, even after an unknown outcome.
        retry = latest is None or latest.state not in ("released",)
        admission, created = resources.reserve(
            user,
            scope_id,
            request_id,
            payload,
            kind="conversation",
            retry=retry,
            dispatch_channel="web_stream",
        )
        if not created:
            raise ProductError("request_already_processed", "该对话请求已处理或正在处理中", 409)
        events = None
        streaming = False
        delivered = False  # a public terminal done event reached the client
        token = self._token()

        def authorize() -> None:
            # Queue time may outlive a session, password version or team grant.
            # Resolve all three again immediately before model dispatch.
            current = self.server.accounts.authenticate(token)
            if current.id != user.id or current.must_change_password:
                raise ProductError("unauthorized", "会话权限已变化", 403)
            self.server.accounts.scope(current, scope_id, edit=True)

        try:
            events = self.server.rabbit_chat.events(
                payload,
                actor_id=user.id,
                scope_id=scope_id,
                request_id=request_id,
                authorize=authorize,
            )
            self.server.runtime.resources.transition(
                admission.id,
                "running",
                worker_pid=os.getpid(),
                worker_start=process_identity(os.getpid()),
            )
            streaming = True
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                for event in events:
                    self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode())
                    self.wfile.flush()
                    if event.get("type") == "done":
                        delivered = True
                        break
            except Exception:
                # The NDJSON framing is already committed; never append a second
                # HTTP response after the headers. The stream simply ends here.
                logging.getLogger(__name__).warning(
                    "Chat stream terminated before delivery", exc_info=True
                )
            self.close_connection = True
        finally:
            try:
                close = getattr(events, "close", None)
                if close is not None:
                    close()
            except Exception:
                # Cleanup trouble must neither mask the outcome nor strand quota.
                logging.getLogger(__name__).warning("Chat cleanup failed", exc_info=True)
            try:
                if delivered:
                    self.server.runtime.resources.transition(admission.id, "released")
                elif streaming:
                    # Headers were sent: the failure is already framed as NDJSON
                    # events (the provider appends a terminal error event); the
                    # admission records it; the AI ledger prevents redispatch.
                    self.server.runtime.resources.transition(
                        admission.id, "failed", reason="chat_failed"
                    )
                else:
                    self.server.runtime.resources.transition(
                        admission.id, "failed", reason="chat_unavailable"
                    )
            except ProductError:
                logging.getLogger(__name__).warning(
                    "Chat admission already terminal", exc_info=True
                )

    def _drafts(self, service: ScopedProductService, parts: list[str]) -> None:
        store = ProjectDrafts(service.root / "drafts.sqlite")
        if self.command == "GET":
            self.send(
                200, {"drafts": store.list()} if len(parts) == 1 else {"draft": store.get(parts[1])}
            )
            return
        service.access(edit=True)
        if len(parts) in {1, 2}:
            value = self._fields({"title", "goal", "input_id", "revision"}, {"title", "goal"})
            draft = CreateProject(
                request_id=uuid4().hex,
                title=value["title"],
                goal=value["goal"],
                input_id=value.get("input_id"),
                surface="easy",
            )
            payload = draft.model_dump(mode="json", exclude={"request_id"})
            saved = store.save(
                service.user.id,
                payload,
                identity=parts[1] if len(parts) == 2 else None,
                expected_revision=value.get("revision"),
            )
            with self.server.accounts.db(write=True) as db:
                self.server.accounts.audit_record(
                    db, service.user.id, "draft.save", scope=service.scope_id, target=saved["id"]
                )
            self.send(200, {"draft": saved})
            return
        if len(parts) == 3 and parts[2] == "start":
            service.access(execute=True)
            value = self._fields({"revision", "request_id"}, {"revision", "request_id"})
            selected = store.claim(parts[1], value["revision"], value["request_id"])
            create = CreateProject(request_id=value["request_id"], **selected["payload"])
            try:
                result = service.create(create)
            except BaseException:
                # Only a journal row created from this draft's exact payload may be
                # adopted; a colliding request id that already belongs to another
                # create must leave the draft editable and unattached.
                journal = service.journal()
                try:
                    existing = journal.get(value["request_id"])
                finally:
                    journal.close()
                adopted = None
                if existing is not None and existing["payload"] == {
                    "operation": "create",
                    **create.model_dump(mode="json", exclude_none=True),
                }:
                    adopted = existing["project"]
                store.finish_start(parts[1], value["request_id"], adopted)
                raise
            store.finish_start(parts[1], value["request_id"], result["project"])
            self.send(202, result)
            return
        raise ProductError("not_found", "草稿操作不存在", 404)

    def dispatch(self) -> None:
        self.account_user = None
        self.current_scope = None
        self.resource_tail = []
        reading = False
        try:
            self.host_guard()
            url = urlsplit(self.path)
            path = unquote(url.path)
            if "\x00" in path or "\\" in path or ".." in path.split("/"):
                raise ProductError("invalid_path", "请求路径不合法", 403)
            if not path.startswith("/api/"):
                self.static(path)
                return
            if "%" in path:
                raise ProductError("invalid_path", "API 路径不能重复编码", 403)
            if path == "/api/compute/resources" and self.command == "GET":
                self.account_user = self._principal()
                self.send(200, self.server.compute_monitor())
                return
            parts = path.strip("/").split("/")
            if parts[:2] != ["api", "v1"]:
                raise ProductError("not_found", "接口不存在", 404)
            tail = parts[2:]
            # Classify the router's decoded, validated segments, not the raw URL.
            # Acquire before authentication so a queued request cannot retain an
            # identity or scope that was revoked while it waited.
            if (
                self.command == "GET"
                and tail[:1] == ["scopes"]
                and (
                    (len(tail) == 4 and tail[2] == "requests")
                    or (len(tail) == 5 and tail[2] == "projects" and tail[4] == "workbench")
                )
            ):
                reading = self.server.read_slots.acquire(
                    timeout=self.server.transport_policy.read_wait_timeout
                )
                if not reading:
                    raise ProductError("read_busy", "状态读取繁忙，请稍后重试", 503)
            if self._account_routes(tail, parse_qs(url.query)):
                return
            if len(tail) < 3 or tail[0] != "scopes":
                raise ProductError("scope_required", "接口需要明确的工作区", 404)
            user = self.account_user
            assert user is not None
            scope_id, product_tail = tail[1], tail[2:]
            self.current_scope = self.server.accounts.scope(user, scope_id)
            self.resource_tail = product_tail
            if product_tail == ["usage"] and self.command == "GET":
                self.send(200, self.server.runtime.resources.usage(user, scope_id))
                return
            # New upstream write routes are denied until explicitly classified.
            if self.command == "POST":
                allowed = (
                    product_tail in (["projects"], ["inputs"], ["rabbit", "chat"])
                    or (product_tail[0] == "drafts" and len(product_tail) in {1, 2, 3})
                    or (
                        len(product_tail) == 3
                        and product_tail[0] == "projects"
                        and product_tail[2] in {"title", "actions", "lab-order"}
                    )
                    or (
                        len(product_tail) == 3
                        and product_tail[0] == "requests"
                        and product_tail[2] in {"resume", "cancel"}
                    )
                    or (
                        len(product_tail) == 4
                        and product_tail[:2] == ["rabbit", "requests"]
                        and product_tail[3] == "cancel"
                    )
                )
                if not allowed:
                    raise ProductError("not_found", "操作不存在", 404)
            elif self.command == "GET":
                if product_tail[0] not in {
                    "projects",
                    "requests",
                    "artifacts",
                    "health",
                    "rabbit",
                    "drafts",
                }:
                    raise ProductError("not_found", "资源不存在", 404)
            else:
                raise ProductError("method_not_allowed", "请求方法不受支持", 405)
            with self.server.runtime.bind(user, scope_id) as service:
                if product_tail[0] == "drafts":
                    self._drafts(service, product_tail)
                    return
                if product_tail == ["rabbit", "chat"]:
                    self._rabbit(user, scope_id)
                    return
                if product_tail[:2] == ["rabbit", "requests"]:
                    if len(product_tail) < 3:
                        raise ProductError("not_found", "对话请求接口不存在", 404)
                    identity = dict(actor_id=user.id, scope_id=scope_id, request_id=product_tail[2])
                    if len(product_tail) == 3 and self.command == "GET":
                        self.send(200, self.server.rabbit_chat.request_status(**identity))
                        return
                    if (
                        len(product_tail) == 4
                        and product_tail[3] == "cancel"
                        and self.command == "POST"
                    ):
                        self.server.accounts.scope(user, scope_id, edit=True)
                        self._fields(set())
                        self.send(200, self.server.rabbit_chat.cancel(**identity))
                        return
                    raise ProductError("not_found", "对话请求接口不存在", 404)
                token = _SERVICE.set(service)
                original_path = self.path
                try:
                    self.path = (
                        "/api/v1/" + "/".join(product_tail) + ("?" + url.query if url.query else "")
                    )
                    super().dispatch()
                finally:
                    self.path = original_path
                    _SERVICE.reset(token)
        except ProductError as error:
            self.send(error.status, {"error": {"code": error.code, "message": str(error)}})
        except (ValidationError, ValueError, TypeError):
            self.send(400, {"error": {"code": "invalid_request", "message": "请求字段不正确"}})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            logging.getLogger(__name__).exception("Account product request failed")
            self.send(500, {"error": {"code": "operational_error", "message": "操作暂时无法完成"}})
        finally:
            if reading:
                self.server.read_slots.release()

    def static(self, path: str) -> None:
        if path in {"/account", "/account/"}:
            root = self.server.easy_web_root
            if root is None or self.command != "GET":
                raise ProductError("not_found", "账户页面尚未构建", 404)
            self.send(200, confined_bytes(root, "account/index.html"), "text/html")
            return
        super().static(path)

    def send(
        self,
        status: int,
        data: Any,
        mime: str = "application/json",
        *,
        cookie: str | None = None,
        immutable: bool = False,
    ) -> None:
        scope = getattr(self, "current_scope", None)
        if scope is not None:
            if mime == "application/json" and not isinstance(data, bytes):
                data = _scoped_urls(data, scope.id)
            if scope.role == "observer" and self.command == "GET":
                user = self.account_user
                assert user is not None
                with self.server.accounts.db(write=True) as db:
                    self.server.accounts.audit_record(
                        db,
                        user.id,
                        "admin.scope.read",
                        scope=scope.id,
                        target=self.resource_tail[1] if len(self.resource_tail) > 1 else None,
                        details={
                            "resource": self.resource_tail[0] if self.resource_tail else "scope",
                            "status": status,
                        },
                    )
        if mime == "text/html" and isinstance(data, bytes):
            marker = b'<meta name="easydesign-identity-mode" content="accounts" />'
            data = data.replace(b"</head>", marker + b"</head>", 1)
        super().send(status, data, mime, cookie=cookie, immutable=immutable and scope is None)
