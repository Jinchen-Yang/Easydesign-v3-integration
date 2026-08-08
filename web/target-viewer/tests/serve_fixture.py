#!/usr/bin/env python3
"""Test-only server for a verified report plus a typed Stage 02 overlay."""

from __future__ import annotations

import argparse
from pathlib import Path

from easydesign.core import load_model
from easydesign.reporting import Stage02ViewerOverlay, create_target_viewer_server


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--overlay", type=Path)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    overlay = (
        None
        if args.overlay is None
        else load_model(args.overlay, Stage02ViewerOverlay)
    )
    server = create_target_viewer_server(
        args.report, port=args.port, stage02_overlay=overlay
    )
    try:
        server.serve_forever()
    finally:
        server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
