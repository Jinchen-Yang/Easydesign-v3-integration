"""Owner-only account bootstrap and the multi-user Workbench service entry."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Literal

from easydesign.agent.session_store import confined
from easydesign.orchestration.runtime_setup import initialize_workspace_metadata
from easydesign.workspace_context import WorkspaceContext

from .account_server import MultiUserServer
from .accounts import AccountStore
from .capacity_config import LoginSettings, load_capacity_config
from .contracts import ProductError
from .domain import NativeGateway
from .rabbit_capacity import RabbitCapacityLimits
from .rabbit_chat import RabbitChatService, SubprocessChatProvider
from .resource_supervisor import ResourceSupervisor
from .server import load_provider_credentials
from .tenancy import MultiUserRuntime


def store_for(context: WorkspaceContext, *, login: LoginSettings | None = None) -> AccountStore:
    if context.execution_scope is not None:
        raise ProductError("controller_required", "账户管理必须从工作区控制端执行", 403)
    limits = login or LoginSettings()
    return AccountStore(
        context.runtime_root / "state/accounts/accounts.sqlite",
        login_max_concurrency=limits.max_concurrency,
        login_max_pending=limits.max_pending,
        login_wait_timeout=limits.wait_timeout,
    )


def serve_accounts(
    *,
    port: int,
    models: Path,
    env_file: Path | None,
    web: Path,
    easy_web: Path,
    prediction_backend: Literal["protenix-v2", "openfold3-af3-jax"],
    public_origin: str | None,
    accounts_only: bool,
    gpu_devices: str | None,
    capacity_config: Path | None = None,
    app_web: Path | None = None,
) -> int:
    context = WorkspaceContext.discover()
    capacity = load_capacity_config(context.root, capacity_config)
    accounts = store_for(context, login=capacity.login)
    initialize_workspace_metadata(context)
    model_path = confined(context.root, context.root / models)
    gateway = NativeGateway(context, model_path, prediction_backend=prediction_backend)
    if not accounts_only:
        load_provider_credentials(gateway, env_file)
    web_root = confined(context.root, context.root / web)
    easy_root = confined(context.root, context.root / easy_web)
    if not (easy_root / "account/index.html").is_file() or not (easy_root / "index.html").is_file():
        raise ProductError("account_ui_not_built", "请先构建包含账户页面的 Easy UI", 503)
    if not accounts_only and not (web_root / "index.html").is_file():
        raise ProductError("workbench_not_built", "请先构建专业版工作台", 503)
    app_root = None
    if app_web is not None:
        app_root = confined(context.root, context.root / app_web)
        if not (app_root / "index.html").is_file():
            raise ProductError("app_ui_not_built", "请先构建统一应用（web/app）", 503)
    runtime = MultiUserRuntime(
        context,
        accounts,
        lambda scoped: NativeGateway(scoped, model_path, prediction_backend=prediction_backend),
        max_active_admissions=capacity.queue.max_active_admissions,
    )
    allowed = None
    if gpu_devices is not None:
        try:
            allowed = tuple(int(value.strip()) for value in gpu_devices.split(","))
        except ValueError as error:
            raise ProductError("invalid_gpu_devices", "显卡编号格式不正确", 400) from error
        if (
            not allowed
            or any(device < 0 for device in allowed)
            or len(allowed) != len(set(allowed))
        ):
            raise ProductError("invalid_gpu_devices", "显卡编号必须非负且不能重复", 400)
    supervisor = (
        None
        if accounts_only
        else ResourceSupervisor(
            runtime,
            allowed_devices=allowed,
            max_conversation_workers=capacity.queue.max_conversation_workers,
            startup_timeout_seconds=capacity.queue.startup_timeout_seconds,
        )
    )
    rabbit_script = Path(__file__).resolve().parents[3] / "web/easy/server/rabbit_chat.py"
    rabbit = RabbitChatService(
        SubprocessChatProvider(
            confined(context.root, rabbit_script),
            confined(context.root, context.root / (env_file or Path(".env.local"))),
            environment=lambda: WorkspaceContext.discover().subprocess_environment(),
        )
        if os.environ.get("DEEPSEEK_API_KEY") and rabbit_script.is_file() and not accounts_only
        else None,
        limits=RabbitCapacityLimits(**capacity.ai),
        ledger_path=context.runtime_root / "state/accounts/rabbit-chat.sqlite",
    )
    server = MultiUserServer(
        runtime,
        port=port,
        web_root=web_root,
        easy_web_root=easy_root,
        app_web_root=app_root,
        public_origin=public_origin,
        rabbit_chat=rabbit,
        transport_policy=capacity.http.policy(),
        web_history=tuple(context.root / path for path in capacity.web_history),
        easy_web_history=tuple(context.root / path for path in capacity.easy_web_history),
    )
    if supervisor is not None:
        supervisor.start()
    print(f"EasyDesign accounts: http://127.0.0.1:{server.server_port}/account/", flush=True)
    print(
        "Mode: account-administration-only" if accounts_only else "Mode: multi-user-native",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        rabbit.close()
        if supervisor is not None:
            supervisor.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Owner-only multi-user account bootstrap")
    sub = parser.add_subparsers(dest="command", required=True)
    bootstrap = sub.add_parser("bootstrap-admin")
    bootstrap.add_argument("--username", required=True)
    bootstrap.add_argument("--display-name", default="系统管理员")
    bootstrap.add_argument(
        "--password-stdin", action="store_true", help="Read password from stdin without logging it"
    )
    args = parser.parse_args(argv)
    context = WorkspaceContext.discover()
    store = store_for(context)
    if store.has_admin():
        raise ProductError("already_initialized", "管理员已初始化", 409)
    if args.password_stdin:
        password = sys.stdin.readline(1025).rstrip("\r\n")
    else:
        password = getpass.getpass("管理员密码（至少12字符）: ")
        if password != getpass.getpass("再次输入密码: "):
            raise ProductError("password_mismatch", "两次密码不一致", 400)
    user = store.bootstrap_admin(args.username, password, args.display_name)
    print(
        json.dumps(
            {"status": "administrator-created", "user": user.model_dump()}, ensure_ascii=False
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
