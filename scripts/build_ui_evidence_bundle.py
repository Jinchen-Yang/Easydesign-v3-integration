#!/usr/bin/env python3
"""Build or verify a compact, manifest-faithful UI evidence bundle."""

from __future__ import annotations

import argparse
from pathlib import Path

from easydesign.reporting import build_ui_evidence_bundle, verify_ui_evidence_bundle


def main() -> int:
    parser = argparse.ArgumentParser(
        description="构建或校验不含重型 backend 中间目录的 EasyDesign UI evidence bundle"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="从一个完整 run 构建精简共享包")
    build.add_argument("source_run", type=Path)
    build.add_argument("output_root", type=Path)
    verify = subparsers.add_parser("verify", help="校验共享包文件和 manifest 闭包")
    verify.add_argument("bundle_root", type=Path)
    arguments = parser.parse_args()

    if arguments.command == "build":
        outcome = build_ui_evidence_bundle(
            arguments.source_run,
            arguments.output_root,
        )
        print(f"Evidence bundle：{outcome.bundle_root}")
    else:
        outcome = verify_ui_evidence_bundle(arguments.bundle_root)
        print(f"Evidence bundle 已验证：{outcome.bundle_root}")
    print(f"Run：{outcome.run_root}")
    print(f"文件：{outcome.file_count}")
    print(f"大小：{outcome.size_bytes} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
