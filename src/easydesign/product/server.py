"""Single-user loopback Product API and same-origin Workbench static delivery."""

from __future__ import annotations

import argparse
import hmac
import json
import logging
import mimetypes
import os
import secrets
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

from .artifacts import confined_bytes
from .contracts import ActionRequest, CreateProject, ProductError, RenameProject
from .domain import NativeGateway
from .service import ProductService


# Keep an authenticated local browser usable across ordinary browser restarts.
# The cookie remains origin-bound, HttpOnly and strict same-site; the durable
# workspace token is still required for the first login in each browser profile.
SESSION_COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


class ProductServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        service: ProductService,
        *,
        port: int = 14380,
        web_root: Path | None = None,
        token: str | None = None,
    ) -> None:
        self.service, self.web_root = service, web_root
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
        super().__init__(("127.0.0.1", port), Handler)


class Handler(BaseHTTPRequestHandler):
    server: ProductServer
    server_version = "EasyDesignProduct/1"

    def log_message(self, format: str, *args: Any) -> None:
        # Never log access tokens or user-supplied URLs/structure data.
        pass

    def send(
        self, status: int, data: Any, mime: str = "application/json", *, cookie: str | None = None
    ) -> None:
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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

    def body(self, maximum: int = 128 * 1024) -> bytes:
        if self.headers.get("Transfer-Encoding"):
            raise ProductError("invalid_body", "Chunked input is not accepted")
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ProductError("invalid_body", "Invalid content length") from error
        if size < 0 or size > maximum:
            raise ProductError("payload_too_large", "Request exceeds the bounded input size", 413)
        self.connection.settimeout(20)
        return self.rfile.read(size)

    def json_body(self) -> Any:
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise ProductError("invalid_content_type", "Expected application/json", 415)
        return json.loads(self.body())

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
                self.static(path)
                return
            if not self.authenticated():
                raise ProductError("unauthorized", "Open the Workbench access link", 401)
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
                    result = service.projects(offset, limit)
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
                        result = service.candidates(
                            project, offset, limit, tail[3] if len(tail) == 4 else None
                        )
                    elif resource == "events" and len(tail) == 3:
                        result = service.events(project, int(query.get("after", ["0"])[0]), limit)
                    else:
                        raise ProductError("not_found", "Unknown project resource", 404)
                else:
                    raise ProductError("not_found", "Unknown API resource", 404)
                self.send(200, result)
            elif tail == ["inputs"]:
                self.send(
                    201, service.upload(query.get("filename", [""])[0], self.body(32 * 1024**2))
                )
            elif tail == ["projects"]:
                self.send(202, service.create(CreateProject.model_validate(self.json_body())))
            elif len(tail) == 3 and tail[0] == "projects" and tail[2] == "title":
                payload = RenameProject.model_validate(self.json_body())
                self.send(200, service.rename(tail[1], payload.title))
            elif len(tail) == 3 and tail[0] == "projects" and tail[2] == "actions":
                self.send(
                    202, service.submit(tail[1], ActionRequest.model_validate(self.json_body()))
                )
            elif len(tail) == 3 and tail[0] == "requests" and tail[2] == "resume":
                self.json_body()
                self.send(202, service.retry(tail[1]))
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
        if self.command != "GET" or self.server.web_root is None:
            raise ProductError("not_found", "Workbench build is not available", 404)
        relative = path.lstrip("/") or "index.html"
        if not (
            relative == "index.html"
            or relative.startswith(("assets/", "structures/"))
            or relative in {"favicon.svg"}
        ):
            raise ProductError("not_found", "Unknown Workbench resource", 404)
        data = confined_bytes(self.server.web_root, relative, maximum=32 * 1024**2)
        self.send(200, data, mimetypes.guess_type(relative)[0] or "application/octet-stream")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local EasyDesign Workbench product service")
    parser.add_argument("--port", type=int, default=14380)
    parser.add_argument("--models", type=Path, default=Path("config/llm.yaml"))
    parser.add_argument("--web", type=Path, default=Path("web/workbench/dist"))
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
    context = WorkspaceContext.discover()
    # A product launch owns its workspace-local writable metadata.  This creates
    # only the empty default profile/registries when no explicit runtime link has
    # been activated; backend availability and all scientific checks still fail closed.
    initialize_workspace_metadata(context)
    gateway = NativeGateway(
        context,
        confined(context.root, context.root / args.models),
        prediction_backend=args.prediction_backend,
    )
    # A live product must be ready to answer, not merely serve saved screenshots.
    # Only declared credential names are read; shell syntax is never executed.
    import shlex

    config = gateway.config()
    names = {p.secret_env for p in [config.default, *config.roles.values()]}
    if args.env_file:
        env_path = confined(context.root, context.root / args.env_file)
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
    web_root = confined(context.root, context.root / args.web)
    if not (web_root / "index.html").is_file():
        raise ProductError(
            "workbench_not_built",
            "Workbench build is missing; run pnpm install --frozen-lockfile and pnpm build "
            "inside web/workbench",
        )
    server = ProductServer(
        ProductService(gateway, actor=f"local-workbench:uid:{os.getuid()}"),
        port=args.port,
        web_root=web_root,
    )
    print(f"Workbench: http://127.0.0.1:{server.server_port}/#access={server.token}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
