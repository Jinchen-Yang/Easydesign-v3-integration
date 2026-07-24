#!/usr/bin/env python3
"""验证并通过 127.0.0.1 打开一个 Stage 01 Target Viewer 报告。"""

from __future__ import annotations

import argparse
from pathlib import Path

from easydesign.reporting import (
    HOST,
    create_target_viewer_server,
    resolve_target_viewer_argument,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="仅向 127.0.0.1 暴露一个已验证的 Target Viewer 报告目录。",
    )
    parser.add_argument(
        "path",
        type=Path,
        help="EasyDesign run 根目录，或具体的 report-XXXX 目录",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="本地监听端口，默认 8000；使用 0 可自动分配空闲端口",
    )
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    report_root = resolve_target_viewer_argument(arguments.path)
    server = create_target_viewer_server(report_root, port=arguments.port)
    print(f"Target Viewer report: {server.report_root}")
    print(f"Local URL: {server.url}")
    print(
        "远程服务器访问提示：在本机执行 "
        f"`ssh -N -L {server.server.server_address[1]}:{HOST}:"
        f"{server.server.server_address[1]} <server>`，"
        f"然后打开 {server.url}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nTarget Viewer server 已停止。")
    finally:
        server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
