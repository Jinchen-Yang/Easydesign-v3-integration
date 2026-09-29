"""Single-user loopback Product API and same-origin Workbench static delivery."""

from __future__ import annotations

import argparse
import csv
import hmac
import io
import json
import logging
import mimetypes
import os
import re
import secrets
import socket
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from pydantic import ValidationError

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.session_store import confined
from easydesign.orchestration.runtime_setup import initialize_workspace_metadata
from easydesign.workspace_context import WorkspaceContext

from .capacity_config import load_capacity_config
from .contracts import ActionRequest, CreateProject, ProductError, RenameProject
from .domain import NativeGateway
from .lab_order import LabOrderCommand
from .rabbit_capacity import RabbitCapacityLimits
from .rabbit_chat import RabbitChatService, SubprocessChatProvider
from .service import ProductService
from .static_assets import HASHED_BUILD_ASSET, GzipCache, StaticAssets, accepts_gzip
from .transport_policy import DeadlineReader, TransportPolicy

# Keep an authenticated local browser usable across ordinary browser restarts.
# The cookie remains origin-bound, HttpOnly and strict same-site; the durable
# workspace token is still required for the first login in each browser profile.
SESSION_COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60

# Server-level 404 for browser navigations; client-side routes are handled by the
# SPA's own NotFoundPage once the app has loaded. Plain markup only: the shared
# CSP header forbids inline styles and scripts.
_STATIC_NOT_FOUND_PAGE = (
    '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    "<title>页面不存在 · EasyDesign</title></head>"
    "<body><h1>404 · 页面不存在</h1>"
    "<p>您访问的地址不存在或尚未发布。请从已有入口重新进入。</p>"
    "</body></html>"
).encode()
GPU_SAMPLE_TTL_SECONDS = 10.0
# Vite's content-addressed output is public and immutable across releases. Never
# infer cacheability for API/artifact URLs or unhashed files from their suffix.


