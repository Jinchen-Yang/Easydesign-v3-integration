import json
from pathlib import Path

import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.product.capacity_config import load_capacity_config
from easydesign.product.contracts import ProductError
from easydesign.product.static_assets import GzipCache, StaticAssets, accepts_gzip
from easydesign.workspace_context import WorkspaceContext


def test_defaults_preserve_conservative_login_ai_and_transport_capacity(tmp_path):
    config = load_capacity_config(tmp_path, None)
    assert config.login.max_concurrency == 8
    assert config.login.max_pending == 300
    assert config.http.policy().trusted_proxies == ()
    assert config.http.max_connections > config.http.max_uploads


@pytest.mark.parametrize(
    "body",
    [
        {"unknown": 1},
        {"login": {"max_concurrency": True}},
        {"login": {"wait_timeout": -1}},
        {"http": {"max_connections": 2, "max_uploads": 3}},
        {"http": {"trusted_proxies": ["everything"]}},
        {"ai": {"unknown": 1}},
        {"ai": {"max_active": 0}},
        {"queue": {"max_conversation_workers": 0}},
    ],
)
def test_capacity_file_rejects_unknown_fields_and_invalid_limits(tmp_path, body):
    path = tmp_path / "capacity.json"
    path.write_text(json.dumps(body))
    with pytest.raises(ProductError) as error:
        load_capacity_config(tmp_path, path)
    assert error.value.code == "invalid_capacity_config"


@pytest.mark.parametrize(
    "header,expected",
    [
        ("gzip", True),
        ("gzip;q=0", False),
        ("gzip;q=0, *;q=1", False),
        ("br, *;q=0.5", True),
        ("gzip;q=bogus", False),
        ("gzip;q=1, gzip;q=0", False),
    ],
)
def test_gzip_negotiation_respects_explicit_refusal(header, expected):
    assert accepts_gzip(header) is expected


def test_repeated_bundle_compression_is_reused_and_cache_eviction_is_bounded(monkeypatch):
    import gzip

    original = gzip.compress
    calls = []

    def compress(data, **kwargs):
        calls.append(data)
        return original(data, **kwargs)

    monkeypatch.setattr(gzip, "compress", compress)
    cache = GzipCache(maximum_bytes=1024, maximum_entries=1)
    first = cache.encode(b"first" * 100)
    assert cache.encode(b"first" * 100) == first
    assert len(calls) == 1
    cache.encode(b"second" * 100)
    assert cache.encode(b"first" * 100) == first
    assert len(calls) == 3


def test_account_cli_wires_one_explicit_config_into_each_owned_capacity_boundary(
    tmp_path, monkeypatch
):
    from easydesign.product import accounts_cli

    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    for relative in ("easy/account/index.html", "easy/index.html", "pro/index.html"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    (tmp_path / "capacity.json").write_text(
        json.dumps(
            {
                "login": {"max_concurrency": 3, "max_pending": 7, "wait_timeout": 2.5},
                "http": {
                    "max_connections": 24,
                    "max_uploads": 2,
                    "trusted_proxies": ["127.0.0.1/32"],
                },
                "ai": {"max_active": 1, "max_queued": 5},
                "queue": {
                    "max_active_admissions": 17,
                    "max_conversation_workers": 2,
                    "startup_timeout_seconds": 12.0,
                },
            }
        )
    )
    captured = {}
    original = accounts_cli.AccountStore

    def store(path, **kwargs):
        captured["login"] = kwargs
        return original(path, **kwargs)

    class Supervisor:
        def __init__(self, runtime, **kwargs):
            captured["queue"] = kwargs

        def start(self):
            pass

        def close(self):
            pass

    class Server:
        server_port = 0

        def __init__(self, runtime, **kwargs):
            captured["server"] = kwargs
            captured["runtime"] = runtime

        def serve_forever(self):
            pass

        def server_close(self):
            captured["server"]["rabbit_chat"].close()

    monkeypatch.setattr(accounts_cli.WorkspaceContext, "discover", lambda: context)
    monkeypatch.setattr(accounts_cli, "AccountStore", store)
    monkeypatch.setattr(accounts_cli, "ResourceSupervisor", Supervisor)
    monkeypatch.setattr(accounts_cli, "MultiUserServer", Server)
    monkeypatch.setattr(accounts_cli, "initialize_workspace_metadata", lambda _context: None)
    monkeypatch.setattr(accounts_cli, "load_provider_credentials", lambda *_args: None)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert (
        accounts_cli.serve_accounts(
            port=0,
            models=Path("models.yaml"),
            env_file=None,
            web=Path("pro"),
            easy_web=Path("easy"),
            prediction_backend="protenix-v2",
            public_origin=None,
            accounts_only=False,
            gpu_devices=None,
            capacity_config=Path("capacity.json"),
        )
        == 0
    )
    assert captured["login"] == {
        "login_max_concurrency": 3,
        "login_max_pending": 7,
        "login_wait_timeout": 2.5,
    }
    assert captured["queue"] == {
        "allowed_devices": None,
        "max_conversation_workers": 2,
        "startup_timeout_seconds": 12.0,
    }
    assert captured["runtime"].resources.max_active_admissions == 17
    assert captured["server"]["transport_policy"].max_connections == 24
    assert captured["server"]["transport_policy"].max_uploads == 2
    assert captured["server"]["rabbit_chat"].limits.max_active == 1
    assert captured["server"]["rabbit_chat"].limits.max_queued == 5
    assert (context.runtime_root / "state/accounts/rabbit-chat.sqlite").is_file()


def test_history_rejects_symlink_and_outside_roots_and_detects_post_start_changes(tmp_path):
    workspace = tmp_path / "workspace"
    current, previous = workspace / "current", workspace / "previous"
    for root in (current, previous):
        (root / "assets").mkdir(parents=True)
    relative = "assets/retained-BAsZliUl.js"
    (previous / relative).write_text("initial")
    assets = StaticAssets(workspace, current, (previous,))
    assert assets.read(relative) == b"initial"
    (previous / relative).write_text("modified after publication")
    with pytest.raises(ProductError) as changed:
        assets.read(relative)
    assert changed.value.code == "immutable_conflict"
    alias = workspace / "alias"
    alias.symlink_to(previous, target_is_directory=True)
    with pytest.raises(AgentBoundaryError):
        StaticAssets(workspace, current, (alias,))
    with pytest.raises(AgentBoundaryError):
        StaticAssets(workspace, current, (tmp_path,))
    (previous / "assets/linked-ZAsZliUl.js").symlink_to(previous / relative)
    with pytest.raises(ProductError):
        StaticAssets(workspace, current, (previous,))
