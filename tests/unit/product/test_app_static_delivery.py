"""Unified app (/app/) static delivery: allowlist, caching and HTML 404 pages."""

from __future__ import annotations

import threading

import httpx
import pytest

from easydesign.product.account_server import MultiUserServer
from easydesign.product.accounts import AccountStore
from easydesign.product.domain import NativeGateway
from easydesign.product.server import ProductServer
from easydesign.product.service import ProductService
from easydesign.product.tenancy import MultiUserRuntime
from easydesign.workspace_context import WorkspaceContext

HASHED_JS = "assets/app-BAsZliUl.js"


@pytest.fixture
def app_site(tmp_path):
    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    web = tmp_path / "web-build"
    (web / "account").mkdir(parents=True)
    (web / "index.html").write_text("<head></head><body>pro</body>")
    (web / "account/index.html").write_text("<head></head><body>account</body>")
    app = tmp_path / "app-build"
    (app / "assets").mkdir(parents=True)
    (app / "mascot/rabbit").mkdir(parents=True)
    (app / "structures").mkdir(parents=True)
    (app / "index.html").write_text("<head></head><body>unified app</body>")
    (app / HASHED_JS).write_text("export const fixture = true;")
    (app / "mascot/rabbit/rabbit-mascot.png").write_bytes(b"png-fixture")
    (app / "structures/1MEL.pdb").write_text("ATOM      1  N   ALA A   1\n")
    (app / "favicon.svg").write_text("<svg/>")
    accounts = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    runtime = MultiUserRuntime(
        context, accounts, lambda scoped: NativeGateway(scoped, tmp_path / "models.yaml")
    )
    server = MultiUserServer(runtime, port=0, web_root=web, easy_web_root=web, app_web_root=app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False
        ) as client:
            yield client
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def app_site_without_app(tmp_path):
    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    web = tmp_path / "web-build"
    (web / "account").mkdir(parents=True)
    (web / "index.html").write_text("<head></head><body>pro</body>")
    (web / "account/index.html").write_text("<head></head><body>account</body>")
    accounts = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    runtime = MultiUserRuntime(
        context, accounts, lambda scoped: NativeGateway(scoped, tmp_path / "models.yaml")
    )
    server = MultiUserServer(runtime, port=0, web_root=web, easy_web_root=web)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False
        ) as client:
            yield client
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_app_index_served_at_app_root(app_site):
    for path in ("/app", "/app/", "/app/index.html"):
        response = app_site.get(path)
        assert response.status_code == 200, path
        assert "unified app" in response.text
        assert response.headers["Content-Type"] == "text/html"
        assert response.headers["Cache-Control"] == "no-store"


def test_app_hashed_assets_are_immutable(app_site):
    response = app_site.get("/app/" + HASHED_JS)
    assert response.status_code == 200
    assert response.text == "export const fixture = true;"
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"


def test_app_mascot_and_structure_assets_served(app_site):
    mascot = app_site.get("/app/mascot/rabbit/rabbit-mascot.png")
    assert mascot.status_code == 200
    assert mascot.content == b"png-fixture"
    structure = app_site.get("/app/structures/1MEL.pdb")
    assert structure.status_code == 200
    assert structure.text.startswith("ATOM")
    favicon = app_site.get("/app/favicon.svg")
    assert favicon.status_code == 200


def test_app_allowlist_misses_and_traversal_are_not_served(app_site):
    assert app_site.get("/app/secret.txt").status_code == 404
    # A missing whitelisted file follows the parent tree's semantics: 409
    # artifact_unavailable from the confined reader, same as / and /easy/.
    missing = app_site.get("/app/assets/missing-BAsZliUl.js")
    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "artifact_unavailable"
    assert app_site.get("/apple").status_code == 404
    # The dispatcher rejects decoded ".." segments before static() runs.
    traversal = app_site.get("/app/%2e%2e/etc/passwd")
    assert traversal.status_code == 403


def test_app_non_get_is_rejected(app_site):
    # Same-site non-GET reaches static() and is not found; a cross-site POST is
    # stopped even earlier by the CSRF origin guard.
    origin = str(app_site.base_url).rstrip("/")
    assert app_site.post("/app/", headers={"Origin": origin}).status_code == 404
    assert app_site.post("/app/").status_code == 403


def test_existing_surfaces_are_untouched(app_site):
    assert "pro" in app_site.get("/").text
    assert "account" in app_site.get("/account/").text
    assert "pro" in app_site.get("/easy/").text


def test_app_stays_404_until_a_release_points_app_web(app_site_without_app):
    response = app_site_without_app.get("/app/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_browser_misses_get_an_html_404(app_site):
    page = app_site.get("/missing-page", headers={"Accept": "text/html,application/xhtml+xml"})
    assert page.status_code == 404
    assert page.headers["Content-Type"].startswith("text/html")
    assert "页面不存在" in page.text
    api = app_site.get("/missing-page", headers={"Accept": "application/json"})
    assert api.status_code == 404
    assert api.headers["Content-Type"] == "application/json"
    assert api.json()["error"]["code"] == "not_found"


def test_single_user_static_misses_also_get_html_404(tmp_path):
    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    web = tmp_path / "web-build"
    (web / "account").mkdir(parents=True)
    (web / "index.html").write_text("<head></head><body>pro</body>")
    gateway = NativeGateway(context, tmp_path / "models.yaml")
    server = ProductServer(
        ProductService(gateway), port=0, web_root=web, easy_web_root=web, token="fixture"
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False
        ) as client:
            page = client.get("/missing-page", headers={"Accept": "text/html"})
            assert page.status_code == 404
            assert "页面不存在" in page.text
            api = client.get("/missing-page", headers={"Accept": "application/json"})
            assert api.json()["error"]["code"] == "not_found"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
