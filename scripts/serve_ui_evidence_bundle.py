#!/usr/bin/env python3
"""Verify and serve a repository-shared EasyDesign UI evidence bundle."""

from __future__ import annotations

import argparse
from pathlib import Path

from easydesign.reporting import verify_ui_evidence_bundle
from easydesign.ui import serve_ui


def main() -> int:
    parser = argparse.ArgumentParser(
        description="校验一个 EasyDesign UI evidence bundle，并在本机启动科研工作台"
    )
    parser.add_argument("bundle_root", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", dest="open_browser")
    arguments = parser.parse_args()

    outcome = verify_ui_evidence_bundle(arguments.bundle_root)
    print(f"共享案例完整性已验证：{outcome.file_count} 个文件")
    serve_ui(
        runs_root=outcome.run_root.parent.parent,
        port=arguments.port,
        open_browser=arguments.open_browser,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
