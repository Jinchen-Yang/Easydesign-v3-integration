"""Public build assets may be cached; account and private responses may not."""

from __future__ import annotations

import json
import socket
import threading
from http.client import HTTPResponse

import httpx
import pytest

from easydesign.product.account_server import MultiUserServer
from easydesign.product.accounts import AccountStore
from easydesign.product.domain import NativeGateway
from easydesign.product.server import ProductServer
from easydesign.product.service import ProductService
from easydesign.product.tenancy import MultiUserRuntime
from easydesign.workspace_context import WorkspaceContext


@pytest.fixture(params=["local", "accounts"])
def static_site(tmp_path, request):
    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    web = tmp_path / "web-build"
    (web / "assets").mkdir(parents=True)
    (web / "account").mkdir()
    (web / "index.html").write_text("<head></head><body>fixture</body>")
    (web / "account/index.html").write_text("<head></head><body>account</body>")
    gateway = NativeGateway(context, tmp_path / "models.yaml")
    if request.param == "accounts":
        accounts = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
        runtime = MultiUserRuntime(
            context, accounts, lambda scoped: NativeGateway(scoped, tmp_path / "models.yaml")
        )
        server = MultiUserServer(runtime, port=0, web_root=web, easy_web_root=web)
    else:
        server = ProductServer(
            ProductService(gateway), port=0, web_root=web, easy_web_root=web, token="fixture"
        )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False
        ) as client:
            yield client, web
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_content_hashed_build_scripts_allow_browser_and_shared_cache(static_site):
    client, web = static_site
    (web / "assets/app-BAsZliUl.js").write_text("export const fixture = true;")
    for path in ("/assets/app-BAsZliUl.js", "/easy/assets/app-BAsZliUl.js"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.text == "export const fixture = true;"
        assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"
        assert "Set-Cookie" not in response.headers


@pytest.mark.parametrize("name", ["style-BwqamVgK.css", "font-CqBn_3x2.woff2"])
def test_hashed_styles_and_fonts_are_cacheable(static_site, name):
    client, web = static_site
    (web / "assets" / name).write_bytes(b"fixture")
    response = client.get("/easy/assets/" + name)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"


def test_html_unversioned_files_and_errors_remain_uncacheable(static_site):
    client, web = static_site
    for name in ("app.js", "app-short.js", "report-BAsZliUl.json", "app-BAsZliUl.js.map"):
        (web / "assets" / name).write_bytes(b"fixture")
    for path in (
        "/",
        "/easy/",
        "/account/",
        "/assets/app.js",
        "/easy/assets/app-short.js",
        "/assets/report-BAsZliUl.json",
        "/assets/app-BAsZliUl.js.map",
        "/assets/missing-BAsZliUl.js",
        "/easy/%2e%2e/assets/app-BAsZliUl.js",
        "/api/v1/health",
        "/api/v1/accounts/config",
        "/api/v1/artifacts/app-BAsZliUl.js",
    ):
        assert client.get(path).headers["Cache-Control"] == "no-store", path
    response = client.post("/api/v1/session", json={"token": "fixture"})
    assert response.headers["Cache-Control"] == "no-store"
    invalid_host = client.get("/assets/app-BAsZliUl.js", headers={"Host": "untrusted.invalid"})
    assert invalid_host.status_code == 403
    assert invalid_host.headers["Cache-Control"] == "no-store"


def test_incomplete_request_body_is_rejected_before_processing(static_site):
    client, _web = static_site
    accounts_mode = client.get("/api/v1/accounts/config").status_code == 200
    path = "/api/v1/accounts/login" if accounts_mode else "/api/v1/session"
    payload = json.dumps(
        {"username": "fixture", "password": "Fixture-password-2026!"}
        if accounts_mode
        else {"token": "fixture"}
    ).encode()
    origin = str(client.base_url).rstrip("/")
    headers = (
        f"POST {path} HTTP/1.1\r\n"
        f"Host: {client.base_url.host}:{client.base_url.port}\r\n"
        f"Origin: {origin}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload) + 10}\r\n\r\n"
    ).encode()
    with socket.create_connection((client.base_url.host, client.base_url.port), timeout=5) as conn:
        conn.sendall(headers + payload)
        conn.shutdown(socket.SHUT_WR)
        response = HTTPResponse(conn)
        response.begin()
        assert response.status == 400
        assert json.loads(response.read())["error"]["code"] == "invalid_body"
        assert response.getheader("Cache-Control") == "no-store"