class LocalGpuMonitor:
    """Bounded, read-only local GPU telemetry for the loopback product UI."""

    _GPU_QUERY = (
        "index,name,uuid,utilization.gpu,memory.total,memory.used,"
        "temperature.gpu,power.draw,power.limit,driver_version"
    )

    def __init__(
        self,
        *,
        runner: Any = subprocess.run,
        clock: Any = time.monotonic,
        node: str | None = None,
    ) -> None:
        self.runner = runner
        self.clock = clock
        self.node = node or os.uname().nodename
        self._checked_at = float("-inf")
        self._sample: dict[str, Any] | None = None
        self._failed = False
        self._lock = threading.Lock()

    @staticmethod
    def _number(value: str) -> float | None:
        try:
            return float(value.strip())
        except ValueError:
            return None

    def _query(self, kind: str, fields: str) -> str:
        completed: Any = self.runner(
            [
                "nvidia-smi",
                f"--query-{kind}={fields}",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            check=True,
            text=True,
            timeout=5,
        )
        return str(completed.stdout)

    def _collect(self) -> dict[str, Any]:
        counts: dict[str, set[str]] | None
        try:
            counts = {}
            for uuid, pid in csv.reader(io.StringIO(self._query("compute-apps", "gpu_uuid,pid"))):
                counts.setdefault(uuid.strip(), set()).add(pid.strip())
        except (OSError, subprocess.SubprocessError, ValueError):
            counts = None  # unknown process occupancy, never "no processes"
        gpus: list[dict[str, Any]] = []
        rows = csv.reader(io.StringIO(self._query("gpu", self._GPU_QUERY)))
        for row in rows:
            if len(row) != 10:
                raise ValueError("Unexpected nvidia-smi row")
            index, name, uuid, util, total, used, temp, power, limit, driver = (
                value.strip() for value in row
            )
            gpus.append(
                {
                    "index": int(index),
                    "name": name,
                    "utilization": self._number(util),
                    "memoryTotalMiB": self._number(total),
                    "memoryUsedMiB": self._number(used),
                    "temperatureC": self._number(temp),
                    "powerW": self._number(power),
                    "powerLimitW": self._number(limit),
                    "processCount": len(counts.get(uuid, set())) if counts is not None else None,
                    "driverVersion": driver,
                }
            )
        if not gpus:
            raise ValueError("No GPUs reported")
        return {
            "sampledAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "gpus": gpus,
        }

    def __call__(self) -> dict[str, Any]:
        with self._lock:
            now = self.clock()
            if now - self._checked_at >= GPU_SAMPLE_TTL_SECONDS:
                try:
                    self._sample = self._collect()
                    self._failed = False
                except (OSError, subprocess.SubprocessError, ValueError):
                    self._failed = True
                self._checked_at = now
            if self._sample is None:
                return {"connection": "unavailable", "node": self.node, "sample": None}
            return {
                "connection": "stale" if self._failed else "connected",
                "node": self.node,
                "sample": self._sample,
            }


class ProductServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 512

    def __init__(
        self,
        service: ProductService,
        *,
        port: int = 14380,
        web_root: Path | None = None,
        easy_web_root: Path | None = None,
        token: str | None = None,
        service_provider: Callable[[], ProductService] | None = None,
        handler_type: type[BaseHTTPRequestHandler] | None = None,
        rabbit_chat: RabbitChatService | None = None,
        transport_policy: TransportPolicy | None = None,
        web_history: tuple[Path, ...] = (),
        easy_web_history: tuple[Path, ...] = (),
    ) -> None:
        self.transport_policy = transport_policy or TransportPolicy()
        self._connection_slots = threading.BoundedSemaphore(self.transport_policy.max_connections)
        self.upload_slots = threading.BoundedSemaphore(self.transport_policy.max_uploads)
        self.upload_admissions = threading.BoundedSemaphore(
            self.transport_policy.max_uploads + self.transport_policy.effective_pending_uploads
        )
        self._service, self.web_root, self.easy_web_root = service, web_root, easy_web_root
        self.service_provider = service_provider
        self.asset_root = service.context.root
        self.web_assets = StaticAssets(self.asset_root, web_root, web_history)
        self.easy_assets = StaticAssets(self.asset_root, easy_web_root, easy_web_history)
        self.gzip_cache = GzipCache()
        self.rabbit_chat = rabbit_chat or RabbitChatService()
        self.compute_monitor = LocalGpuMonitor()
        token_path = service.root / "access-token"
        if token is None:
            try:
                with token_path.open("x") as handle:
                    os.chmod(token_path, 0o600)
                    handle.write(secrets.token_urlsafe(32))
            except FileExistsError:
                pass
            token = token_path.read_text().strip()
        self.token = token
        super().__init__(("127.0.0.1", port), handler_type or Handler)

    def process_request(
        self, request: socket.socket | tuple[bytes, socket.socket], client_address: Any
    ) -> None:
        assert isinstance(request, socket.socket)  # This server is TCP-only.
        if not self._connection_slots.acquire(blocking=False):
            body = b'{"error":{"code":"http_busy","message":"Please retry later"}}'
            try:
                request.settimeout(0.1)
                request.sendall(
                    b"HTTP/1.0 503 Service Unavailable\r\nConnection: close\r\n"
                    b"Content-Type: application/json\r\nCache-Control: no-store\r\n"
                    b"Retry-After: 2\r\nContent-Length: "
                    + str(len(body)).encode()
                    + b"\r\n\r\n"
                    + body
                )
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._connection_slots.release()
            raise

    def process_request_thread(
        self, request: socket.socket | tuple[bytes, socket.socket], client_address: Any
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connection_slots.release()

    @property
    def service(self) -> ProductService:
        return self.service_provider() if self.service_provider is not None else self._service

    def server_close(self) -> None:
        try:
            super().server_close()
        finally:
            close = getattr(self.rabbit_chat, "close", None)
            if close is not None:
                close()


class Handler(BaseHTTPRequestHandler):
    server: ProductServer
    server_version = "EasyDesignProduct/1"

    def setup(self) -> None:
        self._upload_admitted = False
        self._upload_processing = False
        super().setup()
        self.rfile.close()
        self._reader = DeadlineReader(self.connection, self.server.transport_policy.header_timeout)
        self.rfile = io.BufferedReader(self._reader)

    def finish(self) -> None:
        try:
            super().finish()
        finally:
            try:
                if self._upload_processing:
                    self._upload_processing = False
                    self.server.upload_slots.release()
            finally:
                if self._upload_admitted:
                    self._upload_admitted = False
                    self.server.upload_admissions.release()

    def client_ip(self) -> str:
        return self.server.transport_policy.client_ip(self.client_address[0], self.headers)

    def log_message(self, format: str, *args: Any) -> None:
        # Never log access tokens or user-supplied URLs/structure data.
        pass

    def send(
        self,
        status: int,
        data: Any,
        mime: str = "application/json",
        *,
        cookie: str | None = None,
        immutable: bool = False,
    ) -> None:
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        compressible = (
            immutable
            and status == 200
            and cookie is None
            and mime in {"text/javascript", "application/javascript", "text/css"}
            and 1024 <= len(body) <= 8 * 1024 * 1024
        )
        compressed = compressible and accepts_gzip(
            ",".join(self.headers.get_all("Accept-Encoding", []))
        )
        if compressed:
            body = self.server.gzip_cache.encode(body)
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.close_connection = True
        if (
            status == 503
            and isinstance(data, dict)
            and isinstance(data.get("error"), dict)
            and data["error"].get("code") in {"upload_busy", "read_busy"}
        ):
            self.send_header("Retry-After", "2")
        if compressible:
            self.send_header("Vary", "Accept-Encoding")
        if compressed:
            self.send_header("Content-Encoding", "gzip")
        self.send_header(
            "Cache-Control",
            "public, max-age=31536000, immutable"
            if immutable and status == 200 and cookie is None
            else "no-store",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
            "font-src 'self'; connect-src 'self'; worker-src 'self' blob:; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def host_guard(self) -> None:
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = self.headers.get("Host", "")
        if host not in hosts:
            raise ProductError("invalid_host", "Use the local Workbench origin", 403)
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{host}":
            raise ProductError("invalid_origin", "Cross-origin product access is forbidden", 403)

    def authenticated(self) -> bool:
        bearer = self.headers.get("Authorization", "")
        if bearer.startswith("Bearer "):
            return hmac.compare_digest(bearer[7:], self.server.token)
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        value = cookie.get("easydesign_session")
        valid = value is not None and hmac.compare_digest(value.value, self.server.token)
        if valid and self.command == "POST" and not self.headers.get("Origin"):
            raise ProductError(
                "origin_required", "Browser writes require a same-origin request", 403
            )
        return valid

    def body_size(self, maximum: int = 128 * 1024) -> int:
        if self.headers.get("Transfer-Encoding"):
            raise ProductError("invalid_body", "Chunked input is not accepted")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) > 1 or (lengths and not re.fullmatch(r"0|[1-9][0-9]*", lengths[0])):
            raise ProductError("invalid_body", "Ambiguous content length")
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ProductError("invalid_body", "Invalid content length") from error
        if size < 0 or size > maximum:
            raise ProductError("payload_too_large", "Request exceeds the bounded input size", 413)
        return size

    def body(self, maximum: int = 128 * 1024, *, deadline: float | None = None) -> bytes:
        size = self.body_size(maximum)
        self._reader.reset(self.server.transport_policy.body_timeout, deadline=deadline)
        try:
            if self._reader.deadline <= time.monotonic():
                raise TimeoutError("HTTP body deadline exceeded")
            body = self.rfile.read(size)
        except TimeoutError as error:
            raise ProductError("body_timeout", "Request body reading timed out", 408) from error
        if len(body) != size:
            raise ProductError("invalid_body", "Request body ended before its declared length")
        return body

    def json_body(self) -> Any:
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise ProductError("invalid_content_type", "Expected application/json", 415)
        return json.loads(self.body())

    def authorize_upload(self) -> None:
        if not self.authenticated():
            raise ProductError("unauthorized", "Open the Workbench access link", 401)

    def receive_upload(
        self, service: ProductService, filename: str, deadline: float
    ) -> dict[str, Any]:
        # Recheck after queueing and after the body read; neither phase grants
        # lasting permission to persist data. This frame releases the body on return.
        self.authorize_upload()
        data = self.body(32 * 1024**2, deadline=deadline)
        self.authorize_upload()
        return service.upload(filename, data)

    def do_GET(self) -> None:
        self.dispatch()

    def do_POST(self) -> None:
        self.dispatch()

    def dispatch(self) -> None:
        try:
            self.host_guard()
            url = urlsplit(self.path)
            path = unquote(url.path)
            if "\x00" in path or "\\" in path or ".." in path.split("/"):
                raise ProductError("invalid_path", "Invalid product path", 403)
            if path == "/api/v1/session" and self.command == "POST":
                payload = self.json_body()
                if (
                    not isinstance(payload, dict)
                    or not isinstance(payload.get("token"), str)
                    or not hmac.compare_digest(payload["token"], self.server.token)
                ):
                    raise ProductError("unauthorized", "A local access token is required", 401)
                self.send(
                    200,
                    {"authenticated": True, "mode": "single-user-local"},
                    cookie=(
                        f"easydesign_session={self.server.token}; "
                        f"Max-Age={SESSION_COOKIE_MAX_AGE_SECONDS}; "
                        "HttpOnly; SameSite=Strict; Path=/"
                    ),
                )
                return
            if not path.startswith("/api/"):
                self.serve_static_page(path)
                return
            if not self.authenticated():
                raise ProductError("unauthorized", "Open the Workbench access link", 401)
            if path == "/api/rabbit/chat":
                if url.query:
                    raise ProductError("invalid_request", "Chat endpoint takes no query", 400)
                if self.command == "GET":
                    self.send(200, self.server.rabbit_chat.status())
                    return
                if self.command != "POST":
                    raise ProductError("method_not_allowed", "Chat accepts GET and POST", 405)
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ProductError("invalid_content_type", "Expected application/json", 415)
                payload = json.loads(self.body(140 * 1024))
                events = self.server.rabbit_chat.events(payload)
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Connection", "close")
                self.end_headers()
                for event in events:
                    self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode())
                    self.wfile.flush()
                self.close_connection = True
                return
            if path == "/api/compute/resources":
                if self.command != "GET":
                    raise ProductError("method_not_allowed", "Resource telemetry is read-only", 405)
                if url.query:
                    raise ProductError("invalid_request", "Resource telemetry takes no query", 400)
                self.send(200, self.server.compute_monitor())
                return
            parts = path.strip("/").split("/")
            query = parse_qs(url.query)
            service = self.server.service
            offset = max(0, int(query.get("offset", ["0"])[0]))
            limit = min(100, max(1, int(query.get("limit", ["20"])[0])))
            if parts[:2] != ["api", "v1"]:
                raise ProductError("not_found", "Unknown API version", 404)
            tail = parts[2:]
            if self.command == "GET":
                if tail == ["health"]:
                    result: Any = {"schema_version": "1", "mode": "live", "status": "ready"}
                elif tail == ["projects"]:
                    surface = query.get("surface", [None])[0]
                    result = service.projects(offset, limit, surface=surface)
                elif len(tail) == 2 and tail[0] == "requests":
                    result = service.request(tail[1])
                elif len(tail) == 2 and tail[0] == "artifacts":
                    data, fmt = service.catalog.read(tail[1])
                    mime = {
                        "pdb": "chemical/x-pdb",
                        "cif": "chemical/x-mmcif",
                        "mmcif": "chemical/x-mmcif",
                        "json": "application/json",
                        "yaml": "text/plain",
                        "yml": "text/plain",
                    }.get(fmt, "application/octet-stream")
                    self.send(200, data, mime)
                    return
                elif len(tail) >= 3 and tail[0] == "projects":
                    project, resource = tail[1:3]
                    if resource == "workbench" and len(tail) == 3:
                        result = service.snapshot(project)
                    elif resource == "candidates" and len(tail) in {3, 4}:
                        view = query.get("view", ["full"])[0]
                        if view not in {"full", "summary"}:
                            raise ProductError(
                                "invalid_request", "Candidate view must be full or summary", 400
                            )
                        result = service.candidates(
                            project,
                            offset,
                            limit,
                            tail[3] if len(tail) == 4 else None,
                            compact=view == "summary",
                        )
                    elif resource == "events" and len(tail) == 3:
                        result = service.events(project, int(query.get("after", ["0"])[0]), limit)
                    elif resource == "lab-order" and len(tail) == 3:
                        result = service.lab_order(project)
                    else:
                        raise ProductError("not_found", "Unknown project resource", 404)
                else:
                    raise ProductError("not_found", "Unknown API resource", 404)
                self.send(200, result)
            elif tail == ["inputs"]:
                self.authorize_upload()
                self.body_size(32 * 1024**2)
                policy = self.server.transport_policy
                deadline = time.monotonic() + policy.body_timeout
                if not self.server.upload_admissions.acquire(blocking=False):
                    raise ProductError("upload_busy", "上传通道繁忙，请稍后重试", 503)
                self._upload_admitted = True
                wait = policy.upload_wait_timeout if policy.effective_pending_uploads else 0
                if not self.server.upload_slots.acquire(
                    timeout=min(wait, max(0, deadline - time.monotonic()))
                ):
                    if time.monotonic() >= deadline:
                        raise ProductError("body_timeout", "Request body reading timed out", 408)
                    raise ProductError("upload_busy", "上传通道繁忙，请稍后重试", 503)
                self._upload_processing = True
                # Failures keep this slot until finish: exception tracebacks may
                # retain body bytes while the original error response is sent.
                result = self.receive_upload(service, query.get("filename", [""])[0], deadline)
                self._upload_processing = False
                self.server.upload_slots.release()
                self.send(201, result)
            elif tail == ["projects"]:
                self.send(202, service.create(CreateProject.model_validate(self.json_body())))
            elif len(tail) == 3 and tail[0] == "projects" and tail[2] == "title":
                payload = RenameProject.model_validate(self.json_body())
                self.send(200, service.rename(tail[1], payload.title))
            elif len(tail) == 3 and tail[0] == "projects" and tail[2] == "actions":
                self.send(
                    202, service.submit(tail[1], ActionRequest.model_validate(self.json_body()))
                )
            elif len(tail) == 3 and tail[0] == "projects" and tail[2] == "lab-order":
                self.send(
                    200,
                    service.apply_lab_order(
                        tail[1], LabOrderCommand.model_validate(self.json_body())
                    ),
                )
            elif len(tail) == 3 and tail[0] == "requests" and tail[2] == "resume":
                self.json_body()
                self.send(202, service.retry(tail[1]))
            elif len(tail) == 3 and tail[0] == "requests" and tail[2] == "cancel":
                self.json_body()
                cancel = getattr(service, "cancel_queued", None)
                if cancel is None:
                    raise ProductError(
                        "queue_not_cancellable", "This request cannot be cancelled", 409
                    )
                self.send(200, cancel(tail[1]))
            else:
                raise ProductError("not_found", "Unknown API action", 404)
        except ProductError as error:
            self.send(
                error.status,
                {
                    "error": {
                        "code": error.code,
                        "message": str(error),
                        "refresh_required": error.code == "stale_state",
                    }
                },
            )
        except (ValidationError, ValueError, json.JSONDecodeError):
            self.send(
                400, {"error": {"code": "invalid_request", "message": "Request fields are invalid"}}
            )
        except AgentBoundaryError:
            self.send(
                409,
                {
                    "error": {
                        "code": "native_boundary",
                        "message": "Native evidence or session requires reconciliation",
                        "refresh_required": True,
                    }
                },
            )
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            logging.getLogger(__name__).exception("Product HTTP request failed")
            self.send(
                500,
                {
                    "error": {
                        "code": "operational_error",
                        "message": "The product request could not be completed; "
                        "scientific evidence is retained",
                    }
                },
            )

    def static(self, path: str) -> None:
        if self.command != "GET":
            raise ProductError("not_found", "Workbench build is not available", 404)
        easy = path == "/easy" or path.startswith("/easy/")
        root = self.server.easy_web_root if easy else self.server.web_root
        if root is None:
            raise ProductError("not_found", "Workbench build is not available", 404)
        relative = (
            "index.html"
            if path == "/easy"
            else path.removeprefix("/easy/").lstrip("/")
            if easy
            else path.lstrip("/")
        )
        relative = relative or "index.html"
        if not (
            relative == "index.html"
            or relative.startswith(("assets/", "structures/", "mascot/rabbit/"))
            or relative in {"favicon.svg"}
        ):
            raise ProductError("not_found", "Unknown Workbench resource", 404)
        data = (self.server.easy_assets if easy else self.server.web_assets).read(relative)
        self.send(
            200,
            data,
            mimetypes.guess_type(relative)[0] or "application/octet-stream",
            immutable=HASHED_BUILD_ASSET.fullmatch(relative) is not None,
        )

    def serve_static_page(self, path: str) -> None:
        """Browsers navigating to an unknown page get an HTML 404, not bare JSON."""
        try:
            self.static(path)
        except ProductError as error:
            if error.status == 404 and "text/html" in self.headers.get("Accept", ""):
                self.send(404, _STATIC_NOT_FOUND_PAGE, "text/html; charset=utf-8")
            else:
                raise


def load_provider_credentials(gateway: NativeGateway, env_file: Path | None) -> None:
    """Load only declared provider variables; never execute a credential file."""
    import shlex

    config = gateway.config()
    names = {p.secret_env for p in [config.default, *config.roles.values()]}
    if env_file:
        env_path = confined(gateway.context.root, gateway.context.root / env_file)
        for line in env_path.read_text().splitlines():
            line = line.strip().removeprefix("export ")
            name, separator, value = line.partition("=")
            if separator and name.strip() in names:
                parts = shlex.split(value, comments=True)
                if len(parts) == 1:
                    os.environ[name.strip()] = parts[0]
    missing = sorted(name for name in names if not os.environ.get(name))
    if missing:
        raise ProductError(
            "model_not_configured", "Provider credential missing: " + ", ".join(missing)
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local EasyDesign Workbench product service")
    parser.add_argument("--port", type=int, default=14380)
    parser.add_argument("--models", type=Path, default=Path("config/llm.yaml"))
    parser.add_argument(
        "--multi-user", action="store_true", help="Serve isolated accounts and team workspaces"
    )
    parser.add_argument(
        "--accounts-only",
        action="store_true",
        help="Explicitly enable account administration without scientific execution",
    )
    parser.add_argument("--public-origin", help="Explicit trusted HTTPS origin for a reverse proxy")
    parser.add_argument(
        "--capacity-config",
        type=Path,
        help="Explicit workspace-local JSON for HTTP, login, AI and queue limits",
    )
    parser.add_argument(
        "--gpu-devices",
        help="Optional comma-separated physical GPU indices available to this product",
    )
    parser.add_argument("--web", type=Path, default=Path("web/workbench/dist"))
    parser.add_argument(
        "--easy-web",
        type=Path,
        default=Path("web/easy/dist"),
        help="Optional Easy UI build served from /easy/ on the same authenticated origin",
    )
    parser.add_argument(
        "--app-web",
        type=Path,
        help="Optional unified app build served from /app/ on the same authenticated origin",
    )
    parser.add_argument(
        "--prediction-backend",
        choices=("openfold3-af3-jax", "protenix-v2"),
        default="openfold3-af3-jax",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Private provider credentials; parsed as values, never executed",
    )
    args = parser.parse_args(argv)
    if args.accounts_only and not args.multi_user:
        parser.error("--accounts-only requires --multi-user")
    if args.multi_user:
        from .accounts_cli import serve_accounts

        return serve_accounts(
            port=args.port,
            models=args.models,
            env_file=args.env_file,
            web=args.web,
            easy_web=args.easy_web,
            prediction_backend=args.prediction_backend,
            public_origin=args.public_origin,
            accounts_only=args.accounts_only,
            gpu_devices=args.gpu_devices,
            capacity_config=args.capacity_config,
            app_web=args.app_web,
        )
    context = WorkspaceContext.discover()
    capacity = load_capacity_config(context.root, args.capacity_config)
    # A product launch owns its workspace-local writable metadata.  This creates
    # only the empty default profile/registries when no explicit runtime link has
    # been activated; backend availability and all scientific checks still fail closed.
    initialize_workspace_metadata(context)
    gateway = NativeGateway(
        context,
        confined(context.root, context.root / args.models),
        prediction_backend=args.prediction_backend,
    )
    load_provider_credentials(gateway, args.env_file)
    web_root = confined(context.root, context.root / args.web)
    if not (web_root / "index.html").is_file():
        raise ProductError(
            "workbench_not_built",
            "Workbench build is missing; run pnpm install --frozen-lockfile and pnpm build "
            "inside web/workbench",
        )
    easy_web_root = confined(context.root, context.root / args.easy_web)
    if not (easy_web_root / "index.html").is_file():
        raise ProductError(
            "easy_workbench_not_built",
            "Easy Workbench build is missing; run pnpm install --frozen-lockfile and pnpm build "
            "inside web/easy",
        )
    source_root = Path(__file__).resolve().parents[3]
    rabbit_script = confined(context.root, source_root / "web/easy/server/rabbit_chat.py")
    server = ProductServer(
        ProductService(gateway, actor=f"local-workbench:uid:{os.getuid()}"),
        port=args.port,
        web_root=web_root,
        easy_web_root=easy_web_root,
        transport_policy=capacity.http.policy(),
        web_history=tuple(context.root / path for path in capacity.web_history),
        easy_web_history=tuple(context.root / path for path in capacity.easy_web_history),
        rabbit_chat=RabbitChatService(
            SubprocessChatProvider(
                rabbit_script,
                confined(context.root, context.root / (args.env_file or Path(".env.local"))),
            )
            if os.environ.get("DEEPSEEK_API_KEY") and rabbit_script.is_file()
            else None,
            limits=RabbitCapacityLimits(**capacity.ai),
            ledger_path=context.runtime_root / "state/product/rabbit-chat.sqlite",
        ),
    )
    # The token is written to the owner-only state file.  Never duplicate it in
    # process logs, shell history, or service-manager output.
    print(f"Workbench: http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
