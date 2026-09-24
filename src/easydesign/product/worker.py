"""Detached product request runner. Native Runtime owns all scientific execution."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from easydesign.agent.session_store import confined
from easydesign.workspace_context import WorkspaceContext

from .domain import NativeGateway
from .service import ProductService


def main() -> int:
    context = WorkspaceContext.discover()
    path = confined(context.runtime_root / "state/product/config", Path(sys.argv[1]))
    config = json.loads(path.read_text())
    gateway = NativeGateway(
        context,
        confined(context.root, context.root / config["models"]),
        prediction_backend=config["prediction_backend"],
    )
    ProductService(gateway, actor=config["actor"]).run(sys.argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
